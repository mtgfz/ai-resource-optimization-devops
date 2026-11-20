"""Draw baseline-vs-optimized bar charts from results.csv into docs/figures/."""
import pathlib
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = pathlib.Path(__file__).resolve().parents[1]
df = pd.read_csv(ROOT / "experiments" / "results" / "results.csv")
metrics = {"cpu_avg_pct": "CPU utilization (% of limit)", "mem_avg_mb": "Memory (MB)",
           "p95_latency_ms": "p95 response time (ms)", "throughput_rps": "Throughput (req/s)",
           "deploy_duration_s": "Deployment duration (s)"}
for col, label in metrics.items():
    g = df.groupby(["load_level", "config"])[col].agg(["mean", "std"]).unstack("config")
    ax = g["mean"].plot(kind="bar", yerr=g["std"], capsize=3, figsize=(6, 4))
    ax.set_ylabel(label); ax.set_xlabel("Workload level"); ax.set_title(label)
    plt.xticks(rotation=0); plt.tight_layout()
    plt.savefig(ROOT / "docs" / "figures" / f"{col}.png", dpi=150); plt.close()
print("Figures saved to docs/figures/")
