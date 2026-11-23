import os, re, sys, collections
import requests
from bs4 import BeautifulSoup

OUT = "probe/out/agents6"
os.makedirs(OUT, exist_ok=True)
UA = {"User-Agent": "ManxOneBot/1.0 (+mailto:hammerpunch786@gmail.com)"}
lines = []

def log(s):
    print(s); lines.append(str(s))

two = re.compile(r"^https?://www\.chapman\.im/([a-z0-9-]+)/([a-z0-9-]+)/?$")
for label, tmpl in (("plain", "https://www.chapman.im/commercial-property/?wpv_paged={}"),
                    ("vc", "https://www.chapman.im/commercial-property/?wpv_view_count=762&wpv_paged={}")):
    urls, prefixes = set(), collections.Counter()
    for p in range(1, 15):
        r = requests.get(tmpl.format(p), headers=UA, timeout=30)
        soup = BeautifulSoup(r.text, "html.parser")
        found = set()
        for a in soup.select(".listing h4 a[href]"):
            m = two.match(a["href"])
            if m:
                found.add(a["href"]); prefixes[m.group(1)] += 1
        fresh = found - urls
        log(f"{label} page {p}: {r.status_code} found {len(found)} fresh {len(fresh)}")
        if not fresh: break
        urls |= fresh
    log(f"{label}: {len(urls)} urls, prefixes {dict(prefixes)}")

# all cards' price text so we can see sale vs let wording
r = requests.get("https://www.chapman.im/commercial-property/", headers=UA, timeout=30)
soup = BeautifulSoup(r.text, "html.parser")
for card in soup.select(".listing")[:12]:
    log("CARD: " + card.get_text(" | ", strip=True)[:200])

for u in sorted(urls)[:40]:
    pass
picks = [u for u in sorted(urls) if "investment" in u][:1] + [u for u in sorted(urls) if "unit-7-villa" in u][:1] + sorted(urls)[:2]
for u in picks:
    rr = requests.get(u, headers=UA, timeout=30)
    nm = u.rstrip("/").rsplit("/", 1)[-1]
    open(f"{OUT}/item_{nm}.html", "w").write(rr.text[:250000])
    s = BeautifulSoup(rr.text, "html.parser")
    main = s.select_one("#main-content") or s
    log(f"ITEM {u}: {rr.status_code}\n" + main.get_text(" | ", strip=True)[:1500])

open(f"{OUT}/summary.txt", "w").write("\n".join(lines) + "\n")
