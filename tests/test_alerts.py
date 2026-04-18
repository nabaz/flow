from tests.conftest import ROUTE_BASIC, ALERT_CRITICAL


def test_alert_routed(client):
    client.post("/routes", json=ROUTE_BASIC)
    r = client.post("/alerts", json=ALERT_CRITICAL)
    assert r.status_code == 200
    body = r.json()
    assert body["alert_id"] == "a1"
    assert body["routed_to"]["route_id"] == "r1"
    assert body["suppressed"] is False
    assert "r1" in body["matched_routes"]


def test_alert_unrouted(client):
    r = client.post("/alerts", json=ALERT_CRITICAL)
    assert r.status_code == 200
    body = r.json()
    assert body["routed_to"] is None
    assert body["matched_routes"] == []
    assert body["evaluation_details"]["routes_matched"] == 0


def test_alert_highest_priority_wins(client):
    client.post("/routes", json={**ROUTE_BASIC, "id": "low", "priority": 1,
                                  "target": {"type": "slack", "channel": "#low"}})
    client.post("/routes", json={**ROUTE_BASIC, "id": "high", "priority": 99,
                                  "target": {"type": "slack", "channel": "#high"}})
    r = client.post("/alerts", json=ALERT_CRITICAL)
    assert r.json()["routed_to"]["route_id"] == "high"


def test_glob_service_match(client):
    route = {**ROUTE_BASIC, "conditions": {"service": ["payment-*"]}}
    client.post("/routes", json=route)
    r = client.post("/alerts", json=ALERT_CRITICAL)
    assert r.json()["routed_to"]["route_id"] == "r1"


def test_glob_service_no_match(client):
    route = {**ROUTE_BASIC, "conditions": {"service": ["auth-*"]}}
    client.post("/routes", json=route)
    r = client.post("/alerts", json=ALERT_CRITICAL)
    assert r.json()["routed_to"] is None


def test_label_condition_match(client):
    route = {**ROUTE_BASIC, "conditions": {"labels": {"env": "prod"}}}
    client.post("/routes", json=route)
    alert = {**ALERT_CRITICAL, "labels": {"env": "prod", "region": "us-east-1"}}
    r = client.post("/alerts", json=alert)
    assert r.json()["routed_to"]["route_id"] == "r1"


def test_label_condition_no_match(client):
    route = {**ROUTE_BASIC, "conditions": {"labels": {"env": "prod"}}}
    client.post("/routes", json=route)
    alert = {**ALERT_CRITICAL, "labels": {"env": "staging"}}
    r = client.post("/alerts", json=alert)
    assert r.json()["routed_to"] is None


def test_suppression_window(client):
    route = {**ROUTE_BASIC, "suppression_window_seconds": 300}
    client.post("/routes", json=route)

    r1 = client.post("/alerts", json={**ALERT_CRITICAL, "id": "a1",
                                       "timestamp": "2026-03-25T14:30:00Z"})
    assert r1.json()["suppressed"] is False

    # same service, within 5-minute window
    r2 = client.post("/alerts", json={**ALERT_CRITICAL, "id": "a2",
                                       "timestamp": "2026-03-25T14:31:00Z"})
    assert r2.json()["suppressed"] is True
    assert "suppression_reason" in r2.json()

    # same service, past window
    r3 = client.post("/alerts", json={**ALERT_CRITICAL, "id": "a3",
                                       "timestamp": "2026-03-25T14:40:00Z"})
    assert r3.json()["suppressed"] is False


def test_suppression_different_service_not_suppressed(client):
    route = {**ROUTE_BASIC, "suppression_window_seconds": 300}
    client.post("/routes", json=route)

    client.post("/alerts", json={**ALERT_CRITICAL, "id": "a1", "service": "payment-api"})
    r = client.post("/alerts", json={**ALERT_CRITICAL, "id": "a2", "service": "auth-service"})
    assert r.json()["suppressed"] is False


def test_active_hours_within_window(client):
    route = {**ROUTE_BASIC, "active_hours": {
        "timezone": "America/New_York",
        "start": "09:00",
        "end": "17:00",
    }}
    client.post("/routes", json=route)
    # 14:30 UTC = 10:30 ET (within 09:00–17:00)
    r = client.post("/alerts", json={**ALERT_CRITICAL, "timestamp": "2026-03-25T14:30:00Z"})
    assert r.json()["routed_to"]["route_id"] == "r1"


def test_active_hours_outside_window(client):
    route = {**ROUTE_BASIC, "active_hours": {
        "timezone": "America/New_York",
        "start": "09:00",
        "end": "17:00",
    }}
    client.post("/routes", json=route)
    # 02:00 UTC = 22:00 ET previous day (outside 09:00–17:00)
    r = client.post("/alerts", json={**ALERT_CRITICAL, "timestamp": "2026-03-25T02:00:00Z"})
    assert r.json()["routed_to"] is None


def test_get_alert(client):
    client.post("/routes", json=ROUTE_BASIC)
    client.post("/alerts", json=ALERT_CRITICAL)
    r = client.get("/alerts/a1")
    assert r.status_code == 200
    assert r.json()["alert_id"] == "a1"


def test_get_alert_not_found(client):
    r = client.get("/alerts/nonexistent")
    assert r.status_code == 404
    assert r.json() == {"error": "alert not found"}


def test_list_alerts_filter_routed(client):
    client.post("/routes", json=ROUTE_BASIC)
    client.post("/alerts", json={**ALERT_CRITICAL, "id": "a1"})
    client.post("/alerts", json={**ALERT_CRITICAL, "id": "a2", "severity": "info"})

    r = client.get("/alerts?routed=true")
    assert r.json()["total"] == 1
    assert r.json()["alerts"][0]["alert_id"] == "a1"

    r = client.get("/alerts?routed=false")
    assert r.json()["total"] == 1
    assert r.json()["alerts"][0]["alert_id"] == "a2"


def test_list_alerts_filter_severity(client):
    client.post("/alerts", json={**ALERT_CRITICAL, "id": "a1", "severity": "critical"})
    client.post("/alerts", json={**ALERT_CRITICAL, "id": "a2", "severity": "warning"})
    r = client.get("/alerts?severity=critical")
    assert r.json()["total"] == 1


def test_resubmit_same_id_updates(client):
    # First submit: routes to r1
    client.post("/routes", json=ROUTE_BASIC)
    client.post("/alerts", json=ALERT_CRITICAL)
    # Delete route so second submit is unrouted
    client.delete("/routes/r1")
    client.post("/alerts", json=ALERT_CRITICAL)
    # GET should reflect the updated (unrouted) result
    r = client.get("/alerts/a1")
    assert r.json()["routed_to"] is None


def test_active_hours_overnight_window(client):
    route = {**ROUTE_BASIC, "active_hours": {
        "timezone": "UTC",
        "start": "22:00",
        "end": "06:00",
    }}
    client.post("/routes", json=route)
    # 23:00 UTC — inside overnight window
    r = client.post("/alerts", json={**ALERT_CRITICAL, "id": "a1", "timestamp": "2026-03-25T23:00:00Z"})
    assert r.json()["routed_to"]["route_id"] == "r1"
    # 03:00 UTC — inside overnight window (past midnight)
    r = client.post("/alerts", json={**ALERT_CRITICAL, "id": "a2", "timestamp": "2026-03-26T03:00:00Z"})
    assert r.json()["routed_to"]["route_id"] == "r1"
    # 12:00 UTC — outside overnight window
    r = client.post("/alerts", json={**ALERT_CRITICAL, "id": "a3", "timestamp": "2026-03-25T12:00:00Z"})
    assert r.json()["routed_to"] is None


def test_active_hours_exact_end_time_excluded(client):
    route = {**ROUTE_BASIC, "active_hours": {"timezone": "UTC", "start": "09:00", "end": "17:00"}}
    client.post("/routes", json=route)
    # Exactly at end time — should NOT match (exclusive end)
    r = client.post("/alerts", json={**ALERT_CRITICAL, "timestamp": "2026-03-25T17:00:00Z"})
    assert r.json()["routed_to"] is None


def test_label_condition_empty_alert_labels(client):
    route = {**ROUTE_BASIC, "conditions": {"labels": {"env": "prod"}}}
    client.post("/routes", json=route)
    # Alert has no labels — should not match
    r = client.post("/alerts", json={**ALERT_CRITICAL, "labels": {}})
    assert r.json()["routed_to"] is None


def test_list_alerts_filter_service(client):
    client.post("/alerts", json={**ALERT_CRITICAL, "id": "a1", "service": "payment-api"})
    client.post("/alerts", json={**ALERT_CRITICAL, "id": "a2", "service": "auth-service"})
    r = client.get("/alerts?service=payment-api")
    assert r.json()["total"] == 1
    assert r.json()["alerts"][0]["alert_id"] == "a1"


def test_list_alerts_filter_suppressed(client):
    route = {**ROUTE_BASIC, "suppression_window_seconds": 300}
    client.post("/routes", json=route)
    client.post("/alerts", json={**ALERT_CRITICAL, "id": "a1", "timestamp": "2026-03-25T14:30:00Z"})
    client.post("/alerts", json={**ALERT_CRITICAL, "id": "a2", "timestamp": "2026-03-25T14:31:00Z"})

    r = client.get("/alerts?suppressed=true")
    assert r.json()["total"] == 1
    assert r.json()["alerts"][0]["alert_id"] == "a2"

    r = client.get("/alerts?suppressed=false")
    assert r.json()["total"] == 1
    assert r.json()["alerts"][0]["alert_id"] == "a1"


def test_list_alerts_combined_filters(client):
    client.post("/routes", json=ROUTE_BASIC)
    client.post("/alerts", json={**ALERT_CRITICAL, "id": "a1", "service": "payment-api"})
    client.post("/alerts", json={**ALERT_CRITICAL, "id": "a2", "service": "payment-api", "severity": "warning"})
    client.post("/alerts", json={**ALERT_CRITICAL, "id": "a3", "service": "auth-service"})

    r = client.get("/alerts?service=payment-api&routed=true")
    assert r.json()["total"] == 1
    assert r.json()["alerts"][0]["alert_id"] == "a1"


def test_empty_conditions_matches_all(client):
    route = {**ROUTE_BASIC, "conditions": {}}
    client.post("/routes", json=route)
    # any severity, any service, any group should match
    r = client.post("/alerts", json={**ALERT_CRITICAL, "severity": "info", "service": "anything", "group": "anywhere"})
    assert r.json()["routed_to"]["route_id"] == "r1"


def test_three_routes_priority_and_matched_routes(client):
    client.post("/routes", json={**ROUTE_BASIC, "id": "low",  "priority": 1,  "target": {"type": "slack", "channel": "#low"}})
    client.post("/routes", json={**ROUTE_BASIC, "id": "mid",  "priority": 5,  "target": {"type": "slack", "channel": "#mid"}})
    client.post("/routes", json={**ROUTE_BASIC, "id": "high", "priority": 10, "target": {"type": "slack", "channel": "#high"}})
    r = client.post("/alerts", json=ALERT_CRITICAL)
    body = r.json()
    assert body["routed_to"]["route_id"] == "high"
    assert set(body["matched_routes"]) == {"low", "mid", "high"}
    assert body["evaluation_details"]["routes_matched"] == 3
    assert body["evaluation_details"]["total_routes_evaluated"] == 3


def test_evaluation_details_counts(client):
    client.post("/routes", json=ROUTE_BASIC)
    client.post("/routes", json={**ROUTE_BASIC, "id": "r2", "conditions": {"severity": ["warning"]}})
    r = client.post("/alerts", json=ALERT_CRITICAL)
    body = r.json()
    assert body["evaluation_details"]["total_routes_evaluated"] == 2
    assert body["evaluation_details"]["routes_matched"] == 1
    assert body["evaluation_details"]["routes_not_matched"] == 1
