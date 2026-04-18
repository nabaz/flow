from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from app.models import AlertInput
from app.engine import evaluate_alert
from app.store import store

router = APIRouter()


@router.post("/alerts")
def submit_alert(alert: AlertInput):
    return evaluate_alert(alert, store, dry_run=False)


@router.get("/alerts/{alert_id}")
def get_alert(alert_id: str):
    result = store.alerts.get(alert_id)
    if result is None:
        return JSONResponse(status_code=404, content={"error": "alert not found"})
    return result


@router.get("/alerts")
def list_alerts(
    service: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    routed: bool | None = Query(default=None),
    suppressed: bool | None = Query(default=None),
):
    results = []
    for alert_id, result in store.alerts.items():
        inp = store.alert_inputs.get(alert_id)

        if service is not None and (inp is None or inp.service != service):
            continue
        if severity is not None and (inp is None or inp.severity != severity):
            continue
        if routed is not None:
            is_routed = result.get("routed_to") is not None
            if routed != is_routed:
                continue
        if suppressed is not None and result.get("suppressed") != suppressed:
            continue

        results.append(result)

    return {"alerts": results, "total": len(results)}
