# results.csv schema (one row = one run)

| Column | Meaning |
|---|---|
| run_id | unique id (timestamp) |
| config | baseline or optimized |
| load_level | low (10 VUs) or high (100 VUs) |
| repetition | 1..N |
| cpu_limit / mem_limit_mb | limits applied for the run |
| cpu_avg_pct | average CPU usage as % of the CPU limit during the run |
| mem_avg_mb | average memory working set during the run |
| p95_latency_ms | 95th percentile response time (k6) |
| throughput_rps | requests per second (k6) |
| restarts | container restart count after the run (docker inspect) |
| deploy_duration_s | time of `docker compose up -d --wait` |
| metrics_source | where CPU/memory came from: `prometheus` or `docker-stats` (fallback when cAdvisor cannot see the container) |

Rule: only real measurements are written here. Never edit values by hand.
