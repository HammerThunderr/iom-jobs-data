"""
Tide predictions scraper - Isle of Man ports (gov.im).

TWO MODES:

1. DISCOVERY MODE (current) - runs automatically while PORT_PAGES still
   contains REPLACE-ME placeholders. It fetches the gov.im tides index
   page, lists every tide-related link it finds, then fetches the first
   port-prediction candidate and prints its content-type and a sample of
   its HTML/table structure into the workflow log. Paste that log output
   back into the chat and the real parser gets written to match.
   Discovery always exits 0 (green run) so the log is easy to read.

2. SCRAPE MODE - once PORT_PAGES holds real URLs and parse_port_page is
   implemented, it scrapes all ports daily and writes docs/tides.json.

Output schema (docs/tides.json):
{
  "success": true, "lastUpdated": "YYYY-MM-DD",
  "source": "Isle of Man Government (gov.im) - Crown Copyright, OGL",
  "ports": [
    {"name": "Douglas", "days": [
      {"date": "YYYY-MM-DD", "tides": [
        {"type": "high"|"low", "time": "HH:MM", "height_m": 6.1}, ...]}
    ]}
  ]
}
"""

import json
import re
import sys
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

INDEX_URL = ("https://www.gov.im/categories/travel-traffic-and-motoring/"
             "harbours/tides-and-flapgates/")

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"),
    "Referer": "https://www.gov.im/",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# TODO: replace with the real URLs found by discovery mode.
PORT_PAGES = {
    "Douglas": "https://www.gov.im/REPLACE-ME-douglas-tide-predictions/",
    "Peel": "https://www.gov.im/REPLACE-ME-peel-tide-predictions/",
    "Ramsey": "https://www.gov.im/REPLACE-ME-ramsey-tide-predictions/",
    "Port St Mary": "https://www.gov.im/REPLACE-ME-psm-tide-predictions/",
}


def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r


# ─────────────────────────────────────────────────────────────
# DISCOVERY MODE
# ─────────────────────────────────────────────────────────────

def discover():
    print("=" * 70)
    print("DISCOVERY MODE - paste everything below back into the chat")
    print("=" * 70)

    try:
        r = fetch(INDEX_URL)
    except Exception as exc:  # noqa: BLE001
        print(f"\nINDEX FETCH FAILED: {exc}")
        print("gov.im may be blocking the runner - paste this log anyway.")
        return

    print(f"\nINDEX: {INDEX_URL}")
    print(f"status={r.status_code} content-type={r.headers.get('content-type')}")

    soup = BeautifulSoup(r.text, "html.parser")

    print("\n--- ALL LINKS CONTAINING 'tide' (href or text) ---")
    candidates = []
    for a in soup.find_all("a", href=True):
        text = " ".join(a.get_text(" ", strip=True).split())
        href = urljoin(INDEX_URL, a["href"])
        if "tide" in href.lower() or "tide" in text.lower():
            print(f"  [{text[:60]}] -> {href}")
            candidates.append((text, href))

    print("\n--- ALL LINKS ENDING .pdf ON INDEX PAGE ---")
    for a in soup.find_all("a", href=True):
        href = urljoin(INDEX_URL, a["href"])
        if href.lower().split("?")[0].endswith(".pdf"):
            text = " ".join(a.get_text(" ", strip=True).split())
            print(f"  [{text[:60]}] -> {href}")

    # Fetch the first candidate that looks like a port prediction page
    port_words = ("douglas", "peel", "ramsey", "port")
    target = next(
        ((t, h) for t, h in candidates
         if any(w in (t + h).lower() for w in port_words)),
        candidates[0] if candidates else None,
    )
    if not target:
        print("\nNo tide links found - the page structure may differ. "
              "Paste this log back anyway.")
        return

    text, href = target
    print(f"\n--- FETCHING SAMPLE CANDIDATE: [{text[:50]}] {href} ---")
    try:
        r2 = fetch(href)
    except Exception as exc:  # noqa: BLE001
        print(f"CANDIDATE FETCH FAILED: {exc}")
        return

    ctype = r2.headers.get("content-type", "")
    print(f"status={r2.status_code} content-type={ctype} "
          f"length={len(r2.content)}")

    if "pdf" in ctype.lower():
        print("FORMAT: PDF - the parser will need PDF text extraction.")
        return

    s2 = BeautifulSoup(r2.text, "html.parser")
    tables = s2.find_all("table")
    print(f"FORMAT: HTML - {len(tables)} <table> element(s) found")

    if tables:
        sample = str(tables[0])
        sample = re.sub(r"\s+", " ", sample)
        print("\n--- FIRST TABLE (up to 4000 chars) ---")
        print(sample[:4000])
    else:
        # No tables - show text around the word 'tide' to reveal structure
        body = re.sub(r"\s+", " ", s2.get_text(" ", strip=True))
        idx = body.lower().find("tide")
        print("\n--- PAGE TEXT AROUND 'tide' (2000 chars) ---")
        print(body[max(0, idx - 200): idx + 1800])
        print("\n--- PDF LINKS ON THIS PAGE ---")
        for a in s2.find_all("a", href=True):
            h = urljoin(href, a["href"])
            if h.lower().split("?")[0].endswith(".pdf"):
                print(f"  {h}")

    print("\n" + "=" * 70)
    print("END OF DISCOVERY - paste this whole section into the chat")
    print("=" * 70)


# ─────────────────────────────────────────────────────────────
# SCRAPE MODE (parser pending discovery output)
# ─────────────────────────────────────────────────────────────

def parse_port_page(resp):
    """TODO: implement once discovery output shows the real structure."""
    raise NotImplementedError("Parser pending - run discovery first.")


def scrape():
    ports = []
    for name, url in PORT_PAGES.items():
        try:
            days = parse_port_page(fetch(url))
            if days:
                ports.append({"name": name, "days": days})
                print(f"{name}: {len(days)} days")
        except Exception as exc:  # noqa: BLE001
            print(f"{name}: FAILED ({exc})", file=sys.stderr)

    if not ports:
        print("No ports parsed - keeping previous tides.json", file=sys.stderr)
        sys.exit(1)

    payload = {
        "success": True,
        "lastUpdated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "source": "Isle of Man Government (gov.im) - Crown Copyright, OGL",
        "ports": ports,
    }
    with open("docs/tides.json", "w") as f:
        json.dump(payload, f, indent=2)
    print(f"tides.json written with {len(ports)} ports")


if __name__ == "__main__":
    if any("REPLACE-ME" in u for u in PORT_PAGES.values()):
        discover()          # always exits 0 - log is the deliverable
    else:
        scrape()
