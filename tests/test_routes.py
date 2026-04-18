from tests.conftest import ROUTE_BASIC


def test_create_route(client):
    r = client.post("/routes", json=ROUTE_BASIC)
    assert r.status_code == 201
    assert r.json() == {"id": "r1", "created": True}


def test_create_route_idempotent(client):
    client.post("/routes", json=ROUTE_BASIC)
    r = client.post("/routes", json=ROUTE_BASIC)
    assert r.status_code == 201
    assert r.json() == {"id": "r1", "created": False}


def test_list_routes_empty(client):
    r = client.get("/routes")
    assert r.status_code == 200
    assert r.json() == {"routes": []}


def test_list_routes(client):
    client.post("/routes", json=ROUTE_BASIC)
    r = client.get("/routes")
    assert r.status_code == 200
    assert len(r.json()["routes"]) == 1


def test_delete_route(client):
    client.post("/routes", json=ROUTE_BASIC)
    r = client.delete("/routes/r1")
    assert r.status_code == 200
    assert r.json() == {"id": "r1", "deleted": True}
    assert client.get("/routes").json()["routes"] == []


def test_delete_route_not_found(client):
    r = client.delete("/routes/nonexistent")
    assert r.status_code == 404
    assert r.json() == {"error": "route not found"}


def test_route_requires_target_fields(client):
    bad = {**ROUTE_BASIC, "target": {"type": "slack"}}  # missing channel
    r = client.post("/routes", json=bad)
    assert r.status_code == 400
