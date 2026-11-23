import requests, os, re, json
OUT = "probe/out/agents"
UA = {"User-Agent": "ManxOneBot/1.0 (+https://manxone.hammerlabs.app)"}
URLS = {
 "cg_robots": "https://www.cowleygroves.com/robots.txt",
 "cg_home": "https://www.cowleygroves.com/",
 "cg_sale": "https://www.cowleygroves.com/property-for-sale/",
 "cg_search": "https://www.cowleygroves.com/search/",
 "cg_sitemap": "https://www.cowleygroves.com/sitemap.xml",
 "gg_robots": "https://www.garforthgray.im/robots.txt",
 "gg_home": "https://www.garforthgray.im/",
 "gg_sales": "https://www.garforthgray.im/sales/",
 "gg_rentals": "https://www.garforthgray.im/rentals/",
 "gg_sitemap": "https://www.garforthgray.im/sitemap.php",
 "ar_home": "https://www.arragon.co.im/",
 "ar_home2": "https://arragon.im/",
}
os.makedirs(OUT, exist_ok=True)
log = {}
def red(t):
    return re.sub(r"[A-Za-z0-9_\-]{32,}", "[x]", t)
for k, u in URLS.items():
    try:
        r = requests.get(u, headers=UA, timeout=30)
        t = r.text
        apis = sorted(set(re.findall(r"""["'](\/?[A-Za-z0-9_\-\/\.]*(?:api|ajax|json|wp-json|search|properties|listing)[A-Za-z0-9_\-\/\.\?=&]*)["']""", t, re.I)))[:80]
        srcs = re.findall(r'<script[^>]+src="([^"]+)"', t)[:40]
        links = sorted(set(re.findall(r'href="([^"#]+)"', t)))[:300]
        open(f"{OUT}/{k}.txt", "w").write(red(t[:250000]))
        log[k] = {"status": r.status_code, "final": r.url, "len": len(t), "apis": apis, "scripts": srcs, "links": links}
    except Exception as e:
        log[k] = str(e)
json.dump(log, open(f"{OUT}/log.json", "w"), indent=1)
