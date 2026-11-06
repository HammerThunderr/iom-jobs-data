"""
scripts/scrape_events.py — Isle of Man events, straight from the organisers.

Replaces the old whatsoniom.im scraper (a copy of other sites, with most
dates missing). Every event now comes from the venue or organiser itself:

  Source                     How it is read
  -------------------------  --------------------------------------------------
  Villa Marina & Gaiety      Ticketsolve public feed  villagaiety.ticketsolve.com/shows.xml
  Manx National Heritage     manxnationalheritage.im/whats-on/ (+ each event page)
  Visit Isle of Man          visitisleofman.com/whats-on?p=N  (official tourism)
  Erin Arts Centre           The Events Calendar REST API  /wp-json/tribe/events/v1/events
  (Centenary Centre, Peel — off: their site refuses automated visitors)

These are the same sites the Isle of Man Government's own "Event Directory"
page points people to.

Being polite:
  - robots.txt is checked for every URL before it is fetched (and Crawl-delay
    is honoured — Visit Isle of Man asks for 2 seconds).
  - A clear User-Agent says who we are.
  - Runs a few times a day, not every 30 minutes.

Safety:
  - If one source fails, its events from the previous run are kept.
  - If the total drops by more than 60% compared with the last run, the file
    is NOT overwritten — better yesterday's events than a half-empty list.

Output (docs/events.json) keeps every field the older app versions read, so
installed apps keep working, and adds new ones (id, category, area,
occurrences, bookingUrl, sourceKey...).
"""

from __future__ import annotations

import html as html_lib
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

OUTPUT = os.environ.get("OUTPUT_PATH", "docs/events.json")

USER_AGENT = "ManxOneBot/1.0 (+https://manxone.hammerlabs.app; Isle of Man events listing)"
ROBOTS_AGENT = "ManxOneBot"
TIMEOUT = 30
MIN_DELAY = 1.0            # seconds between requests to the same host
MAX_DESC = 900             # characters kept from each description
MAX_OCCURRENCES = 60

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": USER_AGENT,
    "Accept-Language": "en-GB,en;q=0.9",
})

TODAY = datetime.now(timezone.utc).date()

# Higher number wins when the same event appears in two sources.
SOURCE_PRIORITY = {
    "villagaiety": 50,
    "mnh": 50,
    "erin": 50,
    "centenary": 50,
    "visitiom": 10,       # the tourism calendar repeats many venue listings
}

# ─────────────────────────────────────────────────────────────
# Polite fetching
# ─────────────────────────────────────────────────────────────

_robots: dict[str, RobotFileParser | None] = {}
_last_hit: dict[str, float] = {}


def _robots_for(url: str) -> RobotFileParser | None:
    parts = urlparse(url)
    root = f"{parts.scheme}://{parts.netloc}"
    if root not in _robots:
        rp = RobotFileParser()
        try:
            r = SESSION.get(root + "/robots.txt", timeout=TIMEOUT)
            if r.status_code >= 400:
                rp = None          # no robots.txt = no restrictions
            else:
                rp.parse(r.text.splitlines())
        except requests.RequestException:
            rp = None
        _robots[root] = rp
    return _robots[root]


def allowed(url: str) -> bool:
    rp = _robots_for(url)
    return True if rp is None else rp.can_fetch(ROBOTS_AGENT, url)


def _delay_for(url: str) -> float:
    rp = _robots_for(url)
    delay = None
    if rp is not None:
        delay = rp.crawl_delay(ROBOTS_AGENT) or rp.crawl_delay("*")
    return max(MIN_DELAY, float(delay or 0))


def get(url: str, **kw) -> requests.Response:
    """GET that respects robots.txt and a per-host delay. Raises on failure."""
    if not allowed(url):
        raise PermissionError(f"robots.txt disallows {url}")
    host = urlparse(url).netloc
    wait = _delay_for(url) - (time.time() - _last_hit.get(host, 0))
    if wait > 0:
        time.sleep(wait)
    _last_hit[host] = time.time()
    r = SESSION.get(url, timeout=TIMEOUT, **kw)
    r.raise_for_status()
    return r


# ─────────────────────────────────────────────────────────────
# Small helpers
# ─────────────────────────────────────────────────────────────

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def clean(s) -> str:
    if not s:
        return ""
    s = html_lib.unescape(str(s))
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def html_to_text(s: str, limit: int = MAX_DESC) -> str:
    if not s:
        return ""
    text = BeautifulSoup(s, "html.parser").get_text(" ")
    text = clean(text)
    # Boilerplate some sites put first.
    text = re.sub(r"^(?:@\s*|show description\s*:?\s*|description\s*:\s*)+", "", text, flags=re.I)
    if len(text) > limit:
        cut = text[:limit].rsplit(" ", 1)[0]
        text = cut.rstrip(",.;:") + "…"
    return text


def parse_dmy(s: str) -> date | None:
    """'14/11/2026' -> date."""
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", s or "")
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def parse_day_month_year(s: str) -> date | None:
    """'1 Sept  2026', '7 March 2027', '05 Dec 2026' -> date."""
    m = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?\s+(\d{4})", s or "")
    if not m:
        return None
    mon = MONTHS.get(m.group(2)[:3].lower())
    if not mon:
        return None
    try:
        return date(int(m.group(3)), mon, int(m.group(1)))
    except ValueError:
        return None


def to_24h(token: str) -> str | None:
    """'7pm' -> '19:00', '9.30am' -> '09:30', '12 noon' -> '12:00'."""
    t = token.strip().lower().replace(" ", "")
    if t in ("noon", "12noon", "midday"):
        return "12:00"
    m = re.fullmatch(r"(\d{1,2})(?:[.:](\d{2}))?(am|pm)", t)
    if not m:
        m2 = re.fullmatch(r"(\d{1,2})[.:](\d{2})", t)
        if m2 and int(m2.group(1)) < 24:
            return f"{int(m2.group(1)):02d}:{m2.group(2)}"
        return None
    h, mins, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    if h > 12 or mins > 59:
        return None
    if ap == "pm" and h != 12:
        h += 12
    if ap == "am" and h == 12:
        h = 0
    return f"{h:02d}:{mins:02d}"


def normalise_time_text(s: str) -> str:
    """Turn '9.30am - 4.30pm' into '09:30 – 16:30' and '7pm' into '19:00'.
    Anything more complicated ('11am or 1pm') is kept as written."""
    s = clean(s)
    if not s:
        return ""
    s2 = re.sub(r"^(open|from|between)\s+", "", s, flags=re.I)
    s2 = re.sub(r"\(.*?\)", "", s2).strip()
    parts = re.split(r"\s*(?:-|–|—|to|and)\s*", s2)
    if 1 <= len(parts) <= 2:
        conv = [to_24h(p) for p in parts]
        if all(conv):
            return " – ".join(conv)
    return s


def first_time(s: str) -> str:
    m = re.search(r"\d{1,2}(?:[.:]\d{2})?\s*(?:am|pm)|\b\d{1,2}:\d{2}\b", s or "", re.I)
    return (to_24h(m.group(0)) or "") if m else ""


def norm_title(t: str) -> str:
    t = clean(t).lower()
    t = re.sub(r"[’'`]", "", t)
    t = re.sub(r"\b(the|presents?|live|tour|20\d\d)\b", " ", t)
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60]


# ── Area (town) from venue / address text ──

# Named venues are checked first: some listings have messy addresses
# ("House Of Manannan, Douglas, Peel"), and the venue is the reliable part.
LANDMARKS = [
    ("Douglas", ["villa marina", "gaiety", "manx museum", "broadway cinema", "noble's park",
                 "nobles park", "national sports centre", "summerland", "sea terminal"]),
    ("Peel", ["house of manannan", "centenary centre", "peel castle", "tynwald hill", "st john's", "st johns"]),
    ("Ramsey", ["the grove", "mooragh"]),
    ("Castletown", ["castle rushen", "old grammar school", "nautical museum", "rushen abbey", "1 market square"]),
    ("Port Erin", ["erin arts", "cregneash", "the sound visitor"]),
    ("Laxey", ["lady isabella", "laxey wheel", "great laxey", "snaefell"]),
]
TOWNS = [
    ("Douglas", ["douglas", "onchan"]),
    ("Peel", ["peel", "st johns", "foxdale"]),
    ("Ramsey", ["ramsey", "andreas", "jurby", "bride", "sulby"]),
    ("Castletown", ["castletown", "ballasalla", "derbyhaven", "ronaldsway"]),
    ("Port Erin", ["port erin", "port st mary", "colby"]),
    ("Laxey", ["laxey"]),
    ("Kirk Michael", ["kirk michael", "ballaugh"]),
    ("Islandwide", ["islandwide", "island wide", "various venues", "all over the island"]),
]


def detect_area(*texts: str) -> str:
    blob = " ".join(t for t in texts if t).lower()
    for town, keys in LANDMARKS:
        if any(k in blob for k in keys):
            return town
    # Otherwise the town named first in the text.
    best, best_pos = "", len(blob) + 1
    for town, keys in TOWNS:
        for k in keys:
            pos = blob.find(k)
            if 0 <= pos < best_pos:
                best, best_pos = town, pos
    if best:
        return best
    if "islandwide" in blob or "island wide" in blob or "various" in blob:
        return "Islandwide"
    return ""


# ── Categories ──
# One primary category per event (for the filter chips) plus up to three tags.

CATEGORIES = [
    "Festive", "Family & Kids", "Music", "Theatre & Comedy", "Film",
    "Arts & Workshops", "Heritage", "Talks & Learning", "Sport",
    "Markets & Fairs", "Community", "Other",
]

KEYWORDS = [
    ("Festive", r"christmas|xmas|santa|father christmas|festive|panto|pantomime|grotto|nativity|carol|hogmanay|new year|winterfest|tinsel|elf\b|reindeer"),
    ("Family & Kids", r"\bkids?\b|children|family|families|little makers|toddler|peppa|paw patrol|half.?term|junior|youth|teen|baby|storytime|lego"),
    ("Film", r"cinema|\bfilm\b|screening|movie|on screen|nt live|event cinema"),
    ("Music", r"music|concert|\bgig\b|orchestra|choir|\bband\b|tribute|singer|jazz|\bfolk\b|blues|album|symphony|recital|wurlitzer|\bdj\b"),
    ("Theatre & Comedy", r"theatre|panto|drama|\bplay\b|musical|comedy|comedian|stand.?up|ballet|\bdance\b|dancing|magic|opera|players|stage"),
    ("Talks & Learning", r"\btalk\b|lecture|speaker|learning|seminar|course|creative sessions|in conversation|q&a|symposium"),
    ("Arts & Workshops", r"workshop|craft|\bart\b|arts\b|exhibition|gallery|photograph|painting|pottery|sculpt|makers|weaving"),
    ("Heritage", r"heritage|museum|castle|history|historic|archaeolog|victorian|viking|manx national heritage|tour of"),
    ("Sport", r"sport|\brace\b|racing|\brun\b|marathon|boxing|powerlifting|orienteering|football|rugby|cycling|motorsport|\btt\b|swim|golf|darts|tennis|hockey|athletic|triathlon|walk(?:ing)? festival|parkrun"),
    ("Markets & Fairs", r"market|\bfair\b|fayre|food festival|craft fair|car boot|agricultural show"),
    ("Community", r"charity|fundrais|community|volunteer|\bquiz\b|coffee morning|open day|hospice|rotary"),
]

SOURCE_CATEGORY_MAP = {
    # Ticketsolve event_category
    "music": "Music", "cinema": "Film", "comedy": "Theatre & Comedy", "dance": "Theatre & Comedy",
    "drama": "Theatre & Comedy", "musical theatre": "Theatre & Comedy", "magic": "Theatre & Comedy",
    "pantomime": "Festive", "children": "Family & Kids", "speaker": "Talks & Learning",
    "boxing": "Sport",
    # Manx National Heritage badges
    "christmas": "Festive", "exhibitions": "Arts & Workshops", "for families": "Family & Kids",
    "workshops": "Arts & Workshops", "talks and lectures": "Talks & Learning",
    "guided tours": "Heritage", "community event": "Community", "special event": "Heritage",
    "half term event": "Family & Kids", "drop in": "Family & Kids",
}


def categorise(source_cat: str, title: str, desc: str = "", default: str = "Other") -> tuple[str, list[str]]:
    """The organiser's own category first, then keywords in the TITLE.
    The description is only used when the title says nothing — descriptions
    mention all sorts ("...in time for Christmas", "...a run through the
    history of") and gave too many wrong categories."""
    tags: list[str] = []
    for part in re.split(r"[,/|]", source_cat or ""):
        sc = SOURCE_CATEGORY_MAP.get(clean(part).lower())
        if sc and sc not in tags:
            tags.append(sc)
    title_l = title.lower()
    for cat, rx in KEYWORDS:
        if cat not in tags and re.search(rx, title_l):
            tags.append(cat)
    if not tags and desc:
        first = desc[:200].lower()
        for cat, rx in KEYWORDS:
            if cat != "Festive" and cat not in tags and re.search(rx, first):
                tags.append(cat)
                if len(tags) == 2:
                    break
    if not tags:
        tags = [default]
    # Festive wins as the primary category in season — that's what people browse for.
    if "Festive" in tags:
        tags.remove("Festive")
        tags.insert(0, "Festive")
    return tags[0], tags[:3]


def make_event(*, key: str, source_key: str, source_name: str, title: str,
               occurrences: list[dict], venue: str = "", address: str = "",
               description: str = "", image: str = "", price: str = "",
               url: str = "", booking_url: str = "", source_cat: str = "",
               default_cat: str = "Other", time_text: str = "",
               date_range: tuple[date, date] | None = None) -> dict | None:
    """Build one event in the output format. `occurrences` is a list of
    {"date": date, "time": "19:30"|"" , "soldOut": bool}. For long-running
    things (exhibitions) pass date_range instead."""
    title = clean(title)
    if not title:
        return None

    occs = sorted(
        (o for o in occurrences if o.get("date")),
        key=lambda o: (o["date"], o.get("time") or ""))
    if date_range:
        start, end = date_range
    elif occs:
        start, end = occs[0]["date"], occs[-1]["date"]
    else:
        return None
    if end < start:
        end = start
    if end < TODAY:
        return None                         # finished

    upcoming = [o for o in occs if o["date"] >= TODAY]
    times = sorted({o["time"] for o in upcoming if o.get("time")})
    if time_text:
        shown_time = normalise_time_text(time_text)
    elif len(times) == 1:
        shown_time = times[0]
    else:
        shown_time = ""
    category, tags = categorise(source_cat, title, description, default_cat)
    sold_out = bool(upcoming) and all(o.get("soldOut") for o in upcoming)

    return {
        # ── fields older app versions read ──
        "title": title,
        "venue": clean(venue),
        # First upcoming performance; for long runs (exhibitions) the real start.
        "startDate": (upcoming[0]["date"] if upcoming and not date_range else start).isoformat(),
        "endDate": end.isoformat(),
        "isTbc": False,
        "duration": float((end - start).days),
        "tags": tags,
        "source": source_name,
        "recurring": len({o["date"] for o in occs}) > 1 or bool(date_range and end > start),
        "description": description,
        "imageUrl": image or "",
        "time": shown_time,
        "price": clean(price),
        "url": url or booking_url or "",
        # ── new fields ──
        "id": f"{source_key}-{key}",
        "sourceKey": source_key,
        "category": category,
        "area": detect_area(venue, address, title),
        "address": clean(address),
        "bookingUrl": booking_url or "",
        "soldOut": sold_out,
        "occurrences": [
            {"date": o["date"].isoformat(), "time": o.get("time") or "",
             **({"soldOut": True} if o.get("soldOut") else {})}
            for o in upcoming[:MAX_OCCURRENCES]
        ],
    }


# ─────────────────────────────────────────────────────────────
# Source 1 — Villa Marina & Gaiety Theatre (Ticketsolve feed)
# ─────────────────────────────────────────────────────────────

SKIP_TITLES = re.compile(r"private hire|gift voucher|membership|test event|donation", re.I)


def source_villagaiety() -> list[dict]:
    r = get("https://villagaiety.ticketsolve.com/shows.xml")
    root = ET.fromstring(r.content)
    out = []
    for venue in root.findall("venue"):
        venue_name = clean(venue.findtext("name"))
        for show in venue.findall("./shows/show"):
            title = clean(show.findtext("name"))
            if not title or SKIP_TITLES.search(title):
                continue
            occs = []
            for ev in show.findall("./events/event"):
                name = clean(ev.findtext("name"))
                # The event name carries the local date/time: "05 Dec 2026 - 19:00 @ ..."
                m = re.match(r"(\d{1,2} \w{3} \d{4}) - (\d{1,2}:\d{2})", name)
                d = parse_day_month_year(m.group(1)) if m else None
                t = m.group(2) if m else ""
                if not d:
                    iso = ev.findtext("date_time_iso") or ""
                    try:
                        dt = datetime.fromisoformat(iso.strip())
                        d, t = dt.date(), dt.strftime("%H:%M")
                    except ValueError:
                        continue
                status = clean(ev.findtext("status")).lower()
                occs.append({"date": d, "time": t, "soldOut": "sold out" in status})
            if not occs:
                continue
            image = ""
            imgs = show.findall("./images/image")
            imgs.sort(key=lambda i: -int(i.get("priority") or 0))
            for img in imgs:
                for u in img.findall("url"):
                    if u.get("size") == "large" and u.text:
                        image = u.text.strip()
                        break
                if image:
                    break
            show_url = clean(show.findtext("url"))
            ev_obj = make_event(
                key=show.get("id") or slug(title),
                source_key="villagaiety",
                source_name="Villa Marina & Gaiety",
                title=title,
                occurrences=occs,
                venue=venue_name,
                address="Douglas",
                description=html_to_text(show.findtext("description") or ""),
                image=image,
                url=show_url,
                booking_url=show_url,
                source_cat=show.findtext("event_category") or "",
            )
            if ev_obj:
                out.append(ev_obj)
    return out


# ─────────────────────────────────────────────────────────────
# Source 2 — Manx National Heritage
# ─────────────────────────────────────────────────────────────

MNH = "https://manxnationalheritage.im"


def source_mnh() -> list[dict]:
    cards = []
    for page in range(1, 11):
        url = f"{MNH}/whats-on/" if page == 1 else f"{MNH}/whats-on/page/{page}/"
        try:
            r = get(url)
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                break
            raise
        soup = BeautifulSoup(r.text, "html.parser")
        items = [i for i in soup.select(".item") if i.select_one('a[href*="/whats-on/detail/"]')]
        if not items:
            break
        for it in items:
            a = it.select_one('a[href*="/whats-on/detail/"]')
            img = it.select_one("img")
            cards.append({
                "url": a["href"],
                "title": clean(it.select_one("h2").get_text() if it.select_one("h2") else ""),
                "dates": clean(it.select_one(".article-date").get_text() if it.select_one(".article-date") else ""),
                "badge": clean(it.select_one(".badge").get_text() if it.select_one(".badge") else ""),
                "summary": clean(it.select_one(".summary").get_text() if it.select_one(".summary") else ""),
                "image": img.get("src", "") if img else "",
            })

    out = []
    for c in cards:
        attrs: dict[str, str] = {}
        booking = ""
        description = c["summary"]
        image = c["image"]
        try:
            d = BeautifulSoup(get(c["url"]).text, "html.parser")
            for li in d.select("ul.attr-list-simple li"):
                k = clean(li.find("em").get_text() if li.find("em") else "").lower()
                v = clean(li.find("strong").get_text() if li.find("strong") else "")
                if k:
                    attrs[k] = v
            btn = d.select_one("a.button-link")
            if btn and btn.get("href"):
                booking = btn["href"]
            body = d.select_one(".full-width-text .text-content")
            if body:
                h2 = body.find("h2")
                if h2:
                    h2.decompose()
                description = html_to_text(str(body)) or description
            bg = d.select_one(".attributes-intro-block .image")
            if bg and "url(" in (bg.get("style") or ""):
                image = re.search(r"url\('?([^')]+)", bg["style"]).group(1)
        except Exception as e:                       # one bad page is not fatal
            print(f"    ! MNH detail failed {c['url']}: {e}")

        date_text = attrs.get("date") or c["dates"]
        found = re.findall(r"\d{1,2}/\d{1,2}/\d{4}", date_text)
        start = parse_dmy(found[0]) if found else parse_day_month_year(date_text)
        end = parse_dmy(found[-1]) if len(found) > 1 else None
        if not start:
            # e.g. "Entries close midnight 7 March 2027." — show it until then.
            close = parse_day_month_year(date_text)
            if not close:
                continue
            start, end = TODAY, close
        time_text = attrs.get("time", "")
        price = attrs.get("price", "")
        # Some pages put opening times in the Price row.
        if price and re.search(r"\d(am|pm)", price, re.I) and "£" not in price and not time_text:
            time_text, price = price, ""
        long_running = end is not None and end > start
        ev = make_event(
            key=slug(urlparse(c["url"]).path.rstrip("/").split("/")[-1]),
            source_key="mnh",
            source_name="Manx National Heritage",
            title=c["title"],
            occurrences=[] if long_running else [{"date": start, "time": first_time(time_text)}],
            date_range=(start, end) if long_running else None,
            venue=attrs.get("location", ""),
            address=attrs.get("location", ""),
            description=description,
            image=image,
            price=price,
            url=c["url"],
            booking_url=booking,
            source_cat=c["badge"],
            default_cat="Heritage",
            time_text=time_text,
        )
        if ev:
            out.append(ev)
    return out


# ─────────────────────────────────────────────────────────────
# Source 3 — Visit Isle of Man (official tourism calendar)
# ─────────────────────────────────────────────────────────────

VIOM = "https://www.visitisleofman.com"

VIOM_CAT = {
    "cat_christmas": "Festive", "cat_music": "Music", "cat_photog": "Arts & Workshops",
    "cat_sport": "Sport", "cat_sports": "Sport", "cat_motorsport": "Sport",
    "cat_family": "Family & Kids", "cat_arts": "Arts & Workshops", "cat_heritage": "Heritage",
    "cat_food": "Markets & Fairs", "cat_festival": "Community",
}


def source_visitiom() -> list[dict]:
    out = []
    seen = set()
    for page in range(1, 16):
        url = f"{VIOM}/whats-on" if page == 1 else f"{VIOM}/whats-on?p={page}"
        soup = BeautifulSoup(get(url).text, "html.parser")
        items = soup.select('li[class*="Item"]')
        items = [i for i in items if i.select_one("a.ProductDetail")]
        new = 0
        for it in items:
            a = it.select_one(".ProductName a.ProductDetail") or it.select_one("a.ProductDetail")
            href = urljoin(VIOM, a.get("href", ""))
            if href in seen:
                continue
            seen.add(href)
            new += 1
            title = clean(a.get_text()) or clean(it.select_one("img").get("alt", "") if it.select_one("img") else "")
            dfrom = parse_day_month_year(it.select_one(".datefrom").get_text() if it.select_one(".datefrom") else "")
            dto = parse_day_month_year(it.select_one(".dateto").get_text() if it.select_one(".dateto") else "")
            if not dfrom:
                single = it.select_one("dd.dates")
                dfrom = parse_day_month_year(single.get_text() if single else "")
            if not dfrom:
                continue
            img = it.select_one("img[data-lazy-src]") or it.select_one("img")
            image = (img.get("data-lazy-src") or img.get("src") or "") if img else ""
            if "lazyloadplaceholder" in image:
                image = ""
            address = clean(it.select_one("address").get_text() if it.select_one("address") else "")
            desc = clean(it.select_one(".desc").get_text() if it.select_one(".desc") else "")
            cls = " ".join(it.get("class", []))
            vcat = next((v for k, v in VIOM_CAT.items() if k in cls), "")
            pid = re.search(r"-p(\d+)$", href)
            long_running = dto is not None and dto > dfrom
            ev = make_event(
                key=pid.group(1) if pid else slug(title),
                source_key="visitiom",
                source_name="Visit Isle of Man",
                title=title,
                occurrences=[] if long_running else [{"date": dfrom, "time": ""}],
                date_range=(dfrom, dto) if long_running else None,
                venue=address.split(",")[0] if address else "",
                address=address,
                description=desc,
                image=image,
                url=href,
            )
            if ev:
                if vcat and vcat not in ev["tags"]:
                    ev["tags"] = ([vcat] + ev["tags"])[:3]
                    if ev["category"] == "Other":
                        ev["category"] = vcat
                out.append(ev)
        if not items or new == 0:
            break
    return out


# ─────────────────────────────────────────────────────────────
# Source 4 — Erin Arts Centre (The Events Calendar REST API)
# ─────────────────────────────────────────────────────────────

def source_erin() -> list[dict]:
    out = []
    url = "https://www.erinartscentre.com/wp-json/tribe/events/v1/events?per_page=50&start_date=now"
    pages = 0
    while url and pages < 10:
        pages += 1
        data = get(url).json()
        for e in data.get("events", []):
            try:
                s = datetime.strptime(e["start_date"], "%Y-%m-%d %H:%M:%S")
                en = datetime.strptime(e["end_date"], "%Y-%m-%d %H:%M:%S")
            except (KeyError, ValueError):
                continue
            all_day = bool(e.get("all_day"))
            t = "" if all_day else s.strftime("%H:%M")
            if not all_day and en > s and en.date() == s.date():
                t = f"{s.strftime('%H:%M')} – {en.strftime('%H:%M')}"
            venue = e.get("venue") or {}
            if isinstance(venue, list):
                venue = venue[0] if venue else {}
            image = (e.get("image") or {}).get("url", "") if isinstance(e.get("image"), dict) else ""
            cats = ", ".join(c.get("name", "") for c in e.get("categories", []) if isinstance(c, dict))
            multi_day = en.date() > s.date()
            ev = make_event(
                key=str(e.get("id") or slug(e.get("title", ""))),
                source_key="erin",
                source_name="Erin Arts Centre",
                title=e.get("title", ""),
                occurrences=[] if multi_day else [{"date": s.date(), "time": t}],
                date_range=(s.date(), en.date()) if multi_day else None,
                venue=clean(venue.get("venue")) or "Erin Arts Centre",
                address=" ".join(filter(None, [clean(venue.get("address")), clean(venue.get("city")) or "Port Erin"])),
                description=html_to_text(e.get("description", "")),
                image=image,
                price=e.get("cost", ""),
                url=e.get("url", ""),
                booking_url=e.get("website", "") or "",
                source_cat=cats,
                time_text=t if " – " in t else "",
            )
            if ev:
                out.append(ev)
        url = data.get("next_rest_url")
    return out


# ─────────────────────────────────────────────────────────────
# Source 5 — Centenary Centre, Peel (WordPress list + schema.org Event)
# ─────────────────────────────────────────────────────────────

CENT = "https://centenarycentre.com"
CENT_MAX_PAGES_FETCHED = 90


def _jsonld_events(html: str) -> list[dict]:
    found = []
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S):
        raw = m.group(1).strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # MEC sometimes leaves stray control characters in descriptions.
            try:
                data = json.loads(re.sub(r"[\x00-\x1f]", " ", raw))
            except json.JSONDecodeError:
                continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                if node.get("@type") == "Event":
                    found.append(node)
                stack.extend(v for v in node.values() if isinstance(v, (dict, list)))
            elif isinstance(node, list):
                stack.extend(node)
    return found


def source_centenary() -> list[dict]:
    # Their API refuses requests from servers, so read the public events
    # listing page instead and visit each event page it links to.
    listing = get(f"{CENT}/events/").text
    links = []
    for m in re.finditer(r'href="(https://(?:www\.)?centenarycentre\.com/events/[^"#?]+/)"', listing):
        u = m.group(1).replace("://www.", "://")
        if u.rstrip("/").endswith("/events") or "/feed" in u or u in links:
            continue
        links.append(u)
    posts = [{"link": u, "id": slug(urlparse(u).path.rstrip("/").split("/")[-1]), "title": {}} for u in links]

    out = []
    for p in posts[:CENT_MAX_PAGES_FETCHED]:
        link = p.get("link")
        if not link:
            continue
        try:
            html = get(link).text
        except Exception as e:
            print(f"    ! Centenary page failed {link}: {e}")
            continue
        evs = _jsonld_events(html)
        if not evs:
            continue
        e = evs[0]
        sd = (e.get("startDate") or "")[:19]
        try:
            s = datetime.fromisoformat(sd) if "T" in sd else datetime.fromisoformat(sd + "T00:00:00")
        except ValueError:
            continue
        ed = (e.get("endDate") or "")[:10]
        try:
            end_d = date.fromisoformat(ed) if ed else s.date()
        except ValueError:
            end_d = s.date()
        offers = e.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        image = e.get("image") or ""
        if isinstance(image, list):
            image = image[0] if image else ""
        if isinstance(image, dict):
            image = image.get("url", "")
        if not image:
            og = re.search(r'<meta property="og:image" content="([^"]+)"', html)
            image = og.group(1) if og else ""
        title = clean(p.get("title", {}).get("rendered", "")) or clean(e.get("name", ""))
        t = "" if s.hour == 0 and s.minute == 0 else s.strftime("%H:%M")
        multi_day = end_d > s.date()
        ev = make_event(
            key=str(p.get("id")),
            source_key="centenary",
            source_name="Centenary Centre",
            title=title,
            occurrences=[] if multi_day else [{"date": s.date(), "time": t}],
            date_range=(s.date(), end_d) if multi_day else None,
            venue="Centenary Centre",
            address="Atholl Street, Peel",
            description=html_to_text(e.get("description", "")),
            image=image if isinstance(image, str) else "",
            price=str(offers.get("price", "") or ""),
            url=link,
            booking_url=str(offers.get("url", "") or ""),
        )
        if ev:
            out.append(ev)
    return out


# ─────────────────────────────────────────────────────────────
# Merging
# ─────────────────────────────────────────────────────────────

def merge_same_source(events: list[dict]) -> list[dict]:
    """Some sources list each performance as its own entry (e.g. a panto
    with eight dates). Fold them into one event with several occurrences."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for e in events:
        groups[(e["sourceKey"], norm_title(e["title"]))].append(e)
    merged = []
    for (_, _), group in groups.items():
        if len(group) == 1:
            merged.append(group[0])
            continue
        group.sort(key=lambda e: e["startDate"])
        base = dict(group[0])
        occ = {(o["date"], o["time"]): o for e in group for o in e.get("occurrences", [])}
        base["occurrences"] = sorted(occ.values(), key=lambda o: (o["date"], o["time"]))[:MAX_OCCURRENCES]
        base["startDate"] = min(e["startDate"] for e in group)
        base["endDate"] = max(e["endDate"] for e in group)
        base["recurring"] = True
        times = {o["time"] for o in base["occurrences"] if o["time"]}
        base["time"] = times.pop() if len(times) == 1 else ""
        merged.append(base)
    return merged


def _overlap(a: dict, b: dict) -> bool:
    return a["startDate"] <= b["endDate"] and b["startDate"] <= a["endDate"]


def _words(title: str) -> set[str]:
    stop = {"the", "and", "with", "for", "from", "presents", "live", "exhibition",
            "isle", "man", "manx", "of", "at"}
    out = set()
    for w in norm_title(title).split():
        if len(w) < 3 or w in stop:
            continue
        out.add(re.sub(r"(es|s)$", "", w) if len(w) > 4 else w)
    return out


def _same_event(a: dict, b: dict) -> bool:
    if norm_title(a["title"]) == norm_title(b["title"]):
        return _overlap(a, b)
    # Different wording for the same thing ("On the Buses" / "A Bus Service"):
    # identical dates, same town, and the titles share words.
    if a["startDate"] != b["startDate"] or a["endDate"] != b["endDate"]:
        return False
    if a.get("area") and b.get("area") and a["area"] != b["area"]:
        return False
    wa, wb = _words(a["title"]), _words(b["title"])
    if not wa or not wb:
        return False
    return len(wa & wb) / len(wa | wb) >= 0.3


def dedupe_across_sources(events: list[dict]) -> list[dict]:
    """The tourism calendar repeats many venue listings. Keep the venue's own
    version (better dates and booking link) and borrow anything it lacks."""
    ordered = sorted(events, key=lambda e: -SOURCE_PRIORITY.get(e["sourceKey"], 0))
    kept: list[dict] = []
    for e in ordered:
        dup = next((k for k in kept if k["sourceKey"] != e["sourceKey"] and _same_event(k, e)), None)
        if dup:
            for field in ("imageUrl", "price", "description", "address", "area", "bookingUrl"):
                if not dup.get(field) and e.get(field):
                    dup[field] = e[field]
            dup.setdefault("alsoListedOn", []).append(e["source"])
        else:
            kept.append(e)
    return kept


SOURCES = [
    ("villagaiety", "Villa Marina & Gaiety", source_villagaiety),
    ("mnh", "Manx National Heritage", source_mnh),
    ("visitiom", "Visit Isle of Man", source_visitiom),
    ("erin", "Erin Arts Centre", source_erin),
    # Centenary Centre, Peel: switched off. Their site (behind Cloudflare)
    # answers 403 to automated visitors on every page, so they have chosen
    # not to be collected. Many of their shows still arrive via Visit Isle of
    # Man. The parser is kept in case they ever allow it.
    # ("centenary", "Centenary Centre", source_centenary),
]


def load_previous() -> dict:
    try:
        with open(OUTPUT, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def main() -> int:
    print(f"Manx One events scraper — identifying as {USER_AGENT}")
    previous = load_previous()
    prev_events = previous.get("events", []) if isinstance(previous.get("events"), list) else []
    prev_by_source = defaultdict(list)
    for e in prev_events:
        if e.get("sourceKey"):
            prev_by_source[e["sourceKey"]].append(e)

    all_events: list[dict] = []
    report = []
    for key, name, fn in SOURCES:
        print(f"\n=== {name} ===")
        started = time.time()
        try:
            evs = fn()
            if not evs:
                raise RuntimeError("no events found")
            all_events.extend(evs)
            report.append({"key": key, "name": name, "count": len(evs), "status": "ok"})
            print(f"  -> {len(evs)} events in {time.time() - started:.0f}s")
        except Exception as exc:                                    # noqa: BLE001
            carried = [e for e in prev_by_source.get(key, []) if e.get("endDate", "") >= TODAY.isoformat()]
            all_events.extend(carried)
            report.append({"key": key, "name": name, "count": len(carried),
                           "status": "failed", "error": str(exc)[:200]})
            print(f"  !! {name} FAILED: {exc} — kept {len(carried)} from last run")

    events = merge_same_source(all_events)
    events = dedupe_across_sources(events)
    events = [e for e in events if e["endDate"] >= TODAY.isoformat()]
    events.sort(key=lambda e: (e["startDate"], e["time"] or "99", e["title"].lower()))

    ok_sources = [r for r in report if r["status"] == "ok"]
    if not ok_sources:
        print("\nABORT: every source failed — leaving the previous file in place.")
        return 1
    prev_total = len(prev_events)
    if prev_total >= 50 and len(events) < prev_total * 0.4 and previous.get("schemaVersion") == 2:
        print(f"\nABORT: only {len(events)} events vs {prev_total} last run — not overwriting.")
        return 1

    categories = Counter(e["category"] for e in events)
    payload = {
        "success": True,
        "schemaVersion": 2,
        "fetchedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "lastUpdated": datetime.now(timezone.utc).strftime("%H:%M UTC"),
        "totalCount": len(events),
        "categories": {c: categories[c] for c in CATEGORIES if categories.get(c)},
        "sources": report,
        "source": "Villa Marina & Gaiety, Manx National Heritage, Visit Isle of Man, Erin Arts Centre",
        "disclaimer": ("Events are collected from the organisers' own websites. Always check "
                       "details and book with the organiser. Manx One is not affiliated with "
                       "any venue or organiser listed."),
        "events": events,
    }
    os.makedirs(os.path.dirname(OUTPUT) or ".", exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    print(f"\nWrote {len(events)} events to {OUTPUT}")
    for r in report:
        print(f"  {r['status']:6} {r['name']}: {r['count']}" + (f"  ({r.get('error')})" if r.get("error") else ""))
    print("  Categories:", dict(categories.most_common()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
