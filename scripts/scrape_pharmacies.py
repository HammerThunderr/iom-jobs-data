#!/usr/bin/env python3
"""
scrape_pharmacies.py  —  Isle of Man community pharmacies -> docs/pharmacies.json

Source : https://www.gov.im/categories/health-and-wellbeing/pharmacy-services/community-pharmacies/
Licence: Open Government Licence v3.0 (attribution kept in the JSON meta).

DESIGN NOTE — why this does not hard-code heading levels
--------------------------------------------------------
Two earlier versions failed because they assumed the page markup:
  v1 assumed h2 = area, h3 = pharmacy, and that hours/phone lines were plain
     text -> every record came out with empty hours and phone.
  v2 fixed the <strong> label reading but kept the h2/h3 assumption -> only
     1 record parsed.

So this version is structure-agnostic. It walks EVERY heading (h2..h5) and
classifies it by what sits underneath:
    - contains a postcode or a telephone  -> it is a PHARMACY
    - otherwise                            -> it is an AREA heading
That survives gov.im changing heading levels, which they evidently have.

Run with --debug to print what it found without writing anything:
    python scrape_pharmacies.py --debug

SAFETY: refuses to write if too few records parse, or if most records are
missing opening hours. For health information a stale-but-correct file beats a
fresh empty one.
"""

import argparse
import datetime
import json
import os
import re
import sys

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

SOURCE_URL = (
    "https://www.gov.im/categories/health-and-wellbeing/"
    "pharmacy-services/community-pharmacies/"
)
OUT_PATH = os.environ.get("PHARMACY_OUT", "docs/pharmacies.json")
USER_AGENT = "ManxOneBot/1.0 (+https://manxone.hammerlabs.app)"

EXPECTED_MIN = 20
MIN_HOURS_RATIO = 0.75

POSTCODE_RE = re.compile(r"\bIM\d{1,2}\s?\d[A-Z]{2}\b")
PHONE_RE = re.compile(r"(?i)\b(telephone|tel|phone|fax)\b")
HEADINGS = ("h2", "h3", "h4", "h5")

DAY_LABELS = (
    ("monday to friday", "monFri"),
    ("monday to saturday", "monFri"),
    ("monday - friday", "monFri"),
    ("monday-friday", "monFri"),
    ("monday", "monFri"),
    ("saturday", "sat"),
    ("sunday", "sun"),
)

SKIP_HEADINGS = {
    "community pharmacies", "related", "share this page",
}

# Sub-headings that BELONG TO the pharmacy above them. The hours usually live
# under one of these, so they must be parsed as a continuation of the current
# pharmacy -- not skipped, and not counted as a new pharmacy. Getting this
# wrong is why an earlier run reported 37 records with only 11 sets of hours.
CONTINUATION_HEADINGS = (
    "opening hours", "opening times", "hours", "contact", "contact details",
    "telephone", "services", "pharmacy services", "services provided",
)


def clean(s):
    return re.sub(r"\s+", " ", (s or "")).replace("\xa0", " ").strip()


def norm_phone(s):
    s = re.sub(r"(?i)^.*?(telephone\s*&\s*fax|telephone|tel|phone|fax)\s*:?", "", s)
    return re.sub(r"[^\d+]", "", s)


def pretty_phone(d):
    return f"+44 1624 {d[7:]}" if d.startswith("+441624") and len(d) > 7 else d


def fix_postcode(s):
    return re.sub(r"\b1M(\d)", r"IM\1", s)


def block_after(heading):
    """All sibling tags between this heading and the next heading."""
    out = []
    for sib in heading.next_siblings:
        if isinstance(sib, Tag):
            if sib.name in HEADINGS:
                break
            out.append(sib)
    return out


def value_after_strong(strong):
    parts = []
    for sib in strong.next_siblings:
        if isinstance(sib, Tag) and sib.name in ("br", "strong"):
            break
        parts.append(sib if isinstance(sib, NavigableString) else sib.get_text())
    return clean("".join(str(p) for p in parts)).lstrip(":").strip()


def parse_block(block):
    rec = {"phone": "", "hours": {"monFri": "", "sat": "", "sun": ""},
           "address_lines": [], "services": []}

    for node in block:
        if node.name == "ul":
            rec["services"] += [clean(li.get_text()) for li in node.find_all("li")]
            continue
        if node.name not in ("p", "div", "span"):
            continue

        labelled = False
        for strong in node.find_all(["strong", "b"]):
            label = clean(strong.get_text()).lower().rstrip(":").strip()
            value = value_after_strong(strong)
            if not value:
                continue
            if label.startswith(("telephone", "tel", "phone", "fax")):
                if not rec["phone"] and "fax" not in label.split()[0]:
                    rec["phone"] = norm_phone(value)
                elif not rec["phone"]:
                    rec["phone"] = norm_phone(value)
                labelled = True
                continue
            for key, slot in DAY_LABELS:
                if label.startswith(key):
                    rec["hours"][slot] = value
                    labelled = True
                    break

        text_lines = [clean(x) for x in node.get_text("\n").split("\n") if clean(x)]

        # Unlabelled fallback: "Monday to Friday: 9am to 6pm" as plain text.
        for line in text_lines:
            low = line.lower()
            if PHONE_RE.match(low) or low.startswith(("telephone", "tel:", "phone")):
                if not rec["phone"]:
                    rec["phone"] = norm_phone(line)
                labelled = True
                continue
            matched = False
            for key, slot in DAY_LABELS:
                if low.startswith(key):
                    if not rec["hours"][slot]:
                        rec["hours"][slot] = clean(line.split(":", 1)[-1])
                    matched = True
                    labelled = True
                    break
            if matched:
                continue
            if re.fullmatch(r"[\d\s+()-]{9,}", line):
                if not rec["phone"]:
                    rec["phone"] = norm_phone(line)
                labelled = True
                continue
            if not labelled:
                rec["address_lines"].append(fix_postcode(line))

    return rec


def scrape(debug=False):
    resp = requests.get(SOURCE_URL, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    root = (soup.find("div", id="content") or soup.find("main")
            or soup.find("article") or soup.body)

    pharmacies, area = [], None

    for heading in root.find_all(HEADINGS):
        title = clean(heading.get_text())
        if not title or title.lower() in SKIP_HEADINGS:
            continue

        block = block_after(heading)
        block_text = " ".join(n.get_text(" ") for n in block if isinstance(n, Tag))
        low_title = title.lower().rstrip(":").strip()

        # A sub-heading belonging to the pharmacy above: merge its data in.
        if low_title.startswith(CONTINUATION_HEADINGS) and pharmacies:
            extra = parse_block(block)
            target = pharmacies[-1]
            for slot in ("monFri", "sat", "sun"):
                if not target["hours"][slot] and extra["hours"][slot]:
                    target["hours"][slot] = extra["hours"][slot]
            if not target["phone"] and extra["phone"]:
                target["phone"] = extra["phone"]
                target["phoneDisplay"] = pretty_phone(extra["phone"])
            for sv in extra["services"]:
                if sv not in target["services"]:
                    target["services"].append(sv)
            if debug:
                print(f"[{heading.name}] {title[:44]:<46} -> merged into "
                      f"{target['name'][:28]}")
            continue

        # A NEW pharmacy must have a postcode beneath it. Requiring a postcode
        # (rather than just a phone number) stops nav/footer blocks and stray
        # sub-headings being counted as pharmacies.
        looks_like_pharmacy = bool(POSTCODE_RE.search(block_text))

        if debug:
            print(f"[{heading.name}] {title[:44]:<46} "
                  f"{'PHARMACY' if looks_like_pharmacy else 'area?'}")

        if not looks_like_pharmacy:
            area = title
            continue

        rec = parse_block(block)
        if not rec["address_lines"] and not rec["phone"]:
            continue

        postcode = ""
        for ln in rec["address_lines"]:
            m = POSTCODE_RE.search(ln)
            if m:
                postcode = m.group(0)
                break
        addr = [ln for ln in rec["address_lines"] if ln != postcode]
        full = ", ".join(addr + ([postcode] if postcode else []) + ["Isle of Man"])

        pharmacies.append({
            "name": title,
            "area": area or "",
            "address": addr,
            "postcode": postcode,
            "addressText": ", ".join(addr + ([postcode] if postcode else [])),
            "phone": rec["phone"],
            "phoneDisplay": pretty_phone(rec["phone"]) if rec["phone"] else None,
            "hours": rec["hours"],
            "services": rec["services"],
            "mapsQuery": f"{title}, {full}",
        })

    with_hours = sum(1 for p in pharmacies if p["hours"]["monFri"])
    with_phone = sum(1 for p in pharmacies if p["phone"])
    print(f"Parsed {len(pharmacies)} pharmacies "
          f"({with_hours} with hours, {with_phone} with phone).")

    if debug:
        for p in pharmacies[:3]:
            print(json.dumps(p, indent=1, ensure_ascii=False))

    def _dump():
        print("\n--- diagnostic: first 5 parsed records ---", file=sys.stderr)
        for p in pharmacies[:5]:
            print(f"  {p['name']} | area={p['area']} | pc={p['postcode']} | "
                  f"phone={p['phone']} | hours={p['hours']}", file=sys.stderr)
        print("--- headings on page ---", file=sys.stderr)
        for h in root.find_all(HEADINGS)[:60]:
            print(f"  <{h.name}> {clean(h.get_text())[:60]}", file=sys.stderr)

    if len(pharmacies) < EXPECTED_MIN:
        _dump()
        raise RuntimeError(
            f"Only parsed {len(pharmacies)} pharmacies (expected >= {EXPECTED_MIN}). "
            "Refusing to overwrite.")

    if with_hours / max(len(pharmacies), 1) < MIN_HOURS_RATIO:
        _dump()
        raise RuntimeError(
            f"Only {with_hours}/{len(pharmacies)} records have opening hours. "
            "Refusing to overwrite good data with empty data.")

    return {
        "meta": {
            "schemaVersion": 1,
            "generated": datetime.date.today().isoformat(),
            "source": "Isle of Man Government - Community Pharmacies",
            "sourceUrl": SOURCE_URL,
            "licence": "Open Government Licence v3.0",
            "attribution": ("Contains public sector information licensed under "
                            "the Open Government Licence v3.0."),
            "note": ("Routine opening hours. Sunday and bank-holiday cover is via "
                     "the pharmacy rota. Hours may vary on public holidays."),
            "count": len(pharmacies),
        },
        "pharmacies": pharmacies,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--debug", action="store_true",
                    help="print headings found and do not write the file")
    args = ap.parse_args()

    data = scrape(debug=args.debug)
    if args.debug:
        print("\n--debug: nothing written.")
        return

    os.makedirs(os.path.dirname(OUT_PATH) or ".", exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"Wrote {data['meta']['count']} pharmacies to {OUT_PATH}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
