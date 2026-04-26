"""
Isle of Man Airport Flight Scraper
-----------------------------------
Scrapes departures + arrivals from airport.im every 5 minutes.
Saves to docs/flights.json on GitHub Pages.

This version handles:
- Static HTML tables
- JavaScript-rendered data (looks for JSON in <script> tags)
- API endpoints (tries common paths)

Place at: scripts/scrape_flights.py in your iom-jobs-data repo.
"""

import requests
import urllib3
import json
import os
import re
from datetime import datetime, timezone
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

URLS = [
    "https://www.airport.im/",
    "https://airport.im/",
    "https://www.airport.im/live-flight-information/",
]

# Possible API endpoints used by airport.im
API_ENDPOINTS = [
    "https://www.airport.im/api/flights",
    "https://www.airport.im/wp-json/wp/v2/flights",
    "https://www.airport.im/wp-admin/admin-ajax.php?action=get_flights",
    "https://www.airport.im/wp-json/airport/v1/flights",
    "https://api.airport.im/flights",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}


def fetch(url, accept_json=False):
    """Fetch URL with multiple SSL fallbacks."""
    headers = HEADERS.copy()
    if accept_json:
        headers["Accept"] = "application/json"
    
    for verify in [True, False]:
        try:
            resp = requests.get(url, headers=headers, timeout=20,
                              verify=verify, allow_redirects=True)
            resp.raise_for_status()
            return resp
        except Exception as e:
            print(f"    SSL verify={verify}: {type(e).__name__}: {str(e)[:60]}")
    return None


def try_api_endpoints():
    """Try common API endpoints to find one that returns flight data."""
    print("\n--- Trying API endpoints ---")
    for url in API_ENDPOINTS:
        print(f"  Trying {url}")
        resp = fetch(url, accept_json=True)
        if resp and resp.status_code == 200:
            try:
                data = resp.json()
                # Quick check if it looks like flight data
                text = str(data).lower()
                if any(k in text for k in ['flight', 'departure', 'arrival', 'destination']):
                    print(f"  ✓ Found flight data API: {url}")
                    return data
            except Exception:
                pass
    print("  No API endpoint found")
    return None


def find_inline_json(html):
    """Look for flight data embedded in JavaScript on the page."""
    print("\n--- Searching for inline JSON ---")
    
    # Common patterns for embedded data
    patterns = [
        r'window\.__INITIAL_STATE__\s*=\s*({.+?});',
        r'window\.flightData\s*=\s*(\[.+?\]);',
        r'var\s+flights\s*=\s*(\[.+?\]);',
        r'"departures"\s*:\s*(\[.+?\])',
        r'"arrivals"\s*:\s*(\[.+?\])',
        r'data-flights\s*=\s*[\'"]({.+?})[\'"]',
    ]
    
    for pattern in patterns:
        m = re.search(pattern, html, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(1))
                print(f"  ✓ Found inline JSON with pattern: {pattern[:40]}")
                return data
            except Exception as e:
                print(f"    Failed to parse: {str(e)[:60]}")
    
    print("  No inline JSON found")
    return None


def parse_html_tables(html):
    """Parse static HTML tables (original approach, but with better detection)."""
    soup = BeautifulSoup(html, "html.parser")
    departures = []
    arrivals = []

    # Get ALL elements that might represent flights
    # Try tables first
    tables = soup.find_all("table")
    print(f"\n--- Parsing HTML: found {len(tables)} <table> elements ---")
    
    # Also try div-based layouts
    flight_divs = soup.find_all("div", class_=re.compile(r"flight|departure|arrival", re.IGNORECASE))
    print(f"--- Also found {len(flight_divs)} flight-related <div> elements ---")
    
    # Also try section/article tags
    sections = soup.find_all(["section", "article"], class_=re.compile(r"flight|departure|arrival", re.IGNORECASE))
    print(f"--- Also found {len(sections)} flight-related <section>/<article> elements ---")

    for idx, table in enumerate(tables):
        is_dep, is_arr = False, False
        
        # Check the table's own classes/id
        attrs = " ".join([
            table.get("id", ""),
            " ".join(table.get("class", [])),
        ]).lower()
        if "depart" in attrs: is_dep = True
        elif "arriv" in attrs: is_arr = True
        
        # Check headings before this table
        if not is_dep and not is_arr:
            for prev in table.find_all_previous(['h1','h2','h3','h4','h5'], limit=5):
                t = prev.get_text().lower()
                if 'depart' in t:
                    is_dep = True
                    break
                elif 'arriv' in t:
                    is_arr = True
                    break
        
        # Check thead
        if not is_dep and not is_arr:
            thead = table.find("thead")
            if thead:
                t = thead.get_text().lower()
                if any(k in t for k in ["destination", "departing"]): is_dep = True
                elif any(k in t for k in ["origin", "arriving"]): is_arr = True

        print(f"  Table #{idx}: dep={is_dep}, arr={is_arr}, rows={len(table.find_all('tr'))}")
        
        if not is_dep and not is_arr:
            continue

        tbody = table.find("tbody")
        rows = tbody.find_all("tr") if tbody else table.find_all("tr")[1:]

        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 5:
                continue
            try:
                if is_dep:
                    f = {
                        "destination": cols[0].get_text(strip=True),
                        "flightNo":    cols[1].get_text(strip=True),
                        "airline":     cols[2].get_text(strip=True),
                        "scheduled":   cols[3].get_text(strip=True),
                        "status":      cols[4].get_text(strip=True),
                    }
                    if f["flightNo"]: departures.append(f)
                else:
                    f = {
                        "origin":      cols[0].get_text(strip=True),
                        "flightNo":    cols[1].get_text(strip=True),
                        "airline":     cols[2].get_text(strip=True),
                        "scheduled":   cols[3].get_text(strip=True),
                        "status":      cols[4].get_text(strip=True),
                    }
                    if f["flightNo"]: arrivals.append(f)
            except Exception as e:
                print(f"    Row parse error: {e}")

    return departures, arrivals


def categorize_status(status):
    s = status.lower()
    if "cancel"   in s: return "cancelled"
    if "delay"    in s: return "delayed"
    if "boarding" in s: return "boarding"
    if "departed" in s: return "departed"
    if "arrived"  in s: return "arrived"
    if "expected" in s: return "expected"
    if "on-time"  in s or "on time" in s: return "ontime"
    if "scheduled" in s: return "scheduled"
    return "scheduled"


def main():
    os.makedirs("docs", exist_ok=True)
    departures, arrivals = [], []
    
    # Strategy 1: Try API endpoints first (most reliable if they exist)
    api_data = try_api_endpoints()
    
    # Strategy 2: Fetch the page HTML
    html = None
    for url in URLS:
        print(f"\n=== Trying {url} ===")
        resp = fetch(url)
        if resp:
            html = resp.text
            print(f"  ✓ Got {len(html)} bytes")
            
            # Save HTML for debugging
            os.makedirs("docs/_debug", exist_ok=True)
            with open(f"docs/_debug/last_page.html", "w", encoding="utf-8") as f:
                f.write(html[:50000])  # save first 50KB for inspection
            
            break
    
    if not html and not api_data:
        data = {
            "success": False,
            "error": "Could not reach airport.im on any URL",
            "fetchedAt": datetime.now(timezone.utc).isoformat(),
            "departures": [],
            "arrivals": [],
        }
        with open("docs/flights.json", "w") as f:
            json.dump(data, f, indent=2)
        return
    
    # Strategy 3: Look for inline JSON in HTML
    if html and not departures:
        inline = find_inline_json(html)
        if inline:
            print(f"  Inline JSON keys: {list(inline.keys()) if isinstance(inline, dict) else 'array'}")
    
    # Strategy 4: Parse HTML tables
    if html and not departures:
        departures, arrivals = parse_html_tables(html)

    # Add status categories
    for f in departures + arrivals:
        f["statusType"] = categorize_status(f.get("status", ""))

    # Save result
    if departures or arrivals:
        data = {
            "success":     True,
            "fetchedAt":   datetime.now(timezone.utc).isoformat(),
            "lastUpdated": "",
            "departures":  departures,
            "arrivals":    arrivals,
            "totalCount":  len(departures) + len(arrivals),
        }
        print(f"\n✓ SUCCESS — {len(departures)} departures, {len(arrivals)} arrivals")
    else:
        data = {
            "success":     False,
            "error":       "No flight data found on page. Site may load data via JavaScript. Check docs/_debug/last_page.html",
            "fetchedAt":   datetime.now(timezone.utc).isoformat(),
            "departures":  [],
            "arrivals":    [],
        }
        print("\n✗ FAILED — no flight data extracted")
        print("  Check docs/_debug/last_page.html in your repo to see the HTML")

    with open("docs/flights.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("\n✓ Saved docs/flights.json")


if __name__ == "__main__":
    main()
