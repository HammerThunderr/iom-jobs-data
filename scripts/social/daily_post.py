"""
Daily community post — "Today on the Island".

Reads the data files this repo already keeps fresh (docs/*.json) and writes a
short, friendly morning round-up of what is NEW or HAPPENING TODAY:

  weather + warnings, ferries (and any disruption or new Steam Packet notice),
  road closures starting today (and a new fortnightly list), tonight's events
  and newly announced ones, new jobs, new homes and price drops, Sunday /
  bank-holiday duty pharmacies, bank holidays and school dates coming up,
  cruise ships, tides.

Only things that are fresh make it in: social/state.json remembers which
jobs, events, price drops, notices and lists have already been mentioned, so
the same item is never announced twice.

Output:
  docs/social/today.json  — {date, text, sections} (the app can show it too)
  docs/social/today.txt   — the post text, ready to copy

Posting: if FB_PAGE_ID and FB_PAGE_TOKEN are set (GitHub secrets), the text
is posted to that Facebook Page. Without them the script only writes the
files. DRY_RUN=1 only prints a preview (never posts, never writes files).
SOCIAL_DATE=YYYY-MM-DD fakes "today" for tests — use it with DRY_RUN.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
STATE = ROOT / "social" / "state.json"
OUT_JSON = DOCS / "social" / "today.json"
OUT_TXT = DOCS / "social" / "today.txt"

APP_URL = "https://manxone.hammerlabs.app"
TZ = ZoneInfo("Europe/Isle_of_Man")
MAX_LEN = 1900  # keep it readable on a phone


# ── helpers ────────────────────────────────────────────────────────────────

def load(name):
    try:
        return json.loads((DOCS / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def h(s: str) -> str:
    return hashlib.sha1(s.encode()).hexdigest()[:12]


def d(s) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def nice(day: dt.date, ref: dt.date | None = None) -> str:
    year = f" {day.year}" if ref and day.year != ref.year else ""
    return f"{day:%a} {day.day} {day:%b}{year}"


def cut(s: str, n: int) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0] + "…"


def money(v) -> str:
    try:
        return f"£{int(v):,}"
    except (TypeError, ValueError):
        return ""


# ── sections ───────────────────────────────────────────────────────────────

def weather(today):
    data = load("weather_5day.json")
    if not data or not data.get("items"):
        return None
    item = data["items"][0]
    m = re.search(r"as of (\d{1,2} \w+ \d{4})", item.get("title", ""))
    try:
        issued = dt.datetime.strptime(m.group(1), "%d %B %Y").date() if m else None
    except ValueError:
        issued = None
    text = item.get("description", "")
    blocks = dict(re.findall(r"##([^#]+)##\s*(.*?)(?=\n##|\Z)", text, re.S))
    if issued == today:
        key = "Today"
    elif issued == today - dt.timedelta(days=1):
        key = "Tomorrow"
    else:
        return None
    body = blocks.get(key, "").strip()
    if not body:
        return None
    forecast, _, comments = body.partition("Comments:")
    line = f"🌤️ Weather: {cut(forecast, 220)}"
    comments = comments.strip().rstrip(".")
    if comments and comments.lower() != "nil":
        line += f"\n⚠️ {cut(comments, 200)}"
    return line


def ferries(today, state):
    data = load("ferry.json")
    if not data:
        return None
    lines = []
    label = f"{today:%A}, {today.day} {today:%B %Y}"
    day = next((x for x in data.get("days", []) if x.get("date") == label), None)
    if day:
        sailings = day.get("sailings", [])
        bad = [s for s in sailings
               if s.get("statusType") not in ("scheduled", "departed", "arrived", "ontime", "boarding")]
        if bad:
            for s in bad[:4]:
                lines.append(f"⛴️ {s.get('departTime')} {s.get('departPort')} → {s.get('arrivePort')}: "
                             f"{s.get('status')}")
        elif sailings:
            lines.append(f"⛴️ Ferries: {len(sailings)} sailings today, all running as planned so far")
    notice = (data.get("notice") or "").strip()
    if notice and h(notice) not in state["notices"]:
        state["notices"].append(h(notice))
        lines.append(f"📢 Steam Packet: {cut(notice, 220)}")
    return "\n".join(lines) or None


def roads(today, state):
    data = load("road_closures.json")
    if not data:
        return None
    lines = []
    latest = data.get("latestList") or {}
    if latest.get("file") and latest["file"] not in state["lists"]:
        state["lists"].append(latest["file"])
        fr, to = d(latest.get("from")), d(latest.get("to"))
        if fr and to:
            lines.append(f"🚧 New road closures list out ({nice(fr)} – {nice(to)}): "
                         f"{data.get('count', 0)} planned closures and restrictions")
    starting = [i for i in data.get("items", []) if d(i.get("startDate")) == today]
    if starting:
        lines.append("🚧 Starting today:")
        for i in starting[:6]:
            end = d(i.get("endDate"))
            until = "today only" if end == today else f"until {nice(end)}" if end else ""
            what = i.get("type") or "Restriction"
            lines.append(f"   • {i.get('road')}, {i.get('locality')} — {what.lower()}"
                         f"{', ' + until if until else ''} ({cut(i.get('reason', ''), 50)})")
        if len(starting) > 6:
            lines.append(f"   …and {len(starting) - 6} more")
    return "\n".join(lines) or None


def _event_dates(e):
    occ = e.get("occurrences") or []
    if occ:
        out: dict = {}
        for o in occ:
            day = d(o.get("date"))
            if day:
                t = o.get("time", "")
                out[day] = f"{out[day]} & {t}" if out.get(day) and t else (out.get(day) or t)
        return out
    start, end = d(e.get("startDate")), d(e.get("endDate")) or d(e.get("startDate"))
    if start and end and (end - start).days <= 1:  # one-off, not a months-long exhibition
        return {start: e.get("time", "")}
    return {}


def events(today, state, first_run):
    data = load("events.json")
    if not data:
        return None
    evs = data.get("events", [])
    todays = []
    for e in evs:
        dates = _event_dates(e)
        if today in dates:
            todays.append((dates[today] or e.get("time") or "", e))
    todays.sort(key=lambda t: t[0] or "99")
    lines = []
    if todays:
        lines.append("🎭 On today:")
        for time, e in todays[:5]:
            t = f"{time.split('–')[0].strip()} " if time else ""
            sold = " (sold out)" if e.get("soldOut") else ""
            lines.append(f"   • {t}{cut(e.get('title', ''), 60)} — {e.get('venue', '')}{sold}")
        if len(todays) > 5:
            lines.append(f"   …and {len(todays) - 5} more")
    shown = {e.get("id") for _, e in todays}
    new = [e for e in evs if e.get("id") and e["id"] not in state["events"]
           and e["id"] not in shown and (d(e.get("endDate") or e.get("startDate")) or today) >= today]
    for e in evs:
        if e.get("id") and e["id"] not in state["events"]:
            state["events"].append(e["id"])
    if new and not first_run:
        new.sort(key=lambda e: e.get("startDate", ""))
        lines.append("🆕 Just announced:")
        for e in new[:3]:
            sd = d(e.get("startDate"))
            lines.append(f"   • {cut(e.get('title', ''), 60)} — {e.get('venue', '')}"
                         f"{', ' + nice(sd, today) if sd else ''}")
    return "\n".join(lines) or None


def jobs(state, first_run):
    found = []
    for name, src in (("jobs.json", "JobCentre"), ("gov_jobs.json", "Government")):
        data = load(name) or {}
        for j in data.get("jobs", []):
            key = f"{src}:{j.get('jobId')}"
            if key not in state["jobs"]:
                state["jobs"].append(key)
                found.append(j)
    if first_run or not found:
        return None
    titles = ", ".join(cut(j.get("title", ""), 40) for j in found[:3])
    more = f" and {len(found) - 3} more" if len(found) > 3 else ""
    return f"💼 {len(found)} new jobs: {titles}{more}"


def property_(today, state, first_run):
    data = load("property/properties.json") or {}
    items = data.get("listings", [])
    since = today - dt.timedelta(days=1)
    new = [p for p in items if (d(p.get("firstSeen")) or dt.date.min) >= since
           and p.get("id") not in state["homes"]]
    drops = []
    for p in items:
        prev, now = p.get("previousPrice"), p.get("price")
        # Skip "listings" with no real location (e.g. "cash buyers wanted"
        # adverts) and implausible drops from a mis-read price.
        if prev and now and prev > now and p.get("locality") and now >= prev * 0.5:
            key = f"{p.get('id')}:{now}"
            if key not in state["drops"]:
                state["drops"].append(key)
                drops.append(p)
    for p in new:
        state["homes"].append(p.get("id"))
    if first_run:
        return None
    lines = []
    if new:
        sale = sum(1 for p in new if p.get("listingType") == "sale")
        rent = sum(1 for p in new if p.get("listingType") == "rent")
        bits = [f"{sale} for sale" if sale else "", f"{rent} to rent" if rent else ""]
        lines.append(f"🏠 {len(new)} new property listings ({', '.join(b for b in bits if b)})")
    if drops:
        drops.sort(key=lambda p: (p["previousPrice"] - p["price"]), reverse=True)
        p = drops[0]
        where = p.get("address") or p.get("locality")
        lines.append(f"📉 {len(drops)} price drops — biggest: {where} now {money(p['price'])}"
                     f" (was {money(p['previousPrice'])})")
    return "\n".join(lines) or None


def pharmacy(today):
    hol = holidays()
    if today.weekday() != 6 and today not in hol:
        return None
    data = load("pharmacy.json") or {}
    lines = []
    for area in data.get("areas", []):
        for e in area.get("entries", []):
            if d(e.get("date")) == today and e.get("pharmacy"):
                p = e["pharmacy"]
                lines.append(f"   • {area.get('name')}: {p.get('name')} ({p.get('hours', '')})")
    return ("💊 Duty pharmacies today:\n" + "\n".join(lines)) if lines else None


def holidays():
    data = load("bank_holidays.json") or {}
    out = {}
    for y in data.get("years", []):
        for x in y.get("holidays", []):
            if d(x.get("date")):
                out[d(x["date"])] = x.get("name", "")
    return out


def coming_up(today):
    lines = []
    for day, name in sorted(holidays().items()):
        if 0 <= (day - today).days <= 3:
            when = "today" if day == today else nice(day)
            lines.append(f"📅 Bank holiday {when}: {name}")
    data = load("school_terms.json") or {}
    for y in data.get("years", []):
        for term in y.get("terms", []):
            for ev in term.get("events", []):
                sd = d(ev.get("start"))
                if sd and 0 <= (sd - today).days <= 3 and ev.get("type") != "in_service":
                    when = "today" if sd == today else nice(sd)
                    lines.append(f"🎒 Schools: {ev.get('label')} {when}")
    bins = load("bins.json") or {}
    for ex in bins.get("exceptions", []):
        sd = d(ex.get("date"))
        if sd and 0 <= (sd - today).days <= 2:
            lines.append(f"🗑️ Bin change {nice(sd)}: {cut(ex.get('note') or ex.get('label') or '', 120)}")
    return "\n".join(lines) or None


def cruise(today):
    data = load("cruise.json") or {}
    calls = [c for c in data.get("calls", []) if d(c.get("date")) == today]
    if not calls:
        return None
    return "\n".join(f"🛳️ Cruise ship today: {c.get('ship')} at {c.get('port')} "
                     f"({c.get('eta')}–{c.get('etd')}, ~{c.get('passengers')} passengers)" for c in calls)


def tides(today):
    data = load("tides.json") or {}
    port = next((p for p in data.get("ports", []) if p.get("name") == "Douglas"), None)
    if not port:
        return None
    day = next((x for x in port.get("days", []) if d(x.get("date")) == today), None)
    if not day:
        return None
    highs = [f"{t['time']} ({t['height_m']:.1f}m)" for t in day.get("tides", []) if t.get("type") == "high"]
    return f"🌊 High tide Douglas: {' and '.join(highs)}" if highs else None


# ── main ───────────────────────────────────────────────────────────────────

def build(today: dt.date):
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    first_run = not state
    for k in ("jobs", "events", "homes", "drops", "notices", "lists"):
        state.setdefault(k, [])

    sections = [
        ("weather", weather(today)),
        ("ferries", ferries(today, state)),
        ("roads", roads(today, state)),
        ("events", events(today, state, first_run)),
        ("coming_up", coming_up(today)),
        ("pharmacy", pharmacy(today)),
        ("cruise", cruise(today)),
        ("jobs", jobs(state, first_run)),
        ("property", property_(today, state, first_run)),
        ("tides", tides(today)),
    ]
    sections = [(k, v) for k, v in sections if v]

    head = f"☀️ Today on the Island — {today:%A} {today.day} {today:%B}"
    foot = f"📱 Live updates for all of this in Manx One 👉 {APP_URL}"
    parts = [head]
    for _, v in sections:
        if len("\n\n".join(parts + [v, foot])) > MAX_LEN:
            continue  # drop a section rather than cut the post mid-line
        parts.append(v)
    parts.append(foot)
    text = "\n\n".join(parts)

    # Keep state from growing forever.
    for k, n in (("jobs", 4000), ("events", 3000), ("homes", 6000), ("drops", 3000),
                 ("notices", 50), ("lists", 50)):
        state[k] = state[k][-n:]
    state["lastPost"] = today.isoformat()
    return text, sections, state


def post_to_facebook(text: str) -> None:
    page, token = os.environ.get("FB_PAGE_ID"), os.environ.get("FB_PAGE_TOKEN")
    if not page or not token or os.environ.get("DRY_RUN"):
        print("Not posting (no Facebook Page details, or DRY_RUN).")
        return
    import requests
    r = requests.post(f"https://graph.facebook.com/{page}/feed",
                      data={"message": text, "link": APP_URL, "access_token": token}, timeout=30)
    if r.status_code != 200:
        # Never print the token; Facebook's error message doesn't contain it.
        sys.exit(f"Facebook post failed: HTTP {r.status_code} {r.text[:300]}")
    print(f"Posted to Facebook: {r.json().get('id')}")


def main():
    today = (dt.date.fromisoformat(os.environ["SOCIAL_DATE"]) if os.environ.get("SOCIAL_DATE")
             else dt.datetime.now(TZ).date())
    try:
        prev = json.loads(STATE.read_text(encoding="utf-8")).get("lastPost")
    except (OSError, ValueError):
        prev = None
    if prev == today.isoformat() and not os.environ.get("FORCE"):
        print(f"Already posted for {today}; nothing to do.")
        return
    text, sections, state = build(today)
    print(text)
    print(f"\n({len(text)} characters)")
    if os.environ.get("DRY_RUN"):
        print("DRY_RUN: preview only, files and state left as they were.")
        return
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps({"date": today.isoformat(), "text": text,
                                    "sections": dict(sections)}, indent=1, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    OUT_TXT.write_text(text + "\n", encoding="utf-8")
    post_to_facebook(text)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=0) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
