#!/usr/bin/env python3
"""
scrape_pharmacies.py

Scrapes the Isle of Man Government "Community Pharmacies" page and writes
docs/pharmacies.json for the Manx One app.

Source : https://www.gov.im/categories/health-and-wellbeing/pharmacy-services/community-pharmacies/
Licence: Open Government Licence v3.0 (attribution retained in the JSON meta).

WHY THE PARSING LOOKS FUSSY
---------------------------
The hours and telephone lines on gov.im sit inside <strong> tags:

    <p><strong>Telephone:</strong> +44 1624 824793</p>
    <p><strong>Monday to Friday:</strong> 9am to 6pm<br>
       <strong>Saturday:</strong> 9am to 1pm<br>
       <strong>Sunday:</strong> Closed</p>

An earlier version split the <p> on <br> and looked for lines *starting* with
"Telephone"/"Monday" — but get_text() puts the label and value together in ways
that did not match, so every record came out with empty hours and phone. This
version reads the <strong> label and takes the text that follows it, which is
robust to the label being bold, having a colon or not, etc.

SAFETY: refuses to overwrite the JSON if the scrape looks broken (too few
records, or most records missing hours). A stale-but-correct file beats a fresh
empty one for health information.

Pipeline: Python scraper (GitHub Actions) -> docs/pharmacies.json -> Pages -> Flutter
"""

import datetime
import json
import os
import re
import sys

import requests
from bs4 import BeautifulSoup, NavigableString

SOURCE_URL = (
    "https://www.gov.im/categories/health-and-wellbeing/"
    "pharmacy-services/community-pharmacies/"
)
OUT_PATH = os.environ.get("PHARMACY_OUT", "docs/pharmacies.json")
USER_AGENT = "ManxOneBot/1.0 (+https://manxone.hammerlabs.app)"

EXPECTED_MIN = 20          # fewer than this => template changed
MIN_HOURS_RATIO = 0.75     # at least this share must have Mon-Fri hours

POSTCODE_RE = re.compile(r"\bIM\d{1,2}\s?\d[A-Z]{2}\b")

DAY_LABELS = {
    "monday to friday": "monFri",
    "monday to saturday": "monFri",
    "monday - friday": "monFri",
    "monday": "monFri",
    "saturday": "sat",
    "sunday": "sun",
}


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).replace("\xa0", " ").strip()


def norm_phone(s: str) -> str:
    s = re.sub(r"(?i)^.*?(telephone|tel|phone)\s*:?", "", s)
    return re.sub(r"[^\d+]", "", s)


def pretty_phone(digits: str) -> str:
    if digits.startswith("+441624") and len(digits) > 7:
        return f"+44 1624 {digits[7:]}"
    return digits


def fix_postcode(s: str) -> str:
    return re.sub(r"\b1M(\d)", r"IM\1", s)


def value_after_strong(strong) -> str:
    """Text following a <strong> label, up to the next <br> or <strong>."""
    parts = []
    for sib in strong.next_siblings:
        if getattr(sib, "name", None) in ("br", "strong"):
            break
        parts.append(sib if isinstance(sib, NavigableString) else sib.get_text())
    return clean("".join(str(p) for p in parts)).lstrip(":").strip()


def parse_p(p, out):
    """Pull phone / hours / address lines out of one <p>."""
    handled_labels = False

    for strong in p.find_all("strong"):
        label = clean(strong.get_text()).lower().rstrip(":").strip()
        value = value_after_strong(strong)
        if not value:
            continue
        if label.startswith(("telephone", "tel", "phone")):
            if not out["phone"]:
                out["phone"] = norm_phone(value)
            handled_labels = True
        elif label.startswith("fax"):
            handled_labels = True
        else:
            for key, slot in DAY_LABELS.items():
                if label.startswith(key):
                    out["hours"][slot] = value
                    handled_labels = True
                    break

    if handled_labels:
        return

    # Plain <p>: address lines (and the odd unlabelled phone number).
    for line in [clean(x) for x in p.get_text("\n").split("\n") if clean(x)]:
        low = line.lower()
        if low.startswith(("telephone", "tel ", "tel:", "phone")):
            if not out["phone"]:
                out["phone"] = norm_phone(line)
        elif low.startswith("fax"):
            continue
        elif re.fullmatch(r"[\d\s+()-]{9,}", line):
            if not out["phone"]:
                out["phone"] = norm_phone(line)
        else:
            out["address_lines"].append(fix_postcode(line))


def scrape() -> dict:
    resp = requests.get(SOURCE_URL, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    content = (
        soup.find("div", id="content")
        or soup.find("main")
        or soup.find("article")
        or soup.body
    )

    pharmacies = []
    area = None

    for el in content.find_all(["h2", "h3"]):
        title = clean(el.get_text())
        if not title:
            continue

        if el.name == "h2":
            if title.lower() != "community pharmacies":
                area = title
            continue

        out = {
            "phone": "",
            "hours": {"monFri": "", "sat": "", "sun": ""},
            "address_lines": [],
            "services": [],
        }

        for sib in el.next_siblings:
            name = getattr(sib, "name", None)
            if name in ("h2", "h3"):
                break
            if name == "ul":
                out["services"] += [clean(li.get_text()) for li in sib.find_all("li")]
            elif name == "p":
                parse_p(sib, out)

        if not out["address_lines"]:
            continue

        postcode = ""
        for ln in out["address_lines"]:
            m = POSTCODE_RE.search(ln)
            if m:
                postcode = m.group(0)
                break
        addr = [ln for ln in out["address_lines"] if ln != postcode]

        full = ", ".join(addr + ([postcode] if postcode else []) + ["Isle of Man"])
        pharmacies.append({
            "name": title,
            "area": area,
            "address": addr,
            "postcode": postcode,
            "addressText": ", ".join(addr + ([postcode] if postcode else [])),
            "phone": out["phone"],
            "phoneDisplay": pretty_phone(out["phone"]) if out["phone"] else None,
            "hours": out["hours"],
            "services": out["services"],
            "mapsQuery": f"{title}, {full}",
        })

    # --- sanity gates -------------------------------------------------
    if len(pharmacies) < EXPECTED_MIN:
        raise RuntimeError(
            f"Only parsed {len(pharmacies)} pharmacies (expected >= {EXPECTED_MIN}). "
            "gov.im template may have changed — refusing to overwrite."
        )

    with_hours = sum(1 for p in pharmacies if p["hours"]["monFri"])
    ratio = with_hours / len(pharmacies)
    if ratio < MIN_HOURS_RATIO:
        raise RuntimeError(
            f"Only {with_hours}/{len(pharmacies)} records have opening hours "
            f"({ratio:.0%}). Refusing to overwrite a good file with empty data."
        )

    with_phone = sum(1 for p in pharmacies if p["phone"])
    print(f"Parsed {len(pharmacies)} pharmacies "
          f"({with_hours} with hours, {with_phone} with phone).")

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
    data = scrape()
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
