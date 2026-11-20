"""Demo application used as the workload target.

Endpoints
- GET /health        : liveness check
- GET /light         : cheap response (baseline traffic)
- GET /heavy?ms=&mb= : burns CPU for `ms` milliseconds and holds `mb` MB of memory
- GET /metrics       : Prometheus metrics (request count + latency histogram)
"""
import time

from fastapi import FastAPI, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

app = FastAPI(title="Demo App - Resource Optimization")

REQUESTS = Counter("app_requests_total", "Total HTTP requests", ["route", "status"])
LATENCY = Histogram(
    "app_request_duration_seconds",
    "HTTP request latency in seconds",
    ["route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)


@app.middleware("http")
async def track_metrics(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    route = request.url.path
    if route != "/metrics":
        LATENCY.labels(route).observe(time.perf_counter() - start)
        REQUESTS.labels(route, str(response.status_code)).inc()
    return response


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/light")
def light():
    return {"message": "hello", "ts": time.time()}


@app.get("/heavy")
def heavy(ms: int = 50, mb: int = 5):
    """Busy-loop for `ms` milliseconds and allocate `mb` MB (released on return)."""
    ms = max(0, min(ms, 2000))
    mb = max(0, min(mb, 200))
    block = bytearray(mb * 1024 * 1024)  # memory pressure
    for i in range(0, len(block), 4096):
        block[i] = 1  # touch pages so memory is really committed
    end = time.perf_counter() + ms / 1000
    x = 0
    while time.perf_counter() < end:  # CPU pressure
        x += 1
    return {"burned_ms": ms, "allocated_mb": mb}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
