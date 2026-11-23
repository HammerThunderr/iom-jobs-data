import os, re, sys
import requests
from bs4 import BeautifulSoup

sys.path.insert(0, "scripts/property")
import common  # noqa: E402

OUT = "probe/out/agents5"
os.makedirs(OUT, exist_ok=True)
UA = {"User-Agent": common.USER_AGENT}
lines = []

def log(s):
    print(s); lines.append(str(s))

pat = re.compile(r"^(https://www\.garforthgray\.im)?/rentals/[a-z0-9]+(-[a-z0-9]+)+/?$")

def collect(url):
    urls, cards = set(), {}
    for p in range(1, 20):
        r = requests.get(url + f"&page={p}", headers=UA, timeout=30)
        soup = BeautifulSoup(r.text, "html.parser")
        found = set()
        for a in soup.select("a[href]"):
            if pat.match(a["href"]):
                u = a["href"] if a["href"].startswith("http") else "https://www.garforthgray.im" + a["href"]
                found.add(u)
                card = a.find_parent(["div", "li", "article"])
                for _ in range(3):
                    if card is not None and len(card.get_text(" ", strip=True)) < 60:
                        card = card.find_parent(["div", "li", "article"])
                if card is not None:
                    cards.setdefault(u, card.get_text(" | ", strip=True)[:220])
        if not found - urls: break
        urls |= found
    return urls, cards

B = "https://www.garforthgray.im/assets/inc/ajax.php?submitform=1&order=latest&keyword=&ajaxGetRentalsResults=1"
a, _ = collect(B + "&excludeRented=1")
b, cards = collect(B)
for u in sorted(b - a):
    r = requests.get(u, headers=UA, timeout=30)
    s = BeautifulSoup(r.text, "html.parser")
    m = s.select_one(".main-data")
    head = m.get_text(" | ", strip=True)[:200] if m else "?"
    badges = [e.get_text(" ", strip=True) for e in s.select("[class*=status],[class*=badge],[class*=label],[class*=sticker],[class*=ribbon]")][:6]
    log(f"{u}\n   page: {head}\n   badges: {badges}\n   card: {cards.get(u, '')}")

# Chapman commercial property list
for path in ("/commercial-property/",):
    r = requests.get("https://www.chapman.im" + path, headers=UA, timeout=30)
    log(f"chapman {path}: {r.status_code} {len(r.text)}")
    open(f"{OUT}/chapman_list.html", "w").write(r.text[:300000])
    soup = BeautifulSoup(r.text, "html.parser")
    links = sorted({a["href"] for a in soup.select("a[href]") if "chapman.im" in a["href"] or a["href"].startswith("/")})
    log("  links: " + "\n   ".join(links))
    first = [l for l in links if "/property/" in l or "/commercial-property/" in l and l.rstrip("/").count("/") > 3]
    for l in first[:2]:
        rr = requests.get(l, headers=UA, timeout=30)
        nm = l.rstrip("/").rsplit("/", 1)[-1]
        open(f"{OUT}/chapman_item_{nm}.html", "w").write(rr.text[:200000])
        log(f"  item {l}: {rr.status_code}")

open(f"{OUT}/summary.txt", "w").write("\n".join(lines) + "\n")
