"""Unit tests for SideGate FastAPI backend server and console endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from sidegate.console.server import app


def test_console_html_endpoint():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "SideGate Telemetry Console" in response.text
    assert "RUNTIME INTERCEPTION STREAM" in response.text


def test_console_api_status_and_stats():
    client = TestClient(app)

    res_status = client.get("/api/status")
    assert res_status.status_code == 200
    data_status = res_status.json()
    assert data_status["status"] == "ARMED"
    assert "HARNESS" in data_status["layers"]

    res_stats = client.get("/api/stats")
    assert res_stats.status_code == 200
    data_stats = res_stats.json()
    assert "total_intercepted" in data_stats
    assert "blocked" in data_stats


def test_console_api_events_and_tokens():
    client = TestClient(app)

    res_events = client.get("/api/events")
    assert res_events.status_code == 200
    assert isinstance(res_events.json(), list)

    res_token = client.post("/api/tokens/issue", json={"action_id": "act-test-101"})
    assert res_token.status_code == 200
    data_token = res_token.json()
    assert "confirmation_token" in data_token
    assert data_token["confirmation_token"].startswith("CONFIRMED-")


def test_console_api_intercept_and_diff():
    client = TestClient(app)

    # Test intercepting checkout click
    res_intercept = client.post(
        "/api/intercept",
        json={
            "target": "button#checkout",
            "category": "ui_click",
            "tier": 3,
            "parameters": {"text": "Pay Now $99"},
        },
    )
    assert res_intercept.status_code == 200
    data_intercept = res_intercept.json()
    assert data_intercept["decision"]["decision"] == "BLOCKED"

    # Test computing diff
    res_diff = client.post(
        "/api/diff",
        json={
            "pre_state": {"count": 1},
            "post_state": {"count": 2},
        },
    )
    assert res_diff.status_code == 200
    data_diff = res_diff.json()
    assert data_diff["total_mutations"] >= 1


def test_console_api_simulation_run():
    client = TestClient(app)
    response = client.post("/api/simulate/run?task_name=ecommerce")
    assert response.status_code == 200
    data = response.json()
    assert "regimes" in data
    assert len(data["regimes"]) == 4
