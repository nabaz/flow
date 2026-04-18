from tests.conftest import ROUTE_BASIC, ALERT_CRITICAL


def test_stats_empty(client):
    r = client.get("/stats")
    assert r.status_code == 200
    body = r.json()
    assert body["total_alerts_processed"] == 0
    assert body["total_routed"] == 0
    assert body["total_unrouted"] == 0
    assert body["total_suppressed"] == 0


def test_stats_after_routing(client):
    client.post("/routes", json=ROUTE_BASIC)
    client.post("/alerts", json={**ALERT_CRITICAL, "id": "a1"})
    client.post("/alerts", json={**ALERT_CRITICAL, "id": "a2", "severity": "info"})

    body = client.get("/stats").json()
    assert body["total_alerts_processed"] == 2
    assert body["total_routed"] == 1
    assert body["total_unrouted"] == 1
    assert body["by_severity"]["critical"] == 1
    assert body["by_severity"]["info"] == 1
    assert body["by_service"]["payment-api"] == 2
    assert body["by_route"]["r1"]["total_routed"] == 1


def test_stats_suppression_counted(client):
    route = {**ROUTE_BASIC, "suppression_window_seconds": 300}
    client.post("/routes", json=route)
    client.post("/alerts", json={**ALERT_CRITICAL, "id": "a1", "timestamp": "2026-03-25T14:30:00Z"})
    client.post("/alerts", json={**ALERT_CRITICAL, "id": "a2", "timestamp": "2026-03-25T14:31:00Z"})

    body = client.get("/stats").json()
    assert body["total_suppressed"] == 1
    assert body["by_route"]["r1"]["total_suppressed"] == 1
    assert body["by_route"]["r1"]["total_matched"] == 2


def test_test_endpoint_no_side_effects(client):
    client.post("/routes", json=ROUTE_BASIC)
    r = client.post("/test", json=ALERT_CRITICAL)
    assert r.status_code == 200
    assert r.json()["routed_to"]["route_id"] == "r1"

    # alert should NOT be stored
    assert client.get("/alerts/a1").status_code == 404
    # stats should NOT be updated
    assert client.get("/stats").json()["total_alerts_processed"] == 0


def test_reset(client):
    client.post("/routes", json=ROUTE_BASIC)
    client.post("/alerts", json=ALERT_CRITICAL)

    r = client.post("/reset")
    assert r.json() == {"status": "ok"}
    assert client.get("/routes").json()["routes"] == []
    assert client.get("/stats").json()["total_alerts_processed"] == 0


def test_validation_missing_severity(client):
    alert = {k: v for k, v in ALERT_CRITICAL.items() if k != "severity"}
    r = client.post("/alerts", json=alert)
    assert r.status_code == 400
    assert "error" in r.json()


def test_validation_invalid_severity(client):
    r = client.post("/alerts", json={**ALERT_CRITICAL, "severity": "catastrophic"})
    assert r.status_code == 400


def test_validation_invalid_timezone(client):
    route = {**ROUTE_BASIC, "active_hours": {"timezone": "Fake/Zone", "start": "09:00", "end": "17:00"}}
    r = client.post("/routes", json=route)
    assert r.status_code == 400


def test_validation_invalid_active_hours_format(client):
    route = {**ROUTE_BASIC, "active_hours": {"timezone": "UTC", "start": "9:00", "end": "17:00"}}
    r = client.post("/routes", json=route)
    assert r.status_code == 400


def test_validation_negative_suppression(client):
    route = {**ROUTE_BASIC, "suppression_window_seconds": -1}
    r = client.post("/routes", json=route)
    assert r.status_code == 400


def test_validation_missing_alert_fields(client):
    required = ["id", "service", "group", "timestamp"]
    for field in required:
        body = {k: v for k, v in ALERT_CRITICAL.items() if k != field}
        r = client.post("/alerts", json=body)
        assert r.status_code == 400, f"expected 400 when '{field}' is missing"
        assert "error" in r.json()


def test_validation_naive_timestamp(client):
    r = client.post("/alerts", json={**ALERT_CRITICAL, "timestamp": "2026-03-25T14:30:00"})
    assert r.status_code == 400


def test_validation_malformed_timestamp(client):
    r = client.post("/alerts", json={**ALERT_CRITICAL, "timestamp": "not-a-date"})
    assert r.status_code == 400


def test_validation_priority_not_integer(client):
    r = client.post("/routes", json={**ROUTE_BASIC, "priority": "high"})
    assert r.status_code == 400


def test_validation_invalid_target_type(client):
    route = {**ROUTE_BASIC, "target": {"type": "carrier_pigeon", "channel": "#oncall"}}
    r = client.post("/routes", json=route)
    assert r.status_code == 400


def test_stats_by_route_total_matched_includes_suppressed(client):
    route = {**ROUTE_BASIC, "suppression_window_seconds": 300}
    client.post("/routes", json=route)
    client.post("/alerts", json={**ALERT_CRITICAL, "id": "a1", "timestamp": "2026-03-25T14:30:00Z"})
    client.post("/alerts", json={**ALERT_CRITICAL, "id": "a2", "timestamp": "2026-03-25T14:31:00Z"})
    client.post("/alerts", json={**ALERT_CRITICAL, "id": "a3", "timestamp": "2026-03-25T14:40:00Z"})

    body = client.get("/stats").json()
    rs = body["by_route"]["r1"]
    assert rs["total_matched"] == 3
    assert rs["total_routed"] == 2
    assert rs["total_suppressed"] == 1
    assert rs["total_matched"] == rs["total_routed"] + rs["total_suppressed"]


def test_reset_clears_suppression(client):
    route = {**ROUTE_BASIC, "suppression_window_seconds": 300}
    client.post("/routes", json=route)
    client.post("/alerts", json={**ALERT_CRITICAL, "id": "a1", "timestamp": "2026-03-25T14:30:00Z"})

    client.post("/reset")
    client.post("/routes", json=route)

    # After reset, same service should NOT be suppressed
    r = client.post("/alerts", json={**ALERT_CRITICAL, "id": "a2", "timestamp": "2026-03-25T14:31:00Z"})
    assert r.json()["suppressed"] is False
