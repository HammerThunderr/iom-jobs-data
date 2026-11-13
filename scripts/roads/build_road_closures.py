"""
Road closures — builds docs/road_closures.json from the Department of
Infrastructure's fortnightly "Upcoming TTRNs" lists.

SOURCE
------
Every two weeks the Department of Infrastructure publishes a PDF called
"Isle of Man upcoming TTRNs issued for road works & events" on:
  https://www.gov.im/about-the-government/departments/infrastructure/highway-services/upcoming-roadworks-and-events-on-roads/

Each row is one Temporary Traffic Restriction Notice: who is doing the work,
the road, the village/town, the type (closure, parking ban, one-way, speed
limit...), proposed start and end dates, what it's for, a helpline and a link
to the work on the Roadwatch (one.network) map.

WHY THE PDFs ARE UPLOADED BY HAND
---------------------------------
gov.im sits behind a firewall that refuses requests from servers such as
GitHub Actions (tested November 2026: every gov.im page and PDF returned
"Request Rejected" or a browser challenge). We do not try to get round that.
Instead, the PDF is saved from gov.im in a normal browser and uploaded into
roads/lists/ in this repo. Any push there runs this script.

The script also runs daily, so finished works drop off without anyone
touching it.

HOW IT READS THE PDF
--------------------
The PDFs are Word tables with cells that wrap over several lines, so plain
table extraction splits cells apart. Instead, every row is anchored on its
pair of dd/mm/yyyy dates; the words within half a row-gap above and below the
anchor belong to that row, and each word goes to the column whose header it
sits under. The one.network link is matched to the row by its position.

SAFETY
------
If a PDF in roads/lists/ yields no rows, the script stops with an error and
the previous road_closures.json is left as it was.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import statistics
import sys
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parents[2]
LISTS = ROOT / "roads" / "lists"
OUT = ROOT / "docs" / "road_closures.json"

SOURCE_PAGE = ("https://www.gov.im/about-the-government/departments/infrastructure/"
               "highway-services/upcoming-roadworks-and-events-on-roads/")
ROADWATCH = "https://www.gov.im/roadwatch"

DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], 1)}
PERIOD_RE = re.compile(
    r"(\d{1,2})\s+([A-Za-z]+)\s*(\d{4})?\s*[–\-—to]+\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})")

# Column keys, left to right, and the header words that mark each one.
HEADER_WORDS = {
    "promoter": {"Promoter", "Organisation"},
    "road": {"Name"},  # "Road Name" — "Road" alone also appears in "Road Watch"
    "locality": {"Locality"},
    "type": {"Management", "Traffic"},
    "start": {"Start"},
    "end": {"End"},
    "activity": {"Activity"},
    "phone": {"Telephone", "helpline"},
    "link": {"Causeway", "One.Network", "Watch", "link"},
}
COLS = list(HEADER_WORDS)

AREAS = {
    "Douglas": ["douglas", "braddan", "union mills", "quarterbridge", "governor"],
    "North": ["ramsey", "andreas", "jurby", "bride", "lezayre", "ballaugh", "sulby",
              "maughold", "kirk michael", "michael"],
    "East": ["onchan", "laxey", "lonan", "baldrine", "groudle", "garwick", "santon"],
    "South": ["castletown", "ballasalla", "port erin", "port st mary", "rushen", "arbory",
              "malew", "colby", "ballabeg", "cregneash", "derbyhaven", "ronaldsway"],
    "West": ["peel", "st johns", "st john's", "german", "patrick", "foxdale", "glen helen",
             "glen maye", "dalby", "crosby", "marown", "greeba", "glen vine"],
}


def area_for(locality: str, road: str) -> str:
    text = f"{locality} {road}".lower()
    hits = [a for a, words in AREAS.items() if any(w in text for w in words)]
    if len(hits) == 1:
        return hits[0]
    if "various" in text or "island" in text or len(hits) > 1:
        return "Various"
    return "Other"


def kind_for(t: str, road: str = "") -> str:
    if re.match(r"(?i)^prow\b", road):
        return "footpath"  # Public Right of Way: a footpath or bridleway
    s = t.lower()
    if "closure" in s or "closed" in s:
        return "closure"
    if "parking" in s:
        return "parking"
    if "one-way" in s or "one way" in s:
        return "one_way"
    if "mph" in s or "speed" in s:
        return "speed_limit"
    if "light" in s or "signal" in s:
        return "lights"
    if "turn" in s or "weight" in s or "width" in s:
        return "restriction"
    return "other"


def tidy(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip(" ,")
    s = s.replace(" & ", " & ")
    return s


def fmt_phone(raw: str) -> str:
    d = re.sub(r"\D", "", raw)
    if not d:
        return ""
    if len(d) == 6:
        return f"01624 {d}"
    if len(d) == 10 and d.startswith("7"):
        d = "0" + d
    if len(d) == 10 and d.startswith("1624"):
        d = "0" + d
    if len(d) == 11 and d.startswith("0"):
        return f"{d[:5]} {d[5:]}"
    return raw.strip()


def iso(d: str) -> str:
    day, month, year = d.split("/")
    return f"{year}-{month}-{day}"


def find_columns(words):
    """Column centre x-positions from the header row, or None if no header."""
    found = {}
    for key, labels in HEADER_WORDS.items():
        xs = [(w["x0"] + w["x1"]) / 2 for w in words if w["text"] in labels]
        if xs:
            found[key] = statistics.mean(xs)
    if not {"locality", "start", "end", "activity"} <= found.keys():
        return None
    if "road" not in found and "promoter" in found:
        found["road"] = (found["promoter"] + found["locality"]) / 2
    if "type" not in found:
        found["type"] = (found["locality"] + found["start"]) / 2
    if not set(COLS) <= found.keys():
        return None
    header_bottom = max(w["bottom"] for w in words
                        if w["text"] in {"Start", "End", "Locality", "Activity"})
    return found, header_bottom


def boundaries_for(centres: dict, page) -> list[tuple[str, float]]:
    """Right-hand edge of each column. Uses the table's own cell borders where
    the PDF has them (much more accurate than halfway between header words,
    because text is centred in cells of different widths)."""
    edges = sorted({round(r["x0"], 1) for r in page.rects} | {round(r["x1"], 1) for r in page.rects})
    order = sorted(centres.items(), key=lambda kv: kv[1])
    out = []
    for (k, c), (_, nxt) in zip(order, order[1:]):
        between = [e for e in edges if c + 3 < e < nxt - 3]
        mid = (c + nxt) / 2
        out.append((k, min(between, key=lambda e: abs(e - mid)) if between else mid))
    out.append((order[-1][0], float("inf")))
    return out


def column_of(x: float, bounds: list) -> str:
    for k, right in bounds:
        if x < right:
            return k
    return bounds[-1][0]


def parse_pdf(path: Path) -> tuple[list[dict], dict]:
    rows: list[dict] = []
    period = {}
    centres = None
    with pdfplumber.open(path) as pdf:
        first_text = pdf.pages[0].extract_text() or ""
        m = PERIOD_RE.search(first_text.replace("\n", " "))
        if m:
            d1, m1, y1, d2, m2, y2 = m.groups()
            try:
                frm = dt.date(int(y1 or y2), MONTHS[m1.lower()], int(d1))
                to = dt.date(int(y2), MONTHS[m2.lower()], int(d2))
                period = {"from": frm.isoformat(), "to": to.isoformat()}
            except (KeyError, ValueError):
                pass

        for page in pdf.pages:
            words = page.extract_words(keep_blank_chars=False)
            if not words:
                continue
            hdr = find_columns(words)
            top_limit = 0.0
            if hdr:
                centres, top_limit = hdr
            if not centres:
                continue
            if hdr or page.rects:
                bounds = boundaries_for(centres, page)

            # Anchors: lines with a start AND end date in the date columns.
            dates = [w for w in words if DATE_RE.match(w["text"]) and w["top"] > top_limit]
            anchors = []
            for w in sorted(dates, key=lambda w: (round(w["top"]), w["x0"])):
                col = column_of((w["x0"] + w["x1"]) / 2, bounds)
                mid = (w["top"] + w["bottom"]) / 2
                if col == "start":
                    anchors.append({"y": mid, "start": w["text"], "end": None})
                elif col == "end" and anchors and abs(anchors[-1]["y"] - mid) < 4:
                    anchors[-1]["end"] = w["text"]
            anchors = [a for a in anchors if a["end"]]
            if not anchors:
                continue

            ys = [a["y"] for a in anchors]
            gaps = [b - a for a, b in zip(ys, ys[1:])]
            half = (statistics.median(gaps) / 2) if gaps else 20.0
            links = [h for h in page.hyperlinks if "one.network" in (h.get("uri") or "")]

            for i, a in enumerate(anchors):
                lo = (ys[i - 1] + a["y"]) / 2 if i > 0 else max(top_limit, a["y"] - half * 1.3)
                hi = (ys[i + 1] + a["y"]) / 2 if i + 1 < len(anchors) else a["y"] + half * 1.3
                cells = {k: [] for k in COLS}
                for w in words:
                    yc = (w["top"] + w["bottom"]) / 2
                    if lo <= yc < hi and w["top"] > top_limit:
                        cells[column_of((w["x0"] + w["x1"]) / 2, bounds)].append(w)
                text = {}
                for k, ws in cells.items():
                    ws.sort(key=lambda w: (round(w["top"] / 3), w["x0"]))
                    text[k] = tidy(" ".join(w["text"] for w in ws))
                link = ""
                for h in links:
                    yc = (h["top"] + h["bottom"]) / 2
                    if lo <= yc < hi:
                        link = h["uri"]
                        break
                rows.append({
                    "promoter": text["promoter"],
                    "road": text["road"],
                    "locality": text["locality"],
                    "typeLabel": text["type"],
                    "start": a["start"],
                    "end": a["end"],
                    "activity": text["activity"],
                    "phone": text["phone"],
                    "link": link,
                })
    return rows, period


def build():
    pdfs = sorted(LISTS.glob("*.pdf"))
    if not pdfs:
        print("No PDFs in roads/lists/ yet — writing an empty list.")

    # ROADS_TODAY lets the script be tested against old lists.
    today = (dt.date.fromisoformat(os.environ["ROADS_TODAY"])
             if os.environ.get("ROADS_TODAY") else dt.date.today())
    seen = {}
    lists = []
    for path in pdfs:
        rows, period = parse_pdf(path)
        if not rows:
            sys.exit(f"ERROR: no rows found in {path.name}. The layout may have changed; "
                     "road_closures.json was left as it was.")
        print(f"{path.name}: {len(rows)} rows, period {period or '?'}")
        lists.append({"file": path.name, **period, "rows": len(rows)})
        for r in rows:
            start, end = iso(r["start"]), iso(r["end"])
            if end < start:
                start, end = end, start
            road = r["road"] or "Various"
            locality = r["locality"] or ""
            key = "|".join(x.lower() for x in (road, locality, start, end, r["typeLabel"]))
            uid = hashlib.sha1(key.encode()).hexdigest()[:10]
            item = {
                "id": uid,
                "road": road,
                "locality": locality,
                "area": area_for(locality, road),
                "kind": kind_for(r["typeLabel"], road),
                "type": r["typeLabel"] or "Restriction",
                "startDate": start,
                "endDate": end,
                "reason": r["activity"],
                "promoter": r["promoter"],
                "helpline": fmt_phone(r["phone"]),
                "mapUrl": r["link"],
                "list": path.name,
            }
            seen[uid] = item  # later lists win if a row is repeated

    keep_from = (today - dt.timedelta(days=1)).isoformat()
    items = sorted((i for i in seen.values() if i["endDate"] >= keep_from),
                   key=lambda i: (i["startDate"], i["endDate"], i["road"]))

    periods = [l for l in lists if "to" in l]
    latest = max(periods, key=lambda l: l["to"]) if periods else None
    out = {
        "schemaVersion": 1,
        "updated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "Isle of Man Government, Department of Infrastructure — upcoming TTRNs "
                  "issued for road works & events",
        "sourceUrl": SOURCE_PAGE,
        "roadwatchUrl": ROADWATCH,
        "note": "Only planned works with a Temporary Traffic Restriction Notice. Temporary "
                "traffic lights and emergency closures are not included; check Roadwatch "
                "for live information.",
        "latestList": ({"from": latest["from"], "to": latest["to"], "file": latest["file"]}
                       if latest else None),
        "count": len(items),
        "items": items,
    }
    # Keep the old timestamp if nothing else changed, so the daily run only
    # commits when the list itself changes.
    try:
        prev = json.loads(OUT.read_text(encoding="utf-8"))
        if prev.get("items") == out["items"] and prev.get("latestList") == out["latestList"]:
            out["updated"] = prev.get("updated", out["updated"])
    except (OSError, ValueError):
        pass
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(items)} current/upcoming items to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    build()
