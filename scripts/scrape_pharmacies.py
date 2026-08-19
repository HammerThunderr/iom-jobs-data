#!/usr/bin/env python3
"""
scrape_pharmacies.py

Scrapes the Isle of Man Government "Community Pharmacies" page and writes
docs/pharmacies.json for the Manx One app.

Source : https://www.gov.im/categories/health-and-wellbeing/pharmacy-services/community-pharmacies/
Licence: Open Government Licence v3.0 (attribution retained in the JSON meta).

Pipeline (same pattern as the other feeds):
    Python scraper (GitHub Actions) -> docs/pharmacies.json -> GitHub Pages -> Flutter

The page is server-rendered and laid out as:
    <h2>Area</h2>
      <h3>Pharmacy name</h3>
        <p> address line<br> address line<br> POSTCODE<br>
            <strong>Telephone...</strong> number </p>
        <h4>Opening hours</h4>
        <p><strong>Monday to Friday:</strong> ...<br>
           <strong>Saturday:</strong> ...<br>
           <strong>Sunday:</strong> ... </p>
        <ul><li>service</li>...</ul>

Selectors may need a small tweak if gov.im changes their template — run once and
eyeball the output; the FALLBACK count check will shout if it grabbed too few.
"""

import json
import re
import sys
import datetime

import requests
from bs4 import BeautifulSoup

SOURCE_URL = (
    "https://www.gov.im/categories/health-and-wellbeing/"
    "pharmacy-services/community-pharmacies/"
)
OUT_PATH = "docs/pharmacies.json"
USER_AGENT = "ManxOneBot/1.0 (+https://manxone.hammerlabs.app)"

# Areas we expect — used only as a sanity check on the scrape.
EXPECTED_MIN = 20

POSTCODE_RE = re.compile(r"\bIM\d{1,2}\s?\d[A-Z]{2}\b")


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def norm_phone(s: str) -> str:
    """Keep leading + and digits only, e.g. '+44 1624 824793' -> '+441624824793'."""
    s = s.split(":", 1)[-1]
    return re.sub(r"[^\d+]", "", s)


def fix_postcode(s: str) -> str:
    # gov.im occasionally OCRs 'IM1' as '1M1'; repair the leading digit.
    return re.sub(r"\b1M(\d)", r"IM\1", s)


def lines_from_p(p) -> list:
    """Return visible text lines from a <p>, split on <br>."""
    raw = p.get_text("\n")
    return [clean(x) for x in raw.split("\n") if clean(x)]


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
            # 'Community Pharmacies' is the page title, not an area.
            if title.lower() != "community pharmacies":
                area = title
            continue

        # el.name == 'h3'  -> a pharmacy
        name = title
        addr_lines, phone = [], None
        hours = {"monFri": None, "sat": None, "sun": None}
        services = []
        capturing_hours = False

        for sib in el.next_siblings:
            sib_name = getattr(sib, "name", None)
            if sib_name in ("h2", "h3"):
                break  # next entry starts
            if sib_name == "h4":
                capturing_hours = "opening" in clean(sib.get_text()).lower()
                continue
            if sib_name == "ul":
                services += [clean(li.get_text()) for li in sib.find_all("li")]
                continue
            if sib_name == "p":
                for line in lines_from_p(sib):
                    low = line.lower()
                    if low.startswith(("telephone", "tel ", "tel:")) or "telephone & fax" in low:
                        phone = norm_phone(line)
                    elif low.startswith("fax"):
                        pass  # ignore fax
                    elif low.startswith("monday"):
                        hours["monFri"] = clean(line.split(":", 1)[-1])
                    elif low.startswith("saturday"):
                        hours["sat"] = clean(line.split(":", 1)[-1])
                    elif low.startswith("sunday"):
                        hours["sun"] = clean(line.split(":", 1)[-1])
                    elif re.search(r"\+?\d{6,}", line):
                        # a bare phone/fax number line without a label
                        if phone is None:
                            phone = norm_phone(line)
                    elif not capturing_hours:
                        addr_lines.append(fix_postcode(line))

        if not addr_lines:
            continue  # not a real entry

        # Postcode = the address line that matches the IM pattern.
        postcode = None
        for ln in addr_lines:
            m = POSTCODE_RE.search(ln)
            if m:
                postcode = m.group(0)
                break
        # Drop the standalone postcode line from the address list.
        addr = [ln for ln in addr_lines if ln != postcode]

        full = ", ".join(addr + ([postcode] if postcode else []) + ["Isle of Man"])
        pharmacies.append({
            "name": name,
            "area": area,
            "address": addr,
            "postcode": postcode,
            "addressText": ", ".join(addr + ([postcode] if postcode else [])),
            "phone": phone,
            "phoneDisplay": (
                phone.replace("+441624", "+44 1624 ") if phone else None
            ),
            "hours": hours,
            "services": services,
            "mapsQuery": f"{name}, {full}",
        })

    if len(pharmacies) < EXPECTED_MIN:
        raise RuntimeError(
            f"Only parsed {len(pharmacies)} pharmacies (expected >= {EXPECTED_MIN}). "
            "The gov.im template may have changed — check the selectors."
        )

    return {
        "meta": {
            "schemaVersion": 1,
            "generated": datetime.date.today().isoformat(),
            "source": "Isle of Man Government - Community Pharmacies",
            "sourceUrl": SOURCE_URL,
            "licence": "Open Government Licence v3.0",
            "attribution": (
                "Contains public sector information licensed under the "
                "Open Government Licence v3.0."
            ),
            "note": (
                "Routine opening hours. Sunday and bank-holiday cover is via "
                "the pharmacy rota."
            ),
            "count": len(pharmacies),
        },
        "pharmacies": pharmacies,
    }


def main():
    data = scrape()
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
