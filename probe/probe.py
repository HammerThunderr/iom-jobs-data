import json, requests, pathlib, re
out = pathlib.Path("probe/out/agents"); out.mkdir(parents=True, exist_ok=True)
H = {"User-Agent": "ManxOneBot/1.0 (+mailto:hammerpunch786@gmail.com)"}
sites = {
 "bgc": ["https://www.blackgracecowley.com", ["/search/?PropertySearch%5BsearchType%5D=1", "/property-search/", "/properties/"]],
 "cg": ["https://www.cowleygroves.com", ["/property-search/", "/properties/", "/search/"]],
 "gg": ["https://www.garforthgray.im", ["/sales/", "/rentals/"]],
 "pw": ["https://www.propertywise.co.im", ["/", "/properties/", "/property-search/"]],
 "grays1": ["https://www.graysestateagents.com", ["/"]],
 "grays2": ["https://www.graysestateagents.co.im", ["/"]],
 "grays3": ["https://www.grays.im", ["/"]],
 "grays4": ["https://graysestateagents.im", ["/"]],
}
log = {}
for key, (base, paths) in sites.items():
    entry = {}
    try:
        r = requests.get(base + "/robots.txt", headers=H, timeout=20)
        entry["robots"] = [r.status_code, r.text[:1200]]
    except Exception as e:
        entry["robots"] = str(e)[:200]
    for p in paths:
        try:
            r = requests.get(base + p, headers=H, timeout=25)
            name = key + re.sub(r"[^a-z0-9]+", "_", p.lower())[:40] + ".html"
            (out / name).write_bytes(r.content)
            links = sorted(set(re.findall(r'href="([^"]+)"', r.text)))
            entry[p] = {"status": r.status_code, "final": r.url, "len": len(r.content), "links": [l for l in links if re.search(r"propert|listing|for-sale|to-let|rent|sale", l, re.I)][:40]}
        except Exception as e:
            entry[p] = str(e)[:200]
    log[key] = entry
(out / "log.json").write_text(json.dumps(log, indent=1))
