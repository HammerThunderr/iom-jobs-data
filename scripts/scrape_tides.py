"""
Tide predictions scraper — Isle of Man ports (gov.im).

STATUS: SKELETON — the fetch/output plumbing is complete, but the parser
(parse_port_page) is a TODO until we see the real page format, because
gov.im blocks automated inspection and guessing a parser for TIDE data
is unsafe (wrong tide times are worse than none).

To finish: open https://www.gov.im/categories/travel-traffic-and-motoring/
harbours/tides-and-flapgates/ in a browser, follow one port's
"tide predictions" link, and note whether it is an HTML table or a PDF.
Paste the page HTML (or say "PDF") back into the chat and the parser
gets written to match.

Output schema (docs/tides.json):
{
  "success": true, "lastUpdated": "YYYY-MM-DD",
  "source": "Isle of Man Government (gov.im) - Crown Copyright, OGL",
  "ports": [
    {"name": "Douglas", "days": [
      {"date": "YYYY-MM-DD", "tides": [
        {"type": "high"|"low", "time": "HH:MM", "height_m": 6.1}, ...
      ]}, ...
    ]}, ...
  ]
}
"""

import json
import sys
from datetime import datetime, timezone

import requests

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"),
    "Referer": "https://www.gov.im/",
    "Accept": "text/html,application/xhtml+xml",
}

# TODO: confirm the real per-port prediction URLs from the tides page.
PORT_PAGES = {
    "Douglas": "https://www.gov.im/REPLACE-ME-douglas-tide-predictions/",
    "Peel": "https://www.gov.im/REPLACE-ME-peel-tide-predictions/",
    "Ramsey": "https://www.gov.im/REPLACE-ME-ramsey-tide-predictions/",
    "Port St Mary": "https://www.gov.im/REPLACE-ME-psm-tide-predictions/",
}


def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.text


def parse_port_page(html):
    """TODO: parse the port's 7-day tide predictions.

    Must return: [{"date": "YYYY-MM-DD",
                   "tides": [{"type": "high", "time": "HH:MM",
                              "height_m": 6.1}, ...]}, ...]
    Implementation depends on whether gov.im serves an HTML table or PDF.
    """
    raise NotImplementedError(
        "Parser not written yet - see module docstring for how to finish.")


def main():
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
    main()
