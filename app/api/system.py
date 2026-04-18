from fastapi import APIRouter

from app.models import AlertInput
from app.engine import evaluate_alert
from app.store import store

router = APIRouter()


@router.get("/stats")
def get_stats():
    s = store.stats
    return {
        "total_alerts_processed": s.total_alerts_processed,
        "total_routed": s.total_routed,
        "total_suppressed": s.total_suppressed,
        "total_unrouted": s.total_unrouted,
        "by_severity": s.by_severity,
        "by_route": {
            rid: {
                "total_matched": rs.total_matched,
                "total_routed": rs.total_routed,
                "total_suppressed": rs.total_suppressed,
            }
            for rid, rs in s.by_route.items()
        },
        "by_service": s.by_service,
    }


@router.post("/test")
def test_alert(alert: AlertInput):
    return evaluate_alert(alert, store, dry_run=True)


@router.post("/reset")
def reset():
    store.reset()
    return {"status": "ok"}
