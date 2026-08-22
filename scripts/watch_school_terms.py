#!/usr/bin/env python3
"""
watch_school_terms.py  —  change monitor for Isle of Man school term dates.

WHY A WATCHER RATHER THAN A SCRAPER
-----------------------------------
School term dates are published YEARS ahead and change very rarely, unlike the
pharmacy rota or the race schedule. Scraping them on a schedule is all risk and
no benefit: one bad parse could overwrite three years of correct dates with
rubbish. (That is exactly what happened to pharmacies.json.)

So this script NEVER edits docs/school_terms.json. It fetches the DESC page,
hashes the date-bearing text, and reports whether it changed. The workflow then
opens a GitHub issue so a human updates the JSON deliberately.

desc.gov.im sits behind an F5 firewall that rejects some automated requests.
"Blocked" and "unreachable" are reported as their own statuses and are NOT
treated as failures -- "we could not check" is not "the dates changed".

Exit code is always 0. Status is written to $GITHUB_OUTPUT as status=<value>:
    first_run | unchanged | changed | blocked | unreachable
"""

import hashlib
import os
import pathlib
import re
import sys

import requests

URL = "https://desc.gov.im/education/education/school-holidays/"
HASH_FILE = pathlib.Path(".watch/school_terms.sha256")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def emit(status: str) -> None:
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"status={status}\n")
    print(f"status={status}")


def visible_text(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"&[a-z]+;", " ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def date_core(text: str) -> str:
    """Just the date-bearing section, so page furniture churn is ignored."""
    m = re.search(r"autumn term.{0,4000}?close for summer.{0,200}", text)
    if m:
        return m.group(0)
    dates = re.findall(
        r"\b\d{1,2}(?:st|nd|rd|th)?\s+"
        r"(?:january|february|march|april|may|june|july|august|september|"
        r"october|november|december)\s+\d{4}\b", text)
    return "|".join(dates) if dates else text


def main() -> int:
    try:
        resp = requests.get(URL, headers={"User-Agent": UA}, timeout=30)
    except Exception as exc:  # noqa: BLE001
        print(f"Could not reach DESC: {exc}", file=sys.stderr)
        emit("unreachable")
        return 0

    if resp.status_code != 200 or not resp.text.strip():
        print(f"DESC returned HTTP {resp.status_code}", file=sys.stderr)
        emit("unreachable")
        return 0

    if re.search(r"(?i)request rejected|access denied|support id", resp.text):
        print("DESC firewall rejected the request.", file=sys.stderr)
        emit("blocked")
        return 0

    core = date_core(visible_text(resp.text))
    if len(core) < 80:
        print("Fetched page but found no date content - treating as blocked.",
              file=sys.stderr)
        emit("blocked")
        return 0

    new = hashlib.sha256(core.encode("utf-8")).hexdigest()
    old = HASH_FILE.read_text().strip() if HASH_FILE.exists() else None

    HASH_FILE.parent.mkdir(parents=True, exist_ok=True)
    HASH_FILE.write_text(new + "\n")

    if old is None:
        print("Baseline recorded.")
        emit("first_run")
    elif old == new:
        print("No change.")
        emit("unchanged")
    else:
        print(f"CHANGED\n  was: {old}\n  now: {new}")
        emit("changed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
