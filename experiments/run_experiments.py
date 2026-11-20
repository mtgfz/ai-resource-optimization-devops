"""Run the experiment matrix for one configuration.

  python experiments/run_experiments.py --config baseline
  python experiments/run_experiments.py --config optimized

Matrix: 2 load levels x N repetitions. Requires docker compose and k6 in PATH.
"""
import argparse
import csv
import json
import pathlib
import subprocess
import time

import numpy as np
import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]
INFRA = ROOT / "infra"
RESULTS = ROOT / "experiments" / "results" / "results.csv"
PROM = "http://localhost:9090"
FIELDS = ["run_id", "config", "load_level", "repetition", "cpu_limit", "mem_limit_mb",
          "cpu_avg_pct", "mem_avg_mb", "p95_latency_ms", "throughput_rps",
          "restarts", "deploy_duration_s"]


def sh(cmd, **kw):
    return subprocess.run(cmd, check=True, text=True, capture_output=True, **kw)


def read_env(path):
    d = {}
    for line in path.read_text().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            d[k.strip()] = v.strip()
    return d


def avg(expr, start, end):
    r = requests.get(f"{PROM}/api/v1/query_range",
                     params={"query": expr, "start": start, "end": end, "step": 5}, timeout=30)
    res = r.json()["data"]["result"]
    vals = [float(v) for _, v in res[0]["values"]] if res else []
    return float(np.mean(vals)) if vals else float("nan")


def deploy(env_file):
    """Recreate the stack with the given limits and measure deployment duration."""
    t0 = time.perf_counter()
    sh(["docker", "compose", "--env-file", str(env_file), "up", "-d", "--build",
        "--force-recreate", "--wait"], cwd=INFRA)
    return time.perf_counter() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", choices=["baseline", "optimized"], required=True)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--duration", default="60s")
    args = ap.parse_args()

    env_file = INFRA / ("baseline.env" if args.config == "baseline" else "optimized.env")
    env = read_env(env_file)
    cpu_limit, mem_limit = float(env["APP_CPUS"]), int(env["APP_MEM"].rstrip("m"))

    new_file = not RESULTS.exists()
    with open(RESULTS, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        for level in ["low", "high"]:
            for rep in range(1, args.reps + 1):
                deploy_s = deploy(env_file)
                time.sleep(10)  # let Prometheus scrape a few points
                summary = ROOT / "experiments" / "results" / "k6_tmp.json"
                start = time.time()
                subprocess.run(["k6", "run", "--quiet", "--summary-export", str(summary),
                                "-e", f"LOAD={level}", "-e", f"DURATION={args.duration}",
                                str(ROOT / "loadtest" / "workload.js")], check=True)
                end = time.time()
                m = json.loads(summary.read_text())["metrics"]
                cpu = avg('rate(container_cpu_usage_seconds_total{name="demo-app"}[30s])', start, end)
                mem = avg('container_memory_working_set_bytes{name="demo-app"}', start, end) / 1048576
                restarts = int(sh(["docker", "inspect", "-f", "{{.RestartCount}}", "demo-app"]).stdout.strip())
                row = {
                    "run_id": time.strftime("%Y%m%d-%H%M%S"), "config": args.config,
                    "load_level": level, "repetition": rep,
                    "cpu_limit": cpu_limit, "mem_limit_mb": mem_limit,
                    "cpu_avg_pct": round(100 * cpu / cpu_limit, 2),
                    "mem_avg_mb": round(mem, 1),
                    "p95_latency_ms": round(m["http_req_duration"]["p(95)"], 2),
                    "throughput_rps": round(m["http_reqs"]["rate"], 2),
                    "restarts": restarts, "deploy_duration_s": round(deploy_s, 2),
                }
                w.writerow(row)
                f.flush()
                print(row)


if __name__ == "__main__":
    main()
