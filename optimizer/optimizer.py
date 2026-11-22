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


_UNITS_TO_BYTES = {"B": 1, "kB": 1000, "KB": 1000, "MB": 1000**2, "GB": 1000**3,
                   "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3}


def parse_size_mb(text):
    """Convert a docker size such as '45.6MiB' or '812kB' to MB (1 MB = 1024*1024 bytes)."""
    text = text.strip()
    for unit in sorted(_UNITS_TO_BYTES, key=len, reverse=True):
        if text.endswith(unit):
            return float(text[: -len(unit)]) * _UNITS_TO_BYTES[unit] / (1024 * 1024)
    raise ValueError(f"unknown size: {text!r}")


def parse_docker_stats(text):
    """Parse lines written by: docker stats --no-stream --format '{{.CPUPerc}};{{.MemUsage}}'

    Example line: '12.34%;45.6MiB / 512MiB'. Returns (cpu_cores, memory_mb) as numpy arrays.
    docker reports CPU as a percentage of ONE core, so 100% = 1 core.
    """
    cpu, mem = [], []
    for line in text.splitlines():
        try:
            cpu_part, mem_part = line.strip().split(";", 1)
            cpu_val = float(cpu_part.strip().rstrip("%")) / 100
            mem_val = parse_size_mb(mem_part.split("/")[0])
        except ValueError:
            continue   # skip empty or malformed lines
        cpu.append(cpu_val)
        mem.append(mem_val)
    return np.array(cpu), np.array(mem)


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


def build_report(container, window, margin, cur, p95, rec):
    cur_cpu, cur_mem = cur
    cpu_p95, mem_p95 = p95
    rec_cpu, rec_mem = rec
    return f"""# Resource recommendations for `{container}`

Data source: {window} | safety margin: {margin:.0%}

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
    ap.add_argument("--selector", default=None,
                    help='PromQL label selector, default: name="<container>". '
                         'Example: id=~".*<container-id>.*" when cAdvisor has no name label')
    ap.add_argument("--minutes", type=int, default=30, help="analysis window")
    ap.add_argument("--margin", type=float, default=0.20, help="safety margin (0.20 = +20%%)")
    ap.add_argument("--docker-stats", default=None,
                    help="read samples written by `docker stats` (see parse_docker_stats) "
                         "instead of querying Prometheus")
    args = ap.parse_args()

    if args.docker_stats:
        cpu, mem = parse_docker_stats(pathlib.Path(args.docker_stats).read_text())
        if cpu.size == 0:
            raise SystemExit("No usable samples in the docker stats file.")
        window = f"docker stats, {cpu.size} samples"
    else:
        cpu, mem, window = query_prometheus(args)

    cpu_p95, mem_p95 = float(np.percentile(cpu, 95)), float(np.percentile(mem, 95))
    rec_cpu, rec_mem = recommend(cpu_p95, mem_p95, args.margin)

    (ROOT / "infra" / "optimized.env").write_text(f"APP_CPUS={rec_cpu:.2f}\nAPP_MEM={rec_mem}m\n")
    report = build_report(args.container, window, args.margin, current_limits(),
                          (cpu_p95, mem_p95), (rec_cpu, rec_mem))
    (ROOT / "optimizer" / "recommendations.md").write_text(report)
    print(report)


def query_prometheus(args):
    end = time.time()
    start = end - args.minutes * 60
    selector = args.selector or f'name="{args.container}"'
    cpu = query_range(args.prometheus,
                      f"rate(container_cpu_usage_seconds_total{{{selector}}}[15s])",
                      start, end)
    mem = query_range(args.prometheus,
                      f"container_memory_working_set_bytes{{{selector}}}",
                      start, end) / (1024 * 1024)
    if cpu.size == 0 or mem.size == 0:
        raise SystemExit(f"No data returned by Prometheus for selector {{{selector}}}. "
                         "Run a workload first, or pass --selector.")

    return cpu, mem, f"Prometheus, last {args.minutes} min"


if __name__ == "__main__":
    main()
