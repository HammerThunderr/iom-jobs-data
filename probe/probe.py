import subprocess, json, pathlib, os
out = pathlib.Path("probe/out"); out.mkdir(parents=True, exist_ok=True)
log = {}
for name, ua in {"bot": "ManxOneBot/1.0 (+https://manxone.hammerlabs.app)", "weatherua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}.items():
    env = dict(os.environ, UA=ua, OUT=f"probe/out/tides_{name}.json")
    r = subprocess.run(["python", "probe/tides/scrape_tides.py"], capture_output=True, text=True, env=env, timeout=300)
    log[name] = {"rc": r.returncode, "out": r.stdout[-1500:], "err": r.stderr[-1500:]}
(out / "tides3.json").write_text(json.dumps(log, indent=1))
