"""
scrapers/property/common.py — shared logic for every agent scraper.

FACTS ONLY: price, beds, baths, type, address, locality, agent, listing URL.
No description or photographs are stored. Every listing links back to the agent.

Chrystals is parsed from its actual Expert Agent page structure: the page gives
an explicit price/title, a final 3-number stats block (beds/baths/receptions),
and a dedicated location block containing postcode and locality. Generic agents
still use the heuristic fallback.
"""

import json
import os
import re
import time
from datetime import date
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

USER_AGENT = "ManxOneBot/1.0 (+mailto:hammerpunch786@gmail.com)"
HEADERS = {"User-Agent": USER_AGENT}
DELAY_SECONDS = 2.0
TIMEOUT = 20
OUTPUT = os.environ.get("OUTPUT_PATH", "properties.json")

IOM_PLACES = [
    "Port St Mary", "Kirk Michael", "St Marks", "St Johns", "Glen Vine",
    "Glen Maye", "Union Mills", "Ballabeg", "Ballasalla", "Port Erin",
    "Port St Mary", "Douglas", "Onchan", "Ramsey", "Peel", "Castletown",
    "Laxey", "Kirk Braddan", "Braddan", "Santon", "Andreas", "Jurby",
    "Ballaugh", "Maughold", "Crosby", "Foxdale", "Baldrine", "Dalby",
    "Marown", "Malew", "Lonan", "Bride", "Colby", "Sulby", "Ronague",
    "Grenaby", "Maughold", "Smeale", "Lezayre", "Arbory", "Patrick",
    "German", "Garff", "Rushen", "Michael", "Ayre",
]

PROPERTY_TYPES = [
    "detached bungalow", "semi-detached", "end of terrace", "end-of-terrace",
    "mid terrace", "terraced", "detached", "bungalow", "apartment", "flat",
    "cottage", "townhouse", "maisonette", "farmhouse", "land", "commercial",
    "penthouse",
]

COMMERCIAL_WORDS = [
    "office", "offices", "shop", "retail", "showroom", "workshop",
    "commercial", "warehouse", "industrial", "hotel", "licensed premises",
    "business", "restaurant", "cafe", "salon", "surgery", "storage",
]
LAND_WORDS = ["field no", "field number", "land at", "building plot", "site at"]
WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}

# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def get(url, params=None):
    try:
        res = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
        time.sleep(DELAY_SECONDS)
        if res.status_code != 200:
            print(f"    ! HTTP {res.status_code} for {url}")
            return None
        return res
    except requests.RequestException as exc:
        print(f"    ! {url} -> {exc}")
        return None

# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def page_text(html):
    """Return (title, h1, flattened body text), stripping scripts/styles."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    h1 = soup.find("h1")
    heading = h1.get_text(" ", strip=True) if h1 else ""
    body = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    return title, heading, body

# ---------------------------------------------------------------------------
# Price
# ---------------------------------------------------------------------------

RENT_MARKERS = (
    "per calendar month", "pcm", "p.c.m", "per month", "per week", "pw",
    "monthly rent", "monthly rental", "a month", "a week",
)
SALE_MARKERS = (
    "for sale", "offers around", "offers in the region", "offers over",
    "offers in excess", "asking price", "guide price", "oiro", "oieo",
)
NOT_THE_PRICE = (
    "rate", "rates", "rateable", "ground rent", "service charge",
    "maintenance", "deposit", "bond", "fee", "fees", "yield", "insurance",
    "council tax", "premium", "per annum", "pa", "annual", "epc",
    "commission", "stamp duty", "legal",
)
_AMOUNT_RE = re.compile(r"£\s*([\d,]{3,})")


def _context_before(text, pos, span=55):
    return text[max(0, pos - span):pos].lower()


def _context_after(text, pos, span=45):
    return text[pos:pos + span].lower()


def _candidate_amounts(text):
    out = []
    for m in _AMOUNT_RE.finditer(text):
        try:
            amount = int(m.group(1).replace(",", ""))
        except ValueError:
            continue
        before = _context_before(text, m.start())
        after = _context_after(text, m.end())
        if any(re.search(rf"\b{re.escape(w)}\b", before) for w in NOT_THE_PRICE):
            continue
        out.append((amount, before, after))
    return out


def parse_price(text, listing_type_hint=None):
    """Return (amount, qualifier, listing_type), respecting rent/sale context."""
    low = text.lower()
    candidates = _candidate_amounts(text)

    if listing_type_hint in ("rent", "sale"):
        is_rent = listing_type_hint == "rent"
    else:
        rent_beside = any(
            any(marker in after or marker in before for marker in RENT_MARKERS)
            for _, before, after in candidates
        )
        sale_on_page = any(marker in low for marker in SALE_MARKERS)
        if rent_beside and not sale_on_page:
            is_rent = True
        elif sale_on_page:
            is_rent = False
        else:
            is_rent = rent_beside

    if re.search(r"\bpoa\b", low) or "price on application" in low:
        return None, "poa", "rent" if is_rent else "sale"

    if is_rent:
        amounts = [a for a, _, _ in candidates if 100 <= a <= 100000]
        qualifier = "pcm"
    else:
        amounts = [a for a, _, _ in candidates if a >= 20000]
        amounts.sort(reverse=True)
        if re.search(r"guide price", low):
            qualifier = "guide"
        elif "offers in excess" in low or "oieo" in low:
            qualifier = "oieo"
        elif "offers over" in low or "oio" in low:
            qualifier = "oio"
        elif "offers around" in low:
            qualifier = "offers-around"
        else:
            qualifier = "asking"

    if not amounts:
        return None, "unknown", "rent" if is_rent else "sale"

    return amounts[0], qualifier, "rent" if is_rent else "sale"

# ---------------------------------------------------------------------------
# Generic parsing helpers
# ---------------------------------------------------------------------------

BEDS = ["bed", "bedroom", "bedrooms"]
BATHS = ["bath", "bathroom", "bathrooms"]


def parse_int(text, words):
    noun = "(?:" + "|".join(words) + r")"
    number = r"(\d+|" + "|".join(WORD_NUMBERS) + r")"
    matches = re.findall(rf"\b{number}[-\s]*{noun}\b", text, flags=re.I)
    if not matches:
        return None
    first = matches[0].lower()
    return int(first) if first.isdigit() else WORD_NUMBERS[first]


def parse_type(text):
    """Generic fallback type parser using word boundaries."""
    low = text.lower()
    for candidate in PROPERTY_TYPES:
        if re.search(rf"\b{re.escape(candidate)}\b", low):
            return candidate
    return None


def parse_chrystals_type(text):
    """Classify Chrystals from property-description phrases, avoiding garage noise."""
    low = re.sub(r"\s+", " ", text.lower())

    # Land/building-plot wording must win before a planning proposal such as
    # "planning permission for detached property" is considered.
    rules = (
        (r"\bbuilding plot\b", "land"),
        (r"\bdevelopment site\b", "land"),
        (r"\bplot of land\b", "land"),
        (r"\bsite for (?:residential|commercial) development\b", "land"),
        (r"\bsemi[- ]detached\s+(?:[a-z-]+\s+){0,3}(?:house|home|property|townhouse|bungalow)\b", "semi-detached"),
        (r"\bend[- ]of[- ]terrace\b", "end of terrace"),
        (r"\bmid[- ]terrace\b", "mid terrace"),
        (r"\bterraced\s+(?:house|home|property|townhouse)\b", "terraced"),
        (r"\b(?:top|ground|first|second|third|lower|upper)[- ]floor\s+(?:apartment|flat)\b", "apartment"),
        (r"\b(?:penthouse|apartment)\b", "apartment"),
        (r"\bflat\b", "flat"),
        (r"\bbungalow\b", "bungalow"),
        (r"\btownhouse\b", "townhouse"),
        (r"\bmaisonette\b", "maisonette"),
        (r"\bfarmhouse\b", "farmhouse"),
        (r"\bcottage\b", "cottage"),
        (r"\bdetached\s+(?:[a-z-]+\s+){0,3}(?:house|home|property|residence|bungalow|cottage)\b", "detached"),
    )
    for pattern, value in rules:
        if re.search(pattern, low):
            return value
    return None


def parse_place(text):
    for place in sorted(set(IOM_PLACES), key=len, reverse=True):
        if re.search(rf"\b{re.escape(place)}\b", text, flags=re.I):
            return place
    return None


def parse_category(text):
    low = text.lower()
    if any(word in low for word in LAND_WORDS):
        return "land"
    if any(re.search(rf"\b{re.escape(w)}\b", low) for w in COMMERCIAL_WORDS):
        return "commercial"
    return "residential"


def parse_postcode(url, text=""):
    slug_match = re.search(r"\b(im\d{1,2})-(\d[a-z]{2})\b", url, flags=re.I)
    if slug_match:
        return f"{slug_match.group(1).upper()} {slug_match.group(2).upper()}"

    text_match = re.search(r"\b(IM\d{1,2})\s*-?\s*(\d[A-Z]{2})\b", text, flags=re.I)
    if text_match:
        return f"{text_match.group(1).upper()} {text_match.group(2).upper()}"
    return None


def address_from_slug(url):
    slug = url.rstrip("/").split("/")[-1]
    slug = re.sub(r"-(sale|rent|let|letting)$", "", slug, flags=re.I)
    slug = re.sub(r"-im\d{1,2}-\d[a-z]{2}$", "", slug, flags=re.I)
    slug = re.sub(r"^\d{6,}-", "", slug)
    parts = slug.split("-")
    if len(parts) >= 4 and len(parts) % 2 == 0:
        half = len(parts) // 2
        if parts[:half] == parts[half:]:
            slug = "-".join(parts[:half])
    return slug.replace("-", " ").strip().title()


def listing_type_from_slug(url):
    slug = url.rstrip("/").split("/")[-1].lower()
    if re.search(r"-(rent|let|letting)$", slug):
        return "rent"
    if re.search(r"-sale$", slug):
        return "sale"
    return None

# ---------------------------------------------------------------------------
# Chrystals-specific extraction
# ---------------------------------------------------------------------------

DEAD_PAGE_MARKERS = [
    "property not found", "page not found", "404", "no longer available",
    "not currently available", "under offer no longer", "listing removed",
]


def _looks_dead(title, heading, body):
    blob = f"{heading} {title}".lower()
    if any(marker in blob for marker in DEAD_PAGE_MARKERS):
        return True
    return len(body) < 200


def _clean_address(address, agent_name):
    text = address.strip()
    for separator in (" - ", " | ", " – ", ": "):
        prefix = f"{agent_name}{separator}"
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix):].strip()
        suffix = f"{separator}{agent_name}"
        if text.lower().endswith(suffix.lower()):
            text = text[:-len(suffix)].strip()
    if text.lower().startswith(agent_name.lower()):
        text = text[len(agent_name):].lstrip(" -|–:,").strip()
    text = re.sub(
        r"\s*(monthly rent(al)?( of)?|per calendar month|pcm|price|offers?"
        r"( (in|around|over|above))?|guide price|asking price|from)\b.*$",
        "",
        text,
        flags=re.I,
    ).strip(" -–|,:")
    return text or address


def _chrystals_location(body, heading, url):
    postcode = parse_postcode(url, body)

    # The final "Click to Enlarge" is immediately before the location block on
    # Expert Agent pages. Pull only that tail so footer/nav place names cannot win.
    tail = body.rsplit("Click to Enlarge", 1)[-1]

    if postcode:
        candidates = []
        for place in sorted(set(IOM_PLACES), key=len, reverse=True):
            m = re.search(rf"(.+?)\s+{re.escape(place)}\s+{re.escape(postcode)}\s+County\s*:", tail, flags=re.I)
            if m:
                street = re.sub(r"^[*\s|]+|[*\s|]+$", "", m.group(1)).strip()
                street = re.sub(r"\s+", " ", street)
                candidates.append((len(m.group(1)), street, place))
        if candidates:
            # Shortest match is normally the actual street/address line.
            _, street, place = min(candidates, key=lambda x: x[0])
            if street:
                return _clean_address(f"{street}, {place}", "Chrystals"), place, postcode

    address = _clean_address(heading or address_from_slug(url), "Chrystals")
    return address, parse_place(address), postcode


def _chrystals_stats(body):
    """Chrystals' final three integers are beds, baths, receptions."""
    matches = re.findall(
        r"\b(\d{1,2})\s+(\d{1,2})\s+(\d{1,2})\s+(?:Brochure|Register With Us)\b",
        body,
        flags=re.I,
    )
    if matches:
        b, ba, _rec = matches[-1]
        return int(b), int(ba)
    return None, None


def _chrystals_status(body):
    blob = body[:2500].lower()
    for phrase in ("sold stc", "under offer", "let stc", "new property", "updated"):
        if phrase in blob:
            return phrase.replace(" ", "_")
    return None


def scrape_listing(agent, url):
    """Fetch one property page and pull out facts with provider-aware parsing."""
    res = get(url)
    if not res:
        return None

    title, heading, body = page_text(res.text)
    if _looks_dead(title, heading, body):
        return None

    slug = url.rstrip("/").split("/")[-1]
    url_category, url_type = agent.classify(url)
    type_hint = url_type or listing_type_from_slug(url)

    # Price should come from the page heading first. This avoids service charges,
    # deposits and room dimensions later in the document becoming the headline price.
    head_blob = f"{heading} {title}".strip()
    price, qualifier, listing_type = parse_price(head_blob, type_hint)
    if price is None:
        price, qualifier, listing_type = parse_price(body[:5000], type_hint)

    if agent.key == "chr":
        address, locality, postcode = _chrystals_location(body, heading, url)
        bedrooms, bathrooms = _chrystals_stats(body)
        prop_type = parse_chrystals_type(body[:12000]) or parse_type(address)
        status = _chrystals_status(body)
    else:
        address = _clean_address(heading or title.split("|")[0].strip() or address_from_slug(url), agent.name)
        locality = parse_place(address)
        postcode = parse_postcode(url, body)
        bedrooms = parse_int(head_blob, BEDS) or parse_int(body, BEDS)
        bathrooms = parse_int(head_blob, BATHS) or parse_int(body, BATHS)
        prop_type = parse_type(f"{address} {head_blob}")
        status = None

    listing_type = type_hint or listing_type
    category = url_category or parse_category(address)

    item = {
        "id": f"{agent.key}-{slug}",
        "agent": agent.name,
        "url": url,
        "category": category,
        "listingType": listing_type,
        "price": price,
        "priceQualifier": qualifier,
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "propertyType": prop_type,
        "address": address,
        "locality": locality,
        # Kept for backward compatibility with the current Manx One schema.
        # Chrystals exposes locality + postcode, not a dedicated parish field.
        "parish": locality,
        "postcode": postcode,
    }
    if status:
        item["status"] = status
    return item

# ---------------------------------------------------------------------------
# Merge with previous run
# ---------------------------------------------------------------------------

def load_previous():
    if not os.path.exists(OUTPUT):
        return []
    try:
        with open(OUTPUT, encoding="utf-8") as fh:
            return json.load(fh).get("listings", [])
    except (json.JSONDecodeError, KeyError, OSError):
        print("  ! previous output unreadable; starting fresh")
        return []


def merge(new_listings, previous, failed_agents):
    today = date.today().isoformat()
    prev_by_id = {item["id"]: item for item in previous}

    merged = []
    for item in new_listings:
        old = prev_by_id.get(item["id"])
        if old:
            item["firstSeen"] = old.get("firstSeen", today)
            old_price = old.get("price")
            if old_price and item["price"] and old_price != item["price"]:
                item["previousPrice"] = old_price
            elif old.get("previousPrice"):
                item["previousPrice"] = old["previousPrice"]
        else:
            item["firstSeen"] = today
        item["lastSeen"] = today
        merged.append(item)

    if failed_agents:
        seen_ids = {i["id"] for i in merged}
        for old in previous:
            if old["agent"] in failed_agents and old["id"] not in seen_ids:
                old["stale"] = True
                merged.append(old)

    return merged
