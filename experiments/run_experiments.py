"""Run the experiment matrix for one configuration.

  python experiments/run_experiments.py --config baseline
  python experiments/run_experiments.py --config optimized

Matrix: 2 load levels x N repetitions. Requires docker compose and k6 in PATH.
"""
import argparse
import csv
import json
import math
import pathlib
import subprocess
import sys
import threading
import time

import numpy as np
import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "optimizer"))
from optimizer import parse_docker_stats  # noqa: E402  (reuse the same parser as the optimizer)
INFRA = ROOT / "infra"
RESULTS = ROOT / "experiments" / "results" / "results.csv"
PROM = "http://localhost:9090"
FIELDS = ["run_id", "config", "load_level", "repetition", "cpu_limit", "mem_limit_mb",
          "cpu_avg_pct", "mem_avg_mb", "p95_latency_ms", "throughput_rps",
          "restarts", "deploy_duration_s", "metrics_source"]


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
    """Average of a Prometheus query over [start, end]; NaN if Prometheus has no data."""
    try:
        r = requests.get(f"{PROM}/api/v1/query_range",
                         params={"query": expr, "start": start, "end": end, "step": 5}, timeout=30)
        res = r.json()["data"]["result"]
    except (requests.RequestException, ValueError, KeyError):
        return float("nan")
    vals = [float(v) for _, v in res[0]["values"]] if res else []
    return float(np.mean(vals)) if vals else float("nan")


class DockerStatsSampler:
    """Samples `docker stats` every second in the background (works even when cAdvisor cannot see the container)."""

    def __init__(self, container="demo-app", interval=1.0):
        self.container, self.interval = container, interval
        self.cpu, self.mem = [], []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self._stop.is_set():
            try:
                out = subprocess.run(
                    ["docker", "stats", "--no-stream", "--format", "{{.CPUPerc}};{{.MemUsage}}", self.container],
                    capture_output=True, text=True, timeout=15).stdout
                cpu, mem = parse_docker_stats(out)
                self.cpu.extend(cpu.tolist())
                self.mem.extend(mem.tolist())
            except (OSError, subprocess.SubprocessError):
                pass
            self._stop.wait(self.interval)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=20)

    def averages(self):
        """(average CPU in cores, average memory in MB), NaN when nothing was sampled."""
        if not self.cpu:
            return float("nan"), float("nan")
        return float(np.mean(self.cpu)), float(np.mean(self.mem))


def choose_metrics(prom, sampler, collector="auto"):
    """Pick the metric source. prom and sampler are (cpu_cores, mem_mb) tuples.

    auto          : Prometheus if it returned data, otherwise docker stats
    prometheus    : Prometheus only (NaN if no data)
    docker-stats  : docker stats only
    Returns (cpu_cores, mem_mb, source_name).
    """
    prom_ok = not (math.isnan(prom[0]) or math.isnan(prom[1]))
    if collector == "prometheus" or (collector == "auto" and prom_ok):
        return prom[0], prom[1], "prometheus"
    return sampler[0], sampler[1], "docker-stats"


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
    ap.add_argument("--collector", choices=["auto", "prometheus", "docker-stats"], default="auto",
                    help="where CPU/memory come from (auto = Prometheus, falling back to docker stats)")
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
                sampler = DockerStatsSampler()
                sampler.start()
                start = time.time()
                subprocess.run(["k6", "run", "--quiet", "--summary-export", str(summary),
                                "-e", f"LOAD={level}", "-e", f"DURATION={args.duration}",
                                str(ROOT / "loadtest" / "workload.js")], check=True)
                end = time.time()
                sampler.stop()
                m = json.loads(summary.read_text())["metrics"]
                prom_cpu = avg('rate(container_cpu_usage_seconds_total{name="demo-app"}[30s])', start, end)
                prom_mem = avg('container_memory_working_set_bytes{name="demo-app"}', start, end) / 1048576
                cpu, mem, source = choose_metrics((prom_cpu, prom_mem), sampler.averages(), args.collector)
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
                    "metrics_source": source,
                }
                w.writerow(row)
                f.flush()
                print(row)


if __name__ == "__main__":
    main()
