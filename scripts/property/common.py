"""
scrapers/property/common.py — shared logic for every agent scraper.

DESIGN RULE (applies to all agents): index the FACTS, link out for the CONTENT.
  Collected : price, beds, baths, type, address, parish, agent, listing URL
  NEVER     : description prose, photographs
Facts are not copyrightable; the agent's descriptions and images are theirs.
Every listing carries attribution and links back to the agent's own page.

Always check an agent's robots.txt before adding them to agents.py.
"""

import json
import os
import re
import time
from datetime import date

import requests
from bs4 import BeautifulSoup

# Identify honestly — agents should be able to contact you, not just block you.
USER_AGENT = "ManxOneBot/1.0 (+mailto:hammerpunch786@gmail.com)"
HEADERS = {"User-Agent": USER_AGENT}

DELAY_SECONDS = 2.0   # be polite; these are small businesses' servers
TIMEOUT = 20

OUTPUT = os.environ.get("OUTPUT_PATH", "properties.json")

IOM_PLACES = [
    "Douglas", "Onchan", "Ramsey", "Peel", "Castletown", "Port Erin",
    "Port St Mary", "Laxey", "Ballasalla", "Kirk Michael", "Andreas",
    "Jurby", "Ballaugh", "Maughold", "St Johns", "Glen Vine", "Crosby",
    "Union Mills", "Braddan", "Santon", "Ballabeg", "Colby", "Sulby",
    "Foxdale", "Baldrine", "Dalby", "Marown", "Malew", "Lonan", "Bride",
    "Ballaugh", "Glen Maye", "Ronague", "Grenaby", "Kirk Braddan",
]

PROPERTY_TYPES = [
    "detached bungalow", "semi-detached", "end of terrace", "end-of-terrace",
    "mid terrace", "terraced", "detached", "bungalow", "apartment", "flat",
    "cottage", "townhouse", "maisonette", "farmhouse", "land", "commercial",
]

WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}

# Words that mark a listing as non-residential. Users browsing for a home do
# not want offices and shops mixed into the results, so tag them and let the
# app filter. Kept deliberately specific: "unit"/"premises" alone are too loose.
COMMERCIAL_WORDS = [
    "office", "offices", "shop", "retail", "showroom", "workshop",
    "commercial", "warehouse", "industrial", "hotel", "licensed premises",
    "business", "restaurant", "cafe", "salon", "surgery", "storage",
]

LAND_WORDS = ["field no", "field number", "land at", "building plot", "site at"]


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def get(url, params=None):
    """Polite GET. Returns Response on 200, else None.

    Non-200 responses are logged: a silent None made a 403 from an agent's
    firewall look identical to an empty sitemap, which cost a debugging cycle.
    """
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
# Extraction helpers (shared by every agent)
# ---------------------------------------------------------------------------

def page_text(html):
    """Return (title, h1, flattened body text) with scripts/styles removed."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    title = soup.title.get_text(strip=True) if soup.title else ""
    h1 = soup.find("h1")
    heading = h1.get_text(" ", strip=True) if h1 else ""
    body = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    return title, heading, body


# Agents word rentals inconsistently. Chrystals uses "Monthly Rental Of
# £725", which the original keyword list missed entirely — every one of their
# lettings came back unpriced.
RENT_PHRASES = (
    "per calendar month", "pcm", "p.c.m", "per month", "per week",
    "monthly rent", "monthly rental", "per annum", "rent of", "rental of",
)


def parse_price(text, listing_type_hint=None):
    """Return (amount, qualifier, listing_type).

    listing_type_hint comes from the agent's URL structure or slug where
    available, and is AUTHORITATIVE IN BOTH DIRECTIONS. This matters:

      * A sale listing's text often mentions rent ("rental yield", "currently
        let at £X pa") — common on investment and commercial sales. Without a
        binding hint those flipped to "rent".
      * A rent listing may quote large sale-like figures in passing, which
        flipped it to "sale" and gave it a bogus price.

    Only when no hint exists do we infer the type from the page wording.
    """
    low = text.lower()
    if listing_type_hint in ("rent", "sale"):
        is_rent = listing_type_hint == "rent"
    else:
        is_rent = any(k in low for k in RENT_PHRASES)

    if "poa" in low or "price on application" in low:
        return None, "poa", "rent" if is_rent else "sale"

    amounts = [int(m.replace(",", "")) for m in re.findall(r"£\s*([\d,]{3,})", text)]
    # Filter noise: rents are small, sale prices are large. The upper rent
    # bound is generous because commercial lettings are quoted per annum.
    if is_rent:
        amounts = [a for a in amounts if 100 <= a <= 100000]
    else:
        amounts = [a for a in amounts if a >= 20000]

    if not amounts:
        return None, "unknown", "rent" if is_rent else "sale"
    return (
        amounts[0],
        "pcm" if is_rent else "asking",
        "rent" if is_rent else "sale",
    )


def parse_int(text, words):
    """Find '3 bed', 'three-bedroom', 'two bedroom' -> 3 / 3 / 2.

    Agent copy mixes digits, written numbers and hyphens freely, so all
    three forms must be handled or counts silently go missing.
    """
    noun = "(?:" + "|".join(words) + r")"
    number = r"(\d+|" + "|".join(WORD_NUMBERS) + r")"
    matches = re.findall(rf"\b{number}[-\s]*{noun}\b", text, flags=re.I)
    if not matches:
        return None
    first = matches[0].lower()
    return int(first) if first.isdigit() else WORD_NUMBERS[first]


def parse_type(text):
    """Match on WORD BOUNDARIES.

    Plain substring matching made 'land' match inside 'Island' — and every
    Isle of Man page says Island somewhere — which mis-typed 1447 listings.
    Order matters: 'semi-detached' is listed before 'detached' so it wins.
    """
    low = text.lower()
    for candidate in PROPERTY_TYPES:
        if re.search(rf"\b{re.escape(candidate)}\b", low):
            return candidate
    return None


def parse_place(text):
    for place in IOM_PLACES:
        if re.search(rf"\b{re.escape(place)}\b", text, flags=re.I):
            return place
    return None


def _dedupe_doubled(text):
    """Chrystals slugs often repeat the address twice: 'a-b-c-a-b-c' -> 'a-b-c'."""
    parts = text.split("-")
    if len(parts) >= 4 and len(parts) % 2 == 0:
        half = len(parts) // 2
        if parts[:half] == parts[half:]:
            return "-".join(parts[:half])
    return text


def address_from_slug(url):
    slug = url.rstrip("/").split("/")[-1]
    # Drop a trailing -sale / -rent marker and any postcode fragment.
    slug = re.sub(r"-(sale|rent|let|letting)$", "", slug, flags=re.I)
    slug = re.sub(r"-im\d{1,2}-\d[a-z]{2}$", "", slug, flags=re.I)
    # Some agents prefix a numeric listing reference: 12877821-17-oak-park-peel
    slug = re.sub(r"^\d{6,}-", "", slug)
    slug = _dedupe_doubled(slug)
    return slug.replace("-", " ").strip().title()


def parse_postcode(url, text=""):
    """Isle of Man postcodes are IM1-IM9 + space + digit + two letters.

    Several agents put the postcode straight in the URL slug
    (…-ramsey-im7-1bl), which is more reliable than reading the page.
    """
    slug_match = re.search(r"\b(im\d{1,2})-(\d[a-z]{2})\b", url, flags=re.I)
    if slug_match:
        return f"{slug_match.group(1).upper()} {slug_match.group(2).upper()}"

    text_match = re.search(r"\b(IM\d{1,2})\s*(\d[A-Z]{2})\b", text)
    if text_match:
        return f"{text_match.group(1)} {text_match.group(2)}"
    return None


def parse_category(text):
    """residential | commercial | land — so the app can filter homes only."""
    low = text.lower()
    if any(word in low for word in LAND_WORDS):
        return "land"
    if any(re.search(rf"\b{re.escape(w)}\b", low) for w in COMMERCIAL_WORDS):
        return "commercial"
    return "residential"


def listing_type_from_slug(url):
    """Some agents end the slug with -rent or -sale. Trust it when present."""
    slug = url.rstrip("/").split("/")[-1].lower()
    if re.search(r"-(rent|let|letting)$", slug):
        return "rent"
    if re.search(r"-sale$", slug):
        return "sale"
    return None


BEDS = ["bed", "bedroom", "bedrooms"]
BATHS = ["bath", "bathroom", "bathrooms"]

# Agents leave dead listing URLs in their sitemaps (Chrystals especially).
# Those pages return HTTP 200 with an error message, so they have to be
# detected by content or they end up in the app as "Property Not Found".
DEAD_PAGE_MARKERS = [
    "property not found", "page not found", "404", "no longer available",
    "not currently available", "under offer no longer", "listing removed",
]


def _looks_dead(title, heading, body):
    blob = f"{heading} {title}".lower()
    if any(marker in blob for marker in DEAD_PAGE_MARKERS):
        return True
    # A real listing page always has some substance to it.
    return len(body) < 200


def _clean_address(address, agent_name):
    """Strip the agency name that several agents prepend to their <h1>.

    'Cowley Groves - 1 Forest View Apartments, Ramsey' -> '1 Forest View...'
    Without this the agent name shows twice on every card.
    """
    text = address.strip()
    for separator in (" - ", " | ", " – ", ": "):
        prefix = f"{agent_name}{separator}"
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix):].strip()
        suffix = f"{separator}{agent_name}"
        if text.lower().endswith(suffix.lower()):
            text = text[: -len(suffix)].strip()
    # Also drop a bare leading/trailing agency name.
    if text.lower().startswith(agent_name.lower()):
        text = text[len(agent_name):].lstrip(" -|–:,").strip()

    # Some agents append the price to the heading, e.g.
    # "Central Promenade, Douglas Monthly Rental Of £725" -> drop the tail.
    text = re.sub(
        r"\s*(monthly rent(al)?( of)?|per calendar month|pcm|price|offers?"
        r"( (in|around|over|above))?|guide price|asking price|from)\b.*$",
        "",
        text,
        flags=re.I,
    ).strip(" -–|,:")

    return text or address


def scrape_listing(agent, url):
    """Fetch one property page and pull out the facts. Returns dict or None."""
    res = get(url)
    if not res:
        return None

    title, heading, body = page_text(res.text)

    # Dead or placeholder pages must not reach the app.
    if _looks_dead(title, heading, body):
        return None

    head_blob = f"{heading} {title}"
    slug = url.rstrip("/").split("/")[-1]

    address = heading or title.split("|")[0].strip() or address_from_slug(url)
    address = _clean_address(address, agent.name)

    # Where an agent encodes category/type in the URL, trust that over both the
    # slug suffix and any guess made from the page wording.
    url_category, url_type = agent.classify(url)

    # The binding type hint comes from the URL path (Chrystals) or the slug
    # suffix (Cowley Groves' -rent/-sale). It must be resolved BEFORE price
    # parsing so the price is read with the correct rent/sale expectations —
    # otherwise a rental parsed hint-less can grab a sale-sized number from
    # the page and flip itself.
    type_hint = url_type or listing_type_from_slug(url)

    # Price: the heading usually states it ("... Monthly Rental Of £725"),
    # and the heading has none of the footer noise the body carries.
    price, qualifier, listing_type = parse_price(head_blob, type_hint)
    if price is None:
        price, qualifier, listing_type = parse_price(body, type_hint)

    listing_type = type_hint or listing_type
    category = url_category or parse_category(f"{address} {head_blob}")

    # Parish and property type are read from the ADDRESS ONLY, never the body.
    # Reading the body picked up the agency's own footer address, which made
    # 78% of listings look like they were in Douglas.
    place_blob = f"{address} {heading}"

    return {
        "id": f"{agent.key}-{slug}",
        "agent": agent.name,
        "url": url,
        "category": category,
        "listingType": listing_type,
        "price": price,
        "priceQualifier": qualifier,
        "bedrooms": parse_int(head_blob, BEDS) or parse_int(body, BEDS),
        "bathrooms": parse_int(head_blob, BATHS) or parse_int(body, BATHS),
        "propertyType": parse_type(place_blob),
        "address": address,
        "parish": parse_place(place_blob),
        "postcode": parse_postcode(url, body),
        # Deliberately absent: description, images.
    }


# ---------------------------------------------------------------------------
# Merge with previous run — this is where the real value lives
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
    """Add firstSeen / lastSeen / previousPrice.

    Listings from agents that FAILED this run are carried over from the
    previous file rather than silently vanishing from the app — one broken
    parser should never blank out a whole agency.
    """
    today = date.today().isoformat()
    prev_by_id = {item["id"]: item for item in previous}

    merged = []
    for item in new_listings:
        old = prev_by_id.get(item["id"])
        if old:
            item["firstSeen"] = old.get("firstSeen", today)
            old_price = old.get("price")
            # Track reductions — no agent site shows this, and it's OUR data.
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
                old["stale"] = True   # app can show a "last checked" note
                merged.append(old)

    return merged
