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


def query_range(prom, expr, start, end, step=5):
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
    cur_cpu, cur_mem = current_limits()

    rec_cpu = max(0.1, math.ceil(cpu_p95 * (1 + args.margin) / 0.05) * 0.05)   # round up to 0.05 core
    rec_mem = max(64, math.ceil(mem_p95 * (1 + args.margin) / 16) * 16)        # round up to 16 MB

    (ROOT / "infra" / "optimized.env").write_text(
        f"APP_CPUS={rec_cpu:.2f}\nAPP_MEM={rec_mem}m\n")

    report = f"""# Resource recommendations for `{args.container}`

Analysis window: last {args.minutes} min | safety margin: {args.margin:.0%}

| Resource | Current limit | Observed p95 | Recommended limit |
|---|---|---|---|
| CPU (cores) | {cur_cpu:.2f} | {cpu_p95:.3f} | {rec_cpu:.2f} |
| Memory (MB) | {cur_mem} | {mem_p95:.1f} | {rec_mem} |

Reducible allocation: CPU {100*(1-rec_cpu/cur_cpu):.0f}% , memory {100*(1-rec_mem/cur_mem):.0f}%.

These are **recommendations**. Apply them with:
`cd infra && docker compose --env-file optimized.env up -d --wait`
"""
    (ROOT / "optimizer" / "recommendations.md").write_text(report)
    print(report)


if __name__ == "__main__":
    main()
