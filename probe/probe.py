import os, re, sys, json
import requests
from bs4 import BeautifulSoup

sys.path.insert(0, "scripts/property")
import common  # noqa: E402
from agents import AGENTS  # noqa: E402

OUT = "probe/out/agents4"
os.makedirs(OUT, exist_ok=True)
UA = {"User-Agent": common.USER_AGENT}
lines = []

def log(s):
    print(s); lines.append(str(s))

gg = next(a for a in AGENTS if a.name == "Garforth Gray")
pat = re.compile(r"^(https://www\.garforthgray\.im)?/(rentals/)?[a-z0-9]+(-[a-z0-9]+)+/?$")

def collect(url):
    urls = set()
    for p in range(1, 40):
        r = requests.get(url + f"&page={p}", headers=UA, timeout=30)
        soup = BeautifulSoup(r.text, "html.parser")
        found = {a["href"] for a in soup.select("a[href]") if pat.match(a["href"])}
        if not found - urls: break
        urls |= found
    return {u if u.startswith("http") else "https://www.garforthgray.im" + u for u in urls}

B = "https://www.garforthgray.im/assets/inc/ajax.php?submitform=1&order=latest&keyword="
for kind, flag in (("Sale", "excludeSold"), ("Rentals", "excludeRented")):
    a = collect(B + f"&ajaxGet{kind}Results=1&{flag}=1")
    b = collect(B + f"&ajaxGet{kind}Results=1")
    extra = sorted(b - a)
    log(f"GG {kind}: filtered {len(a)}, all {len(b)}, extra {len(extra)}")
    idx = B + f"&ajaxGet{kind}Results=1"
    stat = {}
    for u in extra[:60]:
        u = u.rstrip("/") + "/"
        gg.origin[u] = idx
        try:
            item = common.scrape_listing(gg, u)
        except Exception as e:
            log(f"  {u} err {e}"); continue
        if not item:
            stat["skipped"] = stat.get("skipped", 0) + 1; continue
        k = f"{item.get('listingType')}|{item.get('status')}"
        stat[k] = stat.get(k, 0) + 1
    log(f"  sample of {min(60, len(extra))} extra: {stat}")
    if extra:
        r = requests.get(extra[0], headers=UA, timeout=30)
        open(f"{OUT}/gg_{kind}_extra.html", "w").write(r.text[:80000])

# Chapman Chartered Surveyors
for path in ("/", "/robots.txt", "/sitemap.xml", "/sitemap_index.xml", "/property-search/", "/?s=&post_type=property"):
    try:
        r = requests.get("https://www.chapman.im" + path, headers=UA, timeout=30)
    except Exception as e:
        log(f"chapman {path} err {e}"); continue
    log(f"chapman {path}: {r.status_code} {r.url} {len(r.text)}")
    name = path.strip("/").replace("/", "_").replace("?", "q") or "home"
    open(f"{OUT}/chapman_{name}.txt", "w").write(r.text[:100000])
    if path == "/":
        soup = BeautifulSoup(r.text, "html.parser")
        links = sorted({a["href"] for a in soup.select("a[href]")})
        log("  links: " + " ".join(links[:80]))
        forms = [(f.get("action"), f.get("method"), [i.get("name") for i in f.select("input,select")]) for f in soup.select("form")]
        log(f"  forms: {forms}")

open(f"{OUT}/summary.txt", "w").write("\n".join(lines) + "\n")
