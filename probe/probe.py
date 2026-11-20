import os, subprocess, pathlib, json
out = pathlib.Path("probe/out"); out.mkdir(parents=True, exist_ok=True)
env = dict(os.environ, PROPERTY_AGENTS="bgc,grays,pre", OUTPUT_PATH="probe/out/prop_test.json")
r = subprocess.run(["python", "probe/property/run.py"], env=env, capture_output=True, text=True, timeout=3000)
(out / "prop_test.log").write_text(r.stdout[-20000:] + "\n---STDERR---\n" + r.stderr[-5000:])
