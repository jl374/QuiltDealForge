"""
Company Discovery Service
Finds businesses that EXIST (not necessarily for sale).

Sources:
  - NPPES NPI Registry  — US healthcare providers (no key, federally authoritative)
  - OpenStreetMap Overpass — general businesses by keyword, city-by-city
  - Google Places API  — best coverage (requires GOOGLE_PLACES_API_KEY in .env)

Results are returned as SourcedCompany objects with source="NPPES", "OpenStreetMap",
or "Google Places" so the frontend can badge them distinctly from deal listings.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Optional
from urllib.parse import urlencode

import httpx

from app.config import settings
from app.services.sourcing_service import (
    SourcedCompany,
    _build_sector_kws,
    _build_keyword_kws,
    _text_matches_any,
    BROWSER_HEADERS,
    TIMEOUT,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# NPPES taxonomy → keyword mapping
# Maps common free-text sector inputs to NPPES taxonomy_description terms
# ---------------------------------------------------------------------------

NPPES_TAXONOMY_MAP: dict[str, list[str]] = {
    # Fertility / reproductive
    "ivf": ["reproductive endocrinology", "reproductive medicine", "fertility"],
    "fertility": ["reproductive endocrinology", "reproductive medicine", "fertility"],
    "reproductive": ["reproductive endocrinology", "reproductive medicine"],
    "infertility": ["reproductive endocrinology", "fertility"],

    # Mental health / behavioral
    "mental health": ["psychiatry", "psychology", "counseling", "behavioral health"],
    "therapy": ["counseling", "psychology", "behavioral health", "marriage and family"],
    "psychiatry": ["psychiatry"],
    "psychology": ["psychology"],
    "addiction": ["addiction medicine", "substance abuse"],
    "counseling": ["counseling", "behavioral health"],

    # Dental
    "dental": ["dentistry", "orthodontics", "oral surgery"],
    "dentistry": ["dentistry"],
    "orthodontics": ["orthodontics"],

    # Eye / vision
    "optometry": ["optometry"],
    "ophthalmology": ["ophthalmology"],
    "vision": ["optometry", "ophthalmology"],

    # Primary care / general
    "primary care": ["family medicine", "internal medicine", "general practice"],
    "family medicine": ["family medicine"],
    "internal medicine": ["internal medicine"],
    "pediatrics": ["pediatrics"],
    "pediatric": ["pediatrics"],

    # Physical
    "physical therapy": ["physical therapy", "physiotherapy"],
    "chiropractic": ["chiropractic"],
    "dermatology": ["dermatology"],

    # Specialty
    "oncology": ["oncology", "hematology"],
    "cardiology": ["cardiology"],
    "neurology": ["neurology"],
    "orthopedic": ["orthopedic surgery"],
    "radiology": ["radiology"],
    "pharmacy": ["pharmacy"],
    "urgent care": ["urgent care"],
    "home health": ["home health", "hospice", "skilled nursing"],

    # Behavioral / autism
    "aba": ["applied behavior analysis"],
    "autism": ["applied behavior analysis", "developmental pediatrics"],

    # Veterinary
    "veterinary": ["veterinary medicine"],
    "vet": ["veterinary medicine"],

    # --- Broad healthcare categories ---
    "healthcare": ["family medicine", "internal medicine", "general practice", "clinic"],
    "health care": ["family medicine", "internal medicine", "clinic"],
    "ambulatory": ["ambulatory surgical", "ambulatory care"],
    "ambulatory services": ["ambulatory surgical", "ambulatory care"],
    "surgical center": ["ambulatory surgical"],
    "surgery center": ["ambulatory surgical"],
    "asc": ["ambulatory surgical"],
    "clinic": ["clinic", "general practice", "family medicine"],
    "medical": ["family medicine", "internal medicine", "general practice"],
    "hospital": ["hospital", "general acute care"],
    "nursing": ["skilled nursing", "nursing"],
    "skilled nursing": ["skilled nursing"],
    "rehab": ["rehabilitation", "physical therapy"],
    "rehabilitation": ["rehabilitation", "physical therapy"],
    "imaging": ["radiology", "diagnostic radiology"],
    "diagnostic": ["diagnostic radiology", "clinical medical laboratory"],
    "lab": ["clinical medical laboratory"],
    "laboratory": ["clinical medical laboratory"],
    "pain": ["pain medicine", "interventional pain"],
    "pain management": ["pain medicine", "interventional pain"],
    "weight loss": ["obesity medicine", "bariatric"],
    "bariatric": ["bariatric", "obesity medicine"],
    "plastic surgery": ["plastic surgery"],
    "cosmetic": ["plastic surgery", "dermatology"],
    "med spa": ["dermatology", "plastic surgery"],
    "allergy": ["allergy", "immunology"],
    "gastro": ["gastroenterology"],
    "gastroenterology": ["gastroenterology"],
    "urology": ["urology"],
    "pulmonary": ["pulmonary disease"],
    "podiatry": ["podiatry"],
    "sleep": ["sleep medicine"],
    "dialysis": ["dialysis"],
    "hospice": ["hospice", "palliative care"],
    "palliative": ["palliative care", "hospice"],
    "occupational therapy": ["occupational therapy"],
    "speech": ["speech-language pathology"],
    "speech therapy": ["speech-language pathology"],
    "ent": ["otolaryngology"],
    "ear nose throat": ["otolaryngology"],
    "ob/gyn": ["obstetrics", "gynecology"],
    "obstetrics": ["obstetrics", "gynecology"],
    "gynecology": ["gynecology"],
    "neonatal": ["neonatology"],
    "endocrinology": ["endocrinology"],
    "rheumatology": ["rheumatology"],
    "nephrology": ["nephrology"],
    "anesthesia": ["anesthesiology"],
    "pathology": ["pathology"],
    "wound care": ["wound care"],
    "home care": ["home health", "home care"],
    "durable medical": ["durable medical equipment"],
    "dme": ["durable medical equipment"],
}


def _get_nppes_taxonomies(sector: str, keywords: str) -> list[str]:
    """Return NPPES taxonomy_description search terms for the given sector.

    When the taxonomy map produces matches, use those.
    When nothing matches, fall back to passing raw keywords directly —
    the NPPES API supports partial matching on taxonomy_description.
    """
    combined = f"{sector} {keywords}".lower().strip()
    taxonomies: list[str] = []
    for key, terms in NPPES_TAXONOMY_MAP.items():
        if key in combined:
            taxonomies.extend(terms)
    # Deduplicate while preserving order
    seen: set[str] = set()
    deduped = [t for t in taxonomies if not (t in seen or seen.add(t))]  # type: ignore[func-returns-value]

    if deduped:
        return deduped

    # FALLBACK: no taxonomy map match — pass raw keywords directly to NPPES API.
    # The API supports partial matching on taxonomy_description, so terms like
    # "ambulatory surgical" or "podiatry" work even without a mapping entry.
    raw: list[str] = []
    if keywords.strip():
        raw.append(keywords.strip().lower())
    if sector.strip() and sector.strip().lower() not in ("other", ""):
        raw.append(sector.strip().lower())
    return raw


# ---------------------------------------------------------------------------
# US city bounding boxes for Overpass queries
# Smaller boxes are more reliable (avoid 504 timeouts)
# ~60 cities covering all 50 states
# ---------------------------------------------------------------------------

CITY_BBOXES = [
    # (name, south, west, north, east)
    # --- Original 20 large metros ---
    ("New York",       40.55, -74.10, 40.85, -73.75),
    ("Chicago",        41.64, -87.94, 42.02, -87.52),
    ("Los Angeles",    33.90, -118.45, 34.15, -118.10),
    ("Houston",        29.62, -95.55, 29.88, -95.18),
    ("Phoenix",        33.35, -112.18, 33.70, -111.85),
    ("Philadelphia",   39.87, -75.28, 40.15, -74.96),
    ("San Antonio",    29.30, -98.65, 29.60, -98.35),
    ("Dallas",         32.65, -96.95, 32.90, -96.65),
    ("San Jose",       37.25, -122.05, 37.45, -121.85),
    ("Austin",         30.18, -97.85, 30.45, -97.60),
    ("Jacksonville",   30.16, -81.82, 30.45, -81.55),
    ("Fort Worth",     32.65, -97.48, 32.85, -97.22),
    ("Columbus",       39.90, -83.10, 40.10, -82.85),
    ("Charlotte",      35.15, -80.94, 35.38, -80.72),
    ("Seattle",        47.48, -122.45, 47.73, -122.25),
    ("Denver",         39.62, -105.10, 39.85, -104.85),
    ("Boston",         42.28, -71.20, 42.42, -71.00),
    ("Miami",          25.70, -80.35, 25.90, -80.15),
    ("Atlanta",        33.65, -84.55, 33.90, -84.30),
    ("Minneapolis",    44.87, -93.38, 45.07, -93.15),
    # --- California ---
    ("San Francisco",  37.70, -122.52, 37.83, -122.35),
    ("San Diego",      32.68, -117.25, 32.88, -117.05),
    ("Sacramento",     38.50, -121.55, 38.65, -121.40),
    # --- Florida ---
    ("Tampa",          27.85, -82.55, 28.05, -82.35),
    ("Orlando",        28.40, -81.50, 28.60, -81.30),
    # --- Michigan ---
    ("Detroit",        42.28, -83.20, 42.45, -82.90),
    ("Grand Rapids",   42.90, -85.75, 43.05, -85.58),
    # --- Ohio ---
    ("Cleveland",      41.40, -81.80, 41.55, -81.60),
    ("Cincinnati",     39.07, -84.60, 39.22, -84.40),
    # --- Pennsylvania ---
    ("Pittsburgh",     40.38, -80.08, 40.50, -79.88),
    # --- Virginia ---
    ("Richmond",       37.48, -77.55, 37.60, -77.38),
    ("Virginia Beach", 36.75, -76.10, 36.90, -75.95),
    # --- Tennessee ---
    ("Nashville",      36.08, -86.90, 36.25, -86.68),
    ("Memphis",        35.05, -90.10, 35.22, -89.85),
    # --- North Carolina ---
    ("Raleigh",        35.72, -78.75, 35.87, -78.55),
    # --- Wisconsin ---
    ("Milwaukee",      42.95, -87.98, 43.10, -87.85),
    # --- Maryland ---
    ("Baltimore",      39.22, -76.72, 39.37, -76.52),
    # --- Missouri ---
    ("St. Louis",      38.55, -90.35, 38.72, -90.15),
    ("Kansas City",    39.00, -94.70, 39.18, -94.48),
    # --- Indiana ---
    ("Indianapolis",   39.70, -86.25, 39.85, -86.05),
    # --- Oregon ---
    ("Portland",       45.45, -122.78, 45.60, -122.55),
    # --- Connecticut ---
    ("Hartford",       41.72, -72.75, 41.82, -72.62),
    # --- Nevada ---
    ("Las Vegas",      36.05, -115.30, 36.25, -115.05),
    # --- Louisiana ---
    ("New Orleans",    29.90, -90.15, 30.05, -89.95),
    # --- Kentucky ---
    ("Louisville",     38.15, -85.85, 38.30, -85.60),
    # --- Oklahoma ---
    ("Oklahoma City",  35.35, -97.65, 35.55, -97.40),
    # --- Utah ---
    ("Salt Lake City", 40.70, -111.98, 40.82, -111.82),
    # --- Alabama ---
    ("Birmingham",     33.44, -86.88, 33.58, -86.70),
    ("Huntsville",     34.65, -86.65, 34.80, -86.48),
    # --- South Carolina ---
    ("Charleston",     32.72, -80.00, 32.85, -79.85),
    # --- Nebraska ---
    ("Omaha",          41.20, -96.05, 41.32, -95.88),
    # --- New Mexico ---
    ("Albuquerque",    35.02, -106.72, 35.18, -106.48),
    # --- Iowa ---
    ("Des Moines",     41.52, -93.68, 41.65, -93.50),
    # --- Mississippi ---
    ("Jackson",        32.25, -90.25, 32.40, -90.10),
    # --- Arkansas ---
    ("Little Rock",    34.68, -92.38, 34.80, -92.20),
    # --- Kansas ---
    ("Wichita",        37.62, -97.42, 37.77, -97.22),
    # --- Arizona ---
    ("Tucson",         32.12, -111.05, 32.32, -110.82),
    # --- West Virginia ---
    ("Charleston WV",  38.30, -81.70, 38.40, -81.55),
    # --- Hawaii ---
    ("Honolulu",       21.27, -157.88, 21.38, -157.75),
    # --- New Hampshire ---
    ("Manchester NH",  42.95, -71.50, 43.05, -71.40),
    # --- Maine ---
    ("Portland ME",    43.63, -70.35, 43.70, -70.22),
    # --- Rhode Island ---
    ("Providence",     41.78, -71.45, 41.87, -71.38),
    # --- Montana ---
    ("Billings",       45.72, -108.60, 45.82, -108.45),
    # --- Delaware ---
    ("Wilmington",     39.72, -75.60, 39.78, -75.50),
    # --- South Dakota ---
    ("Sioux Falls",    43.48, -96.80, 43.60, -96.65),
    # --- North Dakota ---
    ("Fargo",          46.82, -96.85, 46.93, -96.72),
    # --- Alaska ---
    ("Anchorage",      61.10, -150.00, 61.25, -149.75),
    # --- Vermont ---
    ("Burlington",     44.45, -73.25, 44.52, -73.15),
    # --- Wyoming ---
    ("Cheyenne",       41.10, -104.85, 41.20, -104.75),
    # --- Idaho ---
    ("Boise",          43.55, -116.30, 43.68, -116.12),
    # --- New Jersey ---
    ("Newark",         40.70, -74.22, 40.78, -74.12),
]

# ---------------------------------------------------------------------------
# US state → cities mapping for location resolution
# Maps state names and abbreviations to city names in CITY_BBOXES
# ---------------------------------------------------------------------------

_STATE_CITY_MAP: dict[str, list[str]] = {
    "alabama":        ["Birmingham", "Huntsville"],
    "alaska":         ["Anchorage"],
    "arizona":        ["Phoenix", "Tucson"],
    "arkansas":       ["Little Rock"],
    "california":     ["Los Angeles", "San Jose", "San Francisco", "San Diego", "Sacramento"],
    "colorado":       ["Denver"],
    "connecticut":    ["Hartford"],
    "delaware":       ["Wilmington"],
    "florida":        ["Miami", "Jacksonville", "Tampa", "Orlando"],
    "georgia":        ["Atlanta"],
    "hawaii":         ["Honolulu"],
    "idaho":          ["Boise"],
    "illinois":       ["Chicago"],
    "indiana":        ["Indianapolis"],
    "iowa":           ["Des Moines"],
    "kansas":         ["Wichita"],
    "kentucky":       ["Louisville"],
    "louisiana":      ["New Orleans"],
    "maine":          ["Portland ME"],
    "maryland":       ["Baltimore"],
    "massachusetts":  ["Boston"],
    "michigan":       ["Detroit", "Grand Rapids"],
    "minnesota":      ["Minneapolis"],
    "mississippi":    ["Jackson"],
    "missouri":       ["St. Louis", "Kansas City"],
    "montana":        ["Billings"],
    "nebraska":       ["Omaha"],
    "nevada":         ["Las Vegas"],
    "new hampshire":  ["Manchester NH"],
    "new jersey":     ["Newark"],
    "new mexico":     ["Albuquerque"],
    "new york":       ["New York"],
    "north carolina": ["Charlotte", "Raleigh"],
    "north dakota":   ["Fargo"],
    "ohio":           ["Columbus", "Cleveland", "Cincinnati"],
    "oklahoma":       ["Oklahoma City"],
    "oregon":         ["Portland"],
    "pennsylvania":   ["Philadelphia", "Pittsburgh"],
    "rhode island":   ["Providence"],
    "south carolina": ["Charleston"],
    "south dakota":   ["Sioux Falls"],
    "tennessee":      ["Nashville", "Memphis"],
    "texas":          ["Houston", "Dallas", "San Antonio", "Austin", "Fort Worth"],
    "utah":           ["Salt Lake City"],
    "vermont":        ["Burlington"],
    "virginia":       ["Richmond", "Virginia Beach"],
    "washington":     ["Seattle"],
    "west virginia":  ["Charleston WV"],
    "wisconsin":      ["Milwaukee"],
    "wyoming":        ["Cheyenne"],
}

# Build abbreviation → cities mapping from the state_map used in NPPES
_ABBREV_TO_STATE: dict[str, str] = {
    "al": "alabama", "ak": "alaska", "az": "arizona", "ar": "arkansas",
    "ca": "california", "co": "colorado", "ct": "connecticut", "de": "delaware",
    "fl": "florida", "ga": "georgia", "hi": "hawaii", "id": "idaho",
    "il": "illinois", "in": "indiana", "ia": "iowa", "ks": "kansas",
    "ky": "kentucky", "la": "louisiana", "me": "maine", "md": "maryland",
    "ma": "massachusetts", "mi": "michigan", "mn": "minnesota", "ms": "mississippi",
    "mo": "missouri", "mt": "montana", "ne": "nebraska", "nv": "nevada",
    "nh": "new hampshire", "nj": "new jersey", "nm": "new mexico", "ny": "new york",
    "nc": "north carolina", "nd": "north dakota", "oh": "ohio", "ok": "oklahoma",
    "or": "oregon", "pa": "pennsylvania", "ri": "rhode island", "sc": "south carolina",
    "sd": "south dakota", "tn": "tennessee", "tx": "texas", "ut": "utah",
    "vt": "vermont", "va": "virginia", "wa": "washington", "wv": "west virginia",
    "wi": "wisconsin", "wy": "wyoming",
}

# Merge abbreviations into the state map
for _abbr, _state_name in _ABBREV_TO_STATE.items():
    if _state_name in _STATE_CITY_MAP:
        _STATE_CITY_MAP[_abbr] = _STATE_CITY_MAP[_state_name]


def _resolve_location_to_cities(
    location: str,
) -> list[tuple[str, float, float, float, float]]:
    """Resolve a location string to a list of CITY_BBOXES entries.

    Priority order:
    1. Exact state name or abbreviation → all cities in that state
    2. City name match (substring in either direction)
    3. Empty list (caller should fall back to Nominatim or defaults)
    """
    loc = location.lower().strip()
    if not loc:
        return []

    # 1. State name / abbreviation lookup
    state_cities = _STATE_CITY_MAP.get(loc)
    if state_cities:
        return [c for c in CITY_BBOXES if c[0] in state_cities]

    # 2. City name matching (bidirectional substring)
    matched = [
        c for c in CITY_BBOXES
        if c[0].lower() in loc
        or loc in c[0].lower()
        or any(
            word in c[0].lower()
            for word in loc.split()
            if len(word) > 3
        )
    ]
    return matched


# ---------------------------------------------------------------------------
# Nominatim geocoding — fallback for locations not in our city/state lists
# Free, rate-limited to 1 req/sec. Results cached in memory.
# ---------------------------------------------------------------------------

_NOMINATIM_CACHE: dict[str, tuple[float, float, float, float] | None] = {}


async def _nominatim_geocode(
    client: httpx.AsyncClient,
    location: str,
) -> tuple[float, float, float, float] | None:
    """Use Nominatim to get a bounding box for an arbitrary US location.
    Returns (south, west, north, east) or None.
    """
    cache_key = location.lower().strip()
    if cache_key in _NOMINATIM_CACHE:
        return _NOMINATIM_CACHE[cache_key]

    try:
        resp = await client.get(
            "https://nominatim.openstreetmap.org/search",
            params={
                "q": f"{location}, United States",
                "format": "json",
                "limit": "1",
            },
            headers={"User-Agent": "Marvin/1.0 (deal-sourcing)"},
            timeout=5,
        )
        if resp.status_code == 200:
            results = resp.json()
            if results:
                bb = results[0]["boundingbox"]  # [lat_min, lat_max, lon_min, lon_max]
                bbox = (float(bb[0]), float(bb[2]), float(bb[1]), float(bb[3]))
                _NOMINATIM_CACHE[cache_key] = bbox
                logger.info(f"[Nominatim] {location} → bbox {bbox}")
                return bbox
    except Exception as e:
        logger.debug(f"[Nominatim] geocode error for {location!r}: {e}")

    _NOMINATIM_CACHE[cache_key] = None
    return None


def _subdivide_bbox(
    bbox: tuple[float, float, float, float],
    max_span: float = 2.0,
) -> list[tuple[str, float, float, float, float]]:
    """Split a large bounding box into smaller tiles for Overpass.
    Each tile is at most max_span degrees in each dimension.
    Returns list of (label, south, west, north, east).
    """
    south, west, north, east = bbox
    lat_span = north - south
    lon_span = east - west

    lat_steps = max(1, int(lat_span / max_span) + (1 if lat_span % max_span else 0))
    lon_steps = max(1, int(lon_span / max_span) + (1 if lon_span % max_span else 0))

    lat_step = lat_span / lat_steps
    lon_step = lon_span / lon_steps

    tiles: list[tuple[str, float, float, float, float]] = []
    for i in range(lat_steps):
        for j in range(lon_steps):
            tile_s = south + i * lat_step
            tile_w = west + j * lon_step
            tile_n = south + (i + 1) * lat_step
            tile_e = west + (j + 1) * lon_step
            label = f"tile_{i}_{j}"
            tiles.append((label, tile_s, tile_w, tile_n, tile_e))
    return tiles


# Overpass mirror endpoints.
# overpass-api.de and kumi.systems are excluded — both consistently timeout today.
# maps.mail.ru is currently the most reliable public mirror.
OVERPASS_ENDPOINTS = [
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]


async def _overpass_query(
    client: httpx.AsyncClient,
    keyword_pattern: str,
    bbox: tuple[float, float, float, float],
    city_name: str,
    timeout_s: int = 8,
    endpoint_idx: int = 0,
) -> list[dict]:
    """Run a single Overpass bounding-box query with failover across mirrors.
    Hard 10-second wall-clock limit so a single slow city never blocks the rest.
    """
    s, w, n, e = bbox
    query = f"""
[out:json][timeout:{timeout_s}];
(
  node["name"~"{keyword_pattern}",i]({s},{w},{n},{e});
  way["name"~"{keyword_pattern}",i]({s},{w},{n},{e});
  node["office"]["name"~"{keyword_pattern}",i]({s},{w},{n},{e});
  node["shop"]["name"~"{keyword_pattern}",i]({s},{w},{n},{e});
  node["amenity"]["name"~"{keyword_pattern}",i]({s},{w},{n},{e});
);
out center 200;
"""
    for attempt, endpoint in enumerate(
        OVERPASS_ENDPOINTS[endpoint_idx:] + OVERPASS_ENDPOINTS[:endpoint_idx]
    ):
        try:
            resp = await asyncio.wait_for(
                client.post(endpoint, data={"data": query}),
                timeout=timeout_s + 2,  # 10s hard wall-clock limit
            )
            if resp.status_code == 200:
                data = resp.json()
                elements = data.get("elements", [])
                logger.debug(f"[Overpass] {city_name} ({endpoint}): {len(elements)} elements")
                return elements
            elif resp.status_code in (429, 504):
                logger.debug(f"[Overpass] {city_name} ({endpoint}): {resp.status_code}, trying next mirror")
                continue
            else:
                logger.warning(f"[Overpass] {city_name}: {resp.status_code}")
                break
        except (asyncio.TimeoutError, Exception) as e:
            logger.debug(f"[Overpass] {city_name} ({endpoint}) error: {e}")
            continue
    return []


def _overpass_element_to_company(
    el: dict,
    sector: str,
    city_name: str,
) -> Optional[SourcedCompany]:
    """Convert an Overpass element to a SourcedCompany."""
    tags = el.get("tags", {})
    name = tags.get("name", "").strip()
    if not name or len(name) < 3:
        return None

    # Location
    city = tags.get("addr:city", "") or city_name
    state = tags.get("addr:state", "")
    postcode = tags.get("addr:postcode", "")
    street = tags.get("addr:street", "")
    location_parts = [p for p in [city, state] if p]
    location = ", ".join(location_parts)

    address = ""
    if street:
        house = tags.get("addr:housenumber", "")
        address = f"{house} {street}".strip()
        if city:
            address += f", {city}"
        if state:
            address += f", {state}"
        if postcode:
            address += f" {postcode}"

    # Contact
    phone = tags.get("phone") or tags.get("contact:phone") or tags.get("telephone") or ""
    website = tags.get("website") or tags.get("contact:website") or tags.get("url") or ""

    # Description from tags
    desc_parts = []
    for tag in ["description", "opening_hours", "operator"]:
        val = tags.get(tag, "")
        if val:
            desc_parts.append(val)
    desc = " | ".join(desc_parts)

    # OSM type hint
    amenity = tags.get("amenity") or tags.get("office") or tags.get("shop") or tags.get("healthcare") or ""

    return SourcedCompany(
        name=name,
        source="OpenStreetMap",
        source_url=website or f"https://www.openstreetmap.org/node/{el.get('id','')}",
        description=desc or f"{amenity.replace('_',' ').title()} — found via OpenStreetMap".strip(" —"),
        sector=sector,
        location=location,
        website=website,
        extra={
            "address": address,
            "phone": phone,
            "osm_type": amenity,
            "listing_type": "active_business",
        },
    )


# Representative sample of cities for nationwide search (1-2 per US region).
# Picked for geographic diversity so a no-location search covers the whole country.
_NATIONWIDE_SAMPLE_CITIES: list[str] = [
    # Northeast
    "New York", "Boston", "Philadelphia", "Pittsburgh",
    # Southeast
    "Miami", "Atlanta", "Charlotte", "Nashville", "Jacksonville",
    # Midwest
    "Chicago", "Minneapolis", "Columbus", "Detroit", "Indianapolis",
    # Southwest
    "Houston", "Dallas", "Phoenix", "San Antonio", "Denver",
    # West Coast
    "Los Angeles", "San Francisco", "Seattle", "San Diego", "Portland",
]


async def search_openstreetmap(
    client: httpx.AsyncClient,
    sector: str,
    keywords: str,
    location: str,
    match_kws: list[str],
) -> list[SourcedCompany]:
    """
    Search OpenStreetMap Overpass for businesses by keyword.
    Resolves locations via: state/abbreviation → city name → Nominatim geocoding.
    When no location is specified, searches ~25 cities across all US regions.
    Queries multiple bounding boxes in parallel.
    """
    if not match_kws:
        return []

    # Build regex pattern for Overpass — use just the first (most specific) term.
    # Multi-term OR patterns are slow and generic terms like "agency" match everything.
    primary_terms = match_kws[:1]
    pattern = "|".join(re.escape(t) for t in primary_terms)

    nationwide = not location.strip()

    # ---- Location resolution ----
    cities_to_search: list[tuple[str, float, float, float, float]] = []
    nominatim_tiles: list[tuple[str, float, float, float, float]] = []

    if nationwide:
        # No location → search representative sample of cities across all US regions
        sample_names = set(_NATIONWIDE_SAMPLE_CITIES)
        cities_to_search = [c for c in CITY_BBOXES if c[0] in sample_names]
        logger.info(
            f"[Overpass] Nationwide search — {len(cities_to_search)} sample cities"
        )
    else:
        # Tier 1 & 2: State name/abbreviation and city name matching
        cities_to_search = _resolve_location_to_cities(location)

        # Tier 3: Nominatim geocoding for unknown locations
        if not cities_to_search:
            bbox = await _nominatim_geocode(client, location)
            if bbox:
                nominatim_tiles = _subdivide_bbox(bbox, max_span=2.0)
                logger.info(
                    f"[Overpass] Nominatim resolved {location!r} → "
                    f"{len(nominatim_tiles)} tile(s)"
                )

        # Fallback: unresolvable location → top 4 largest US cities
        if not cities_to_search and not nominatim_tiles:
            logger.warning(
                f"[Overpass] Could not resolve location {location!r} — "
                f"defaulting to top 4 cities"
            )
            cities_to_search = CITY_BBOXES[:4]

    # Parallel limits: nationwide gets more bandwidth since it covers the whole US
    MAX_PARALLEL = 25 if nationwide else 10
    all_bboxes: list[tuple[str, float, float, float, float]] = []
    all_bboxes.extend(cities_to_search[:MAX_PARALLEL])
    remaining = MAX_PARALLEL - len(all_bboxes)
    if remaining > 0 and nominatim_tiles:
        all_bboxes.extend(nominatim_tiles[:remaining])

    logger.info(
        f"[Overpass] Searching {len(all_bboxes)} bbox(es) for '{pattern}'"
    )

    # All bboxes in one parallel gather
    tasks = [
        _overpass_query(
            client, pattern, (s, w, n, e), name,
            endpoint_idx=j % len(OVERPASS_ENDPOINTS),
        )
        for j, (name, s, w, n, e) in enumerate(all_bboxes)
    ]
    all_city_results = await asyncio.gather(*tasks, return_exceptions=True)

    results: list[SourcedCompany] = []
    for city_info, elements in zip(all_bboxes, all_city_results):
        if isinstance(elements, Exception) or not isinstance(elements, list):
            continue
        city_name = city_info[0]
        for el in elements:
            co = _overpass_element_to_company(el, sector, city_name)
            if co:
                results.append(co)

    logger.info(f"[Overpass] Total: {len(results)} businesses found")
    return results


# ---------------------------------------------------------------------------
# NPPES NPI Registry — US healthcare providers
# ---------------------------------------------------------------------------

NPPES_BASE = "https://npiregistry.cms.hhs.gov/api/"


async def _nppes_fetch(
    client: httpx.AsyncClient,
    taxonomy: str,
    state: Optional[str],
    skip: int = 0,
) -> list[dict]:
    """Fetch one page of NPPES results."""
    params: dict = {
        "version": "2.1",
        "taxonomy_description": taxonomy,
        "enumeration_type": "NPI-2",
        "limit": 200,
        "skip": skip,
    }
    if state:
        params["state"] = state
    try:
        resp = await client.get(
            f"{NPPES_BASE}?{urlencode(params)}",
            headers={**BROWSER_HEADERS, "Accept": "application/json"},
            timeout=20,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("results", [])
    except Exception as e:
        logger.warning(f"[NPPES] {taxonomy} error: {e}")
    return []


def _nppes_result_to_company(result: dict, sector: str) -> Optional[SourcedCompany]:
    """Convert an NPPES result dict to a SourcedCompany."""
    basic = result.get("basic", {})
    name = basic.get("organization_name", "").strip()
    if not name or len(name) < 3:
        return None

    addresses = result.get("addresses", [])
    # Prefer practice location over mailing
    addr = next(
        (a for a in addresses if a.get("address_purpose") == "LOCATION"),
        addresses[0] if addresses else {},
    )

    city = addr.get("city", "").title()
    state = addr.get("state", "")
    zip_code = addr.get("postal_code", "")[:5]
    street = addr.get("address_1", "").title()
    phone = addr.get("telephone_number", "")
    location = ", ".join(p for p in [city, state] if p)

    address = ""
    if street:
        address = street
        if city:
            address += f", {city}"
        if state:
            address += f", {state}"
        if zip_code:
            address += f" {zip_code}"

    # Taxonomy for sector tag
    taxonomies = result.get("taxonomies", [])
    taxonomy_desc = ""
    for t in taxonomies:
        if t.get("primary"):
            taxonomy_desc = t.get("desc", "")
            break
    if not taxonomy_desc and taxonomies:
        taxonomy_desc = taxonomies[0].get("desc", "")

    npi_number = result.get("number", "")
    npi_url = f"https://npiregistry.cms.hhs.gov/provider-view/{npi_number}" if npi_number else ""

    return SourcedCompany(
        name=name.title(),
        source="NPPES",
        source_url=npi_url,
        description=f"{taxonomy_desc} — NPI #{npi_number}",
        sector=taxonomy_desc or sector,
        location=location,
        extra={
            "address": address,
            "phone": phone,
            "npi": npi_number,
            "taxonomy": taxonomy_desc,
            "listing_type": "active_business",
        },
    )


async def search_nppes(
    client: httpx.AsyncClient,
    sector: str,
    keywords: str,
    location: str,
) -> list[SourcedCompany]:
    """
    Search NPPES for healthcare providers matching the sector.
    Returns up to 400 results (2 pages × 200) across relevant taxonomies.
    """
    taxonomies = _get_nppes_taxonomies(sector, keywords)
    if not taxonomies:
        return []

    # Determine state filter from location
    state_map = {
        "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
        "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
        "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
        "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
        "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
        "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
        "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
        "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
        "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
        "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
        "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
        "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
        "wisconsin": "WI", "wyoming": "WY",
        # Abbreviations
        "ca": "CA", "tx": "TX", "fl": "FL", "ny": "NY", "il": "IL",
        "pa": "PA", "oh": "OH", "ga": "GA", "nc": "NC", "mi": "MI",
        "nj": "NJ", "va": "VA", "wa": "WA", "az": "AZ", "ma": "MA",
        "tn": "TN", "in": "IN", "mo": "MO", "md": "MD", "wi": "WI",
        "co": "CO", "mn": "MN", "sc": "SC", "al": "AL", "la": "LA",
        "ky": "KY", "or": "OR", "ok": "OK", "ct": "CT", "ut": "UT",
        "nv": "NV", "ia": "IA", "ar": "AR", "ms": "MS", "ks": "KS",
        "ne": "NE", "id": "ID", "hi": "HI", "me": "ME", "nh": "NH",
        "ri": "RI", "mt": "MT", "de": "DE", "sd": "SD", "nd": "ND",
        "ak": "AK", "vt": "VT", "wy": "WY", "wv": "WV", "nm": "NM",
    }
    loc_lower = location.lower()
    state_code = None
    for key, code in state_map.items():
        if key in loc_lower:
            state_code = code
            break

    logger.info(f"[NPPES] taxonomies={taxonomies}, state={state_code}")

    # Fetch up to 2 pages per taxonomy (up to 400 results each)
    all_results: list[SourcedCompany] = []
    seen_npis: set[str] = set()

    tasks = []
    for tax in taxonomies[:3]:  # limit to 3 taxonomies to avoid hammering
        tasks.append(_nppes_fetch(client, tax, state_code, skip=0))
        tasks.append(_nppes_fetch(client, tax, state_code, skip=200))

    pages = await asyncio.gather(*tasks, return_exceptions=True)

    for page in pages:
        if isinstance(page, Exception) or not isinstance(page, list):
            continue
        for result in page:
            npi = result.get("number", "")
            if npi in seen_npis:
                continue
            seen_npis.add(npi)
            co = _nppes_result_to_company(result, sector)
            if co:
                all_results.append(co)

    logger.info(f"[NPPES] {len(all_results)} unique providers found")
    return all_results


# ---------------------------------------------------------------------------
# Google Places API — general business search (requires API key)
# ---------------------------------------------------------------------------

# Regions used for nationwide Google Places queries.
# Each region generates a separate search to cover the whole US.
_GP_NATIONWIDE_REGIONS: list[str] = [
    "New York",
    "California",
    "Texas",
    "Florida",
    "Illinois",
    "Ohio",
    "Georgia",
    "Pennsylvania",
    "North Carolina",
    "Washington",
    "Colorado",
    "Arizona",
]


async def _google_places_single_query(
    client: httpx.AsyncClient,
    query: str,
    api_key: str,
    sector: str,
) -> list[SourcedCompany]:
    """Run a single Google Places text search (first page only, 20 results max).
    Pagination tokens are unreliable so we don't attempt page 2+.
    """
    results: list[SourcedCompany] = []
    try:
        resp = await client.get(
            "https://maps.googleapis.com/maps/api/place/textsearch/json",
            params={"query": query, "key": api_key},
            timeout=15,
        )
        if resp.status_code != 200:
            logger.warning(f"[GooglePlaces] status {resp.status_code} for {query!r}")
            return results

        data = resp.json()
        status = data.get("status", "")
        if status not in ("OK", "ZERO_RESULTS"):
            logger.warning(f"[GooglePlaces] API status: {status} for {query!r}")
            return results
        if status == "ZERO_RESULTS":
            return results

        for place in data.get("results", []):
            name = place.get("name", "").strip()
            if not name:
                continue

            address = place.get("formatted_address", "")
            # Extract city/state from address
            location_str = ""
            addr_parts = address.split(",")
            if len(addr_parts) >= 3:
                location_str = ", ".join(addr_parts[-3:-1]).strip()
            elif addr_parts:
                location_str = address

            types = place.get("types", [])
            type_str = types[0].replace("_", " ").title() if types else ""

            rating = place.get("rating")
            user_ratings_total = place.get("user_ratings_total", 0)
            # Employee proxy: use review count as rough size signal
            size_hint = ""
            if user_ratings_total >= 500:
                size_hint = "Large (500+ reviews)"
            elif user_ratings_total >= 100:
                size_hint = "Mid-size (100–500 reviews)"
            elif user_ratings_total > 0:
                size_hint = f"Small ({user_ratings_total} reviews)"

            place_id = place.get("place_id", "")
            maps_url = (
                f"https://www.google.com/maps/place/?q=place_id:{place_id}"
                if place_id else ""
            )

            desc_parts = [type_str] if type_str else []
            if rating:
                desc_parts.append(f"Rating: {rating}★")
            if size_hint:
                desc_parts.append(size_hint)
            desc = " | ".join(desc_parts)

            results.append(SourcedCompany(
                name=name,
                source="Google Places",
                source_url=maps_url,
                description=desc,
                sector=type_str or sector,
                location=location_str,
                extra={
                    "address": address,
                    "place_id": place_id,
                    "rating": rating,
                    "review_count": user_ratings_total,
                    "types": types,
                    "listing_type": "active_business",
                },
            ))

    except Exception as e:
        logger.warning(f"[GooglePlaces] error for {query!r}: {e}")

    return results


async def search_google_places(
    client: httpx.AsyncClient,
    sector: str,
    keywords: str,
    location: str,
) -> list[SourcedCompany]:
    """
    Search Google Places API for businesses matching sector + keywords.
    Requires GOOGLE_PLACES_API_KEY in .env. Skips gracefully if not set.

    When no location is specified, runs parallel queries across 12 US regions
    to get nationwide coverage (~240 results).
    """
    api_key = settings.GOOGLE_PLACES_API_KEY
    if not api_key:
        logger.info("[GooglePlaces] No API key set — skipping")
        return []

    base_query = sector
    if keywords:
        base_query = f"{sector} {keywords}"

    if location.strip():
        # Specific location — single query
        query = f"{base_query} {location}"
        results = await _google_places_single_query(client, query, api_key, sector)
    else:
        # No location — run parallel queries across US regions
        queries = [f"{base_query} {region}" for region in _GP_NATIONWIDE_REGIONS]
        tasks = [
            _google_places_single_query(client, q, api_key, sector)
            for q in queries
        ]
        region_results = await asyncio.gather(*tasks, return_exceptions=True)
        results: list[SourcedCompany] = []
        for res in region_results:
            if isinstance(res, list):
                results.extend(res)
            elif isinstance(res, Exception):
                logger.warning(f"[GooglePlaces] regional query error: {res}")

    logger.info(f"[GooglePlaces] {len(results)} places found")
    return results


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

async def run_discovery_search(criteria: dict) -> list[dict]:
    """
    Run all discovery sources in parallel.
    Returns businesses that EXIST (active businesses, not listings for sale).
    """
    sector = (criteria.get("sector") or "").strip()
    keywords = (criteria.get("keywords") or "").strip()
    location = (criteria.get("location") or "").strip()

    if not sector and not keywords:
        return []

    sector_kws = _build_sector_kws(sector)
    keyword_kws = _build_keyword_kws(keywords)
    match_kws = sector_kws + keyword_kws

    logger.info(f"[Discovery] sector={sector!r} kws={keywords!r} loc={location!r}")

    # Discovery timeout: 30s overall — allows nationwide queries across many cities
    # Overpass queries enforce their own 10s per-city limit
    # Google Places runs up to 12 parallel regional queries
    discovery_timeout = httpx.Timeout(30.0)
    async with httpx.AsyncClient(timeout=discovery_timeout) as client:
        tasks = [
            search_nppes(client, sector, keywords, location),
            search_openstreetmap(client, sector, keywords, location, sector_kws or keyword_kws),
            search_google_places(client, sector, keywords, location),
        ]
        results_nested = await asyncio.gather(*tasks, return_exceptions=True)

    all_companies: list[SourcedCompany] = []
    for result in results_nested:
        if isinstance(result, Exception):
            logger.warning(f"[Discovery] task error: {result}")
        elif isinstance(result, list):
            all_companies.extend(result)

    # Deduplicate by normalized name + location
    seen: set[str] = set()
    deduped: list[SourcedCompany] = []
    for co in all_companies:
        name_norm = re.sub(r"\W+", " ", co.name.lower()).strip()
        loc_norm = re.sub(r"\W+", " ", co.location.lower()).strip()
        key = f"{name_norm}|{loc_norm}"
        if key and len(name_norm) > 2 and key not in seen:
            seen.add(key)
            deduped.append(co)

    # Score by keyword relevance (same scorer logic as sourcing, simplified)
    loc_lower = location.lower().strip()
    loc_words = [w for w in loc_lower.split() if len(w) > 2]

    def _discovery_score(co: SourcedCompany) -> int:
        combined = f"{co.name} {co.description} {co.sector}".lower()
        score = 0
        # Sector match
        # NPPES results are pre-filtered by taxonomy — they already matched the sector
        # at the API query level, so we don't re-gate them on keyword text matching.
        # OpenStreetMap / Google Places do name-based matching so also trust their source match.
        is_trusted_source = co.source in ("NPPES", "Google Places", "OpenStreetMap")
        if sector_kws:
            matched = [kw for kw in sector_kws if kw in combined]
            if matched:
                score += max(30, int(50 * len(matched) / len(sector_kws)))
            elif is_trusted_source:
                # Source already filtered to sector — give baseline sector score
                score += 30
            else:
                return 0  # doesn't match sector — filter out
        else:
            score += 30
        # Keyword boost
        if keyword_kws:
            matched_kw = [kw for kw in keyword_kws if kw in combined]
            if matched_kw:
                score += max(8, int(20 * len(matched_kw) / len(keyword_kws)))
        # Location boost — reward results from the requested area
        if loc_words:
            loc_text = f"{co.location} {co.name}".lower()
            if any(w in loc_text for w in loc_words):
                score += 10
        # Source quality
        source_bonus = {"NPPES": 15, "Google Places": 12, "OpenStreetMap": 8}
        score += source_bonus.get(co.source, 5)
        # Has phone / website
        if co.extra.get("phone"):
            score += 3
        if co.website or co.source_url:
            score += 2
        return min(100, score)

    scored: list[tuple[SourcedCompany, int]] = []
    for co in deduped:
        s = _discovery_score(co)
        if s > 0:
            co.fit_score = s
            co.fit_reasons = [f"Active business — {co.source}", co.location or "US"]
            scored.append((co, s))

    scored.sort(key=lambda x: x[1], reverse=True)

    logger.info(f"[Discovery] {len(scored)} results after scoring")
    return [co.to_dict() for co, _ in scored[:500]]
