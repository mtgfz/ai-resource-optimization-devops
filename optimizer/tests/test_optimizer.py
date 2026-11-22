"""Unit tests for the recommendation logic (no Prometheus or Docker needed)."""
import pathlib
import sys

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import optimizer  # noqa: E402


# ---------- recommend(): the core maths ----------
def test_cpu_gets_margin_and_rounds_up_to_005():
    # 0.20 * 1.2 = 0.24 -> rounded UP to the next 0.05 step = 0.25
    cpu, _ = optimizer.recommend(0.20, 100, margin=0.20)
    assert cpu == pytest.approx(0.25)


def test_memory_gets_margin_and_rounds_up_to_16mb():
    # 100 * 1.2 = 120 -> rounded UP to the next multiple of 16 = 128
    _, mem = optimizer.recommend(0.20, 100, margin=0.20)
    assert mem == 128


def test_minimum_limits_are_enforced():
    cpu, mem = optimizer.recommend(0.001, 1, margin=0.20)
    assert cpu == pytest.approx(optimizer.MIN_CPU)
    assert mem == optimizer.MIN_MEM


def test_zero_margin_keeps_exact_step_values():
    cpu, mem = optimizer.recommend(0.35, 96, margin=0.0)
    assert cpu == pytest.approx(0.35)   # must not jump to 0.40 because of float noise
    assert mem == 96


def test_recommendation_is_never_below_observed_usage():
    for cpu_p95 in (0.07, 0.19, 0.33, 0.61, 0.99):
        cpu, _ = optimizer.recommend(cpu_p95, 50, margin=0.20)
        assert cpu >= cpu_p95 * 1.2 - 1e-9


# ---------- query_range(): Prometheus parsing (HTTP is mocked) ----------
class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


def test_query_range_parses_values(monkeypatch):
    payload = {"data": {"result": [{"values": [[1, "0.1"], [2, "0.3"]]}]}}
    monkeypatch.setattr(optimizer.requests, "get", lambda *a, **k: FakeResponse(payload))
    out = optimizer.query_range("http://x", "up", 0, 10)
    assert list(out) == [0.1, 0.3]


def test_query_range_empty_result(monkeypatch):
    monkeypatch.setattr(optimizer.requests, "get",
                        lambda *a, **k: FakeResponse({"data": {"result": []}}))
    assert optimizer.query_range("http://x", "up", 0, 10).size == 0


# ---------- main(): end-to-end with fake data and a temporary repo ----------
@pytest.fixture
def fake_repo(tmp_path, monkeypatch):
    (tmp_path / "infra").mkdir()
    (tmp_path / "optimizer").mkdir()
    (tmp_path / "infra" / "baseline.env").write_text("APP_CPUS=1.0\nAPP_MEM=512m\n")
    monkeypatch.setattr(optimizer, "ROOT", tmp_path)
    return tmp_path


def test_main_writes_recommendations(fake_repo, monkeypatch):
    def fake_query(prom, expr, start, end, step=5):
        if "cpu" in expr:
            return np.full(20, 0.20)
        return np.full(20, 100 * 1024 * 1024.0)

    monkeypatch.setattr(optimizer, "query_range", fake_query)
    monkeypatch.setattr(sys, "argv", ["optimizer.py", "--minutes", "5"])
    optimizer.main()
    env = (fake_repo / "infra" / "optimized.env").read_text()
    assert "APP_CPUS=0.25" in env
    assert "APP_MEM=128m" in env
    report = (fake_repo / "optimizer" / "recommendations.md").read_text()
    assert "recommendations" in report.lower()


def test_main_without_data_exits(fake_repo, monkeypatch):
    monkeypatch.setattr(optimizer, "query_range", lambda *a, **k: np.array([]))
    monkeypatch.setattr(sys, "argv", ["optimizer.py"])
    with pytest.raises(SystemExit):
        optimizer.main()
