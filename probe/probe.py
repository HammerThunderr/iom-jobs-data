import json, pathlib, re, time, traceback
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

out = pathlib.Path("probe/out/agents2")
out.mkdir(parents=True, exist_ok=True)
H = {"User-Agent": "ManxOneBot/1.0 (+mailto:hammerpunch786@gmail.com)"}
log = {}


def save(key, url):
    try:
        r = requests.get(url, headers=H, timeout=30)
    except Exception as e:
        log[key] = str(e)[:200]
        return None
    # Scripts removed before saving: they hold map/API keys, and GitHub's
    # secret scanning refuses pushes that contain them.
    try:
        soup = BeautifulSoup(r.text, "html.parser")
        for t in soup(["script", "style", "noscript", "svg", "iframe"]):
            t.decompose()
        cleaned = re.sub(r"(?i)(key|token|secret)=[A-Za-z0-9_\-]{12,}", r"\1=REDACTED", str(soup))
    except Exception:
        cleaned = ""
    for pat in (r"AIza[0-9A-Za-z_\-]{20,}", r"pk\.[A-Za-z0-9_\-\.]{20,}", r"[A-Za-z0-9_\-]{32,}"):
        cleaned = re.sub(pat, "REDACTED", cleaned)
    (out / f"{key}.html").write_text(cleaned)
    log[key] = {"url": url, "status": r.status_code, "final": r.url, "len": len(r.content)}
    time.sleep(1.5)
    return r


try:
    save("bgc_robots", "https://bgc.im/robots.txt")
    pages = {
        "bgc_res_buy": "https://bgc.im/residential/buy/",
        "bgc_res_rent": "https://bgc.im/residential/rent/",
        "cg_sales": "https://www.cowleygroves.com/sales",
        "cg_rentals": "https://www.cowleygroves.com/rentals",
        "gg_sales": "https://www.garforthgray.im/sales",
        "gg_rentals": "https://www.garforthgray.im/rentals",
        "pre_sale": "https://www.partners.co.im/property-for-sale",
        "pre_rent": "https://www.partners.co.im/property-to-rent",
        "grays_list": "https://graysestateagents.com/listings",
    }
    for k, u in pages.items():
        r = save(k, u)
        if r is None or r.status_code != 200:
            continue
        soup = BeautifulSoup(r.text, "html.parser")
        hrefs = sorted({a["href"] for a in soup.find_all("a", href=True)})
        log[k]["hrefs"] = [h for h in hrefs if re.search(r"propert|listing|/\d{4,}|page|start=|offset", h, re.I)][:80]
        log[k]["all_hrefs_sample"] = hrefs[:120]

    pat = {"bgc_res_buy": r"/property/", "cg_sales": r"propert", "gg_sales": r"propert|-\d{4,}",
           "pre_sale": r"/property/", "grays_list": r"/listings/"}
    for k, p in pat.items():
        ent = log.get(k)
        if not isinstance(ent, dict):
            continue
        hs = [h for h in ent.get("all_hrefs_sample", []) if re.search(p, h)]
        hs = [h for h in hs if not re.search(r"page=|search|/sales$|/rentals$|/listings$", h)]
        if hs:
            save(k + "_item", urljoin(ent["final"], hs[0]))
except Exception:
    log["fatal"] = traceback.format_exc()

(out / "log.json").write_text(json.dumps(log, indent=1))
