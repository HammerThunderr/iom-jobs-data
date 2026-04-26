"""
What's On IOM Events Scraper
-----------------------------
Scrapes events from whatsoniom.im every 30 minutes.
Saves to docs/events.json on GitHub Pages.

Place at: scripts/scrape_events.py in your iom-jobs-data repo.
"""

import requests
import urllib3
import json
import os
import re
import html as html_lib
from datetime import datetime, timezone
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

URL = "https://whatsoniom.im/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}


def fetch():
    """Fetch the events page."""
    for verify in [True, False]:
        try:
            print(f"Fetching {URL} (verify={verify})...")
            resp = requests.get(URL, headers=HEADERS, timeout=30, verify=verify)
            resp.raise_for_status()
            print(f"  ✓ Got {len(resp.text)} bytes")
            return resp.text
        except Exception as e:
            print(f"  ✗ {type(e).__name__}: {str(e)[:80]}")
    raise Exception("All fetch attempts failed")


def clean_text(s):
    """Clean and decode HTML text."""
    if not s:
        return ""
    s = html_lib.unescape(s)
    s = re.sub(r'\s+', ' ', s)
    return s.strip()


def parse_events(html):
    """Parse all event cards from the HTML."""
    soup = BeautifulSoup(html, "html.parser")
    events = []

    cards = soup.find_all("div", class_="event-card")
    print(f"Found {len(cards)} event cards")

    for card in cards:
        try:
            # Pull all data-* attributes
            title       = clean_text(card.get("data-title", ""))
            venue       = clean_text(card.get("data-venue", ""))
            start_date  = card.get("data-start", "")
            end_date    = card.get("data-end", "")
            is_tbc      = card.get("data-is-tbc", "false") == "true"
            duration    = card.get("data-duration", "0")
            tags_raw    = clean_text(card.get("data-tags", ""))
            source      = clean_text(card.get("data-source", ""))
            recurring   = card.get("data-recurring", "false") == "true"
            desc        = clean_text(card.get("data-desc", ""))

            # Skip if essential data is missing
            if not title:
                continue

            # Title (capitalize properly) — visible heading
            heading = card.find("h3")
            display_title = clean_text(heading.get_text(strip=True)) if heading else title.title()
            # Strip "via Source" pills off the heading
            display_title = re.sub(r'\s*via\s+[\w &().,/-]+$', '', display_title, flags=re.IGNORECASE).strip()

            # Image
            img = card.find("img", class_="event-img")
            image_url = ""
            if img:
                src = img.get("src", "")
                if src and not src.startswith("/og-image"):
                    image_url = src

            # Time and price
            time_str  = ""
            price_str = ""
            for chip in card.find_all("span", class_="meta-chip"):
                cls = chip.get("class", [])
                text = clean_text(chip.get_text(strip=True))
                if "time" in cls:
                    time_str = text
                elif "price" in cls:
                    price_str = text

            # Get Info link
            info_link = ""
            link_btn = card.find("a", class_="btn-view")
            if link_btn:
                info_link = link_btn.get("href", "")

            # Tags as list
            tags = []
            if tags_raw:
                tags = [t.strip() for t in re.split(r'[,&]', tags_raw) if t.strip()]

            event = {
                "title":       display_title,
                "venue":       venue.title() if venue else "",
                "startDate":   start_date,
                "endDate":     end_date,
                "isTbc":       is_tbc,
                "duration":    float(duration) if duration else 0,
                "tags":        tags,
                "source":      source,
                "recurring":   recurring,
                "description": desc,
                "imageUrl":    image_url,
                "time":        time_str,
                "price":       price_str if price_str.lower() != "see event page" else "",
                "url":         info_link,
            }
            events.append(event)

        except Exception as e:
            print(f"  Card parse error: {e}")
            continue

    return events


def main():
    os.makedirs("docs", exist_ok=True)

    try:
        html = fetch()
        events = parse_events(html)

        # Sort by date
        events.sort(key=lambda e: (e["startDate"], e["time"]))

        # Build category index
        categories = {}
        for e in events:
            for tag in e["tags"]:
                categories[tag] = categories.get(tag, 0) + 1

        data = {
            "success":     True,
            "fetchedAt":   datetime.now(timezone.utc).isoformat(),
            "lastUpdated": datetime.now(timezone.utc).strftime("%H:%M UTC"),
            "totalCount":  len(events),
            "categories":  categories,
            "events":      events,
            "source":      "whatsoniom.im",
        }
        print(f"\n✓ SUCCESS — {len(events)} events")
        print(f"  Categories: {list(categories.keys())[:5]}...")

    except Exception as e:
        print(f"\n✗ FAILED: {e}")
        data = {
            "success":     False,
            "error":       str(e)[:200],
            "fetchedAt":   datetime.now(timezone.utc).isoformat(),
            "events":      [],
        }

    with open("docs/events.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("\n✓ Saved docs/events.json")


if __name__ == "__main__":
    main()
