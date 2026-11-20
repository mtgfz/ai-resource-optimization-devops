# Task split (4 pillars, equal share)

Each member = 1 technical pillar + report sections + technical-guide sections + 1 video segment.
Everyone must be able to explain the WHOLE project.

| Pillar | Owner | Technical work | Report sections (EN) | Guide sections | Video segment |
|---|---|---|---|---|---|
| 1 App + infra | Doha | app/, Dockerfile, Compose, (optional K8s manifests) | 4 Architecture, 5 Setup (+ architecture diagram) | Prerequisites, Installation | Architecture + start the stack |
| 2 CI/CD | Mouna | .github/workflows, tests, deploy-time measure | 4 CI/CD workflow (+ pipeline diagram) | Configuration, Deployment | git push -> pipeline run |
| 3 Monitoring + load | Basma | Prometheus, Grafana dashboard, k6 | 5 Metrics + protocol (how each metric is measured) | Monitoring, Troubleshooting | Live dashboard during load test |
| 4 Optimizer + experiments | Fatima-Ezzahra | optimizer/, experiment runner, plots | 3 Problem, 4 Method, 6 Results, 7 Discussion | Execution, Testing | Run optimizer, apply, compare |

## Shared
- Related Work (8+ peer-reviewed refs, IEEE): Basma + Fatima-Ezzahra; everyone reads 2 papers -> `docs/related-work.md`
- Introduction, Abstract (150-250 words), 4-6 keywords: Doha + Mouna
- Conclusion and Future Work: 1 paragraph each
- Cross-review: each person reviews another person's sections
- Video assembly: one person edits, everyone records their segment

## Timeline
| Day | Goal |
|---|---|
| 1 | Repo shared, tools decided, read papers |
| 2 | App + Compose + Prometheus/Grafana working |
| 3 | CI/CD working, k6 scripts ready |
| 4 | Baseline experiments done (results.csv) |
| 5 | Optimizer + optimized experiments |
| 6 | Report + guide complete, figures |
| 7 | Video recorded, final review |

## Bonus ideas (pick 2-3 only after the core works)
- Kubernetes (k3s/kind) + HorizontalPodAutoscaler comparison
- Isolation Forest anomaly detection on CPU/memory series
- CI job that posts the recommendations as a PR comment
- Estimated cloud cost savings table
- Before/after Grafana dashboard screenshot set
