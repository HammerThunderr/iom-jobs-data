import os, re, socket, collections
import requests
from bs4 import BeautifulSoup

OUT = "probe/out/agents3"
os.makedirs(OUT, exist_ok=True)
UA = {"User-Agent": "ManxOneBot/1.0 (+https://manxone.hammerlabs.app)"}
lines = []

def log(s):
    print(s); lines.append(s)

# 1. Garforth Gray: how many sale listings incl. SSTC / under offer?
base = "https://www.garforthgray.im/assets/inc/ajax.php?submitform=1&order=latest&keyword=&ajaxGetSaleResults=1"
for label, extra in (("excludeSold", "&excludeSold=1"), ("all", "")):
    urls, words = set(), collections.Counter()
    for p in range(1, 40):
        try:
            r = requests.get(base + extra + f"&page={p}", headers=UA, timeout=30)
        except Exception as e:
            log(f"GG {label} p{p} err {e}"); break
        soup = BeautifulSoup(r.text, "html.parser")
        found = {a["href"] for a in soup.select("a[href]") if re.match(r"^(https://www\.garforthgray\.im)?/[a-z0-9]+(-[a-z0-9]+)+/?$", a["href"])}
        fresh = found - urls
        if not fresh: break
        urls |= fresh
        t = soup.get_text(" ", strip=True).lower()
        for w in ("sold stc", "sold subject", "under offer", "offer accepted", "sold", "reserved", "new instruction", "reduced"):
            words[w] += t.count(w)
        if p == 1:
            open(f"{OUT}/gg_{label}_p1.html", "w").write(r.text[:60000])
    log(f"GG {label}: {len(urls)} urls, words {dict(words)}")

# 2. Other possible agents: does the domain exist / what is on it?
cands = [
    "propertywise.co.im", "www.propertywise.co.im", "arragonproperties.com", "arragonproperties.im",
    "arragon.im", "www.arragonproperties.co.im", "chapmanandco.im", "chapman.im", "www.chapmanco.im",
    "chapmanandco.co.im", "harmonyhomes.im", "www.harmonyhomes.co.im", "plumproperties.im",
    "www.plumproperties.co.im", "loweyandco.com", "www.lowey.co.im", "chrisblackburn.co.im",
    "islandpropertyconsultants.com", "ashbrooks.im", "www.ashbrooksproperty.com",
    "www.hartfordhomes.co.im", "www.dandara.im", "www.heritagehomes.im", "www.prosearch.im",
]
for host in cands:
    h = host.replace("www.", "")
    try:
        socket.gethostbyname(host)
    except Exception:
        log(f"{host}: no DNS"); continue
    try:
        r = requests.get("https://" + host, headers=UA, timeout=25)
        soup = BeautifulSoup(r.text, "html.parser")
        title = (soup.title.string or "").strip() if soup.title else ""
        t = soup.get_text(" ", strip=True).lower()
        hints = [w for w in ("for sale", "to let", "to rent", "property search", "commercial", "bedroom", "estate agent", "merged", "joined", "now part of") if w in t]
        log(f"{host}: {r.status_code} -> {r.url} | {title[:90]} | {hints}")
        open(f"{OUT}/{h}.txt", "w").write(soup.get_text("\n", strip=True)[:6000])
    except Exception as e:
        log(f"{host}: err {type(e).__name__}")

open(f"{OUT}/summary.txt", "w").write("\n".join(lines) + "\n")
