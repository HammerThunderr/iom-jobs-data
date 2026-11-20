import json, requests, pathlib, re, time
from bs4 import BeautifulSoup
out = pathlib.Path("probe/out/agents2"); out.mkdir(parents=True, exist_ok=True)
H = {"User-Agent": "ManxOneBot/1.0 (+mailto:hammerpunch786@gmail.com)"}
log = {}
def save(key, url):
    try:
        r = requests.get(url, headers=H, timeout=30)
    except Exception as e:
        log[key] = str(e)[:200]; return None
    (out / f"{key}.html").write_bytes(r.content)
    log[key] = {"url": url, "status": r.status_code, "final": r.url, "len": len(r.content)}
    time.sleep(1.5)
    return r
r = save("bgc_robots", "https://bgc.im/robots.txt")
pages = {
 "bgc_res_buy": "https://bgc.im/residential/buy/", "bgc_res_rent": "https://bgc.im/residential/rent/",
 "cg_sales": "https://www.cowleygroves.com/sales", "cg_rentals": "https://www.cowleygroves.com/rentals",
 "gg_sales": "https://www.garforthgray.im/sales", "gg_rentals": "https://www.garforthgray.im/rentals",
 "pre_sale": "https://www.partners.co.im/property-for-sale", "pre_rent": "https://www.partners.co.im/property-to-rent",
 "grays_list": "https://graysestateagents.com/listings",
}
for k, u in pages.items():
    r = save(k, u)
    if r is None or r.status_code != 200: continue
    soup = BeautifulSoup(r.text, "html.parser")
    hrefs = sorted({a["href"] for a in soup.find_all("a", href=True)})
    log[k]["hrefs"] = [h for h in hrefs if re.search(r"propert|listing|/\d{4,}|page|start=|offset", h, re.I)][:60]
# one sample listing each (first matching href)
pat = {"bgc_res_buy": r"/property/", "cg_sales": r"propert|/sales/", "gg_sales": r"^/[a-z0-9-]+-\d+|propert", "pre_sale": r"/property/", "grays_list": r"/listings/"}
for k, p in pat.items():
    hs = [h for h in log.get(k, {}).get("hrefs", []) if re.search(p, h)]
    hs = [h for h in hs if not re.search(r"page|search|sales$|rentals$", h)]
    if hs:
        base = log[k]["final"]
        from urllib.parse import urljoin
        save(k + "_item", urljoin(base, hs[0]))
(out / "log.json").write_text(json.dumps(log, indent=1))
