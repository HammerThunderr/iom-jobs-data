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
    "penthouse", "house",
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

# Waits before retrying a page that timed out or got a "busy" answer
# (429 / 5xx). A 404 is a real answer (e.g. past the last index page) and
# is not retried.
RETRY_WAITS = (15, 45)


def get(url, params=None):
    for attempt in range(len(RETRY_WAITS) + 1):
        try:
            res = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
            time.sleep(DELAY_SECONDS)
            if res.status_code == 200:
                return res
            print(f"    ! HTTP {res.status_code} for {url}")
            if res.status_code != 429 and res.status_code < 500:
                return None
        except requests.RequestException as exc:
            print(f"    ! {url} -> {exc}")
        if attempt < len(RETRY_WAITS):
            wait = RETRY_WAITS[attempt]
            print(f"    … retrying in {wait}s")
            time.sleep(wait)
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


def _deanwood_status(text):
    """Read the status from DeanWood's property header."""
    m = re.search(
        r"\b(sold\s+stc|under\s+offer|let\s+agreed|to\s+let|for\s+sale|sold|let)\b",
        text[:2500],
        flags=re.I,
    )
    if not m:
        return None
    return re.sub(r"\s+", "_", m.group(1).lower())


DEANWOOD_TYPE_RULES = (
    (r"\bsemi[- ]detached\b", "semi-detached"),
    (r"\bend[- ]of[- ]terrace\b", "end of terrace"),
    (r"\bmid[- ]terrace\b", "mid terrace"),
    (r"\bterraced\b", "terraced"),
    (r"\bdetached\b", "detached"),
    (r"\bbungalow\b", "bungalow"),
    (r"\bapartment\b", "apartment"),
    (r"\bflat\b", "flat"),
    (r"\bcottage\b", "cottage"),
    (r"\btownhouse\b", "townhouse"),
    (r"\bhouse\b", "house"),
    (r"\bmaisonette\b", "maisonette"),
    (r"\b[m]ews\b", "mews"),
    (r"\bpenthouse\b", "penthouse"),
    (r"\bfarmhouse\b", "farmhouse"),
    (r"\bblock of flats\b", "block of flats"),
    (r"\boffice(?:s)?\b", "office"),
    (r"\bretail(?: premises)?\b", "retail"),
    (r"\bindustrial\b", "industrial"),
    (r"\bwarehouse\b", "warehouse"),
    (r"\brestaurant\s*/\s*café\b|\brestaurant\b|\bcafe\b", "restaurant / cafe"),
    (r"\bpub\s*/\s*bar\b|\bpub\b", "pub / bar"),
    (r"\bleisure\s*/\s*hospitality\b", "leisure / hospitality"),
    (r"\bparking\s*/\s*garage\b", "parking / garage"),
    (r"\bbuilding plot\b|\bplot of land\b|\bland\b", "land"),
)


def _deanwood_type(header):
    """Extract the property type from the compact header, not the description."""
    low = re.sub(r"\s+", " ", header.lower())
    for pattern, value in DEANWOOD_TYPE_RULES:
        if re.search(pattern, low):
            return value
    return None


def _deanwood_price(body, status):
    """Parse DeanWood prices, including residential pcm and commercial pa rates."""
    low = body.lower()
    if re.search(r"\bpoa\b|price on application", low[:3000]):
        kind = "rent" if status in {"to_let", "let", "let_agreed"} else "sale"
        return None, "poa", kind

    is_rent = status in {"to_let", "let", "let_agreed"}
    candidates = []
    for m in _AMOUNT_RE.finditer(body[:3500]):
        amount = int(m.group(1).replace(",", ""))
        after = body[m.end():m.end() + 45].lower()
        before = body[max(0, m.start() - 20):m.start()].lower()
        if is_rent:
            if re.search(r"\bpcm\b|per (calendar )?month|per week|\bpw\b", after):
                candidates.append((0, amount, "pcm"))
            elif re.search(r"\bpa\b|per annum|per year", after):
                candidates.append((1, amount, "pa"))
            elif re.search(r"per sq ?ft|per square foot|psf", after):
                candidates.append((2, amount, "psf"))
            else:
                candidates.append((9, amount, "rent"))
        else:
            # For a sale page such as "£425,000 £9,000 pa", ignore the annual
            # secondary figure and keep the actual sale consideration.
            if re.search(r"\bpa\b|per annum|per year|\bpcm\b|per month", after):
                continue
            candidates.append((0, amount, "asking"))

    if not candidates:
        return None, "unknown", "rent" if is_rent else "sale"

    if is_rent:
        candidates.sort(key=lambda x: (x[0], -x[1]))
        _, amount, qualifier = candidates[0]
        return amount, qualifier, "rent"

    amount = max(amount for _, amount, _ in candidates)
    qualifier = "guide" if "guide price" in low[:3500] else "asking"
    if "offers over" in low[:3500] or "oio" in low[:3500]:
        qualifier = "oio"
    elif "offers in excess" in low[:3500] or "oieo" in low[:3500]:
        qualifier = "oieo"
    return amount, qualifier, "sale"



MANXMOVE_TYPE_RULES = (
    (r"\bsemi[- ]detached\b", "semi-detached"),
    (r"\bend[- ]of[- ]terrace\b", "end of terrace"),
    (r"\bmid[- ]terrace\b", "mid terrace"),
    (r"\bterraced\b", "terraced"),
    (r"\bdetached\b", "detached"),
    (r"\bbungalow\b", "bungalow"),
    (r"\bapartment\b", "apartment"),
    (r"\bflat\b", "flat"),
    (r"\bcottage\b", "cottage"),
    (r"\btownhouse\b", "townhouse"),
    (r"\bhouse\b", "house"),
    (r"\bmaisonette\b", "maisonette"),
    (r"\bpenthouse\b", "penthouse"),
    (r"\bmews\b", "mews"),
    (r"\bbuilding plot\b|\bplot of land\b|\bland\b", "land"),
    (r"\bgarage\b|\bgaraging\b", "garage"),
)


def _manxmove_status(text):
    """Read Manxmove's status from the top of the property page."""
    m = re.search(
        r"\b(sold\s+stc|under\s+offer|let\s+agreed|for\s+sale|for\s+rent|to\s+let|sold|let)\b",
        text[:1600],
        flags=re.I,
    )
    return re.sub(r"\s+", "_", m.group(1).lower()) if m else None


def _manxmove_type(header):
    low = re.sub(r"\s+", " ", header.lower())
    for pattern, value in MANXMOVE_TYPE_RULES:
        if re.search(pattern, low):
            return value
    return None


def _manxmove_price(header, status):
    """Use the first/only headline amount from Manxmove's header."""
    low = header.lower()
    if re.search(r"\bpoa\b|price on application", low):
        return None, "poa", "rent" if status in {"for_rent", "to_let", "let_agreed", "let"} else "sale"

    is_rent = status in {"for_rent", "to_let", "let_agreed", "let"} or " pcm" in low
    amounts = []
    for m in _AMOUNT_RE.finditer(header):
        amount = int(m.group(1).replace(",", ""))
        after = header[m.end():m.end()+50].lower()
        if is_rent:
            if re.search(r"\bpcm\b|per (calendar )?month|\bpw\b|per week", after):
                amounts.append((0, amount, "pcm"))
            elif 100 <= amount <= 100000:
                amounts.append((1, amount, "pcm"))
        elif amount >= 20000:
            amounts.append((0, amount, "guide" if "guide price" in low else "asking"))

    if not amounts:
        return None, "unknown", "rent" if is_rent else "sale"
    rank, amount, qualifier = sorted(amounts, key=lambda x: (x[0], -x[1]))[0]
    if not is_rent:
        if "offers over" in low or "oio" in low:
            qualifier = "oio"
        elif "offers in excess" in low or "oieo" in low:
            qualifier = "oieo"
        elif "guide price" in low:
            qualifier = "guide"
    return amount, qualifier, "rent" if is_rent else "sale"


def _manxmove_stats(header, body):
    """Extract beds/baths from header/body without counting marketing text.

    The Manxmove property header reliably gives the bedroom count as '<n> Bed'.
    Bathroom counts are usually present in compact wording such as '2 bathrooms'
    or '2 bathrooms' in the description; when absent we leave the field null
    rather than guessing from mentions of a singular family bathroom.
    """
    beds = parse_int(header, BEDS)
    bath = None
    for text in (header, body[:5000]):
        m = re.search(r"\b(\d+)\s+(?:bath(?:room)?s?)\b", text, flags=re.I)
        if m:
            bath = int(m.group(1))
            break
    if bath is None:
        m = re.search(r"\b(\d+)\s+(?:en[- ]?suite|ensuite)s?\b", body[:5000], flags=re.I)
        if m:
            bath = int(m.group(1))
    return beds, bath


def _manxmove_category(prop_type, header, url):
    low = f"{header} {url}".lower()
    if prop_type in {"land", "garage"} or re.search(r"\bbuilding plot\b|\bplot of land\b", low):
        return "land" if prop_type == "land" or "plot" in low else "commercial"
    if prop_type in {"office", "retail", "industrial", "warehouse", "restaurant", "pub / bar"}:
        return "commercial"
    return "residential"


def _deanwood_category(prop_type, header, body):
    """Classify DeanWood pages without letting footer/contact text decide."""
    blob = f"{header} {body[:3500]}".lower()
    if prop_type in {
        "office", "retail", "industrial", "warehouse", "restaurant / cafe",
        "pub / bar", "leisure / hospitality", "parking / garage", "block of flats",
    }:
        return "commercial"
    if prop_type == "land" or re.search(
        r"\bbuilding plot\b|\bplot of land\b|\bdevelopment site\b|\bland for sale\b",
        blob,
    ):
        return "land"
    return "residential"


# ---------------------------------------------------------------------------
# Black Grace Cowley, Grays, Partners (added Nov 2026)
# ---------------------------------------------------------------------------

_STATUS_WORDS = (
    ("sold subject to contract", "Sold STC"), ("sold stc", "Sold STC"),
    ("under offer", "Under Offer"), ("let agreed", "Let Agreed"),
    ("let stc", "Let Agreed"), ("reserved", "Reserved"),
    ("offer accepted", "Offer Accepted"),
)


def _status_in(text):
    low = text.lower()
    for needle, label in _STATUS_WORDS:
        if needle in low:
            return label
    return None


def _between(body, start_marker, end_markers, default_len=1500):
    """The slice of body from start_marker to the first end marker."""
    low = body.lower()
    i = low.find(start_marker.lower()) if start_marker else 0
    i = max(i, 0)
    ends = [low.find(m.lower(), i + 1) for m in end_markers]
    ends = [e for e in ends if e > i]
    j = min(ends) if ends else i + default_len
    return body[i:j]


def _bgc(body, heading, title, type_hint):
    """bgc.im: breadcrumb "Residential / Buy / <address>", then
    "3 Bed 2 Bath 3 Reception", status, "£499,500", then "Key Features"."""
    crumb = re.search(r"\b(Residential|Commercial|Land)\s*/\s*(Buy|Rent|Let)\b", body, re.I)
    category = crumb.group(1).lower() if crumb else None
    listing_type = None
    if crumb:
        listing_type = "rent" if crumb.group(2).lower() in ("rent", "let") else "sale"
    region = _between(body, heading or "", ("Key Features", "Description", "Interested in"), 1200)
    price, qualifier, lt = parse_price(region, listing_type or type_hint)
    note = None
    # Commercial rents are quoted per year ("£97,782 per annum excl"). The
    # app shows rents per month, so convert, and keep the original wording.
    annual = re.search(r"£\s*([\d,]+)(?:\.\d\d)?\s*(?:per annum|p\.a\.|pa\b|per year)", region, re.I)
    if annual and (listing_type or lt) == "rent":
        yearly = int(annual.group(1).replace(",", ""))
        price, qualifier = round(yearly / 12), "pcm"
        note = f"£{yearly:,} per year"
    elif (category == "commercial" and (listing_type or lt) == "rent" and price
          and price > 5000 and not re.search(r"pcm|per month|per calendar month|p/m", region, re.I)):
        # Commercial rents without a stated period are annual figures on
        # BGC (e.g. "£80,000 + VAT"); no Manx unit lets for that a month.
        note = f"£{price:,} per year"
        price, qualifier = round(price / 12), "pcm"
    beds = re.search(r"\b(\d+)\s*Bed\b", region, re.I)
    baths = re.search(r"\b(\d+)\s*Bath\b", region, re.I)
    features = _between(body, "Key Features", ("Description",), 1500)
    if category == "commercial":
        # "Commercial Rent Office 4,548 Sq Ft" -> "office"
        kind = re.search(r"Commercial\s+(?:Buy|Rent|Let)\s+([A-Z][A-Za-z ]{2,20}?)\s+(?:\d|1/|View|£)", region)
        prop_type = kind.group(1).strip().lower() if kind else None
        if prop_type is None and re.search(r"\b(acres?|land at|building plot)\b", f"{heading} {region}", re.I):
            prop_type = "land"
    else:
        prop_type = parse_type(f"{features} {heading}")
    if prop_type == "land":
        category = "land"
    return {
        "category": category,
        "listing_type": listing_type or lt,
        "price": price, "qualifier": qualifier, "note": note,
        "bedrooms": int(beds.group(1)) if beds else None,
        "bathrooms": int(baths.group(1)) if baths else None,
        "status": _status_in(region),
        "prop_type": prop_type,
    }


def _grays(body, heading, type_hint):
    """graysestateagents.com (Rex): "£1,750,000 <address> 6 Bed 6 Bath
    9 Car ... Make an enquiry"."""
    low = body.lower()
    end = low.find("make an enquiry")
    if end < 0:
        end = min(len(body), 2500)
    # The header block: "Let £1,600 pcm £369 pw Barregarrow, ... 3 Bed 2 Bath".
    # Take the FIRST £ in the ~400 characters before "Make an enquiry", so the
    # monthly rent wins over the weekly one.
    start = low.find("£", max(0, end - 400), end)
    region = body[max(0, start - 40): end] if start >= 0 else body[max(0, end - 400): end]
    price, qualifier, lt = parse_price(region, type_hint)
    beds = re.search(r"\b(\d+)\s*Bed\b", region, re.I)
    baths = re.search(r"\b(\d+)\s*Bath\b", region, re.I)
    head_status = _status_in(region)
    if not head_status and re.search(r"\bLet\s+£", region):
        head_status = "Let Agreed"
    if not head_status and re.search(r"\bSold\s+£", region):
        head_status = "Sold"
    return {
        "price": price, "qualifier": qualifier, "listing_type": lt,
        "bedrooms": int(beds.group(1)) if beds else None,
        "bathrooms": int(baths.group(1)) if baths else None,
        "status": head_status,
    }


def _partners_from_slug(url):
    """/property/2-bed-semi-detached-house-to-rent-in-hailwood-avenue-douglas-im2/750096
    -> (2, "semi-detached house", "rent", "hailwood avenue douglas im2")"""
    slug = url.rstrip("/").split("/")[-2].lower()
    m = re.match(r"(?:(\d+)-bed-)?(?:(.*?)-)?(for-sale|to-rent|to-let)-in-(.*)$", slug)
    if not m:
        return None, None, None, None
    beds = int(m.group(1)) if m.group(1) else None
    kind = (m.group(2) or "").replace("-", " ")
    listing_type = "sale" if m.group(3) == "for-sale" else "rent"
    return beds, kind, listing_type, m.group(4).replace("-", " ")



# ---------------------------------------------------------------------------
# Garforth Gray (garforthgray.im) and Cowley Groves (cowleygroves.com)
# Both pages have tidy HTML, so read the elements rather than flattened text.
# ---------------------------------------------------------------------------

def _annual_to_pcm(price, text):
    """Commercial rents quoted per year -> per month, with a note."""
    if price and re.search(r"per annum|\bp\.?a\.?\b|per year|annual", text, re.I):
        return round(price / 12), f"£{price:,} per year"
    return price, None


def _garforth(html, url, agent):
    soup = BeautifulSoup(html, "html.parser")
    main = soup.select_one(".main-data") or soup
    h1 = main.find("h1")
    loc_el = main.select_one(".head-location")
    address = loc_el.get_text(" ", strip=True) if loc_el else ""
    stats = {}
    for hl in main.select(".highlights"):
        num = hl.select_one(".number")
        img = hl.find("img")
        icon = (img.get("data-src") or img.get("src") or "") if img else ""
        if num and num.get_text(strip=True).isdigit():
            for key in ("bed", "bath", "sofa"):
                if f"icon-{key}" in icon:
                    stats[key] = int(num.get_text(strip=True))
    price_el = main.select_one(".head-price")
    price_text = price_el.get_text(" ", strip=True) if price_el else ""
    header_text = main.get_text(" ", strip=True)[:1500]
    # The first thing in the header is the badge: "Let", "Sold",
    # "Offer Accepted", "Sold Subject to Contract"...
    first = main.get_text(" | ", strip=True).split(" | ", 1)[0]

    origin = agent.origin.get(url, "")
    commercial = "Commercial" in origin
    if "Rentals" in origin:
        hint = "rent"
    elif "Sale" in origin:
        hint = "sale"
    else:  # commercial: decide from the price wording
        hint = "rent" if re.search(r"per annum|\bp\.?a\.?\b|pcm|per month|per year|rent",
                                   price_text, re.I) else "sale"
    price, qualifier, listing_type = parse_price(price_text, hint)
    note = None
    if commercial and hint == "rent":
        price, note = _annual_to_pcm(price, price_text)

    district = None
    m = re.search(r"within the\s*(IM\d{1,2})\s*postcode", soup.get_text(" ", strip=True))
    if m:
        district = m.group(1)
    kf = soup.find(string=re.compile(r"Key features", re.I))
    features = kf.find_parent().find_next("ul").get_text(" ", strip=True) if kf and kf.find_parent() and kf.find_parent().find_next("ul") else ""
    title = h1.get_text(" ", strip=True) if h1 else ""
    summary = ""
    sm = soup.find(string=re.compile(r"^\s*Summary\s*$"))
    if sm and sm.find_parent():
        nxt = sm.find_parent().find_next("p")
        summary = nxt.get_text(" ", strip=True) if nxt else ""
    prop_type = parse_type(f"{title} {features[:600]}") or parse_type(summary[:500])
    category = "commercial" if commercial else (
        "land" if re.search(r"\b(building plot|plot of land|land)\b", title, re.I) and not stats.get("bed")
        else "residential")
    return {
        "address": address or title,
        "postcode": district,
        "price": price, "qualifier": qualifier, "listing_type": hint or listing_type,
        "bedrooms": None if commercial else stats.get("bed"),
        "bathrooms": stats.get("bath"),
        "prop_type": None if commercial else prop_type,
        "status": _status_in(header_text),
        "raw_status": first if len(first) < 40 else "",
        "category": category,
        "note": note,
    }


def _cowley(html, url):
    soup = BeautifulSoup(html, "html.parser")
    details = soup.select_one("#details") or soup
    status_el = details.select_one(".status")
    raw_status = status_el.get_text(" ", strip=True) if status_el else ""
    h2 = details.find("h2")
    full_address = h2.get_text(" ", strip=True) if h2 else ""
    price_el = details.select_one(".price")
    price_text = price_el.get_text(" ", strip=True) if price_el else ""

    # "Property Details" is label/value pairs: Location, Property Type, Bedrooms...
    facts = {}
    body = soup.get_text("\n", strip=True)
    i = body.find("Property Details")
    if i >= 0:
        lines = body[i:i + 1500].split("\n")[1:]
        for a, b in zip(lines, lines[1:]):
            if a in ("Location", "Property Type", "Bedrooms", "Bedroom", "Bathroom", "Bathrooms",
                     "Reception", "Furnished", "Tenure", "Size") and a not in facts:
                facts[a] = b

    rent = re.search(r"per calendar month|pcm|per month|per week|per annum|per year", price_text, re.I)
    hint = "rent" if rent else "sale"
    price, qualifier, _ = parse_price(price_text, hint)
    ptype_raw = facts.get("Property Type", "")
    commercial = any(w in ptype_raw.lower() for w in COMMERCIAL_WORDS) or \
        bool(re.search(r"\b(office|retail|shop|warehouse|industrial|unit|commercial|hotel|"
                       r"guest house|pub|restaurant|investment|premises|business)\b", ptype_raw, re.I))
    note = None
    if hint == "rent" and re.search(r"per annum|per year", price_text, re.I):
        price, note = _annual_to_pcm(price, price_text)
    if re.search(r"per week", price_text, re.I) and price:
        note = f"£{price:,} per week"
        price = round(price * 52 / 12)

    def num(key):
        v = facts.get(key, "")
        return int(v) if v.isdigit() else None

    postcode = parse_postcode(url, full_address)
    address = re.sub(r",?\s*IM\d{1,2}\s*\d[A-Z]{2}\s*$", "", full_address).strip(" ,")
    beds = num("Bedrooms") or num("Bedroom")
    land = not beds and bool(re.search(r"\b(land|plot|field|site)\b", f"{ptype_raw} {address}", re.I))
    return {
        "raw_status": raw_status,
        "address": address,
        "locality": facts.get("Location") or parse_place(address),
        "postcode": postcode,
        "price": price, "qualifier": qualifier, "listing_type": hint,
        "bedrooms": None if commercial else beds,
        "bathrooms": num("Bathroom") or num("Bathrooms"),
        "prop_type": None if commercial else (parse_type(ptype_raw) or parse_type(address)),
        "category": "commercial" if commercial else ("land" if land else "residential"),
        "note": note,
    }


def _chapman(html, url):
    """Chapman Chartered Surveyors (commercial). Page layout:
    h1 "Unit 7, Villa Marina Arcade – Douglas"; .contentsp has the price,
    tenure (Freehold = for sale, Leasehold = to let) and use classes."""
    soup = BeautifulSoup(html, "html.parser")
    art = soup.select_one("article") or soup
    h1 = art.find("h1")
    heading = h1.get_text(" ", strip=True) if h1 else ""
    name, _, town = heading.rpartition("–") if "–" in heading else (heading, "", "")
    name, town = name.strip(" -–"), town.strip(" -–")
    name = re.sub(r"\s*[–-]\s*investment sale\s*$", "", name, flags=re.I)
    box = art.select_one(".contentsp")
    box_text = box.get_text(" ", strip=True) if box else ""
    price_el = art.select_one(".contentsp .price") or art.select_one(".price")
    price_text = price_el.get_text(" ", strip=True) if price_el else ""
    uses = art.select_one(".contentsp .smalltxt")
    uses = uses.get_text(" ", strip=True) if uses else ""
    content = art.select_one(".property-content")
    content = content.get_text(" ", strip=True) if content else ""

    low = f"{box_text} {price_text}".lower()
    if "leasehold" in low or re.search(r"pcm|per annum|\bp\.?a\.?\b|per sq|to let|rent", price_text, re.I):
        hint = "rent"
    else:
        hint = "sale"
    note = None
    if re.search(r"per\s*sq\.?\s*f", price_text, re.I):
        # Quoted per square foot: no monthly figure to show.
        price, qualifier = None, "unknown"
        note = price_text.replace("Sq Ft", "sq ft")
    else:
        price, qualifier, _ = parse_price(price_text, hint)
        if hint == "rent":
            price, note = _annual_to_pcm(price, price_text)

    residential = uses.strip().lower() == "residential"
    address = f"{name}, {town}" if town and town.lower() not in name.lower() else name
    return {
        "address": address,
        "town": town,
        "price": price, "qualifier": qualifier, "listing_type": hint,
        "status": _status_in(f"{heading} {box_text} {content[:400]}"),
        "category": "residential" if residential else "commercial",
        "bedrooms": parse_int(content, BEDS) if residential else None,
        "uses": uses,
        "note": note,
    }


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
        # Chrystals index URL rules are authoritative for category.
        # Fall back to the address/header only if a listing comes from an
        # unclassified path. This must be assigned in the Chrystals branch
        # because the result dictionary below always expects ``category``.
        category = url_category or parse_category(f"{address} {head_blob}")
    elif agent.key == "mm":
        address = _clean_address(
            heading or title.split("|")[0].strip() or address_from_slug(url),
            agent.name,
        )
        locality = parse_place(address)
        postcode = parse_postcode(url, body)

        header_end = body.lower().find("book a viewing")
        header_region = body[:header_end if header_end > 0 else 1800]
        status = _manxmove_status(header_region)
        bedrooms, bathrooms = _manxmove_stats(header_region, body)
        prop_type = _manxmove_type(header_region)
        price, qualifier, listing_type = _manxmove_price(header_region, status)
        if price is None and qualifier == "unknown":
            price, qualifier, listing_type = parse_price(header_region, type_hint)
        category = _manxmove_category(prop_type, header_region, url)
    elif agent.key == "dw":
        address = _clean_address(
            heading or title.split("|")[0].strip() or address_from_slug(url),
            agent.name,
        )
        locality = parse_place(address)
        postcode = parse_postcode(url, body)

        # DeanWood puts the useful listing facts together before the viewing
        # controls. Keeping this window narrow avoids bedroom/type words from
        # the long description overwriting the header facts.
        header_end = body.lower().find("book a viewing")
        header_region = body[:header_end if header_end > 0 else 2500]
        status = _deanwood_status(header_region)
        bedrooms = parse_int(header_region, BEDS)
        bathrooms = parse_int(header_region, BATHS)
        prop_type = _deanwood_type(header_region)
        price, qualifier, listing_type = _deanwood_price(
            header_region, status
        )
        if price is None and qualifier == "unknown":
            price, qualifier, listing_type = _deanwood_price(body[:5000], status)
        category = _deanwood_category(prop_type, header_region, body)
    elif agent.key == "bgc":
        address = _clean_address(heading or title.split("–")[0].strip(), agent.name)
        locality = parse_place(address)
        # Only the listing header: the footer carries the office postcodes.
        postcode = parse_postcode(url, _between(body, heading or "", ("Key Features",), 800))
        f = _bgc(body, heading, title, type_hint)
        price, qualifier = f["price"], f["qualifier"]
        type_hint = type_hint or f["listing_type"]
        listing_type = f["listing_type"]
        bedrooms, bathrooms = f["bedrooms"], f["bathrooms"]
        prop_type = f["prop_type"]
        status = f["status"]
        category = f["category"] or url_category or parse_category(address)
        price_note = f["note"]
    elif agent.key == "grays":
        # "Slieu Lewaigue, Isle Of Man, IM7 1" -> "Slieu Lewaigue"
        address = re.sub(r",?\s*Isle Of Man.*$", "", heading or "", flags=re.I).strip() \
            or address_from_slug(url)
        locality = parse_place(f"{address} {title}")
        # The heading may carry a full postcode; the footer has the office's.
        postcode = parse_postcode(url, heading or "")
        f = _grays(body, heading, type_hint)
        price, qualifier = f["price"], f["qualifier"]
        bedrooms, bathrooms = f["bedrooms"], f["bathrooms"]
        prop_type = parse_type(f"{title} {body[:4000]}")
        status = f["status"]
        category = url_category or parse_category(address)
        if status == "Sold":
            # Grays' list also shows completed sales ("Sold £365,000");
            # those are no longer for sale.
            return None
    elif agent.key == "gg":
        if "/rentals/" in url:
            slug = f"rent-{slug}"  # a rental and a sale can share a street slug
        f = _garforth(res.text, url, agent)
        # "Let" / "Sold" badges mean it's gone; "Sold Subject to Contract"
        # and "Offer Accepted" stay, like the other agents' Sold STC.
        if f["raw_status"].strip().lower() in ("let", "sold", "completed", "withdrawn") and not f["status"]:
            return None
        address = _clean_address(f["address"], agent.name)
        locality = parse_place(address)
        postcode = f["postcode"]
        price, qualifier = f["price"], f["qualifier"]
        type_hint = f["listing_type"]
        bedrooms, bathrooms = f["bedrooms"], f["bathrooms"]
        prop_type = f["prop_type"]
        status = f["status"]
        category = f["category"]
        price_note = f["note"]
    elif agent.key == "cg":
        f = _cowley(res.text, url)
        raw = f["raw_status"].lower()
        # Completed sales/lets stay on the site (and in its sitemap) for a
        # while; they're no longer available, so leave them out.
        if raw in ("sold", "let", "completed", "withdrawn") or raw.startswith("sold ") and "stc" not in raw \
                and "subject" not in raw:
            return None
        address = _clean_address(f["address"], agent.name)
        locality = f["locality"]
        postcode = f["postcode"]
        price, qualifier = f["price"], f["qualifier"]
        type_hint = f["listing_type"]
        bedrooms, bathrooms = f["bedrooms"], f["bathrooms"]
        prop_type = f["prop_type"]
        status = _status_in(f["raw_status"])
        category = f["category"]
        price_note = f["note"]
    elif agent.key == "chp":
        f = _chapman(res.text, url)
        address = _clean_address(f["address"], agent.name)
        locality = parse_place(f"{address} {f['town']}")
        postcode = None
        price, qualifier = f["price"], f["qualifier"]
        type_hint = f["listing_type"]
        bedrooms, bathrooms = f["bedrooms"], None
        prop_type = None
        status = f["status"]
        category = f["category"]
        price_note = f["note"]
    elif agent.key == "pre":
        slug_beds, slug_kind, slug_type, slug_place = _partners_from_slug(url)
        type_hint = type_hint or slug_type
        # The page heading is the price; the title has the address:
        # "4 bed detached house for sale in Mannin Veen, Lheaney Road, Ramsey, IM8 2JF | Partners"
        tm = re.search(r"\b(?:for sale|to rent|to let) in (.+?)\s*(?:\||$)", title, re.I)
        address = _clean_address(tm.group(1) if tm else (slug_place or "").title(), agent.name)
        address = re.sub(r",?\s*IM\d{1,2}(?:\s*\d[A-Z]{2})?\s*$", "", address).strip(" ,")
        locality = parse_place(f"{address} {slug_place or ''}")
        postcode = parse_postcode(url, f"{title} {slug_place or ''}")
        if price is None:
            price, qualifier, listing_type = parse_price(body[:5000], type_hint)
        bedrooms = slug_beds or parse_int(head_blob, BEDS)
        bathrooms = parse_int(body[:5000], BATHS)
        kind = (slug_kind or "").replace("semi detached", "semi-detached") \
            .replace("end of terrace", "end-of-terrace")
        prop_type = parse_type(kind) or parse_type(f"{address} {head_blob}")
        status = _status_in(f"{heading} {body[:2500]}")
        origin = agent.origin.get(url, "")
        commercial = "commercial" in origin or (slug_kind and any(w in slug_kind for w in COMMERCIAL_WORDS))
        if slug_kind and re.search(r"\b(plot|land)\b", slug_kind):
            category, prop_type, bedrooms = "land", "land", None
        else:
            category = "commercial" if commercial else (url_category or "residential")
        if commercial and prop_type in ("house", None):
            prop_type = None
    else:
        address = _clean_address(heading or title.split("|")[0].strip() or address_from_slug(url), agent.name)
        locality = parse_place(address)
        postcode = parse_postcode(url, body)
        bedrooms = parse_int(head_blob, BEDS) or parse_int(body, BEDS)
        bathrooms = parse_int(head_blob, BATHS) or parse_int(body, BATHS)
        prop_type = parse_type(f"{address} {head_blob}")
        status = None
        category = url_category or parse_category(address)

    listing_type = type_hint or listing_type

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
    if locals().get("price_note"):
        item["priceNote"] = price_note
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
