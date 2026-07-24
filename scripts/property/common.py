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
    """Polite GET. Returns Response on 200, else None."""
    try:
        res = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
        time.sleep(DELAY_SECONDS)
        return res if res.status_code == 200 else None
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


def parse_price(text):
    """Return (amount, qualifier, listing_type)."""
    low = text.lower()
    is_rent = any(
        k in low for k in ("per calendar month", "pcm", "per month", "per week")
    )
    if "poa" in low or "price on application" in low:
        return None, "poa", "rent" if is_rent else "sale"

    amounts = [int(m.replace(",", "")) for m in re.findall(r"£\s*([\d,]{3,})", text)]
    # Filter noise: rents are small, sale prices are large.
    if is_rent:
        amounts = [a for a in amounts if 200 <= a <= 20000]
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
    low = text.lower()
    for candidate in PROPERTY_TYPES:
        if candidate in low:
            return candidate
    return None


def parse_place(text):
    for place in IOM_PLACES:
        if re.search(rf"\b{re.escape(place)}\b", text, flags=re.I):
            return place
    return None


def address_from_slug(url):
    slug = url.rstrip("/").split("/")[-1]
    # Drop a trailing -sale / -rent marker and any postcode fragment.
    slug = re.sub(r"-(sale|rent|let|letting)$", "", slug, flags=re.I)
    slug = re.sub(r"-im\d{1,2}-\d[a-z]{2}$", "", slug, flags=re.I)
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


def scrape_listing(agent, url):
    """Fetch one property page and pull out the facts. Returns dict or None."""
    res = get(url)
    if not res:
        return None

    title, heading, body = page_text(res.text)
    head_blob = f"{heading} {title}"
    price, qualifier, listing_type = parse_price(body)
    slug = url.rstrip("/").split("/")[-1]

    # An explicit -rent/-sale slug beats inferring from the page wording.
    listing_type = listing_type_from_slug(url) or listing_type

    address = heading or title.split("|")[0].strip() or address_from_slug(url)

    return {
        "id": f"{agent.key}-{slug}",
        "agent": agent.name,
        "url": url,
        "category": parse_category(f"{address} {head_blob}"),
        "listingType": listing_type,
        "price": price,
        "priceQualifier": qualifier,
        "bedrooms": parse_int(head_blob, BEDS) or parse_int(body, BEDS),
        "bathrooms": parse_int(head_blob, BATHS) or parse_int(body, BATHS),
        "propertyType": parse_type(head_blob) or parse_type(body),
        "address": address,
        "parish": parse_place(address) or parse_place(heading or title)
        or parse_place(body),
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
