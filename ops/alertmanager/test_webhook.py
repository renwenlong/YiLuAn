"""Tests for wechat-work-webhook adapter (dry-run mode)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _load_module():
    """Load the hyphenated module path explicitly."""
    src = Path(__file__).parent / "wechat-work-webhook.py"
    spec = importlib.util.spec_from_file_location("wechat_work_webhook", src)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["wechat_work_webhook"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(autouse=True)
def _ensure_dry_run(monkeypatch):
    monkeypatch.delenv("WECHAT_WORK_WEBHOOK_URL", raising=False)
    yield


@pytest.fixture
def mod():
    m = _load_module()
    # Reset rate limiter between tests to avoid cross-pollution.
    m._rate_state.clear()
    return m


@pytest.fixture
def client(mod):
    return TestClient(mod.app)


# ---- formatting ---------------------------------------------------------

def test_format_firing_alert_contains_required_fields(mod):
    payload = {
        "status": "firing",
        "groupLabels": {"alertname": "HighHTTP5xxRate"},
        "commonLabels": {
            "alertname": "HighHTTP5xxRate",
            "severity": "critical",
            "service": "yiluan-api",
            "instance": "api-1:8000",
        },
        "alerts": [
            {
                "startsAt": "2026-04-24T15:00:00Z",
                "endsAt": "0001-01-01T00:00:00Z",
                "annotations": {
                    "summary": "5xx rate above 5%",
                    "description": "rolling 5min window",
                },
                "labels": {},
            }
        ],
        "externalURL": "http://alertmanager.local",
    }
    md = mod.format_alert_markdown(payload)
    assert "🔥" in md
    assert "告警触发" in md
    assert "HighHTTP5xxRate" in md
    assert "critical" in md
    assert "yiluan-api" in md
    assert "api-1:8000" in md
    assert "5xx rate above 5%" in md
    assert "http://alertmanager.local" in md


def test_format_resolved_includes_end_time(mod):
    payload = {
        "status": "resolved",
        "groupLabels": {"alertname": "HighRequestLatency"},
        "commonLabels": {"alertname": "HighRequestLatency", "severity": "warning"},
        "alerts": [
            {
                "startsAt": "2026-04-24T15:00:00Z",
                "endsAt": "2026-04-24T15:10:00Z",
                "annotations": {"summary": "p95 latency back to normal"},
                "labels": {},
            }
        ],
        "externalURL": "",
    }
    md = mod.format_alert_markdown(payload)
    assert "✅" in md
    assert "告警恢复" in md
    assert "2026-04-24T15:10:00Z" in md


def test_to_wechat_work_payload_envelope(mod):
    env = mod.to_wechat_work_payload("hello")
    assert env == {"msgtype": "markdown", "markdown": {"content": "hello"}}


# ---- HTTP / rate limiting -----------------------------------------------

def test_alert_endpoint_dry_run_returns_preview(client):
    payload = {
        "status": "firing",
        "groupLabels": {"alertname": "TestAlert"},
        "commonLabels": {"alertname": "TestAlert", "severity": "warning"},
        "alerts": [
            {
                "startsAt": "2026-04-24T15:00:00Z",
                "endsAt": "0001-01-01T00:00:00Z",
                "annotations": {"summary": "just a test"},
                "labels": {},
            }
        ],
        "externalURL": "http://am.local",
    }
    r = client.post("/alert", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "dry_run"
    assert body["alertname"] == "TestAlert"
    assert "TestAlert" in body["preview"]


def test_rate_limit_drops_after_threshold(client, mod):
    payload = {
        "status": "firing",
        "groupLabels": {"alertname": "Flood"},
        "commonLabels": {"alertname": "Flood", "severity": "warning"},
        "alerts": [{"startsAt": "2026-04-24T15:00:00Z", "endsAt": "0001-01-01T00:00:00Z",
                    "annotations": {}, "labels": {}}],
        "externalURL": "",
    }
    statuses = []
    for _ in range(mod.RATE_LIMIT_MAX + 2):
        r = client.post("/alert", json=payload)
        statuses.append(r.json()["status"])
    # First N succeed (dry_run), the rest are rate_limited.
    assert statuses.count("dry_run") == mod.RATE_LIMIT_MAX
    assert statuses.count("rate_limited") == 2


def test_healthz_reports_dry_run(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["dry_run"] is True
    assert body["rate_limit"]["max"] >= 1
