"""
Company Analysis Service
Uses Claude + web research to generate:
  - A short fit summary (why this company matches the criteria)
  - A deep-dive profile (history, services, leadership, contact info)
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional

import httpx

from app.config import settings
from app.services.web_helpers import fetch_url_text, google_search_text, call_claude_async

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Web research helpers
# ---------------------------------------------------------------------------

async def _research_company(company: dict) -> dict[str, str]:
    """
    Gather web research about a company.
    Returns dict with keys: website_text, search_general, search_leadership, search_news
    """
    name = company.get("name", "")
    location = company.get("location", "")
    website = company.get("website", "") or company.get("source_url", "")
    # Strip NPI/OSM URLs that aren't real company sites
    if website and any(x in website for x in ["npiregistry", "openstreetmap.org", "google.com/maps"]):
        website = ""

    research: dict[str, str] = {}

    async with httpx.AsyncClient(timeout=15) as client:
        tasks = []

        # 1. Company website
        async def _empty() -> str:
            return ""

        if website and website.startswith("http"):
            tasks.append(("website_text", fetch_url_text(client, website, 3000)))
        else:
            tasks.append(("website_text", _empty()))

        # 2. General Google search
        tasks.append((
            "search_general",
            google_search_text(client, f'"{name}" {location} business', 2500),
        ))

        # 3. Leadership search
        tasks.append((
            "search_leadership",
            google_search_text(client, f'"{name}" CEO owner president founder {location}', 2000),
        ))

        # 4. News / recent activity
        tasks.append((
            "search_news",
            google_search_text(client, f'"{name}" {location} 2023 OR 2024 OR 2025', 1500),
        ))

        keys = [k for k, _ in tasks]
        coros = [c for _, c in tasks]
        results = await asyncio.gather(*coros, return_exceptions=True)

        for key, result in zip(keys, results):
            research[key] = result if isinstance(result, str) else ""

    return research


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def generate_fit_summary(company: dict, criteria: dict) -> str:
    """
    Generate a 2–3 sentence AI fit summary for a company card.
    Fast: uses only the data we already have (no web fetch).
    """
    if not settings.ANTHROPIC_API_KEY:
        return _rule_based_summary(company, criteria)

    name = company.get("name", "Unknown")
    sector = company.get("sector", "")
    location = company.get("location", "")
    description = company.get("description", "")
    asking_price = company.get("asking_price", "")
    revenue = company.get("revenue", "")
    source = company.get("source", "")
    fit_score = company.get("fit_score", 0)
    fit_reasons = company.get("fit_reasons", [])

    search_sector = criteria.get("sector", "")
    search_keywords = criteria.get("keywords", "")

    is_active = company.get("extra", {}).get("listing_type") == "active_business"
    listing_context = (
        "This is an active business (not currently listed for sale)."
        if is_active
        else f"This business is listed for sale at {asking_price}." if asking_price
        else "This business is listed for sale."
    )

    prompt = f"""You are an M&A analyst at a private equity firm. Write a 2–3 sentence fit summary for this acquisition target.

Search criteria: sector="{search_sector}", keywords="{search_keywords}"
Company: {name}
Sector/Type: {sector}
Location: {location}
Description: {description[:400]}
Revenue: {revenue}
Asking Price: {asking_price}
Source: {source}
Fit score: {fit_score}/100
Scoring signals: {'; '.join(fit_reasons[:4])}
Context: {listing_context}

Write 2–3 concise sentences explaining why this company is or isn't a strong fit for our criteria.
Focus on: sector alignment, size/scale indicators, any red flags or highlights.
Be direct, specific, and analytical. No fluff. Do not start with "This company"."""

    return await call_claude_async(prompt, max_tokens=150)


async def generate_deep_dive(company: dict, criteria: dict) -> dict:
    """
    Generate a full company profile with web research.
    Returns dict with: summary, history, services, leadership, contact, fit_rationale
    """
    name = company.get("name", "Unknown")
    location = company.get("location", "")
    sector = company.get("sector", "")

    # Gather web research
    logger.info(f"[Analysis] Researching {name}...")
    research = await _research_company(company)

    website_text = research.get("website_text", "")
    search_general = research.get("search_general", "")
    search_leadership = research.get("search_leadership", "")
    search_news = research.get("search_news", "")

    research_context = "\n\n".join(filter(None, [
        f"WEBSITE CONTENT:\n{website_text}" if website_text else "",
        f"GENERAL SEARCH RESULTS:\n{search_general}" if search_general else "",
        f"LEADERSHIP SEARCH RESULTS:\n{search_leadership}" if search_leadership else "",
        f"RECENT NEWS/ACTIVITY:\n{search_news}" if search_news else "",
    ]))

    if not research_context:
        research_context = "No web research available. Base analysis on the provided company data only."

    search_sector = criteria.get("sector", "")
    search_keywords = criteria.get("keywords", "")
    asking_price = company.get("asking_price", "")
    revenue = company.get("revenue", "")
    description = company.get("description", "")
    is_active = company.get("extra", {}).get("listing_type") == "active_business"
    extra = company.get("extra", {})
    phone = extra.get("phone", "")
    address = extra.get("address", "")

    if not settings.ANTHROPIC_API_KEY:
        return _rule_based_deep_dive(company, criteria, research)

    prompt = f"""You are an M&A analyst conducting due diligence on a potential acquisition target for a private equity firm.

COMPANY: {name}
LOCATION: {location}
SECTOR: {sector}
DESCRIPTION: {description[:500]}
ASKING PRICE: {asking_price or "Not listed for sale" if not is_active else "Active business, not listed"}
REVENUE: {revenue}
PHONE: {phone}
ADDRESS: {address}

OUR SEARCH CRITERIA: sector="{search_sector}", keywords="{search_keywords}"

RESEARCH GATHERED:
{research_context[:5000]}

Based on this research, provide a structured analysis with these exact sections. Be specific and cite details from the research. If information isn't available, say "Not found in research" rather than guessing.

1. BUSINESS SUMMARY (2-3 sentences: what the business does, how long it's been operating, key facts)

2. SERVICE LINES (bullet list of their main products/services/specialties)

3. LEADERSHIP (owner, CEO, president, founder — names, titles, tenure if known)

4. CONTACT INFORMATION (compile all available: phone, email, address, website, LinkedIn)

5. FIT RATIONALE (2-3 sentences: why this company specifically matches our "{search_sector}" criteria — be concrete about alignment or gaps)

Format each section with the header exactly as shown above followed by the content."""

    raw = await call_claude_async(prompt, max_tokens=900)

    # Parse sections from Claude output
    sections = _parse_sections(raw)

    return {
        "business_summary": sections.get("BUSINESS SUMMARY", ""),
        "service_lines": sections.get("SERVICE LINES", ""),
        "leadership": sections.get("LEADERSHIP", ""),
        "contact": sections.get("CONTACT INFORMATION", ""),
        "fit_rationale": sections.get("FIT RATIONALE", ""),
        "research_sources": _get_research_sources(company),
        "raw": raw,
    }


def _parse_sections(text: str) -> dict[str, str]:
    """Parse numbered section headers from Claude output."""
    sections: dict[str, str] = {}
    headers = [
        "BUSINESS SUMMARY", "SERVICE LINES", "LEADERSHIP",
        "CONTACT INFORMATION", "FIT RATIONALE",
    ]
    for i, header in enumerate(headers):
        # Find this section
        pattern = rf"\d*\.?\s*{re.escape(header)}\s*\n(.*?)(?=\d*\.?\s*(?:{'|'.join(re.escape(h) for h in headers[i+1:])})|\Z)"
        m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if m:
            sections[header] = m.group(1).strip()
    return sections


def _get_research_sources(company: dict) -> list[str]:
    """Return list of URLs we researched."""
    sources = []
    website = company.get("website", "") or company.get("source_url", "")
    if website and not any(x in website for x in ["npiregistry", "openstreetmap", "google.com/maps"]):
        sources.append(website)
    name = company.get("name", "")
    location = company.get("location", "")
    sources.append(f"https://www.google.com/search?q={name.replace(' ', '+')}+{location.replace(' ', '+')}")
    return sources


def _rule_based_summary(company: dict, criteria: dict) -> str:
    """Fallback summary when no API key is set."""
    name = company.get("name", "Unknown")
    sector = company.get("sector", "")
    location = company.get("location", "")
    asking_price = company.get("asking_price", "")
    score = company.get("fit_score", 0)
    is_active = company.get("extra", {}).get("listing_type") == "active_business"

    parts = [f"{name} is a {sector} business based in {location}.".strip().replace("  ", " ")]
    if asking_price:
        parts.append(f"Listed at {asking_price}.")
    elif is_active:
        parts.append("Currently operating as an active business (not listed for sale).")
    if score >= 70:
        parts.append(f"Strong match for your {criteria.get('sector','')} search criteria.")
    elif score >= 45:
        parts.append(f"Partial match for your search criteria — review details.")
    return " ".join(parts)


def _rule_based_deep_dive(company: dict, criteria: dict, research: dict) -> dict:
    """Fallback deep dive when no API key is set."""
    name = company.get("name", "")
    sector = company.get("sector", "")
    location = company.get("location", "")
    extra = company.get("extra", {})
    phone = extra.get("phone", "Not found")
    address = extra.get("address", location)
    website = company.get("website", "") or company.get("source_url", "")

    # Try to extract any info from research text
    search_text = research.get("search_general", "") + research.get("search_leadership", "")
    leadership_hint = ""
    for pattern in [r"(CEO|President|Owner|Founder|Director)\s+([A-Z][a-z]+ [A-Z][a-z]+)", r"([A-Z][a-z]+ [A-Z][a-z]+),?\s+(CEO|President|Owner|Founder)"]:
        m = re.search(pattern, search_text)
        if m:
            leadership_hint = m.group(0)
            break

    contact_lines = []
    if phone: contact_lines.append(f"Phone: {phone}")
    if address: contact_lines.append(f"Address: {address}")
    if website and not any(x in website for x in ["npiregistry", "openstreetmap", "google.com/maps"]):
        contact_lines.append(f"Website: {website}")

    return {
        "business_summary": f"{name} is a {sector} operation located in {location}. Add your Anthropic API key to enable AI-generated analysis.",
        "service_lines": f"• {sector} services\n• (Set ANTHROPIC_API_KEY for AI-extracted service lines)",
        "leadership": leadership_hint or "Not found in available data. Set ANTHROPIC_API_KEY for AI research.",
        "contact": "\n".join(contact_lines) or "No contact info available.",
        "fit_rationale": f"Matches your '{criteria.get('sector','')}' search criteria based on sector and name alignment.",
        "research_sources": _get_research_sources(company),
        "raw": "",
    }
