import requests, os, re, json
from urllib.parse import urljoin, urlparse
OUT = "probe/out/agents"; os.makedirs(OUT, exist_ok=True)
UA = {"User-Agent": "ManxOneBot/1.0 (+https://manxone.hammerlabs.app)"}
SITES = {
 "cg": "https://www.cowleygroves.com/",
 "gg": "https://www.garforthgray.im/",
 "koops": "https://koopsandco.com/",
 "pros": "https://www.prosearch.co.im/",
 "mm": "https://www.manxmove.im/search-list/",
}
KEY = re.compile(r"propert|sale|rent|let|search|listing|buy|homes", re.I)
def red(t):
    t = re.sub(r"AIza[0-9A-Za-z_\-]{20,}", "[k]", t)
    t = re.sub(r"(?<![/\w.-])[A-Za-z0-9_\-+=]{32,}(?![\w.-]*\.(?:jpg|png|webp|js|css))", "[x]", t)
    return t
log = {}
for key, home in SITES.items():
    host = urlparse(home).netloc
    entry = log.setdefault(key, {})
    try:
        r = requests.get(urljoin(home, "/robots.txt"), headers=UA, timeout=25)
        entry["robots"] = [r.status_code, r.text[:1500]]
    except Exception as e:
        entry["robots"] = str(e)
    seen, queue = set(), [home]
    pages = []
    while queue and len(pages) < 7:
        u = queue.pop(0)
        if u in seen: continue
        seen.add(u)
        try:
            r = requests.get(u, headers=UA, timeout=30)
        except Exception as e:
            pages.append([u, str(e)]); continue
        html = r.text
        fn = f"{OUT}/{key}_{len(pages)}.html"
        open(fn, "w").write(red(html))
        apis = sorted(set(re.findall(r"""["'](https?://[^"'\s]*(?:api|ajax|json|feed|graphql|search)[^"'\s]*)["']""", html, re.I)))[:30]
        apis += sorted(set(re.findall(r"""["'](/[^"'\s]*(?:api|ajax|json|wp-json|feed)[^"'\s]*)["']""", html, re.I)))[:30]
        pages.append([u, r.status_code, len(html), fn, apis])
        links = []
        for a in re.findall(r'href="([^"#]+)"', html):
            full = urljoin(u, a)
            if urlparse(full).netloc == host and KEY.search(urlparse(full).path) and full not in seen:
                links.append(full)
        for l in links[:40]:
            if l not in queue: queue.append(l)
    entry["pages"] = pages
json.dump(log, open(f"{OUT}/log.json", "w"), indent=1)
print(json.dumps(log, indent=1)[:5000])
