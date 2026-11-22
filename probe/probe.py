import requests, os, re, json
from bs4 import BeautifulSoup
OUT = "probe/out/health"
os.makedirs(OUT, exist_ok=True)
URLS = {
 "csw": "https://publichealth.gov.im/community-safety-wellbeing-information-and-support/",
 "support": "https://publichealth.gov.im/support-and-contacts/",
 "esjcr": "https://www.gov.im/about-the-government/departments/home-affairs/communications-division/emergency-services-joint-control-room/",
 "esjcr_contact": "https://www.gov.im/about-the-government/departments/home-affairs/communications-division/emergency-services-joint-control-room/contact-us/",
}
UAS = ["ManxOneBot/1.0 (+https://manxone.hammerlabs.app)"]
log = {}
for k, u in URLS.items():
    for ua in UAS:
        try:
            r = requests.get(u, headers={"User-Agent": ua}, timeout=30)
            soup = BeautifulSoup(r.text, "html.parser")
            for t in soup(["script", "style", "noscript", "svg"]): t.decompose()
            main = soup.find("main") or soup.body or soup
            txt = main.get_text("\n", strip=True)
            txt = re.sub(r"[A-Za-z0-9_\-]{32,}", "[x]", txt)
            open(f"{OUT}/{k}.txt", "w").write(txt)
            log[k] = [r.status_code, len(txt), txt[:120]]
        except Exception as e:
            log[k] = str(e)
json.dump(log, open(f"{OUT}/log.json", "w"), indent=1)
print(json.dumps(log, indent=1))
