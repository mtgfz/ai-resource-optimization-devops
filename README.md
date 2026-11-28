# AI-Assisted Resource Optimization for Cloud-Native DevOps Infrastructure
![CI-CD](https://github.com/mtgfz/ai-resource-optimization-devops/actions/workflows/ci.yml/badge.svg)
Course: Virtualization and Cloud Infrastructure (ENSIAS) - Research Project
Group 1: Doha Idrissi Azami, Mouna Admant, Basma Elgharbaoui, Fatima-Ezzahra Lemtougui

## Goal
Monitor a containerized application, detect over-provisioning with a
data-driven analysis (p95 + safety margin), and **recommend** better
CPU/memory limits to an operator. Compare a baseline configuration against
the adjusted one under two workload levels.

> Scope note: the optimizer produces *recommendations*. Applying them is a
> manual operator step. We do not claim autonomous optimization.

## Repository layout
| Folder | Content | Owner |
|---|---|---|
| `app/` | Demo FastAPI app (light + heavy endpoints, `/metrics`) + tests | Pillar 1 |
| `infra/` | Docker Compose stack (app, cAdvisor, Prometheus, Grafana) | Pillar 1 |
| `.github/workflows/` | CI/CD pipeline | Pillar 2 |
| `monitoring/` | Prometheus config, Grafana provisioning + dashboard | Pillar 3 |
| `loadtest/` | k6 workload script (low / high) | Pillar 3 |
| `optimizer/` | Python recommendation engine | Pillar 4 |
| `experiments/` | Experiment runner + raw results (CSV) | Pillar 4 |
| `docs/` | Report outline, technical guide, related work, figures | Everyone |

## Quick start
```bash
# 1. start the stack with the BASELINE (generous) limits
cd infra
docker compose --env-file baseline.env up -d --build --wait

# 2. open the tools
#   App        http://localhost:8000/docs
#   Prometheus http://localhost:9090
#   Grafana    http://localhost:3000   (admin / admin)
#   cAdvisor   http://localhost:8080

# 3. generate load (needs k6: https://k6.io/docs/get-started/installation/)
cd ..
LOAD=low  k6 run loadtest/workload.js
LOAD=high k6 run loadtest/workload.js
```

## Full experiment (baseline -> recommendation -> optimized)
```bash
pip install -r optimizer/requirements.txt
python experiments/run_experiments.py --config baseline
python optimizer/optimizer.py --minutes 30          # writes recommendations
python experiments/run_experiments.py --config optimized
python experiments/plot_results.py
```
Raw results land in `experiments/results/results.csv` (see `experiments/SCHEMA.md`).
**Only report numbers that were actually measured.**

Note: cAdvisor works best on Linux (or WSL2 with Docker Desktop). If container
metrics are empty on your machine, tell the team before day 3.

## Team workflow
See `CONTRIBUTING.md` and `docs/TASKS.md`.
