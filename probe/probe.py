import os, re, requests
from bs4 import BeautifulSoup
os.makedirs("probe/out", exist_ok=True)
URLS = [
  "https://www.gov.im/categories/travel-traffic-and-motoring/drivers-and-vehicles/learning-to-drive/approved-driving-instructors/",
  "https://gov.im/categories/travel-traffic-and-motoring/drivers-and-vehicles/learning-to-drive/approved-driving-instructors",
]
lines = []
for u in URLS:
    r = requests.get(u, headers={"User-Agent": "ManxOneBot/1.0 (+mailto:hammerpunch786@gmail.com)"}, timeout=30)
    lines.append(f"== {u} -> {r.status_code} final={r.url} len={len(r.text)}")
    soup = BeautifulSoup(r.text, "html.parser")
    lines.append("as-of matches: " + str(re.findall(r"as of\s+[A-Z][a-z]+\s+\d{4}", soup.get_text(" "), flags=re.I)))
    for ti, t in enumerate(soup.find_all("table")):
        rows = t.find_all("tr")
        cap = t.find("caption")
        lines.append(f"-- table {ti}: {len(rows)} rows caption={cap.get_text(' ',strip=True) if cap else None}")
        for row in rows:
            cells = [re.sub(r'\s+',' ',c.get_text(' ')).strip() for c in row.find_all(['td','th'])]
            lines.append(" | ".join(cells)[:220])
    for a in soup.find_all("a", href=True):
        if re.search(r"\.pdf|instructor|register", a["href"], re.I):
            lines.append("link: " + a.get_text(" ", strip=True)[:80] + " -> " + a["href"])
    open("probe/out/adi_raw.html", "w").write(r.text)
open("probe/out/adi.txt", "w").write("\n".join(lines))
