"""Tests for the metric-source selection and the docker stats sampler (no Docker needed)."""
import pathlib
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import run_experiments as rx  # noqa: E402

NAN = float("nan")


def test_auto_prefers_prometheus_when_it_has_data():
    assert rx.choose_metrics((0.2, 100.0), (0.5, 200.0), "auto") == (0.2, 100.0, "prometheus")


def test_auto_falls_back_to_docker_stats_when_prometheus_is_empty():
    assert rx.choose_metrics((NAN, NAN), (0.5, 200.0), "auto") == (0.5, 200.0, "docker-stats")


def test_forced_collectors():
    assert rx.choose_metrics((0.2, 100.0), (0.5, 200.0), "docker-stats")[2] == "docker-stats"
    cpu, mem, source = rx.choose_metrics((NAN, NAN), (0.5, 200.0), "prometheus")
    assert source == "prometheus" and cpu != cpu   # NaN is kept, nothing is invented


def test_sampler_collects_and_averages(monkeypatch):
    class Done:
        stdout = "50.00%;100MiB / 512MiB\n"

    monkeypatch.setattr(rx.subprocess, "run", lambda *a, **k: Done())
    s = rx.DockerStatsSampler(interval=0.01)
    s.start()
    while len(s.cpu) < 3:
        pass
    s.stop()
    cpu, mem = s.averages()
    assert cpu == pytest.approx(0.5)
    assert mem == pytest.approx(100.0)


def test_sampler_survives_docker_errors(monkeypatch):
    def boom(*a, **k):
        raise subprocess.SubprocessError("docker not available")

    monkeypatch.setattr(rx.subprocess, "run", boom)
    s = rx.DockerStatsSampler(interval=0.01)
    s.start()
    s.stop()
    cpu, mem = s.averages()
    assert cpu != cpu and mem != mem   # NaN, no crash


def test_avg_returns_nan_when_prometheus_is_down(monkeypatch):
    def down(*a, **k):
        raise rx.requests.ConnectionError("no prometheus")

    monkeypatch.setattr(rx.requests, "get", down)
    assert rx.avg("up", 0, 1) != rx.avg("up", 0, 1)   # NaN != NaN
