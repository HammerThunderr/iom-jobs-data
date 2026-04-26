"""
Webcam Image Scraper
--------------------
Run by GitHub Actions every minute.
Downloads webcam JPGs from images.gov.im and saves to docs/webcams/ folder.
GitHub Pages then serves them with proper CORS — Chrome can load them.

Place at: scripts/scrape_webcams.py in your iom-jobs-data repo.
"""

import requests
import os
import json
from datetime import datetime, timezone

WEBCAMS = [
    {"name": "Bungalow (A18 North)",    "file": "bungalow3.jpg"},
    {"name": "Bungalow (A18 South)",    "file": "bungalow1.jpg"},
    {"name": "Bungalow (Laxey Valley)", "file": "bungalow2.jpg"},
    {"name": "Douglas Marina",          "file": "douglas_00001.jpg"},
    {"name": "Douglas Promenade",       "file": "DTL_00001.jpg"},
    {"name": "Peel Breakwater",         "file": "peel_00001.jpg"},
    {"name": "Port Erin Bay",           "file": "PortErin.jpg"},
    {"name": "Douglas Outer Harbour",   "file": "ed_tower.jpg"},
    {"name": "Ramsey",                  "file": "Ramsey_00001.jpg"},
    {"name": "Castletown Bay",          "file": "Castletown_Bay.jpg"},
]

BASE_URL = "https://images.gov.im/webcams/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.gov.im/",
    "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
}


def main():
    out_dir = os.path.join("docs", "webcams")
    os.makedirs(out_dir, exist_ok=True)

    success_count = 0
    metadata = []

    for cam in WEBCAMS:
        url  = BASE_URL + cam["file"]
        path = os.path.join(out_dir, cam["file"])
        print(f"Fetching {cam['name']}...")

        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            with open(path, "wb") as f:
                f.write(resp.content)
            size_kb = len(resp.content) // 1024
            print(f"  ✓ {size_kb} KB -> {path}")
            success_count += 1
            metadata.append({
                "name": cam["name"],
                "file": cam["file"],
                "size": len(resp.content),
                "ok":   True,
            })
        except Exception as e:
            print(f"  ✗ Error: {e}")
            metadata.append({
                "name": cam["name"],
                "file": cam["file"],
                "ok":   False,
            })

    # Save metadata for the app
    info = {
        "success":    True,
        "fetchedAt":  datetime.now(timezone.utc).isoformat(),
        "totalCount": len(WEBCAMS),
        "okCount":    success_count,
        "webcams":    metadata,
    }
    with open(os.path.join("docs", "webcams.json"), "w") as f:
        json.dump(info, f, indent=2)

    print(f"\n✓ {success_count}/{len(WEBCAMS)} webcams updated")


if __name__ == "__main__":
    main()
