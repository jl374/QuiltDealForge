"""
Shared web research helpers.
Used by analysis_service, enrichment_service, and other services that need
to fetch URLs or perform web searches.

Search provider chain: Serper.dev → Tavily → Google HTML scraping (fallback).
"""
from __future__ import annotations

import asyncio
import logging
import re

import httpx
from bs4 import BeautifulSoup

from app.config import settings

logger = logging.getLogger(__name__)

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

SERPER_URL = "https://google.serper.dev/search"
TAVILY_URL = "https://api.tavily.com/search"


# ---------------------------------------------------------------------------
# URL fetching (unchanged)
# ---------------------------------------------------------------------------

async def fetch_url_text(client: httpx.AsyncClient, url: str, max_chars: int = 4000) -> str:
    """Fetch a URL and return its cleaned text content."""
    try:
        resp = await client.get(url, headers=BROWSER_HEADERS, follow_redirects=True, timeout=12)
        if resp.status_code != 200:
            return ""
        soup = BeautifulSoup(resp.text, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "noscript"]):
            tag.decompose()
        text = soup.get_text(" ", strip=True)
        text = re.sub(r"\s{2,}", " ", text)
        return text[:max_chars]
    except Exception as e:
        logger.debug(f"[Fetch] {url}: {e}")
        return ""


# ---------------------------------------------------------------------------
# Search provider backends
# ---------------------------------------------------------------------------

async def _serper_search(
    client: httpx.AsyncClient, query: str, num_results: int = 5
) -> dict:
    """Call Serper.dev Google search API. Returns raw JSON response."""
    resp = await client.post(
        SERPER_URL,
        headers={
            "X-API-KEY": settings.SERPER_API_KEY,
            "Content-Type": "application/json",
        },
        json={"q": query, "num": num_results},
        timeout=12,
    )
    resp.raise_for_status()
    return resp.json()


async def _tavily_search(
    client: httpx.AsyncClient, query: str, max_results: int = 5
) -> dict:
    """Call Tavily AI search API. Returns raw JSON response."""
    resp = await client.post(
        TAVILY_URL,
        headers={
            "Authorization": f"Bearer {settings.TAVILY_API_KEY}",
            "Content-Type": "application/json",
        },
        json={"query": query, "max_results": max_results},
        timeout=12,
    )
    resp.raise_for_status()
    return resp.json()


async def _google_scrape_text(
    client: httpx.AsyncClient, query: str, max_chars: int = 3000
) -> str:
    """Legacy: scrape Google search results page for snippets (may be blocked)."""
    url = f"https://www.google.com/search?q={query.replace(' ', '+')}&num=5"
    resp = await client.get(url, headers=BROWSER_HEADERS, follow_redirects=True, timeout=12)
    if resp.status_code != 200:
        return ""
    soup = BeautifulSoup(resp.text, "lxml")
    snippets = []
    for sel in ["div.VwiC3b", "div[data-sncf]", "span.aCOpRe", "div.IsZvec"]:
        for el in soup.select(sel):
            text = el.get_text(" ", strip=True)
            if len(text) > 30:
                snippets.append(text)
    for h3 in soup.select("h3"):
        text = h3.get_text(strip=True)
        if len(text) > 10:
            snippets.append(f"[Result] {text}")
    combined = " | ".join(snippets[:12])
    return combined[:max_chars]


async def _google_scrape_urls(
    client: httpx.AsyncClient, query: str, max_results: int = 5
) -> list[str]:
    """Legacy: scrape Google search results page for organic result URLs (may be blocked)."""
    url = f"https://www.google.com/search?q={query.replace(' ', '+')}&num={max_results}"
    resp = await client.get(url, headers=BROWSER_HEADERS, follow_redirects=True, timeout=12)
    if resp.status_code != 200:
        return []
    soup = BeautifulSoup(resp.text, "lxml")
    urls: list[str] = []
    seen: set[str] = set()
    for sel in [".yuRUbf a", ".tF2Cxc a", ".g a[href]", "a[data-ved]"]:
        for a_tag in soup.select(sel):
            href = a_tag.get("href", "")
            if not href or not href.startswith("http"):
                continue
            if any(
                d in href
                for d in [
                    "google.com/search", "google.com/imgres", "google.com/maps",
                    "accounts.google", "support.google", "translate.google",
                    "webcache.googleusercontent",
                ]
            ):
                continue
            if href not in seen:
                seen.add(href)
                urls.append(href)
                if len(urls) >= max_results:
                    break
        if len(urls) >= max_results:
            break
    return urls


# ---------------------------------------------------------------------------
# Public search API (transparent provider routing)
# ---------------------------------------------------------------------------

async def google_search_text(
    client: httpx.AsyncClient, query: str, max_chars: int = 3000
) -> str:
    """
    Search the web and return concatenated snippet text.
    Routes through: Serper.dev → Tavily → Google scraping (fallback).
    """
    # --- Provider 1: Serper.dev ---
    if settings.SERPER_API_KEY:
        try:
            data = await _serper_search(client, query, num_results=5)
            snippets = []
            for result in data.get("organic", []):
                title = result.get("title", "")
                snippet = result.get("snippet", "")
                if snippet:
                    snippets.append(f"[Result] {title}: {snippet}")
                elif title:
                    snippets.append(f"[Result] {title}")
            combined = " | ".join(snippets)
            if combined:
                return combined[:max_chars]
        except Exception as e:
            logger.debug(f"[Serper] {query}: {e}")

    # --- Provider 2: Tavily ---
    if settings.TAVILY_API_KEY:
        try:
            data = await _tavily_search(client, query, max_results=5)
            snippets = []
            for result in data.get("results", []):
                title = result.get("title", "")
                content = result.get("content", "")
                if content:
                    snippets.append(f"[Result] {title}: {content}")
                elif title:
                    snippets.append(f"[Result] {title}")
            combined = " | ".join(snippets)
            if combined:
                return combined[:max_chars]
        except Exception as e:
            logger.debug(f"[Tavily] {query}: {e}")

    # --- Provider 3: Google HTML scraping (last resort) ---
    try:
        return await _google_scrape_text(client, query, max_chars)
    except Exception as e:
        logger.debug(f"[Google] {query}: {e}")
        return ""


async def google_search_urls(
    client: httpx.AsyncClient, query: str, max_results: int = 5
) -> list[str]:
    """
    Search the web and return organic result URLs.
    Routes through: Serper.dev → Tavily → Google scraping (fallback).
    """
    # --- Provider 1: Serper.dev ---
    if settings.SERPER_API_KEY:
        try:
            data = await _serper_search(client, query, num_results=max_results)
            urls = [r["link"] for r in data.get("organic", []) if r.get("link")]
            if urls:
                return urls[:max_results]
        except Exception as e:
            logger.debug(f"[Serper] {query}: {e}")

    # --- Provider 2: Tavily ---
    if settings.TAVILY_API_KEY:
        try:
            data = await _tavily_search(client, query, max_results=max_results)
            urls = [r["url"] for r in data.get("results", []) if r.get("url")]
            if urls:
                return urls[:max_results]
        except Exception as e:
            logger.debug(f"[Tavily] {query}: {e}")

    # --- Provider 3: Google HTML scraping (last resort) ---
    try:
        return await _google_scrape_urls(client, query, max_results)
    except Exception as e:
        logger.debug(f"[GoogleURLs] {query}: {e}")
        return []


# ---------------------------------------------------------------------------
# Claude API helper (unchanged)
# ---------------------------------------------------------------------------

_CLAUDE_MODELS = [
    "claude-sonnet-4-20250514",   # primary — best quality
    "claude-3-haiku-20240307",    # fallback — always available, fast
]


async def call_claude_async(prompt: str, max_tokens: int = 800) -> str:
    """Call Claude asynchronously with retry + model fallback.

    For each model in the fallback chain:
      - Retries up to 3 times with exponential backoff (2s, 4s, 8s)
        on 429 (rate-limited) or 529 (overloaded)
      - On 404 (model unavailable), skips to next model immediately

    Falls through the chain until one succeeds or all are exhausted.
    """
    if not settings.ANTHROPIC_API_KEY:
        return ""

    import anthropic

    MAX_RETRIES = 1
    BASE_DELAY = 2  # seconds

    def _call_sync() -> str:
        # max_retries=0 disables the SDK's internal retry loop.
        # We handle retries ourselves so we can fall through to the next model faster.
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY, max_retries=0)

        for model in _CLAUDE_MODELS:
            for attempt in range(MAX_RETRIES + 1):
                try:
                    message = client.messages.create(
                        model=model,
                        max_tokens=max_tokens,
                        messages=[{"role": "user", "content": prompt}],
                    )
                    if model != _CLAUDE_MODELS[0]:
                        logger.info(f"[Claude] Used fallback model: {model}")
                    return message.content[0].text.strip()
                except anthropic.APIStatusError as e:
                    if e.status_code == 404:
                        # Model not available on this key — try next model
                        logger.debug(f"[Claude] {model} not available (404), trying next")
                        break
                    if e.status_code in (429, 529) and attempt < MAX_RETRIES:
                        delay = BASE_DELAY * (2 ** attempt)
                        logger.info(
                            f"[Claude] {model} returned {e.status_code} "
                            f"(attempt {attempt + 1}), retrying in {delay}s..."
                        )
                        import time
                        time.sleep(delay)
                        continue
                    # Last retry failed or non-retryable error
                    logger.warning(f"[Claude] {model} failed: {e.status_code}")
                    break  # try next model
                except Exception as e:
                    logger.warning(f"[Claude] {model} error: {e}")
                    break  # try next model

        logger.warning("[Claude] All models exhausted — returning empty")
        return ""

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _call_sync)


# ---------------------------------------------------------------------------
# Website discovery
# ---------------------------------------------------------------------------

# Domains that are NOT real company websites
_REGISTRY_DOMAINS = {
    # NPI / healthcare registries
    "npiregistry.cms.hhs.gov", "npiprofile.com", "npino.com", "npidb.org",
    "npi.fat.gov", "hipaaspace.com", "nppes.cms.hhs.gov",
    # Healthcare aggregators / review sites
    "healthgrades.com", "vitals.com", "webmd.com", "zocdoc.com",
    "ratemds.com", "doximity.com", "sharecare.com", "usnews.com",
    "fertilityiq.com", "fertility.com", "ivf.com",
    # Social media
    "facebook.com", "linkedin.com", "twitter.com", "instagram.com",
    "tiktok.com", "youtube.com", "reddit.com", "pinterest.com",
    # Business directories / aggregators
    "yelp.com", "bbb.org", "crunchbase.com", "bloomberg.com",
    "dnb.com", "zoominfo.com", "mapquest.com", "yellowpages.com",
    "manta.com", "buzzfile.com", "opencorporates.com", "sec.gov",
    "indeed.com", "glassdoor.com", "wikipedia.org",
    # Maps & general
    "openstreetmap.org", "google.com", "google.com.au", "amazon.com",
    # Job / visa sites
    "myvisajobs.com", "h1bdata.info", "h1bgrader.com",
    # Generic hosting / review aggregators
    "trustpilot.com", "birdseye.com", "superpages.com", "citysearch.com",
    "angieslist.com", "thumbtack.com", "expertise.com", "birdeye.com",
}


def _is_registry_or_aggregator(url: str) -> bool:
    """Check if a URL belongs to a registry/aggregator site (not the company's own site)."""
    try:
        from urllib.parse import urlparse
        netloc = urlparse(url).netloc.replace("www.", "").lower()
        return any(netloc == d or netloc.endswith("." + d) for d in _REGISTRY_DOMAINS)
    except Exception:
        return False


def _clean_company_name(name: str) -> str:
    """Strip legal suffixes, punctuation, and extra whitespace from a company name."""
    import re as _re
    # Remove common legal suffixes — longer patterns first to avoid partial matches
    suffixes = [
        r",?\s*Professional\s+Corporation\b",
        r",?\s*Medical\s+Corporation\b",
        r",?\s*Corporation\b",
        r",?\s*Corp\.?\b",
        r",?\s*Incorporated\b",
        r",?\s*Inc\.?\b",
        r",?\s*Limited\b",
        r",?\s*Ltd\.?\b",
        r",?\s*PLLC\.?\b",
        r",?\s*LLC\.?\b",
        r",?\s*L\.?P\.?\b",
        r",?\s*P\.?C\.?\b",
        r",?\s*P\.?A\.?\b",
    ]
    cleaned = name
    for suffix in suffixes:
        cleaned = _re.sub(suffix, "", cleaned, flags=_re.IGNORECASE)
    # Remove trailing commas, periods, and extra whitespace
    cleaned = _re.sub(r"[,.\s]+$", "", cleaned).strip()
    return cleaned


def _extract_candidate_url(urls: list[str]) -> str:
    """From a list of search result URLs, return the best company website candidate."""
    from urllib.parse import urlparse as _urlparse
    for url in urls:
        if _is_registry_or_aggregator(url):
            continue
        parsed = _urlparse(url)
        path = parsed.path.strip("/")
        # Prefer short paths (homepages, /about, /contact)
        if len(path.split("/")) <= 2:
            return f"{parsed.scheme}://{parsed.netloc}"
    # If no short path found, take the first non-aggregator result's domain
    for url in urls:
        if not _is_registry_or_aggregator(url):
            parsed = _urlparse(url)
            return f"{parsed.scheme}://{parsed.netloc}"
    return ""


async def discover_company_website(
    client: httpx.AsyncClient, company_name: str, location: str
) -> str:
    """
    Search for a company's actual website when the stored URL is missing or
    points to a registry/aggregator. Uses multiple search strategies with
    cleaned company names. Returns the best candidate URL or "".
    """
    clean_name = _clean_company_name(company_name)

    # Strategy 1: Clean name + location + "official website"
    queries = [
        f'{clean_name} {location} official website',
        f'{clean_name} website',
    ]

    for query in queries:
        urls = await google_search_urls(client, query, max_results=8)
        candidate = _extract_candidate_url(urls)
        if candidate:
            return candidate

    # Strategy 2: If name is very long, try just key words
    words = clean_name.split()
    if len(words) > 3:
        # Use first 3 meaningful words
        short_name = " ".join(words[:3])
        urls = await google_search_urls(
            client, f'{short_name} {location} website', max_results=5
        )
        candidate = _extract_candidate_url(urls)
        if candidate:
            return candidate

    return ""


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

def get_search_provider() -> str:
    """Return the name of the active search provider."""
    if settings.SERPER_API_KEY:
        return "Serper.dev"
    if settings.TAVILY_API_KEY:
        return "Tavily"
    return "Google scraping (unreliable)"
