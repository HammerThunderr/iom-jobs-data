"""
Steam Packet (IOM Ferry) Sailing Status Scraper
------------------------------------------------
Scrapes upcoming sailings from steam-packet.com.
Saves to docs/ferry.json on GitHub Pages every 15 minutes.

Place at: scripts/scrape_ferry.py in your iom-jobs-data repo.
"""

import requests
import json
import os
import re
import time
from datetime import datetime, timezone
from bs4 import BeautifulSoup

URL = "https://www.steam-packet.com/sailing-status"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*",
    "Accept-Language": "en-GB,en;q=0.9",
}

# Status keywords found in the page
STATUSES = [
    "Arrived", "Departed", "Scheduled", "Cancelled",
    "Delayed", "Boarding", "Loading", "Diverted",
]


def fetch():
    """Fetch the sailing status page."""
    for verify in [True, False]:
        try:
            print(f"Fetching {URL} (verify={verify})...")
            resp = requests.get(URL, headers=HEADERS, timeout=25, verify=verify)
            resp.raise_for_status()
            print(f"  ✓ Got {len(resp.text)} bytes")
            return resp.text
        except Exception as e:
            print(f"  ✗ {type(e).__name__}: {str(e)[:80]}")
    raise Exception("Fetch failed")


def clean(s):
    """Whitespace-collapse a string."""
    if not s:
        return ""
    return re.sub(r'\s+', ' ', s).strip()


def parse_sailings(html):
    """Parse all sailings grouped by date."""
    soup = BeautifulSoup(html, "html.parser")
    days = []

    # The page has h3 headers with dates like "Sunday, 3 May 2026"
    # followed by sailing blocks until the next h3.
    # Each sailing block contains: status text, "Departure"/"Departed at",
    # times, ports, and "Ferry" label.

    # Find all h3 (date headers) inside the main content area
    main = soup.find("main") or soup.find("div", id="main") or soup
    headers = main.find_all(["h3"])

    last_updated = ""
    # Try to extract last updated time
    last_text_match = re.search(
        r'Last\s+updated[:\s]+([\d:]+\s*[\d/]+)', soup.get_text(), re.IGNORECASE)
    if last_text_match:
        last_updated = last_text_match.group(1).strip()

    for header in headers:
        date_label = clean(header.get_text())

        # Skip if not a date heading (e.g. "Customer services", etc.)
        if not re.search(
            r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)',
            date_label, re.IGNORECASE
        ):
            continue

        sailings_for_day = []

        # Walk forward through sibling elements until we hit the next h3
        sibling = header
        while True:
            sibling = sibling.find_next_sibling()
            if sibling is None:
                break
            if sibling.name == "h3":
                break
            # Get all text in this sibling
            block_text = clean(sibling.get_text(separator="\n"))
            if not block_text:
                continue

            # A "sailing" block typically contains all of: status, time, port, "Ferry"
            # We split on "Ferry" or status repetitions
            # Simpler: find sections with two times + two ports
            sailings_for_day.extend(extract_sailings_from_block(block_text))

        if sailings_for_day:
            days.append({
                "date":     date_label,
                "sailings": sailings_for_day,
            })

    # Fallback: if header-based grouping found nothing, parse the whole text
    if not days:
        all_text = clean(main.get_text(separator="\n"))
        # Try to parse without grouping
        sailings = extract_sailings_from_block(all_text)
        if sailings:
            days.append({"date": "Upcoming", "sailings": sailings})

    return days, last_updated


def extract_sailings_from_block(text):
    """
    Pull individual sailings from a block of text.
    Each sailing pattern: status + time + port + time + port + "Ferry" + ferry name + status
    """
    sailings = []

    # Time pattern: HH:MM
    time_pat = r'\d{2}:\d{2}'

    # Try to match sailing groups using a regex that captures the structure
    # Pattern: [Status] [Departure|Departed at|Departure] [time] [port] [Arrival|Expected] [time] [port] [Ferry] [shipname] [status]
    pattern = (
        r'(Arrived|Departed|Scheduled|Cancelled|Delayed|Boarding|Loading|Diverted)\s+'   # status1
        r'(?:Departure|Departed\s+at)\s+'
        r'(' + time_pat + r')\s+'                  # depart time
        r'([A-Za-z][A-Za-z\s]+?)\s+'               # depart port
        r'(?:Arrival|Expected)\s+'
        r'(' + time_pat + r')\s+'                  # arrive time
        r'([A-Za-z][A-Za-z\s]+?)\s+'               # arrive port
        r'Ferry\s+'
        r'([A-Za-z][A-Za-z\s]+?)\s+'               # ferry name
        r'(Arrived|Departed|Scheduled|Cancelled|Delayed|Boarding|Loading|Diverted)'  # status2 (matches start)
    )

    for m in re.finditer(pattern, text, re.IGNORECASE):
        status     = m.group(1).strip().title()
        depart_at  = m.group(2).strip()
        depart_pt  = m.group(3).strip()
        arrive_at  = m.group(4).strip()
        arrive_pt  = m.group(5).strip()
        ferry      = m.group(6).strip()

        sailings.append({
            "departTime": depart_at,
            "departPort": depart_pt,
            "arriveTime": arrive_at,
            "arrivePort": arrive_pt,
            "ferry":      ferry,
            "status":     status,
        })

    return sailings


def categorize_status(status):
    s = status.lower()
    if "cancel"  in s: return "cancelled"
    if "delay"   in s: return "delayed"
    if "divert"  in s: return "delayed"
    if "depart"  in s: return "departed"
    if "arriv"   in s: return "arrived"
    if "board"   in s: return "boarding"
    if "load"    in s: return "boarding"
    return "scheduled"


def main():
    os.makedirs("docs", exist_ok=True)

    try:
        html = fetch()
        days, last_updated = parse_sailings(html)

        # Add status type to every sailing
        total = 0
        for day in days:
            for s in day["sailings"]:
                s["statusType"] = categorize_status(s.get("status", ""))
                total += 1

        data = {
            "success":     True,
            "fetchedAt":   datetime.now(timezone.utc).isoformat(),
            "lastUpdated": last_updated or datetime.now(timezone.utc).strftime("%H:%M UTC"),
            "totalCount":  total,
            "days":        days,
            "source":      "steam-packet.com",
        }

        if total == 0:
            print("⚠ No sailings parsed!")
            if os.path.exists("docs/ferry.json"):
                print("Keeping existing data")
                return
        else:
            print(f"\n✓ SUCCESS — {total} sailings across {len(days)} day(s)")

    except Exception as e:
        print(f"\n✗ FAILED: {e}")
        import traceback
        traceback.print_exc()
        data = {
            "success":     False,
            "error":       str(e)[:200],
            "fetchedAt":   datetime.now(timezone.utc).isoformat(),
            "days":        [],
        }

    with open("docs/ferry.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("✓ Saved docs/ferry.json")


if __name__ == "__main__":
    main()
