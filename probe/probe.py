import os, subprocess, json, shutil, collections
OUT = "probe/out/prop3"
os.makedirs(OUT, exist_ok=True)
env = dict(os.environ, PROPERTY_AGENTS="cg,gg")
p = subprocess.run(["python", "run.py"], cwd="scripts/property", env=env, capture_output=True, text=True, timeout=3000)
open(f"{OUT}/log.txt", "w").write(p.stdout[-60000:] + "\n---STDERR---\n" + p.stderr[-8000:])
try:
    d = json.load(open("docs/property/properties.json"))
    keep = [x for x in d["listings"] if x["agent"] in ("Cowley Groves", "Garforth Gray")]
    json.dump({"meta": d.get("meta"), "listings": keep}, open(f"{OUT}/out.json", "w"), indent=1)
except Exception as e:
    open(f"{OUT}/err.txt", "w").write(str(e))
