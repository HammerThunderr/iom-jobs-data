"""
Tide predictions scraper - Isle of Man ports (gov.im).

Auto-discovers the per-port prediction pages from the gov.im tides index
(links whose text contains "tide predictions"), then parses each port's
7-day table (table#tideTable) into docs/tides.json.

Notes:
- Dates: the table headers are weekday names only (first column = today,
  Isle of Man local time). Real dates are computed by aligning the first
  header's weekday against today in Europe/Isle_of_Man.
- gov.im groups tides by tidal cycle, so a day's final tide can spill
  past midnight (e.g. "Low 00:40" in Wednesday's column is technically
  Thursday morning). We mirror gov.im's own grouping exactly rather than
  re-dating those entries - matching the official presentation.

Output schema (docs/tides.json):
{
  "success": true, "lastUpdated": "YYYY-MM-DD",
  "source": "Isle of Man Government (gov.im) - Crown Copyright, OGL",
  "ports": [
    {"name": "Douglas", "days": [
      {"date": "YYYY-MM-DD", "tides": [
        {"type": "high"|"low", "time": "HH:MM", "height_m": 6.29}, ...]}
    ]}
  ]
}
"""

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

try:
    from zoneinfo import ZoneInfo
    IOM_TZ = ZoneInfo("Europe/Isle_of_Man")
except Exception:                                   # noqa: BLE001
    IOM_TZ = timezone.utc  # fallback; only shifts dates near midnight UTC

INDEX_URL = ("https://www.gov.im/categories/travel-traffic-and-motoring/"
             "harbours/tides-and-flapgates/")

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"),
    "Referer": "https://www.gov.im/",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")
HEIGHT_RE = re.compile(r"([\d.]+)")


def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.text


def discover_port_pages():
    """Find '<Port> tide predictions' links on the index page."""
    soup = BeautifulSoup(fetch(INDEX_URL), "html.parser")
    pages = {}
    for a in soup.find_all("a", href=True):
        text = " ".join(a.get_text(" ", strip=True).split())
        if "tide prediction" in text.lower():
            name = re.sub(r"(?i)\s*tide predictions?\s*$", "", text).strip()
            url = urljoin(INDEX_URL, a["href"])
            if name:
                pages[name] = url
    return pages


def align_start_date(first_th):
    """Match the first weekday header to today +/- 1 day (IoM time)."""
    today = datetime.now(IOM_TZ).date()
    want = (first_th or "")[:3].lower()
    for offset in (0, -1, 1):
        d = today + timedelta(days=offset)
        if d.strftime("%a")[:3].lower() == want:
            return d
    return today  # header unrecognised - assume first column is today


def parse_port_page(html, fallback_name):
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="tideTable") or soup.find("table")
    if table is None:
        raise ValueError("no tide table found on page")

    # Port name from the caption: "7 day tide times for Douglas."
    name = fallback_name
    cap = table.find("caption")
    if cap:
        m = re.search(r"for\s+(.+?)\.?\s*$", cap.get_text(strip=True), re.I)
        if m:
            name = m.group(1).strip()

    ths = [th.get_text(strip=True) for th in table.find_all("th")]
    if not ths:
        raise ValueError("no weekday headers found")
    start = align_start_date(ths[0])

    # The data row: the <tr> whose <td>s contain the tide lists.
    tds = []
    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        if cells:
            tds = cells
            break
    if not tds:
        raise ValueError("no data cells found")

    days = []
    for i, td in enumerate(tds):
        tides = []
        for wrap in td.select(".tidal-wrap"):
            state = wrap.select_one(".tidal-state")
            time_ = wrap.select_one(".tidal-time")
            height = wrap.select_one(".tidal-height")
            if not (state and time_):
                continue
            t_type = state.get_text(strip=True).lower()
            t_time = time_.get_text(strip=True)
            if t_type not in ("high", "low") or not TIME_RE.match(t_time):
                continue
            h = 0.0
            if height:
                m = HEIGHT_RE.search(height.get_text(strip=True))
                if m:
                    try:
                        h = float(m.group(1))
                    except ValueError:
                        h = 0.0
            # zero-pad "2:29" -> "02:29" for consistent app-side parsing
            hh, mm = t_time.split(":")
            tides.append({
                "type": t_type,
                "time": f"{int(hh):02d}:{mm}",
                "height_m": h,
            })
        if tides:
            days.append({
                "date": (start + timedelta(days=i)).isoformat(),
                "tides": tides,
            })

    if not days:
        raise ValueError("table parsed but produced no tide days")
    return name, days


def main():
    try:
        pages = discover_port_pages()
    except Exception as exc:                        # noqa: BLE001
        print(f"Index discovery failed: {exc}", file=sys.stderr)
        sys.exit(1)

    if not pages:
        print("No 'tide predictions' links found on index page",
              file=sys.stderr)
        sys.exit(1)
    print(f"Discovered {len(pages)} port page(s): {', '.join(pages)}")

    ports = []
    for fallback_name, url in pages.items():
        try:
            name, days = parse_port_page(fetch(url), fallback_name)
            ports.append({"name": name, "days": days})
            n_tides = sum(len(d["tides"]) for d in days)
            print(f"{name}: {len(days)} days, {n_tides} tides")
        except Exception as exc:                    # noqa: BLE001
            print(f"{fallback_name}: FAILED ({exc})", file=sys.stderr)

    if not ports:
        print("No ports parsed - keeping previous tides.json",
              file=sys.stderr)
        sys.exit(1)

    payload = {
        "success": True,
        "lastUpdated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "source": "Isle of Man Government (gov.im) - Crown Copyright, OGL",
        "ports": ports,
    }
    with open("docs/tides.json", "w") as f:
        json.dump(payload, f, indent=2)
    print(f"tides.json written with {len(ports)} port(s)")


if __name__ == "__main__":
    main()
