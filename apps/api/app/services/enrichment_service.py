"""
Owner Enrichment Service
Finds principal owner / decision-maker info for a company via:
  Phase 1: Expanded web research (Google search + website scraping) — 8 parallel searches
  Phase 2: Senior employee fallback if owner not found
  Phase 3: Social profile scraping + personality extraction for outreach personalization
  Apollo.io API — optional, runs if web research didn't find an email
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.company import Company
from app.models.contact import Contact
from app.models.project import ProjectCompany
from app.services.web_helpers import (
    fetch_url_text,
    google_search_text,
    google_search_urls,
    call_claude_async,
    discover_company_website,
    _is_registry_or_aggregator,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Phase 1: Expanded Owner Research
# ---------------------------------------------------------------------------

async def _research_owner(company_name: str, location: str, website: str) -> dict[str, str]:
    """
    Run parallel web searches to find owner/principal information.
    8 parallel searches across multiple sources.
    Returns dict of research text keyed by search type.
    """
    # Clean website URL
    if website and any(x in website for x in ["npiregistry", "openstreetmap", "google.com/maps"]):
        website = ""

    domain = ""
    if website:
        try:
            domain = urlparse(website).netloc.replace("www.", "")
        except Exception:
            pass

    # Extract state from location for state filing searches
    state = ""
    if location:
        # Try to extract 2-letter state abbreviation or state name
        state_match = re.search(r"\b([A-Z]{2})\b", location)
        if state_match:
            state = state_match.group(1)

    research: dict[str, str] = {}

    async with httpx.AsyncClient(timeout=15) as client:
        tasks = []

        # 1. Company website about/team pages (expanded URL list)
        if website and website.startswith("http"):
            base = website.rstrip("/")
            about_urls = [
                f"{base}/about", f"{base}/team", f"{base}/leadership",
                f"{base}/about-us", f"{base}/our-team", f"{base}/staff",
            ]
            for about_url in about_urls:
                tasks.append(("website_about", fetch_url_text(client, about_url, 3000)))
        else:
            async def _empty() -> str:
                return ""
            tasks.append(("website_about", _empty()))

        # 2. Owner/CEO search
        tasks.append((
            "search_owner",
            google_search_text(client, f'"{company_name}" owner OR CEO OR founder OR president {location}', 3000),
        ))

        # 3. Contact/email search
        tasks.append((
            "search_contact",
            google_search_text(client, f'"{company_name}" owner email contact {domain}', 2500),
        ))

        # 4. LinkedIn search (refined to /in/ for personal profiles)
        tasks.append((
            "search_linkedin",
            google_search_text(client, f'site:linkedin.com/in "{company_name}" owner OR CEO OR founder', 2000),
        ))

        # 5. Facebook search
        tasks.append((
            "search_facebook",
            google_search_text(client, f'site:facebook.com "{company_name}" {location}', 1500),
        ))

        # 6. BBB listings (often have owner names)
        tasks.append((
            "search_bbb",
            google_search_text(client, f'site:bbb.org "{company_name}" {location}', 2000),
        ))

        # 7. State business filings / registered agent
        if state:
            tasks.append((
                "search_filings",
                google_search_text(
                    client,
                    f'"{company_name}" "registered agent" OR "registered owner" OR "principal" {state}',
                    2000,
                ),
            ))

        # 8. Crunchbase (founder/CEO info)
        tasks.append((
            "search_crunchbase",
            google_search_text(client, f'site:crunchbase.com "{company_name}"', 1500),
        ))

        keys = [k for k, _ in tasks]
        coros = [c for _, c in tasks]
        results = await asyncio.gather(*coros, return_exceptions=True)

        for key, result in zip(keys, results):
            if isinstance(result, str) and result:
                if key in research:
                    research[key] += " " + result
                else:
                    research[key] = result

    return research


# ---------------------------------------------------------------------------
# Phase 2: Senior Employee Fallback
# ---------------------------------------------------------------------------

async def _research_senior_employees(
    company_name: str, location: str, website: str, domain: str
) -> dict[str, str]:
    """
    Fallback research when the principal owner can't be found.
    Searches for VP, Director, COO, CFO, or other senior employees.
    """
    research: dict[str, str] = {}

    async with httpx.AsyncClient(timeout=15) as client:
        tasks = [
            # Senior leadership search
            (
                "search_senior",
                google_search_text(
                    client,
                    f'"{company_name}" VP OR "Vice President" OR Director OR COO OR CFO OR "Managing Director" {location}',
                    3000,
                ),
            ),
            # LinkedIn management profiles
            (
                "search_linkedin_mgmt",
                google_search_text(
                    client,
                    f'site:linkedin.com/in "{company_name}" "Vice President" OR Director OR Manager',
                    2500,
                ),
            ),
            # Team page content
            (
                "search_team",
                google_search_text(
                    client,
                    f'"{company_name}" "our team" OR "meet the team" OR "leadership team" {domain}',
                    2000,
                ),
            ),
        ]

        keys = [k for k, _ in tasks]
        coros = [c for _, c in tasks]
        results = await asyncio.gather(*coros, return_exceptions=True)

        for key, result in zip(keys, results):
            if isinstance(result, str) and result:
                research[key] = result

    return research


# ---------------------------------------------------------------------------
# Claude Extraction
# ---------------------------------------------------------------------------

async def _extract_owner_with_claude(
    company_name: str,
    location: str,
    website: str,
    research: dict[str, str],
    fallback_mode: bool = False,
) -> dict:
    """
    Use Claude to extract structured owner info from raw research text.
    In fallback_mode, searches for the most senior person available.
    Returns dict with: name, title, email, phone, linkedin_url, facebook_url,
                       confidence, other_contacts
    """
    research_text = "\n\n".join(
        f"[{k.upper()}]\n{v}" for k, v in research.items() if v
    )

    if not research_text:
        return {}

    if fallback_mode:
        target_desc = (
            "the MOST SENIOR decision-maker available. Prioritize in this order: "
            "CEO/Owner/President/Founder > COO/CFO/Managing Director > "
            "VP/Senior Director > Director > Senior Manager. "
            "Set the title field to their ACTUAL title, not 'Owner' if they're a VP."
        )
    else:
        target_desc = (
            "the PRINCIPAL OWNER, CEO, PRESIDENT, or FOUNDER of this specific company. "
            "Only include information you are confident about from the research."
        )

    prompt = f"""You are a research analyst. Extract contact information for {target_desc}

COMPANY: {company_name}
LOCATION: {location}
WEBSITE: {website}

RESEARCH DATA:
{research_text[:8000]}

Do not guess or fabricate. Return ONLY a JSON object:
{{
  "name": "Full Name",
  "title": "Their actual title (CEO, Owner, VP Operations, etc.)",
  "email": "their@email.com",
  "phone": "phone number",
  "linkedin_url": "https://linkedin.com/in/...",
  "facebook_url": "https://facebook.com/...",
  "confidence": "high|medium|low",
  "other_contacts": [
    {{"name": "Other Person Name", "title": "Their Title", "linkedin_url": "url if found"}}
  ]
}}

Use null for unknown fields. The other_contacts array should list any OTHER senior people
you noticed in the research (up to 3). Return ONLY the JSON. No other text."""

    raw = await call_claude_async(prompt, max_tokens=500)

    # Parse JSON from Claude response
    if raw:
        try:
            # Find the outermost JSON object (may contain nested objects)
            brace_depth = 0
            start = -1
            for i, c in enumerate(raw):
                if c == '{':
                    if start == -1:
                        start = i
                    brace_depth += 1
                elif c == '}':
                    brace_depth -= 1
                    if brace_depth == 0 and start != -1:
                        json_str = raw[start:i + 1]
                        return json.loads(json_str)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"[Enrichment] Failed to parse Claude response: {e}")

    # Fallback: rule-based extraction when Claude is unavailable
    logger.info(f"[Enrichment] Claude unavailable, attempting rule-based extraction for {company_name}")
    return _rule_based_extraction(company_name, research)


def _rule_based_extraction(company_name: str, research: dict[str, str]) -> dict:
    """
    Rule-based fallback to extract owner info from research text using regex.
    Less accurate than Claude but works without an API key.
    """
    combined = " ".join(research.values())
    if not combined:
        return {}

    result: dict[str, str | None] = {}

    # Extract email addresses
    emails = re.findall(
        r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
        combined,
    )
    # Filter out common generic emails
    generic = {"info@", "contact@", "support@", "hello@", "admin@", "sales@",
               "office@", "mail@", "noreply@", "webmaster@", "help@"}
    personal_emails = [
        e for e in emails
        if not any(e.lower().startswith(g) for g in generic)
    ]
    if personal_emails:
        result["email"] = personal_emails[0]

    # Extract LinkedIn URLs
    linkedin = re.findall(r"https?://(?:www\.)?linkedin\.com/in/[a-zA-Z0-9\-_%]+", combined)
    if linkedin:
        result["linkedin_url"] = linkedin[0]

    # Extract Facebook URLs
    facebook = re.findall(r"https?://(?:www\.)?facebook\.com/[a-zA-Z0-9.\-_]+", combined)
    if facebook:
        result["facebook_url"] = facebook[0]

    # Extract phone numbers (US format)
    phones = re.findall(
        r"(?:\+?1[\-.\s]?)?\(?\d{3}\)?[\-.\s]?\d{3}[\-.\s]?\d{4}",
        combined,
    )
    if phones:
        result["phone"] = phones[0]

    # Try to extract a person's name near leadership title keywords
    title_patterns = [
        r"(?:CEO|Chief Executive Officer|Owner|President|Founder|Managing Partner|Principal|Director|"
        r"Vice President|VP|COO|CFO|Managing Director)"
    ]
    for pat in title_patterns:
        name_before = re.search(
            r"([A-Z][a-z]+ (?:[A-Z]\.? )?[A-Z][a-z]+)[\s,\-–—]+(?:is |as )?" + pat,
            combined,
        )
        name_after = re.search(
            pat + r"[\s:,\-–—]+([A-Z][a-z]+ (?:[A-Z]\.? )?[A-Z][a-z]+)",
            combined,
        )
        if name_before:
            result["name"] = name_before.group(1).strip()
            title_match = re.search(pat, combined)
            if title_match:
                result["title"] = title_match.group(0)
            break
        elif name_after:
            result["name"] = name_after.group(1).strip()
            title_match = re.search(pat, combined)
            if title_match:
                result["title"] = title_match.group(0)
            break

    # Clean up null values
    return {k: v for k, v in result.items() if v}


# ---------------------------------------------------------------------------
# Phase 3: Social Profile Scraping + Personality Extraction
# ---------------------------------------------------------------------------

async def _scrape_social_profiles(
    person_name: str,
    company_name: str,
    linkedin_url: str | None,
    facebook_url: str | None,
    location: str,
) -> dict[str, str]:
    """
    Scrape LinkedIn, Facebook, and web for personality/context data.
    Returns dict of scraped text keyed by source.
    """
    social: dict[str, str] = {}

    async with httpx.AsyncClient(timeout=15) as client:
        tasks: list[tuple[str, object]] = []

        # 1. LinkedIn profile page
        if linkedin_url:
            tasks.append(("linkedin_profile", fetch_url_text(client, linkedin_url, 4000)))
        else:
            # Try to find LinkedIn profile via Google
            async def _find_and_fetch_linkedin() -> str:
                urls = await google_search_urls(
                    client,
                    f'site:linkedin.com/in "{person_name}" "{company_name}"',
                    max_results=3,
                )
                for url in urls:
                    if "/in/" in url:
                        text = await fetch_url_text(client, url, 4000)
                        if text and len(text) > 100:
                            return text
                return ""
            tasks.append(("linkedin_profile", _find_and_fetch_linkedin()))

        # 2. LinkedIn posts/activity
        tasks.append((
            "linkedin_posts",
            google_search_text(
                client,
                f'site:linkedin.com/posts "{person_name}" OR site:linkedin.com/pulse "{person_name}"',
                2000,
            ),
        ))

        # 3. Facebook profile page
        if facebook_url:
            tasks.append(("facebook", fetch_url_text(client, facebook_url, 3000)))
        else:
            async def _find_and_fetch_facebook() -> str:
                urls = await google_search_urls(
                    client,
                    f'site:facebook.com "{person_name}" "{company_name}" {location}',
                    max_results=3,
                )
                for url in urls:
                    if "facebook.com" in url and "/search" not in url:
                        text = await fetch_url_text(client, url, 3000)
                        if text and len(text) > 100:
                            return text
                return ""
            tasks.append(("facebook", _find_and_fetch_facebook()))

        # 4. Interviews, podcasts, speaking engagements
        tasks.append((
            "interviews",
            google_search_text(
                client,
                f'"{person_name}" interview OR podcast OR speaking OR keynote "{company_name}"',
                2500,
            ),
        ))

        # 5. Bio, personal website, background
        tasks.append((
            "bio",
            google_search_text(
                client,
                f'"{person_name}" "{company_name}" bio OR about OR background OR profile',
                2000,
            ),
        ))

        keys = [k for k, _ in tasks]
        coros = [c for _, c in tasks]
        results = await asyncio.gather(*coros, return_exceptions=True)

        for key, result in zip(keys, results):
            if isinstance(result, str) and result and len(result) > 50:
                social[key] = result

    return social


async def _extract_personality(
    person_name: str,
    company_name: str,
    social_data: dict[str, str],
) -> dict:
    """
    Use Claude to extract personality insights from social media content.
    Returns structured personality profile for email personalization.
    """
    social_text = "\n\n".join(
        f"[{k.upper()}]\n{v}" for k, v in social_data.items() if v
    )

    if not social_text:
        return {}

    prompt = f"""You are a personality analyst helping a private equity partner craft personalized outreach.
Analyze the following social media and web content about {person_name} at {company_name}.

SOCIAL MEDIA & WEB CONTENT:
{social_text[:6000]}

Extract a personality and context profile that will help write a compelling, personalized cold
outreach email. Focus on actionable insights, not generic observations.

Only include information you can OBSERVE in the provided content. Do not guess or infer details
that aren't supported by the text.

Return ONLY a JSON object:
{{
  "professional_background": "2-3 sentences about their career path, education, key achievements — things that show we did our homework",
  "interests_and_passions": ["list", "of", "specific", "interests", "hobbies", "causes they care about"],
  "communication_style": "formal OR conversational OR technical OR inspirational — based on how they write/speak",
  "values_and_priorities": ["list", "of", "values", "they seem to care about"],
  "personal_details": "Any notable tidbits: alma mater, hometown, military service, awards, board memberships, family mentions",
  "ice_breakers": ["2-3 specific conversation starters based on their content"],
  "outreach_angle": "1-2 sentences suggesting the best angle for cold outreach based on what matters to this person"
}}

Return ONLY the JSON. No other text."""

    raw = await call_claude_async(prompt, max_tokens=600)

    if raw:
        try:
            brace_depth = 0
            start = -1
            for i, c in enumerate(raw):
                if c == '{':
                    if start == -1:
                        start = i
                    brace_depth += 1
                elif c == '}':
                    brace_depth -= 1
                    if brace_depth == 0 and start != -1:
                        return json.loads(raw[start:i + 1])
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"[Personality] Failed to parse Claude response: {e}")

    # Fallback: rule-based personality extraction
    return _rule_based_personality_extraction(social_data)


def _rule_based_personality_extraction(social_data: dict[str, str]) -> dict:
    """
    Rule-based fallback for basic personality extraction without Claude.
    Extracts what it can from social media text using regex patterns.
    """
    combined = " ".join(social_data.values())
    if not combined or len(combined) < 50:
        return {}

    result: dict = {}

    # Extract university/education mentions
    uni_patterns = [
        r"(?:University of \w+(?:\s\w+)?)",
        r"(?:\w+ University)",
        r"(?:\w+ College)",
        r"(?:MBA|Bachelor|Master|PhD|Doctorate)",
        r"(?:Harvard|Stanford|MIT|Yale|Princeton|Wharton|Columbia|Berkeley|UCLA|NYU)",
    ]
    education = []
    for pat in uni_patterns:
        matches = re.findall(pat, combined, re.IGNORECASE)
        education.extend(matches[:2])
    if education:
        result["personal_details"] = f"Education: {', '.join(set(education[:3]))}"

    # Extract professional keywords
    prof_keywords = re.findall(
        r"(?:years? (?:of )?experience|founded|launched|grew|scaled|"
        r"built|managed|led|transformed|acquired|invested|partnership)",
        combined, re.IGNORECASE,
    )
    if prof_keywords:
        unique = list(set(k.lower() for k in prof_keywords[:5]))
        result["professional_background"] = f"Keywords found: {', '.join(unique)}"

    # Extract interests from common patterns
    interest_patterns = [
        r"(?:passionate about|interested in|love[s]? |enjoy[s]? |advocate for|committed to) ([^.]{5,60})",
    ]
    interests = []
    for pat in interest_patterns:
        matches = re.findall(pat, combined, re.IGNORECASE)
        interests.extend(m.strip() for m in matches[:3])
    if interests:
        result["interests_and_passions"] = interests[:3]

    return result


# ---------------------------------------------------------------------------
# Email Discovery: Pattern Guessing + SMTP Verification + Website Scraping
# ---------------------------------------------------------------------------

def _clean_name_parts(full_name: str) -> tuple[str, str]:
    """
    Extract clean first and last name from a full name string.
    Strips titles (Dr., Mr., Mrs.), suffixes (Jr., III), and handles edge cases.
    Returns (first_name_lower, last_name_lower).
    """
    # Remove common prefixes and suffixes
    prefixes = {"dr", "dr.", "mr", "mr.", "mrs", "mrs.", "ms", "ms.", "prof", "prof."}
    suffixes = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv", "md", "m.d.", "phd",
                "ph.d.", "esq", "esq.", "cpa", "dds", "d.d.s.", "do", "d.o."}

    parts = full_name.strip().split()
    # Strip prefixes
    while parts and parts[0].lower().rstrip(".,") in prefixes:
        parts.pop(0)
    # Strip suffixes
    while parts and parts[-1].lower().rstrip(".,") in suffixes:
        parts.pop()

    if len(parts) < 2:
        return (parts[0].lower() if parts else "", "")

    first = parts[0].lower()
    last = parts[-1].lower()  # Use last word for multi-word last names

    # Clean non-alpha chars
    first = re.sub(r"[^a-z]", "", first)
    last = re.sub(r"[^a-z]", "", last)

    return (first, last)


def _generate_email_candidates(full_name: str, domain: str) -> list[str]:
    """
    Generate common email pattern candidates from a person's name and company domain.
    Returns 7-8 candidates ordered by popularity.
    """
    first, last = _clean_name_parts(full_name)
    if not first or not last or not domain:
        return []

    fi = first[0]  # first initial

    candidates = [
        f"{first}.{last}@{domain}",       # first.last (most common)
        f"{first}@{domain}",              # first
        f"{fi}{last}@{domain}",           # flast
        f"{first}{last}@{domain}",        # firstlast
        f"{first}_{last}@{domain}",       # first_last
        f"{fi}.{last}@{domain}",          # f.last
        f"{last}@{domain}",              # last
        f"{last}.{first}@{domain}",       # last.first
    ]

    return candidates


async def _verify_emails_smtp(candidates: list[str], timeout: float = 5.0) -> list[dict]:
    """
    Verify email candidates via SMTP RCPT TO check.
    Returns list of {email, status} where status is 'valid', 'invalid', or 'unknown'.
    Valid emails sorted first.
    """
    if not candidates:
        return []

    import dns.resolver
    import aiosmtplib

    # Extract domain from first candidate
    domain = candidates[0].split("@")[1]

    # Step 1: MX lookup
    try:
        mx_records = dns.resolver.resolve(domain, "MX")
        mx_hosts = sorted(mx_records, key=lambda r: r.preference)
        mx_host = str(mx_hosts[0].exchange).rstrip(".")
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers, Exception) as e:
        logger.debug(f"[Email] No MX record for {domain}: {e}")
        # No MX record — domain likely doesn't accept email
        return [{"email": c, "status": "unknown"} for c in candidates]

    logger.info(f"[Email] MX for {domain}: {mx_host}")

    # Step 2: SMTP verification for each candidate
    results = []
    is_catch_all = None  # Will detect catch-all domains

    for candidate in candidates:
        try:
            smtp = aiosmtplib.SMTP(hostname=mx_host, port=25, timeout=timeout)
            await smtp.connect()
            await smtp.ehlo("marvin.local")
            await smtp.mail("verify@marvin.local")
            code, message = await smtp.rcpt(candidate)
            await smtp.quit()

            if code == 250:
                results.append({"email": candidate, "status": "valid"})
            elif code in (550, 551, 552, 553):
                results.append({"email": candidate, "status": "invalid"})
            else:
                results.append({"email": candidate, "status": "unknown"})

        except aiosmtplib.SMTPResponseException as e:
            # Some servers reject at RCPT with an exception
            if e.code in (550, 551, 552, 553):
                results.append({"email": candidate, "status": "invalid"})
            else:
                results.append({"email": candidate, "status": "unknown"})
        except Exception as e:
            logger.debug(f"[Email] SMTP check failed for {candidate}: {e}")
            results.append({"email": candidate, "status": "unknown"})

    # Detect catch-all: if ALL candidates are "valid", likely a catch-all domain
    valid_count = sum(1 for r in results if r["status"] == "valid")
    if valid_count == len(candidates) and len(candidates) > 3:
        logger.info(f"[Email] {domain} appears to be a catch-all domain (all {valid_count} candidates accepted)")
        is_catch_all = True
        # In catch-all case, mark all as "unknown" but prefer first.last pattern
        for r in results:
            r["status"] = "catch_all"

    # Sort: valid first, then catch_all, then unknown, then invalid
    priority = {"valid": 0, "catch_all": 1, "unknown": 2, "invalid": 3}
    results.sort(key=lambda r: priority.get(r["status"], 2))

    return results


async def _scrape_website_emails(
    client: httpx.AsyncClient, website: str
) -> list[str]:
    """
    Scrape a company's website pages for email addresses.
    Returns list of personal email addresses found (filtered, deduplicated).
    """
    if not website or not website.startswith("http"):
        return []

    base = website.rstrip("/")
    pages = [
        base,
        f"{base}/contact",
        f"{base}/contact-us",
        f"{base}/about",
        f"{base}/about-us",
        f"{base}/team",
        f"{base}/our-team",
    ]

    all_emails: list[str] = []
    seen: set[str] = set()

    tasks = [fetch_url_text(client, url, 5000) for url in pages]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    email_pattern = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
    generic_prefixes = {
        "info@", "contact@", "support@", "hello@", "admin@", "sales@",
        "office@", "mail@", "noreply@", "webmaster@", "help@", "enquiries@",
        "general@", "careers@", "jobs@", "privacy@", "press@", "media@",
    }

    for result in results:
        if isinstance(result, str) and result:
            emails = email_pattern.findall(result)
            for email in emails:
                email_lower = email.lower()
                if email_lower in seen:
                    continue
                seen.add(email_lower)
                # Filter out generic and image/file extensions
                if any(email_lower.startswith(g) for g in generic_prefixes):
                    continue
                if email_lower.endswith((".png", ".jpg", ".gif", ".svg", ".css", ".js")):
                    continue
                all_emails.append(email_lower)

    return all_emails


# ---------------------------------------------------------------------------
# Apollo.io Enrichment
# ---------------------------------------------------------------------------

async def _enrich_with_apollo(
    company_name: str, domain: str, owner_name: str | None = None
) -> dict:
    """
    Use Apollo.io API to find/enrich the principal owner's contact info.
    Returns dict with enriched fields.
    """
    if not settings.APOLLO_API_KEY:
        return {}

    headers = {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
    }

    async with httpx.AsyncClient(timeout=20) as client:
        # Strategy 1: Search for people at this company with leadership titles
        try:
            search_payload = {
                "api_key": settings.APOLLO_API_KEY,
                "q_organization_name": company_name,
                "person_titles": ["CEO", "Owner", "President", "Founder", "Managing Partner", "Principal"],
                "page": 1,
                "per_page": 3,
            }
            if domain:
                search_payload["q_organization_domains"] = domain

            resp = await client.post(
                "https://api.apollo.io/v1/mixed_people/search",
                json=search_payload,
                headers=headers,
            )

            if resp.status_code == 200:
                data = resp.json()
                people = data.get("people", [])
                if people:
                    person = people[0]
                    result = {
                        "name": person.get("name"),
                        "title": person.get("title"),
                        "email": person.get("email"),
                        "phone": None,
                        "linkedin_url": person.get("linkedin_url"),
                    }
                    phones = person.get("phone_numbers", [])
                    if phones:
                        result["phone"] = phones[0].get("sanitized_number")
                    return {k: v for k, v in result.items() if v}

        except Exception as e:
            logger.warning(f"[Apollo] People search failed: {e}")

        # Strategy 2: If we have a name, try email finder
        if owner_name and domain:
            try:
                name_parts = owner_name.strip().split()
                if len(name_parts) >= 2:
                    finder_payload = {
                        "api_key": settings.APOLLO_API_KEY,
                        "first_name": name_parts[0],
                        "last_name": " ".join(name_parts[1:]),
                        "organization_name": company_name,
                        "domain": domain,
                    }
                    resp = await client.post(
                        "https://api.apollo.io/v1/people/match",
                        json=finder_payload,
                        headers=headers,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        person = data.get("person", {})
                        if person and person.get("email"):
                            return {
                                "name": person.get("name", owner_name),
                                "title": person.get("title"),
                                "email": person.get("email"),
                                "phone": None,
                                "linkedin_url": person.get("linkedin_url"),
                            }
            except Exception as e:
                logger.warning(f"[Apollo] Email finder failed: {e}")

    return {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def enrich_company(db: AsyncSession, company_id: str) -> dict:
    """
    Enrich a single company with principal owner info + personality.
    Phase 1: Expanded web research (8 parallel searches)
    Phase 2: Senior employee fallback if owner not found
    Phase 3: Social profile scraping + personality extraction
    Apollo.io: Optional email enrichment
    Returns the enrichment result dict.
    """
    # Load company
    result = await db.execute(
        select(Company).where(Company.id == company_id)
    )
    company = result.scalar_one_or_none()
    if not company:
        raise ValueError(f"Company {company_id} not found")

    company_name = company.name
    location = company.hq_location or ""
    website = company.website or ""

    # Check if there's already an enriched principal owner
    result = await db.execute(
        select(Contact).where(
            Contact.company_id == company.id,
            Contact.is_principal_owner == True,
            Contact.enrichment_status == "completed",
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return {
            "status": "already_enriched",
            "contact_id": str(existing.id),
            "name": existing.name,
            "email": existing.email,
        }

    email_discovery: dict = {}

    # --- Phase 0: Website Discovery ---
    # If website is missing or points to a registry, find the real website
    if not website or _is_registry_or_aggregator(website):
        logger.info(f"[Enrichment] Phase 0: Discovering website for {company_name}...")
        async with httpx.AsyncClient(timeout=15) as client:
            discovered = await discover_company_website(client, company_name, location)
        if discovered:
            logger.info(f"[Enrichment] Discovered website: {discovered} for {company_name}")
            company.website = discovered
            website = discovered
            email_discovery["domain_source"] = "discovered"
            email_discovery["website_discovered"] = discovered
            await db.flush()
        else:
            logger.info(f"[Enrichment] Could not discover website for {company_name}")
            email_discovery["domain_source"] = "none"
    else:
        email_discovery["domain_source"] = "stored"

    # Extract domain from website
    domain = ""
    if website:
        try:
            domain = urlparse(website).netloc.replace("www.", "")
        except Exception:
            pass

    # --- Phase 1: Expanded web research ---
    logger.info(f"[Enrichment] Phase 1: Researching owner of {company_name}...")
    research = await _research_owner(company_name, location, website)

    owner_data = await _extract_owner_with_claude(company_name, location, website, research)

    is_fallback_contact = False
    enrichment_source = "web"

    # --- Phase 2: Senior employee fallback ---
    if not owner_data.get("name") and not owner_data.get("email"):
        logger.info(f"[Enrichment] Phase 2: Owner not found, searching for senior employees at {company_name}...")
        senior_research = await _research_senior_employees(company_name, location, website, domain)
        if senior_research:
            research.update(senior_research)
            owner_data = await _extract_owner_with_claude(
                company_name, location, website, senior_research, fallback_mode=True
            )
            if owner_data.get("name"):
                is_fallback_contact = True
                logger.info(f"[Enrichment] Found senior contact: {owner_data.get('name')} ({owner_data.get('title', '?')}) at {company_name}")

    # --- Phase 1.5: Email Discovery ---
    # If we found a person's name but no email, try to discover the email
    # Guard: don't guess emails on registry/aggregator domains
    domain_is_real = domain and not _is_registry_or_aggregator(f"https://{domain}")
    if owner_data.get("name") and not owner_data.get("email") and domain_is_real:
        logger.info(f"[Enrichment] Phase 1.5: Discovering email for {owner_data['name']} at {domain}...")

        # Step A: Scrape company website for email addresses
        async with httpx.AsyncClient(timeout=15) as client:
            scraped_emails = await _scrape_website_emails(client, website)

        if scraped_emails:
            # Use the first personal email found on the website
            owner_data["email"] = scraped_emails[0]
            email_discovery["method"] = "website_scraped"
            email_discovery["verified_email"] = scraped_emails[0]
            enrichment_source = "web"
            logger.info(f"[Enrichment] Found email on website: {scraped_emails[0]}")
        else:
            # Step B: Generate email pattern candidates and verify via SMTP
            candidates = _generate_email_candidates(owner_data["name"], domain)
            email_discovery["candidates_tested"] = len(candidates)

            if candidates:
                logger.info(f"[Enrichment] Testing {len(candidates)} email candidates for {owner_data['name']}@{domain}...")
                try:
                    smtp_results = await _verify_emails_smtp(candidates, timeout=5.0)

                    # Pick the best email
                    valid = [r for r in smtp_results if r["status"] == "valid"]
                    catch_all = [r for r in smtp_results if r["status"] == "catch_all"]

                    if valid:
                        owner_data["email"] = valid[0]["email"]
                        email_discovery["method"] = "smtp_verified"
                        email_discovery["verified_email"] = valid[0]["email"]
                        enrichment_source = "web"
                        logger.info(f"[Enrichment] SMTP verified email: {valid[0]['email']}")
                    elif catch_all:
                        # Catch-all domain: use first.last as the best guess
                        owner_data["email"] = catch_all[0]["email"]
                        email_discovery["method"] = "catch_all_guess"
                        email_discovery["verified_email"] = catch_all[0]["email"]
                        enrichment_source = "web"
                        logger.info(f"[Enrichment] Catch-all domain, best guess: {catch_all[0]['email']}")
                    else:
                        # All unknown (SMTP blocked/inconclusive): use best-guess pattern
                        owner_data["email"] = candidates[0]  # first.last@domain
                        email_discovery["method"] = "pattern_guess"
                        email_discovery["verified_email"] = candidates[0]
                        enrichment_source = "web"
                        logger.info(f"[Enrichment] SMTP inconclusive, best guess: {candidates[0]}")
                except Exception as e:
                    logger.warning(f"[Enrichment] SMTP verification failed: {e}")
                    # Fallback: use first.last as unverified guess
                    owner_data["email"] = candidates[0]
                    email_discovery["method"] = "pattern_guess"
                    email_discovery["verified_email"] = candidates[0]

    # Apollo enrichment if still no email
    if not owner_data.get("email") and settings.APOLLO_API_KEY:
        logger.info(f"[Enrichment] No email from web/SMTP, trying Apollo for {company_name}...")
        apollo_data = await _enrich_with_apollo(company_name, domain, owner_data.get("name"))
        if apollo_data:
            for key, value in apollo_data.items():
                if value and not owner_data.get(key):
                    owner_data[key] = value
            if apollo_data.get("email"):
                enrichment_source = "apollo"
                email_discovery["method"] = "apollo"
                email_discovery["verified_email"] = apollo_data["email"]

    # --- Failed: no name and no email ---
    if not owner_data.get("name") and not owner_data.get("email"):
        contact = await _find_or_create_contact(db, company.id, {
            "name": f"Owner of {company_name}",
            "is_principal_owner": True,
            "enrichment_status": "failed",
            "enrichment_data": {
                "research": {k: v[:500] for k, v in research.items()},
                "email_discovery": email_discovery,
                "enrichment_version": 2,
            },
            "enrichment_source": enrichment_source,
            "enriched_at": datetime.utcnow(),
        })
        await db.commit()

        partial: dict = {}
        for field in ("email", "phone", "linkedin_url", "facebook_url"):
            if owner_data.get(field):
                partial[field] = owner_data[field]

        return {
            "status": "failed",
            "message": "Could not identify principal owner from available sources. You can add contact info manually.",
            "contact_id": str(contact.id),
            "partial": partial,
        }

    # --- Phase 3: Social profile scraping + personality extraction ---
    contact_name = owner_data.get("name") or f"Owner of {company_name}"
    personality_data: dict = {}
    social_profiles: dict[str, str] = {}

    if owner_data.get("name"):
        try:
            logger.info(f"[Enrichment] Phase 3: Scraping social profiles for {contact_name}...")
            social_profiles = await _scrape_social_profiles(
                person_name=owner_data["name"],
                company_name=company_name,
                linkedin_url=owner_data.get("linkedin_url"),
                facebook_url=owner_data.get("facebook_url"),
                location=location,
            )
            if social_profiles:
                logger.info(f"[Enrichment] Extracting personality for {contact_name} (sources: {list(social_profiles.keys())})")
                personality_data = await _extract_personality(
                    person_name=owner_data["name"],
                    company_name=company_name,
                    social_data=social_profiles,
                )
        except Exception as e:
            logger.warning(f"[Enrichment] Personality extraction failed for {contact_name}: {e}")
            # Non-fatal: we still have the contact info

    # --- Create/update Contact ---
    enrichment_data = {
        "research": {k: v[:500] for k, v in research.items()},
        "extracted": owner_data,
        "email_discovery": email_discovery,
        "enrichment_version": 2,
        "is_fallback_contact": is_fallback_contact,
    }
    if social_profiles:
        enrichment_data["social_profiles"] = {k: v[:500] for k, v in social_profiles.items()}
    if personality_data:
        enrichment_data["personality"] = personality_data

    contact = await _find_or_create_contact(db, company.id, {
        "name": contact_name,
        "title": owner_data.get("title"),
        "email": owner_data.get("email"),
        "phone": owner_data.get("phone"),
        "linkedin_url": owner_data.get("linkedin_url"),
        "facebook_url": owner_data.get("facebook_url"),
        "is_principal_owner": True,
        "enrichment_status": "completed",
        "enrichment_data": enrichment_data,
        "enrichment_source": enrichment_source,
        "enriched_at": datetime.utcnow(),
    })

    await db.commit()
    await db.refresh(contact)

    logger.info(
        f"[Enrichment] Completed: {contact_name} ({owner_data.get('email', 'no email')}) "
        f"for {company_name} | personality={'yes' if personality_data else 'no'} | "
        f"fallback={is_fallback_contact}"
    )

    return {
        "status": "completed",
        "contact_id": str(contact.id),
        "name": contact.name,
        "title": contact.title,
        "email": contact.email,
        "phone": contact.phone,
        "linkedin_url": contact.linkedin_url,
        "facebook_url": contact.facebook_url,
        "enrichment_source": enrichment_source,
        "has_personality": bool(personality_data),
        "is_fallback_contact": is_fallback_contact,
    }


async def enrich_project(db: AsyncSession, project_id: str) -> dict:
    """
    Enrich all companies in a project that don't have an enriched principal owner.
    Rate-limited to avoid Google blocking.
    Returns summary of results.
    """
    result = await db.execute(
        select(ProjectCompany.company_id).where(ProjectCompany.project_id == project_id)
    )
    company_ids = [row[0] for row in result.all()]

    if not company_ids:
        return {"total": 0, "enriched": 0, "failed": 0, "skipped": 0, "results": []}

    result = await db.execute(
        select(Contact.company_id).where(
            Contact.company_id.in_(company_ids),
            Contact.is_principal_owner == True,
            Contact.enrichment_status == "completed",
        )
    )
    already_enriched = {row[0] for row in result.all()}

    to_enrich = [cid for cid in company_ids if cid not in already_enriched]

    results = []
    enriched = 0
    failed = 0

    for cid in to_enrich:
        try:
            res = await enrich_company(db, str(cid))
            results.append(res)
            if res["status"] == "completed":
                enriched += 1
            else:
                failed += 1
        except Exception as e:
            logger.error(f"[Enrichment] Error enriching company {cid}: {e}")
            failed += 1
            results.append({"status": "error", "company_id": str(cid), "message": str(e)})

        # Rate limit: wait between companies to avoid Google blocking
        await asyncio.sleep(1.5)

    return {
        "total": len(company_ids),
        "enriched": enriched,
        "failed": failed,
        "skipped": len(already_enriched),
        "results": results,
    }


async def get_enrichment_status(db: AsyncSession, company_id: str) -> dict:
    """Get the enrichment status for a company's principal owner."""
    result = await db.execute(
        select(Contact).where(
            Contact.company_id == company_id,
            Contact.is_principal_owner == True,
        )
    )
    contact = result.scalar_one_or_none()

    if not contact:
        return {"status": "not_started", "contact": None}

    return {
        "status": contact.enrichment_status or "unknown",
        "contact": {
            "id": str(contact.id),
            "name": contact.name,
            "title": contact.title,
            "email": contact.email,
            "phone": contact.phone,
            "linkedin_url": contact.linkedin_url,
            "facebook_url": contact.facebook_url,
            "enrichment_source": contact.enrichment_source,
            "enriched_at": contact.enriched_at.isoformat() if contact.enriched_at else None,
        },
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _find_or_create_contact(
    db: AsyncSession, company_id, data: dict
) -> Contact:
    """Find existing principal owner contact or create a new one."""
    result = await db.execute(
        select(Contact).where(
            Contact.company_id == company_id,
            Contact.is_principal_owner == True,
        )
    )
    contact = result.scalar_one_or_none()

    if contact:
        for key, value in data.items():
            if value is not None:
                setattr(contact, key, value)
    else:
        contact = Contact(company_id=company_id, **data)
        db.add(contact)

    return contact
