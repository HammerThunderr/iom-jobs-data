import json, requests, pathlib, re
from bs4 import BeautifulSoup
out = pathlib.Path("probe/out"); out.mkdir(parents=True, exist_ok=True)
U = "https://www.visitisleofman.com/traveltrade/cruise/cruise-schedule"
r = requests.get(U, headers={"User-Agent": "ManxOneBot/1.0 (+mailto:hammerpunch786@gmail.com)"}, timeout=30)
soup = BeautifulSoup(r.text, "html.parser")
main = soup.find("main") or soup
links = [{"text": " ".join(a.get_text(" ", strip=True).split())[:100], "href": a["href"]} for a in soup.find_all("a", href=True)
         if any(k in (a["href"] + a.get_text()).lower() for k in ("cruise", ".pdf", "schedule", "dbimgs"))]
text = " ".join(main.get_text(" ", strip=True).split())
i = text.lower().find("schedule")
(out / "cruise.json").write_text(json.dumps({"status": r.status_code, "len": len(r.text), "links": links[:60], "text": text[max(0,i-1500):i+2500]}, indent=1))
