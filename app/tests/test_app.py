import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_light():
    assert client.get("/light").status_code == 200


def test_heavy_is_bounded():
    r = client.get("/heavy?ms=5&mb=1")
    assert r.status_code == 200
    assert r.json()["burned_ms"] == 5


def test_metrics_exposed():
    client.get("/light")
    body = client.get("/metrics").text
    assert "app_requests_total" in body
