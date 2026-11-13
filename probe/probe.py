import json, requests, pathlib, re
out = pathlib.Path("probe/out"); out.mkdir(parents=True, exist_ok=True)
H = {"User-Agent": "ManxOneBot/1.0 (+https://manxone.hammerlabs.app)"}
log = {}
r = requests.get("https://web.archive.org/cdx/search/cdx",
    params={"url": "gov.im/media/*", "output": "json", "filter": ["original:.*ttrn.*", "statuscode:200"], "collapse": "urlkey", "limit": "5000"},
    headers=H, timeout=120)
log["cdx_status"] = r.status_code
rows = r.json()[1:] if r.status_code == 200 and r.text.strip() else []
rows.sort(key=lambda x: x[1])
log["count"] = len(rows)
log["rows"] = [[x[1], x[2]] for x in rows]
for x in rows[-3:] + rows[:1]:
    ts, orig = x[1], x[2]
    u = f"https://web.archive.org/web/{ts}id_/{orig}"
    try:
        p = requests.get(u, headers=H, timeout=120)
        name = "s_" + re.sub(r"[^a-z0-9.-]", "_", orig.rsplit('/',1)[-1].lower())[:90]
        (out / name).write_bytes(p.content)
        log[name] = [p.status_code, len(p.content), p.headers.get("content-type")]
    except Exception as e:
        log[u] = str(e)
(out / "log3.json").write_text(json.dumps(log, indent=1))
