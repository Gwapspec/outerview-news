"""Seeds the next N cities from queue.json: streams each city's Overture places through overture.py, writes
data/<cc>_<name>.jsonl and data/index.json ({cityId: {"n": rows, "updated": day}}). Skips cities already in the index.
usage: python3 -I places/seed.py 40"""
import json
import math
import os
import subprocess
import sys
import time

N = int(sys.argv[1]) if len(sys.argv) > 1 else 40
MINUTES = float(os.environ.get("SEED_MINUTES", "40"))  # stop in time for the commit; the job has a hard timeout
START = time.time()
HERE = os.path.dirname(os.path.abspath(__file__))
queue = json.load(open(os.path.join(HERE, "queue.json")))
idx_path = os.path.join(HERE, "data", "index.json")
index = json.load(open(idx_path)) if os.path.exists(idx_path) else {}
today = time.strftime("%Y-%m-%d")


def eligible(c):
    e = index.get(c["id"])
    if e is None:
        return True
    if not e.get("fail"):
        return False
    if "attempts" not in e:
        return True  # failed under the first job, which had no retries: try again now
    return e["attempts"] < 6 and e["updated"] < today  # one more try a day, up to six


todo = [c for c in queue if eligible(c)][:N]
print(f"{len(index)} in the index, {len(todo)} this run, {sum(1 for c in queue if eligible(c))} eligible", flush=True)


def fetch(c, bbox, out):
    """Streams one city through the filter (download.py, release pinned); three tries with backoff (S3 answers 503 now and then)."""
    err_path = out + ".err"
    for attempt in range(3):
        with open(err_path, "w") as errf:
            dl = subprocess.Popen([sys.executable, "-I", os.path.join(HERE, "download.py"), f"--bbox={bbox}", "-f", "geojsonseq", "--type=place"], stdout=subprocess.PIPE, stderr=errf)
            with open(out + ".tmp", "w") as f:
                flt = subprocess.run([sys.executable, "-I", os.path.join(HERE, "overture.py"), c["id"], str(c["lat"]), str(c["lng"])], stdin=dl.stdout, stdout=f, stderr=subprocess.PIPE, text=True)
            dl.wait()
        err = open(err_path, errors="replace").read().strip()[-240:]
        os.remove(err_path)
        if dl.returncode == 0 and flt.returncode == 0:
            return True, ""
        print(f"RETRY {c['id']} try {attempt + 1} dl={dl.returncode} filter={flt.returncode} {err} {flt.stderr[-120:].strip()}", flush=True)
        time.sleep(5 * (3 ** attempt))
    return False, err


for c in todo:
    if time.time() - START > MINUTES * 60:
        print(f"time budget of {MINUTES:.0f} min spent, the rest waits for the next run", flush=True)
        break
    pop = c.get("population") or 0
    r = 0.10 if pop < 1_000_000 else 0.16 if pop < 5_000_000 else 0.24
    k = r / max(0.2, math.cos(math.radians(c["lat"])))
    bbox = f"{c['lng'] - k:.3f},{c['lat'] - r:.3f},{c['lng'] + k:.3f},{c['lat'] + r:.3f}"
    out = os.path.join(HERE, "data", c["id"].replace("/", "_", 1) + ".jsonl")
    t0 = time.time()
    ok, err = fetch(c, bbox, out)
    if not ok and "429" in err:
        print(f"THROTTLED {c['id']}, left for the next run", flush=True)
        if os.path.exists(out + ".tmp"):
            os.remove(out + ".tmp")
        time.sleep(60)
        continue
    if not ok:
        prev = index.get(c["id"]) or {}
        print(f"FAIL {c['id']} {err}", flush=True)
        if os.path.exists(out + ".tmp"):
            os.remove(out + ".tmp")
        index[c["id"]] = {"n": 0, "updated": today, "fail": 1, "attempts": int(prev.get("attempts", 0)) + 1}
        json.dump(index, open(idx_path, "w"), sort_keys=True)
        continue
    os.replace(out + ".tmp", out)
    n = sum(1 for _ in open(out))
    index[c["id"]] = {"n": n, "updated": today}
    json.dump(index, open(idx_path, "w"), sort_keys=True)
    print(f"{c['id']} {n} rows {time.time() - t0:.0f}s", flush=True)
print("done", flush=True)
