"""Rule-based resource recommender.

Reads CPU and memory usage of a container from Prometheus, computes the p95
(the value below which 95% of the samples fall = the "normal peak"), adds a
safety margin and recommends new limits. It only WRITES recommendations:
  - optimizer/recommendations.md  (human readable)
  - infra/optimized.env           (used by `docker compose --env-file`)
Applying them is an operator decision.
"""
import argparse
import math
import pathlib
import time

import numpy as np
import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]

CPU_STEP = 0.05   # CPU limits are rounded up to a multiple of 0.05 core
MEM_STEP = 16     # memory limits are rounded up to a multiple of 16 MB
MIN_CPU = 0.1
MIN_MEM = 64


def query_range(prom, expr, start, end, step=5):
    """Return the samples of the first Prometheus series as a numpy array."""
    r = requests.get(f"{prom}/api/v1/query_range",
                     params={"query": expr, "start": start, "end": end, "step": step},
                     timeout=30)
    r.raise_for_status()
    result = r.json()["data"]["result"]
    if not result:
        return np.array([])
    return np.array([float(v) for _, v in result[0]["values"]])


def current_limits():
    """Read baseline limits from infra/baseline.env."""
    limits = {}
    for line in (ROOT / "infra" / "baseline.env").read_text().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            limits[k.strip()] = v.strip()
    return float(limits["APP_CPUS"]), int(limits["APP_MEM"].rstrip("m"))


def recommend(cpu_p95, mem_p95_mb, margin=0.20):
    """Turn observed p95 usage into recommended limits.

    cpu_p95    : p95 CPU usage in cores
    mem_p95_mb : p95 memory usage in MB
    margin     : safety margin (0.20 = +20%)
    Returns (cpu_limit_in_cores, memory_limit_in_mb).
    """
    cpu = math.ceil(round(cpu_p95 * (1 + margin) / CPU_STEP, 6)) * CPU_STEP
    mem = math.ceil(round(mem_p95_mb * (1 + margin) / MEM_STEP, 6)) * MEM_STEP
    return round(max(MIN_CPU, cpu), 2), int(max(MIN_MEM, mem))


def build_report(container, minutes, margin, cur, p95, rec):
    cur_cpu, cur_mem = cur
    cpu_p95, mem_p95 = p95
    rec_cpu, rec_mem = rec
    return f"""# Resource recommendations for `{container}`

Analysis window: last {minutes} min | safety margin: {margin:.0%}

| Resource | Current limit | Observed p95 | Recommended limit |
|---|---|---|---|
| CPU (cores) | {cur_cpu:.2f} | {cpu_p95:.3f} | {rec_cpu:.2f} |
| Memory (MB) | {cur_mem} | {mem_p95:.1f} | {rec_mem} |

Reducible allocation: CPU {100 * (1 - rec_cpu / cur_cpu):.0f}% , memory {100 * (1 - rec_mem / cur_mem):.0f}%.

These are **recommendations**. Apply them with:
`cd infra && docker compose --env-file optimized.env up -d --wait`
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prometheus", default="http://localhost:9090")
    ap.add_argument("--container", default="demo-app")
    ap.add_argument("--minutes", type=int, default=30, help="analysis window")
    ap.add_argument("--margin", type=float, default=0.20, help="safety margin (0.20 = +20%%)")
    args = ap.parse_args()

    end = time.time()
    start = end - args.minutes * 60
    cpu = query_range(args.prometheus,
                      f'rate(container_cpu_usage_seconds_total{{name="{args.container}"}}[30s])',
                      start, end)
    mem = query_range(args.prometheus,
                      f'container_memory_working_set_bytes{{name="{args.container}"}}',
                      start, end) / (1024 * 1024)
    if cpu.size == 0 or mem.size == 0:
        raise SystemExit("No data returned by Prometheus. Run a workload first.")

    cpu_p95, mem_p95 = float(np.percentile(cpu, 95)), float(np.percentile(mem, 95))
    rec_cpu, rec_mem = recommend(cpu_p95, mem_p95, args.margin)

    (ROOT / "infra" / "optimized.env").write_text(f"APP_CPUS={rec_cpu:.2f}\nAPP_MEM={rec_mem}m\n")
    report = build_report(args.container, args.minutes, args.margin, current_limits(),
                          (cpu_p95, mem_p95), (rec_cpu, rec_mem))
    (ROOT / "optimizer" / "recommendations.md").write_text(report)
    print(report)


if __name__ == "__main__":
    main()
