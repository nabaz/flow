import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.store import store


@pytest.fixture
def client():
    store.reset()
    return TestClient(app)


ROUTE_BASIC = {
    "id": "r1",
    "conditions": {"severity": ["critical"]},
    "target": {"type": "slack", "channel": "#oncall"},
    "priority": 10,
}

ALERT_CRITICAL = {
    "id": "a1",
    "severity": "critical",
    "service": "payment-api",
    "group": "backend",
    "timestamp": "2026-03-25T14:30:00Z",
}
