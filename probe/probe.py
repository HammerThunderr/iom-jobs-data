import requests, os, re, json, time
OUT = "probe/out/agents2"
os.makedirs(OUT, exist_ok=True)
UA = {"User-Agent": "ManxOneBot/1.0 (+https://manxone.hammerlabs.app)"}
URLS = {
 "cg_sales": "https://www.cowleygroves.com/sales",
 "cg_sales_p2": "https://www.cowleygroves.com/sales?page=2",
 "cg_rentals": "https://www.cowleygroves.com/rentals",
 "cg_comm": "https://www.cowleygroves.com/commercials",
 "cg_prop": "https://www.cowleygroves.com/property/39-governors-road-onchan-im3-1ay",
 "cgred_sales": "https://www.cgred.im/sales",
 "gg_rentals": "https://www.garforthgray.im/rentals",
 "gg_ajax_sale1": "https://www.garforthgray.im/assets/inc/ajax.php?submitform=1&order=latest&page=1&keyword=&ajaxGetSaleResults=1&excludeSold=1",
 "gg_ajax_sale2": "https://www.garforthgray.im/assets/inc/ajax.php?submitform=1&order=latest&page=2&keyword=&ajaxGetSaleResults=1&excludeSold=1",
 "gg_comm": "https://www.garforthgray.im/commercial-properties-isle-of-man",
}
log = {}
def red(t):
    return re.sub(r"[A-Za-z0-9_\-]{32,}", "[x]", t)
for k, u in URLS.items():
    try:
        r = requests.get(u, headers=UA, timeout=30)
        t = r.text
        links = sorted(set(re.findall(r'href="([^"#]+)"', t)))
        open(f"{OUT}/{k}.txt", "w").write(red(t[:300000]))
        log[k] = {"status": r.status_code, "final": r.url, "len": len(t), "links": links[:400]}
    except Exception as e:
        log[k] = str(e)
    time.sleep(2)
# first GG listing page from ajax
try:
    t = open(f"{OUT}/gg_ajax_sale1.txt").read()
    cand = [l for l in re.findall(r'href="([^"#]+)"', t) if l.startswith("/") and l.count("/") <= 2 and len(l) > 10]
    if cand:
        u = "https://www.garforthgray.im" + cand[0]
        r = requests.get(u, headers=UA, timeout=30)
        open(f"{OUT}/gg_prop.txt", "w").write(red(r.text[:300000]))
        log["gg_prop"] = {"status": r.status_code, "final": r.url, "len": len(r.text)}
except Exception as e:
    log["gg_prop"] = str(e)
json.dump(log, open(f"{OUT}/log.json", "w"), indent=1)
