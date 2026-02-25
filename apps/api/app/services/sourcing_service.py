"""
Company Sourcing Service
Multi-source acquisition target discovery engine.

Sources:
  - QuietLight Brokerage (733 server-rendered listings, SaaS/ecom/services)
  - EmpireFlippers marketplace (online businesses, FBA, content, SaaS)
  - FE International (online / SaaS / service businesses)
  - Craigslist business-for-sale (15 major US cities)
  - Axial member directory (M&A / lower-middle-market)

Sector is free-text — matched against listing text via keyword overlap.
Results are cached in-process for 30 minutes to avoid repeated slow network calls.
"""
import asyncio
import re
import logging
import time
import xml.etree.ElementTree as ET
from typing import Optional
from urllib.parse import urlencode

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Simple in-process TTL cache (30 minutes)
# Key = frozenset of criteria items; Value = (timestamp, results_list)
# ---------------------------------------------------------------------------
_SEARCH_CACHE: dict[str, tuple[float, list[dict]]] = {}
_CACHE_TTL = 1800  # 30 minutes


def _cache_key(criteria: dict) -> str:
    """Stable string key from criteria dict."""
    return "|".join(f"{k}={v}" for k, v in sorted(criteria.items()) if v)


def _cache_get(key: str) -> list[dict] | None:
    entry = _SEARCH_CACHE.get(key)
    if entry and (time.time() - entry[0]) < _CACHE_TTL:
        return entry[1]
    return None


def _cache_set(key: str, results: list[dict]) -> None:
    _SEARCH_CACHE[key] = (time.time(), results)
    # Evict entries older than TTL
    now = time.time()
    stale = [k for k, (ts, _) in _SEARCH_CACHE.items() if now - ts > _CACHE_TTL]
    for k in stale:
        _SEARCH_CACHE.pop(k, None)


BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    # Note: No Accept-Encoding — httpx handles decompression natively.
    # Explicit gzip/br headers can cause issues with certain CDNs (QuietLight, etc.)
    "Connection": "keep-alive",
}

TIMEOUT = httpx.Timeout(30.0)

# ---------------------------------------------------------------------------
# DealStream RSS category feeds — all return 25 real, distinct items
# ---------------------------------------------------------------------------
DEALSTREAM_RSS_FEEDS = [
    "businesses-for-sale",
    "health-care-businesses-for-sale",
    "finance-and-insurance-businesses-for-sale",
    "service-businesses-for-sale",
    "manufacturing-businesses-for-sale",
    "construction-businesses-for-sale",
    "education-businesses-for-sale",
    "hospitality-businesses-for-sale",
]

# Craigslist cities with active business-for-sale sections
CRAIGSLIST_CITIES = [
    "newyork", "chicago", "dallas", "houston", "losangeles",
    "miami", "atlanta", "boston", "seattle", "denver",
    "phoenix", "sandiego", "minneapolis", "portland", "austin",
]


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class SourcedCompany:
    def __init__(
        self,
        name: str,
        source: str,
        source_url: str = "",
        description: str = "",
        sector: str = "",
        location: str = "",
        revenue: str = "",
        employees: str = "",
        asking_price: str = "",
        website: str = "",
        extra: dict | None = None,
    ):
        self.name = name
        self.source = source
        self.source_url = source_url
        self.description = description
        self.sector = sector
        self.location = location
        self.revenue = revenue
        self.employees = employees
        self.asking_price = asking_price
        self.website = website
        self.extra = extra or {}
        self.fit_score: Optional[int] = None
        self.fit_reasons: list[str] = []

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "source": self.source,
            "source_url": self.source_url,
            "description": self.description,
            "sector": self.sector,
            "location": self.location,
            "revenue": self.revenue,
            "employees": self.employees,
            "asking_price": self.asking_price,
            "website": self.website,
            "fit_score": self.fit_score,
            "fit_reasons": self.fit_reasons,
            "extra": self.extra,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _text_matches_any(text: str, keywords: list[str]) -> bool:
    t = text.lower()
    return any(kw.lower() in t for kw in keywords if len(kw) > 1)


def _extract_money(text: str) -> str:
    m = re.search(
        r"\$[\d,]+(?:\.\d+)?\s*(?:[MKBmkb]|million|thousand|billion)?",
        text, re.IGNORECASE
    )
    return m.group(0) if m else ""


def _extract_location(text: str) -> str:
    m = re.search(r"([A-Z][a-zA-Z\s]{2,20}),\s*([A-Z]{2})\b", text)
    return m.group(0) if m else ""


def _build_search_keywords(sector: str, keywords: str) -> list[str]:
    """
    Build a unified keyword list from free-text sector + user keywords.
    Splits on spaces/commas, filters short words.
    DEPRECATED: use _build_sector_kws / _build_keyword_kws separately.
    Still used for source-level filtering where both are treated equally.
    """
    combined = f"{sector} {keywords}".strip()
    words = re.split(r"[\s,/&]+", combined)
    return [w.lower().strip() for w in words if len(w.strip()) > 2]


def _tokenize(text: str) -> list[str]:
    """Split free-text into lowercase tokens, drop stop words and short tokens."""
    STOP = {"for", "and", "the", "with", "from", "that", "this", "are", "has",
            "have", "been", "will", "its", "was", "our", "not", "but", "can"}
    words = re.split(r"[\s,/&\-]+", text.strip())
    return [w.lower().strip("().") for w in words
            if len(w.strip()) > 2 and w.lower() not in STOP]


def _build_sector_kws(sector: str) -> list[str]:
    """Tokens from the sector field — these are the hard-gate terms."""
    return _tokenize(sector)


def _build_keyword_kws(keywords: str) -> list[str]:
    """Tokens from the keywords field — these boost score but are NOT required."""
    return _tokenize(keywords)


# ---------------------------------------------------------------------------
# Location hard-filter
# When the user specifies a location, results must be from that area.
# Matches the city name, state abbreviation, or state name.
# ---------------------------------------------------------------------------

_CITY_TO_STATE: dict[str, tuple[str, str]] = {
    # city_lower → (state_abbrev_lower, state_name_lower)
    "houston": ("tx", "texas"), "dallas": ("tx", "texas"),
    "austin": ("tx", "texas"), "san antonio": ("tx", "texas"),
    "fort worth": ("tx", "texas"),
    "new york": ("ny", "new york"), "nyc": ("ny", "new york"),
    "los angeles": ("ca", "california"), "san francisco": ("ca", "california"),
    "san jose": ("ca", "california"), "san diego": ("ca", "california"),
    "sacramento": ("ca", "california"),
    "chicago": ("il", "illinois"),
    "miami": ("fl", "florida"), "tampa": ("fl", "florida"),
    "orlando": ("fl", "florida"), "jacksonville": ("fl", "florida"),
    "atlanta": ("ga", "georgia"),
    "boston": ("ma", "massachusetts"),
    "seattle": ("wa", "washington"),
    "denver": ("co", "colorado"), "colorado springs": ("co", "colorado"),
    "phoenix": ("az", "arizona"), "tucson": ("az", "arizona"),
    "philadelphia": ("pa", "pennsylvania"), "pittsburgh": ("pa", "pennsylvania"),
    "minneapolis": ("mn", "minnesota"),
    "portland": ("or", "oregon"),
    "detroit": ("mi", "michigan"), "grand rapids": ("mi", "michigan"),
    "charlotte": ("nc", "north carolina"), "raleigh": ("nc", "north carolina"),
    "nashville": ("tn", "tennessee"), "memphis": ("tn", "tennessee"),
    "columbus": ("oh", "ohio"), "cleveland": ("oh", "ohio"),
    "cincinnati": ("oh", "ohio"),
    "indianapolis": ("in", "indiana"),
    "baltimore": ("md", "maryland"),
    "las vegas": ("nv", "nevada"),
    "new orleans": ("la", "louisiana"),
    "louisville": ("ky", "kentucky"),
    "oklahoma city": ("ok", "oklahoma"),
    "salt lake city": ("ut", "utah"),
    "birmingham": ("al", "alabama"), "huntsville": ("al", "alabama"),
    "richmond": ("va", "virginia"), "virginia beach": ("va", "virginia"),
    "milwaukee": ("wi", "wisconsin"),
    "kansas city": ("mo", "missouri"), "st. louis": ("mo", "missouri"),
    "omaha": ("ne", "nebraska"),
    "albuquerque": ("nm", "new mexico"),
    "des moines": ("ia", "iowa"),
    "little rock": ("ar", "arkansas"),
    "wichita": ("ks", "kansas"),
    "charleston": ("sc", "south carolina"),
    "jacksonville": ("fl", "florida"),
    "hartford": ("ct", "connecticut"),
    "providence": ("ri", "rhode island"),
    "boise": ("id", "idaho"),
    "anchorage": ("ak", "alaska"),
    "honolulu": ("hi", "hawaii"),
    "fargo": ("nd", "north dakota"),
    "sioux falls": ("sd", "south dakota"),
}

_STATE_NAME_TO_ABBREV: dict[str, str] = {
    "alabama": "al", "alaska": "ak", "arizona": "az", "arkansas": "ar",
    "california": "ca", "colorado": "co", "connecticut": "ct", "delaware": "de",
    "florida": "fl", "georgia": "ga", "hawaii": "hi", "idaho": "id",
    "illinois": "il", "indiana": "in", "iowa": "ia", "kansas": "ks",
    "kentucky": "ky", "louisiana": "la", "maine": "me", "maryland": "md",
    "massachusetts": "ma", "michigan": "mi", "minnesota": "mn", "mississippi": "ms",
    "missouri": "mo", "montana": "mt", "nebraska": "ne", "nevada": "nv",
    "new hampshire": "nh", "new jersey": "nj", "new mexico": "nm", "new york": "ny",
    "north carolina": "nc", "north dakota": "nd", "ohio": "oh", "oklahoma": "ok",
    "oregon": "or", "pennsylvania": "pa", "rhode island": "ri", "south carolina": "sc",
    "south dakota": "sd", "tennessee": "tn", "texas": "tx", "utah": "ut",
    "vermont": "vt", "virginia": "va", "washington": "wa", "west virginia": "wv",
    "wisconsin": "wi", "wyoming": "wy",
}

_ABBREV_TO_STATE_NAME: dict[str, str] = {v: k for k, v in _STATE_NAME_TO_ABBREV.items()}


def _build_location_filter_terms(location: str) -> set[str]:
    """Build the set of terms a result's location must contain to pass the filter.

    For a city like "houston" → {"houston", "tx", "texas"}
    For a state like "california" → {"california", "ca"}
    For an abbreviation like "tx" → {"tx", "texas"}

    Returns empty set when no location specified (= no filter).
    """
    loc = location.lower().strip()
    if not loc:
        return set()

    terms: set[str] = set()

    # Add raw location words (skip short ones like "of", "in")
    for w in loc.split():
        if len(w) > 2:
            terms.add(w)
    terms.add(loc)

    # If it's a known city → add state abbreviation and state name
    city_state = _CITY_TO_STATE.get(loc)
    if city_state:
        terms.add(city_state[0])   # e.g. "tx"
        terms.add(city_state[1])   # e.g. "texas"

    # If it's a state name → add abbreviation
    abbrev = _STATE_NAME_TO_ABBREV.get(loc)
    if abbrev:
        terms.add(abbrev)

    # If it's a state abbreviation → add full name
    state_name = _ABBREV_TO_STATE_NAME.get(loc)
    if state_name:
        terms.add(state_name)

    return terms


def _result_passes_location_filter(
    co: "SourcedCompany",
    filter_terms: set[str],
) -> bool:
    """Return True if the result's location matches any of the filter terms.

    Results with no location data are excluded when a filter is active.
    """
    if not filter_terms:
        return True  # no filter active

    result_loc = (co.location or "").lower()
    if not result_loc.strip():
        return False  # no location data → can't confirm match → exclude

    # Check if any filter term appears in the result's location field
    return any(term in result_loc for term in filter_terms)


# ---------------------------------------------------------------------------
# Source 1: DealStream RSS feeds
# ---------------------------------------------------------------------------

async def _fetch_rss_feed(client: httpx.AsyncClient, slug: str) -> list[dict]:
    url = f"https://www.dealstream.com/{slug}.rss"
    try:
        resp = await client.get(url, headers=BROWSER_HEADERS, follow_redirects=True)
        if resp.status_code != 200:
            return []
        root = ET.fromstring(resp.text)
        items = []
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            if not title:
                continue
            link = item.findtext("link") or ""
            desc_raw = item.findtext("description") or ""
            # Strip HTML tags from description
            desc = BeautifulSoup(desc_raw, "lxml").get_text(" ", strip=True)[:500]
            items.append({
                "name": title,
                "description": desc,
                "url": link,
                "price": _extract_money(desc),
                "location": _extract_location(desc),
                "source_feed": slug,
            })
        logger.info(f"[DealStream RSS] {slug}: {len(items)} items")
        return items
    except Exception as e:
        logger.warning(f"[DealStream RSS] {slug} error: {e}")
        return []


async def search_dealstream_rss(
    client: httpx.AsyncClient,
    match_kws: list[str],
    location_words: list[str],
    sector: str,
) -> list[SourcedCompany]:
    """Fetch all RSS feeds in parallel, filter by keywords."""
    tasks = [_fetch_rss_feed(client, slug) for slug in DEALSTREAM_RSS_FEEDS]
    results_nested = await asyncio.gather(*tasks, return_exceptions=True)

    all_raw: list[dict] = []
    for r in results_nested:
        if isinstance(r, list):
            all_raw.extend(r)

    logger.info(f"[DealStream RSS] Total raw: {len(all_raw)}, filtering by: {match_kws[:8]}")

    results: list[SourcedCompany] = []
    for item in all_raw:
        combined = f"{item['name']} {item['description']}".lower()

        # Keyword filter
        if match_kws and not _text_matches_any(combined, match_kws):
            continue

        # Location tagging
        item_loc = item.get("location", "")
        if location_words:
            loc_confirmed = any(w in combined for w in location_words)
            display_loc = item_loc or ("" if not loc_confirmed else "")
        else:
            display_loc = item_loc

        results.append(SourcedCompany(
            name=item["name"],
            source="DealStream",
            source_url=item.get("url", ""),
            description=item["description"][:350],
            sector=sector,
            location=display_loc,
            revenue=item.get("price", ""),
            asking_price=item.get("price", ""),
        ))

    logger.info(f"[DealStream RSS] After filter: {len(results)}")
    return results


# ---------------------------------------------------------------------------
# Source 2: Craigslist business-for-sale (multi-city)
# ---------------------------------------------------------------------------

async def _fetch_craigslist_city(
    client: httpx.AsyncClient,
    city: str,
    query: str,
) -> list[dict]:
    url = f"https://{city}.craigslist.org/search/bfs?{urlencode({'query': query})}"
    try:
        resp = await client.get(url, headers=BROWSER_HEADERS, follow_redirects=True)
        if resp.status_code != 200:
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        items = []
        for li in soup.select("li.cl-static-search-result"):
            title_el = li.select_one(".label, a, .title")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if not title or len(title) < 4:
                continue

            link_el = li.select_one("a[href]")
            link = link_el["href"] if link_el else ""
            if link and not link.startswith("http"):
                link = f"https://{city}.craigslist.org{link}"

            price_el = li.select_one(".priceinfo, .price, [class*=price]")
            price = price_el.get_text(strip=True) if price_el else ""

            meta_el = li.select_one(".meta, .supertitle, [class*=meta]")
            meta = meta_el.get_text(strip=True) if meta_el else ""

            items.append({
                "name": title,
                "description": meta,
                "url": link,
                "price": price,
                "location": city.replace("newyork", "New York").replace("losangeles", "Los Angeles").title(),
            })
        return items
    except Exception as e:
        logger.debug(f"[Craigslist] {city} error: {e}")
        return []


async def search_craigslist(
    client: httpx.AsyncClient,
    match_kws: list[str],
    location_words: list[str],
    sector: str,
    keywords: str,
) -> list[SourcedCompany]:
    # Build a short search query for Craigslist
    query_parts = []
    if keywords:
        query_parts.append(keywords)
    elif sector:
        # Use first 2-3 words of sector
        sector_words = sector.split()[:3]
        query_parts.append(" ".join(sector_words))
    query_parts.append("for sale")
    query = " ".join(query_parts)

    # If location given, only search relevant cities; otherwise search all
    if location_words:
        # Map location words to city slugs
        loc_str = " ".join(location_words).lower()
        city_map = {
            "new york": "newyork", "ny": "newyork", "nyc": "newyork",
            "chicago": "chicago", "il": "chicago",
            "dallas": "dallas", "tx": "dallas", "texas": "dallas",
            "houston": "houston",
            "los angeles": "losangeles", "la": "losangeles", "ca": "losangeles", "california": "losangeles",
            "miami": "miami", "fl": "miami", "florida": "miami",
            "atlanta": "atlanta", "ga": "atlanta", "georgia": "atlanta",
            "boston": "boston", "ma": "boston",
            "seattle": "seattle", "wa": "seattle",
            "denver": "denver", "co": "denver", "colorado": "denver",
            "phoenix": "phoenix", "az": "phoenix",
            "san diego": "sandiego",
            "minneapolis": "minneapolis", "mn": "minneapolis",
            "portland": "portland", "or": "portland",
            "austin": "austin",
        }
        cities_to_search = []
        for key, city in city_map.items():
            if key in loc_str and city not in cities_to_search:
                cities_to_search.append(city)
        if not cities_to_search:
            cities_to_search = CRAIGSLIST_CITIES  # search all if no match
    else:
        cities_to_search = CRAIGSLIST_CITIES

    tasks = [_fetch_craigslist_city(client, city, query) for city in cities_to_search]
    results_nested = await asyncio.gather(*tasks, return_exceptions=True)

    results: list[SourcedCompany] = []
    for r in results_nested:
        if not isinstance(r, list):
            continue
        for item in r:
            combined = f"{item['name']} {item['description']}".lower()
            if match_kws and not _text_matches_any(combined, match_kws):
                continue
            results.append(SourcedCompany(
                name=item["name"],
                source="Craigslist",
                source_url=item.get("url", ""),
                description=item.get("description", ""),
                sector=sector,
                location=item.get("location", ""),
                asking_price=item.get("price", ""),
            ))

    logger.info(f"[Craigslist] Found {len(results)} matching results")
    return results


# ---------------------------------------------------------------------------
# Source 3: QuietLight Brokerage (733 server-rendered listings)
# ---------------------------------------------------------------------------

async def search_quietlight(
    client: httpx.AsyncClient,
    match_kws: list[str],
    sector: str,
) -> list[SourcedCompany]:
    results: list[SourcedCompany] = []
    try:
        resp = await client.get(
            "https://www.quietlight.com/listings/",
            headers=BROWSER_HEADERS,
            follow_redirects=True,
        )
        if resp.status_code != 200:
            logger.warning(f"[QuietLight] status {resp.status_code}")
            return results

        soup = BeautifulSoup(resp.text, "lxml")
        cards = soup.select("div.listing-card.grid-item")
        logger.info(f"[QuietLight] raw cards: {len(cards)}")

        for card in cards:
            body = card.select_one(".listing-card__body") or card
            full_text = body.get_text(" ", strip=True)

            # Extract name — first heading or strong
            name_el = body.select_one("h2, h3, h4, strong, .listing-card__title, [class*=title]")
            name = name_el.get_text(strip=True) if name_el else ""
            if not name:
                # Fallback: first 60 chars of text
                name = full_text[:60].strip()
            if not name or len(name) < 4:
                continue

            # QuietLight returns all listings; scorer will rank by relevance
            # (no keyword pre-filter — too many legitimate listings would be dropped)

            # Link
            link_el = card.select_one("a[href]")
            link = link_el["href"] if link_el else ""
            if link and not link.startswith("http"):
                link = f"https://www.quietlight.com{link}"

            # Prices / revenue
            asking = _extract_money(full_text)
            revenue = ""
            rev_m = re.search(r"[Rr]evenue[:\s]+(\$[\d,\.]+\s*[MKBmkb]?)", full_text)
            if rev_m:
                revenue = rev_m.group(1)

            # Extract actual listing category from card classes or bottom text
            listing_sector = ""
            bottom_el = card.select_one(".listing-card__bottom, [class*=bottom], [class*=category], [class*=type]")
            if bottom_el:
                btxt = bottom_el.get_text(" ", strip=True)
                # Last token of bottom is usually the category tag (e.g. "Ecommerce", "SaaS")
                parts = [p.strip() for p in btxt.split() if len(p.strip()) > 2]
                if parts:
                    listing_sector = parts[-1]
            if not listing_sector:
                # Fallback: check card CSS classes for type tags
                card_classes = " ".join(card.get("class", []))
                for cls in ["ecommerce", "saas", "amazon", "content", "service", "app", "software"]:
                    if cls in card_classes.lower():
                        listing_sector = cls.title()
                        break

            results.append(SourcedCompany(
                name=name,
                source="QuietLight",
                source_url=link,
                description=full_text[:350],
                sector=listing_sector or sector,
                revenue=revenue,
                asking_price=asking,
            ))
    except Exception as e:
        logger.warning(f"[QuietLight] error: {e}")

    logger.info(f"[QuietLight] After filter: {len(results)}")
    return results


# ---------------------------------------------------------------------------
# Source 4: EmpireFlippers (premium online business marketplace)
# ---------------------------------------------------------------------------

async def search_empire_flippers(
    client: httpx.AsyncClient,
    match_kws: list[str],
    sector: str,
) -> list[SourcedCompany]:
    results: list[SourcedCompany] = []
    try:
        resp = await client.get(
            "https://empireflippers.com/marketplace/",
            headers=BROWSER_HEADERS,
            follow_redirects=True,
        )
        if resp.status_code != 200:
            logger.warning(f"[EmpireFlippers] status {resp.status_code}")
            return results

        soup = BeautifulSoup(resp.text, "lxml")
        cards = soup.select(".listing-item")
        logger.info(f"[EmpireFlippers] raw cards: {len(cards)}")

        for card in cards:
            full_text = card.get_text(" ", strip=True)

            # Listing number
            num_el = card.select_one(".listing-number")
            listing_num = num_el.get_text(strip=True) if num_el else ""

            # Details element (for description and name fallback)
            details_el = card.select_one(".listing-details, [class*=details]")
            details_text = details_el.get_text(" ", strip=True) if details_el else full_text

            # Extract category from title/heading elements
            title_el = card.select_one(
                ".listing-title, h2, h3, h4, [class*=title], [class*=heading], [class*=name]"
            )
            if title_el:
                name = title_el.get_text(strip=True)
            else:
                # Fallback: parse category from the status line
                # Pattern in text: "New Listing {Category} Monetization {Type}"
                m = re.search(
                    r"(?:New Listing|Listing)\s+([A-Z][a-zA-Z\s&,/]+?)(?:\s+Monetization|\s+\$|\s+Unlock)",
                    full_text
                )
                if m:
                    name = f"{m.group(1).strip()} ({listing_num})"
                elif listing_num:
                    # Use category from details text before "Monetization"
                    dtext = details_text.replace(listing_num, "").strip()
                    first_part = dtext.split("Monetization")[0].strip()
                    name = f"{first_part[:50]} ({listing_num})" if first_part else listing_num
                else:
                    name = full_text[:50]

            if not name or len(name) < 3:
                continue

            # EmpireFlippers returns all listings; scorer will rank by relevance
            # (no keyword pre-filter — only 22 total cards so show all)

            link_el = card.select_one("a[href]")
            link = link_el["href"] if link_el else ""
            if link and not link.startswith("http"):
                link = f"https://empireflippers.com{link}"

            price_el = card.select_one(".listing-price")
            price = price_el.get_text(strip=True) if price_el else _extract_money(full_text)

            # Use the category already embedded in the name as the sector
            # e.g. name = "Supplements (#88319)" → sector = "Supplements"
            listing_sector = re.sub(r"\s*\(#\d+\)\s*$", "", name).strip()

            results.append(SourcedCompany(
                name=name,
                source="EmpireFlippers",
                source_url=link,
                description=details_text[:350],
                sector=listing_sector or sector,
                asking_price=price,
            ))
    except Exception as e:
        logger.warning(f"[EmpireFlippers] error: {e}")

    logger.info(f"[EmpireFlippers] After filter: {len(results)}")
    return results


# ---------------------------------------------------------------------------
# Source 5: FE International (online / service / SaaS businesses)
# ---------------------------------------------------------------------------

async def search_fe_international(
    client: httpx.AsyncClient,
    match_kws: list[str],
    sector: str,
) -> list[SourcedCompany]:
    results: list[SourcedCompany] = []
    try:
        resp = await client.get("https://feinternational.com/buy-a-website/", headers=BROWSER_HEADERS, follow_redirects=True)
        if resp.status_code != 200:
            return results

        soup = BeautifulSoup(resp.text, "lxml")
        # Webflow CMS items
        for item in soup.select(".w-dyn-item"):
            name_el = item.select_one("h1, h2, h3, h4, [class*=title], [class*=heading], strong")
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            if not name or len(name) < 4:
                continue

            desc_el = item.select_one("p, [class*=desc], [class*=summary]")
            desc = desc_el.get_text(strip=True)[:300] if desc_el else ""

            link_el = item.select_one("a[href]")
            link = link_el["href"] if link_el else ""
            if link and not link.startswith("http"):
                link = f"https://feinternational.com{link}"

            price_el = item.select_one("[class*=price], [class*=asking]")
            price = price_el.get_text(strip=True) if price_el else ""

            combined = f"{name} {desc}".lower()
            if match_kws and not _text_matches_any(combined, match_kws):
                continue

            results.append(SourcedCompany(
                name=name,
                source="FE International",
                source_url=link,
                description=desc,
                sector=sector,
                asking_price=price,
            ))
    except Exception as e:
        logger.warning(f"[FE International] error: {e}")

    logger.info(f"[FE International] Found {len(results)}")
    return results


# ---------------------------------------------------------------------------
# Source 6: Axial member directory
# ---------------------------------------------------------------------------

async def search_axial(
    client: httpx.AsyncClient,
    sector: str,
    keywords: str,
) -> list[SourcedCompany]:
    results: list[SourcedCompany] = []
    try:
        query = keywords or sector or "business acquisition"
        url = f"https://www.axial.net/forum/companies/?{urlencode({'q': query})}"
        resp = await client.get(url, headers=BROWSER_HEADERS, follow_redirects=True)
        if resp.status_code != 200:
            return results

        soup = BeautifulSoup(resp.text, "lxml")
        for article in soup.select("article.teaser1")[:8]:
            try:
                img = article.select_one("img[alt]")
                name_el = article.select_one("[itemprop=name], h2, h3")
                name = name_el.get_text(strip=True) if name_el else (img.get("alt", "") if img else "")
                if not name or len(name) < 3:
                    continue
                link_el = article.select_one("a[itemprop=url], a[href]")
                link = ""
                if link_el:
                    href = link_el.get("href", "")
                    link = href if href.startswith("http") else f"https://www.axial.net{href}"
                desc_el = article.select_one("p, [itemprop=description]")
                desc = desc_el.get_text(strip=True)[:200] if desc_el else ""
                results.append(SourcedCompany(
                    name=name,
                    source="Axial",
                    source_url=link,
                    description=f"Axial M&A platform member — {desc}" if desc else "Axial M&A platform member",
                    sector=sector,
                ))
            except Exception:
                continue
    except Exception as e:
        logger.warning(f"[Axial] error: {e}")

    logger.info(f"[Axial] Found {len(results)}")
    return results


# ---------------------------------------------------------------------------
# Fit scorer — fully keyword-driven, no hardcoded sector maps
# ---------------------------------------------------------------------------

def _parse_money(s: str) -> Optional[float]:
    if not s:
        return None
    s = s.replace(",", "").replace("$", "").replace(" ", "").upper()
    try:
        if "B" in s:
            return float(re.sub(r"[^\d.]", "", s.split("B")[0])) * 1e9
        elif "M" in s:
            return float(re.sub(r"[^\d.]", "", s.split("M")[0])) * 1e6
        elif "K" in s:
            return float(re.sub(r"[^\d.]", "", s.split("K")[0])) * 1e3
        else:
            v = float(re.sub(r"[^\d.]", "", s))
            return v if v > 0 else None
    except Exception:
        return None


def score_company(company: SourcedCompany, criteria: dict) -> tuple[int, list[str]]:
    """
    Score 0–100.

    Two-pass logic:
      Pass 1 — SECTOR (hard gate, 0–55 pts):
        The listing MUST match at least one sector token to score > 0.
        If sector is empty, all listings pass automatically at 30 pts.

      Pass 2 — KEYWORDS (boost, 0–25 pts):
        Only applied after passing the sector gate.
        Listing can score higher if keyword terms also appear.

    Everything else (location, revenue, completeness, source) adds
    incremental points on top of the sector+keyword base.
    """
    score = 0
    reasons: list[str] = []

    sector = (criteria.get("sector") or "").strip()
    keywords = (criteria.get("keywords") or "").strip()
    location = (criteria.get("location") or "").lower()
    min_emp = criteria.get("min_employees")
    max_emp = criteria.get("max_employees")
    min_rev = criteria.get("min_revenue")
    max_rev = criteria.get("max_revenue")

    combined = f"{company.name} {company.description} {company.location}".lower()

    sector_kws = _build_sector_kws(sector)
    keyword_kws = _build_keyword_kws(keywords)

    # ----------------------------------------------------------------
    # PASS 1: Sector gate (0–55 pts)
    # ----------------------------------------------------------------
    if sector_kws:
        matched_sector = [kw for kw in sector_kws if kw in combined]
        if not matched_sector:
            # Hard fail — listing doesn't mention the sector at all
            reasons.append(f"✗ Sector '{sector}' not found in listing")
            return 0, reasons  # Short-circuit: score 0, won't pass MIN_SCORE filter

        sector_ratio = len(matched_sector) / len(sector_kws)
        # All tokens match = 55, one of several = 20, only term = 40
        if len(sector_kws) == 1:
            sector_score = 40  # single-word sector always gets full gate score
        else:
            sector_score = max(20, int(55 * sector_ratio))
        score += sector_score
        reasons.append(f"✓ Sector match ({len(matched_sector)}/{len(sector_kws)}): {', '.join(matched_sector[:4])}")
    else:
        # No sector provided — baseline pass
        score += 30
        reasons.append("△ No sector filter — showing all listings")

    # ----------------------------------------------------------------
    # PASS 2: Keyword boost (0–25 pts) — only reached if sector passed
    # ----------------------------------------------------------------
    if keyword_kws:
        matched_kw = [kw for kw in keyword_kws if kw in combined]
        if matched_kw:
            kw_ratio = len(matched_kw) / len(keyword_kws)
            kw_score = max(8, int(25 * kw_ratio))
            score += kw_score
            reasons.append(f"✓ Keywords matched ({len(matched_kw)}/{len(keyword_kws)}): {', '.join(matched_kw[:4])}")
        else:
            reasons.append(f"△ Keywords not found: {', '.join(keyword_kws[:4])}")

    # ----------------------------------------------------------------
    # Location match (+10 pts)
    # Non-matching results are already hard-filtered by _build_location_filter_terms.
    # This boost helps rank city-specific results above state-level ones.
    # ----------------------------------------------------------------
    if location:
        loc_words = [w for w in location.split() if len(w) > 2]
        loc_text = combined + " " + (company.location or "").lower()
        matched_loc = [w for w in loc_words if w in loc_text]
        if matched_loc:
            score += 10
            reasons.append(f"✓ Location: {company.location or location}")

    # ----------------------------------------------------------------
    # Employee count (+8 pts)
    # ----------------------------------------------------------------
    if company.employees:
        try:
            emp_val = int(re.sub(r"[^\d]", "", company.employees.split("-")[0]))
            if min_emp and max_emp and min_emp <= emp_val <= max_emp:
                score += 8
                reasons.append(f"✓ Employees in range ({emp_val:,})")
            elif (min_emp and emp_val < min_emp) or (max_emp and emp_val > max_emp):
                score -= 5
                reasons.append(f"△ Employees ({emp_val:,}) out of range")
        except Exception:
            pass

    # ----------------------------------------------------------------
    # Revenue / asking price range (+8 pts)
    # ----------------------------------------------------------------
    rev_val = _parse_money(company.revenue or company.asking_price)
    if rev_val is not None:
        rev_str = company.revenue or company.asking_price
        if min_rev and max_rev:
            if min_rev <= rev_val <= max_rev:
                score += 8
                reasons.append(f"✓ Revenue/price in range ({rev_str})")
            else:
                score -= 4
                reasons.append(f"△ Revenue/price out of range ({rev_str})")
        elif min_rev and rev_val >= min_rev:
            score += 4
            reasons.append(f"✓ Revenue ≥ min ({rev_str})")
        elif max_rev and rev_val <= max_rev:
            score += 4
            reasons.append(f"✓ Revenue within max ({rev_str})")

    # ----------------------------------------------------------------
    # Data completeness bonus (+4 pts max)
    # ----------------------------------------------------------------
    if company.asking_price:
        score += 2
        reasons.append(f"✓ Has asking price: {company.asking_price}")
    if company.revenue:
        score += 2
        reasons.append(f"✓ Has revenue data")

    # ----------------------------------------------------------------
    # Source quality bonus (+8 pts max)
    # ----------------------------------------------------------------
    source_bonus = {
        "QuietLight": 8, "EmpireFlippers": 7,
        "DealStream": 6, "FE International": 5,
        "Axial": 5, "Craigslist": 3,
    }
    b = source_bonus.get(company.source, 0)
    if b:
        score += b

    return max(0, min(100, score)), reasons


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

async def run_sourcing_search(criteria: dict) -> list[dict]:
    """
    Run all sources in parallel: deal-listing sites + active business discovery.
    Returns a unified, deduped, scored list sorted by fit_score descending.
    Results are cached for 30 minutes per unique criteria combination.
    """
    # Import here to avoid circular import (discovery imports from sourcing)
    from app.services.discovery_service import run_discovery_search

    sector = (criteria.get("sector") or "").strip()
    keywords = (criteria.get("keywords") or "").strip()
    location = (criteria.get("location") or "").strip()

    # Build unified keyword list for filtering
    match_kws = _build_search_keywords(sector, keywords)
    location_words = [w.lower() for w in location.split() if len(w) > 2]

    # Cache check — skip expensive network calls for repeated identical searches
    cache_key = _cache_key(criteria)
    cached = _cache_get(cache_key)
    if cached is not None:
        logger.info(f"[Sourcing] Cache HIT for key={cache_key!r} ({len(cached)} results)")
        return cached

    logger.info(f"[Sourcing] sector={sector!r} keywords={keywords!r} location={location!r} match_kws={match_kws}")

    # Run ALL sources — listings AND discovery — in one parallel gather
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        listing_tasks = [
            search_quietlight(client, match_kws, sector),
            search_empire_flippers(client, match_kws, sector),
            search_fe_international(client, match_kws, sector),
            search_craigslist(client, match_kws, location_words, sector, keywords),
            search_axial(client, sector, keywords),
        ]
        # Discovery runs in parallel with listing sources.
        # Each Overpass city query has its own 12s per-city hard deadline via asyncio.wait_for
        # inside _overpass_query, so no additional outer timeout is needed here.
        discovery_task = run_discovery_search(criteria)

        all_tasks = listing_tasks + [discovery_task]
        all_results_nested = await asyncio.gather(*all_tasks, return_exceptions=True)

    listing_results_nested = all_results_nested[:-1]
    discovery_result = all_results_nested[-1]

    # Gather deal-listing companies
    listing_companies: list[SourcedCompany] = []
    for result in listing_results_nested:
        if isinstance(result, Exception):
            logger.warning(f"[Sourcing] listing task error: {result}")
        elif isinstance(result, list):
            listing_companies.extend(result)

    # Discovery result (list of dicts)
    discovery_dicts = discovery_result if isinstance(discovery_result, list) else []

    # Convert discovery dicts back to SourcedCompany for unified dedup/sort
    discovery_companies: list[SourcedCompany] = []
    for d in discovery_dicts:
        co = SourcedCompany(
            name=d.get("name", ""),
            source=d.get("source", ""),
            source_url=d.get("source_url", ""),
            description=d.get("description", ""),
            sector=d.get("sector", ""),
            location=d.get("location", ""),
            revenue=d.get("revenue", ""),
            employees=d.get("employees", ""),
            asking_price=d.get("asking_price", ""),
            website=d.get("website", ""),
            extra=d.get("extra", {}),
        )
        co.fit_score = d.get("fit_score")
        co.fit_reasons = d.get("fit_reasons", [])
        discovery_companies.append(co)

    all_companies = listing_companies + discovery_companies

    # Deduplicate by normalized name (+ location for discovery to avoid cross-city collisions)
    seen: set[str] = set()
    deduped: list[SourcedCompany] = []
    for co in all_companies:
        name_norm = re.sub(r"\W+", " ", co.name.lower()).strip()
        name_norm = re.sub(r"\b(llc|inc|corp|ltd|co|pllc|lp)\b", "", name_norm).strip()
        is_discovery = co.extra.get("listing_type") == "active_business"
        if is_discovery:
            # Include location in key for active businesses (same name, diff city = different biz)
            loc_norm = re.sub(r"\W+", " ", co.location.lower()).strip()
            key = f"{name_norm}|{loc_norm}"
        else:
            key = name_norm
        if key and len(name_norm) > 2 and key not in seen:
            seen.add(key)
            deduped.append(co)

    # Score listing companies (discovery companies already scored)
    for co in deduped:
        if co.fit_score is None:
            s, r = score_company(co, criteria)
            co.fit_score = s
            co.fit_reasons = r

    deduped.sort(key=lambda c: c.fit_score or 0, reverse=True)

    # Filter: only show listings that scored above the relevance threshold
    has_criteria = bool(match_kws)
    MIN_SCORE = 20 if has_criteria else 0
    relevant = [co for co in deduped if (co.fit_score or 0) >= MIN_SCORE]

    # Location hard-filter: when a location is specified, only keep results
    # from that location or the same state. No random brokerage results from
    # across the country — if the user says "Houston", they want Houston.
    loc_filter_terms = _build_location_filter_terms(location)
    if loc_filter_terms:
        before_ct = len(relevant)
        relevant = [co for co in relevant if _result_passes_location_filter(co, loc_filter_terms)]
        logger.info(
            f"[Sourcing] Location filter '{location}' → {before_ct} → {len(relevant)} "
            f"(terms: {loc_filter_terms})"
        )

    # Cap at 300 total (listings and active businesses combined)
    final = relevant[:300]

    listing_ct = sum(1 for co in final if not co.extra.get("listing_type"))
    discovery_ct = sum(1 for co in final if co.extra.get("listing_type") == "active_business")
    logger.info(
        f"[Sourcing] {len(deduped)} unique → {len(relevant)} scored → "
        f"{listing_ct} listings + {discovery_ct} active businesses returned"
    )
    results_out = [c.to_dict() for c in final]
    _cache_set(cache_key, results_out)
    return results_out
