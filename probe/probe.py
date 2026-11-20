import json, pathlib, re, time, traceback
import requests
from bs4 import BeautifulSoup
out = pathlib.Path("probe/out/agents3"); out.mkdir(parents=True, exist_ok=True)
H = {"User-Agent": "ManxOneBot/1.0 (+mailto:hammerpunch786@gmail.com)"}
log = {}
def text_of(url):
    r = requests.get(url, headers=H, timeout=30); time.sleep(1.5)
    soup = BeautifulSoup(r.text, "html.parser")
    for t in soup(["script", "style", "noscript", "svg"]): t.decompose()
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    hrefs = sorted({a["href"] for a in soup.find_all("a", href=True)})
    txt = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    txt = re.sub(r"[A-Za-z0-9_\-]{32,}", "X", txt)
    return r.status_code, r.url, title, txt, hrefs
try:
    for k, u in {
        "bgc_comm1": "https://bgc.im/property/victoria-street-douglas-5/",
        "bgc_comm2": "https://bgc.im/property/south-quay-industrial-estate-south-quay-douglas-2/",
        "bgc_rent": "https://bgc.im/property/2-spring-gardens-douglas/",
        "pre_item": "https://www.partners.co.im/property/4-bed-detached-house-for-sale-in-mannin-veen-lheaney-road-ramsey-im8-2jf/712771",
        "pre_comm_rent": "https://www.partners.co.im/commercial-properties-to-rent",
    }.items():
        st, final, title, txt, hrefs = text_of(u)
        log[k] = {"status": st, "final": final, "title": title, "text": txt[:3500],
                  "prop_hrefs": [h for h in hrefs if "/property/" in h][:15]}
    for k, u in {
        "grays_home": "https://graysestateagents.com/",
        "grays_rent_a": "https://graysestateagents.com/listings?saleOrRental=Rental",
        "grays_rent_b": "https://graysestateagents.com/listings?status=available&saleOrRental=Rental",
        "grays_rent_c": "https://graysestateagents.com/rentals",
        "grays_rent_d": "https://graysestateagents.com/listings?listing_type=residential_rental",
    }.items():
        st, final, title, txt, hrefs = text_of(u)
        L = [h for h in hrefs if "/listings/" in h]
        log[k] = {"status": st, "final": final, "n": len(L), "rental": [h for h in L if "rental" in h][:10],
                  "nav": [h for h in hrefs if re.search(r"rent|letting|listings\?", h, re.I)][:25]}
    st, final, title, txt, hrefs = text_of("https://graysestateagents.com/listings/residential_rental-RX822851-isle-of-man")
    log["grays_rent_item"] = {"status": st, "title": title, "text": txt[:2500]}
except Exception:
    log["fatal"] = traceback.format_exc()
(out / "log.json").write_text(json.dumps(log, indent=1))
