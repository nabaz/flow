from datetime import datetime, time, timedelta
from fnmatch import fnmatch
from zoneinfo import ZoneInfo

from app.models import AlertInput, RouteInput


def match_conditions(alert: AlertInput, route: RouteInput) -> bool:
    c = route.conditions

    if c.severity is not None and alert.severity not in c.severity:
        return False

    if c.group is not None and alert.group not in c.group:
        return False

    if c.service is not None:
        if not any(fnmatch(alert.service, pattern) for pattern in c.service):
            return False

    if c.labels is not None:
        for k, v in c.labels.items():
            if alert.labels.get(k) != v:
                return False

    return True


def is_active(alert: AlertInput, route: RouteInput) -> bool:
    if route.active_hours is None:
        return True

    ah = route.active_hours
    local_dt = alert.timestamp.astimezone(ZoneInfo(ah.timezone))
    local_time = local_dt.time().replace(second=0, microsecond=0)

    start_h, start_m = int(ah.start[:2]), int(ah.start[3:])
    end_h, end_m = int(ah.end[:2]), int(ah.end[3:])
    start = time(start_h, start_m)
    end = time(end_h, end_m)

    if start <= end:
        return start <= local_time < end
    # overnight window e.g. 22:00 -> 06:00
    return local_time >= start or local_time < end


def is_suppressed(service: str, route_id: str, alert_ts: datetime, store) -> bool:
    key = (service, route_id)
    expiry = store.suppression.get(key)
    if expiry is None:
        return False
    if alert_ts >= expiry:
        del store.suppression[key]
        return False
    return True


def evaluate_alert(alert: AlertInput, store, dry_run: bool = False) -> dict:
    all_routes = list(store.routes.values())

    matched = [r for r in all_routes if match_conditions(alert, r) and is_active(alert, r)]
    matched.sort(key=lambda r: r.priority, reverse=True)

    total = len(all_routes)
    matched_ids = [r.id for r in matched]

    if not matched:
        result = {
            "alert_id": alert.id,
            "routed_to": None,
            "suppressed": False,
            "matched_routes": [],
            "evaluation_details": {
                "total_routes_evaluated": total,
                "routes_matched": 0,
                "routes_not_matched": total,
                "suppression_applied": False,
            },
        }
        if not dry_run:
            store.alerts[alert.id] = result
            store.alert_inputs[alert.id] = alert
            store.stats.record(alert.severity, alert.service, None, False)
        return result

    winner = matched[0]
    suppressed = is_suppressed(alert.service, winner.id, alert.timestamp, store)

    routed_to = {"route_id": winner.id, "target": winner.target.model_dump(exclude_none=True)}

    result: dict = {
        "alert_id": alert.id,
        "routed_to": routed_to,
        "suppressed": suppressed,
        "matched_routes": matched_ids,
        "evaluation_details": {
            "total_routes_evaluated": total,
            "routes_matched": len(matched),
            "routes_not_matched": total - len(matched),
            "suppression_applied": suppressed,
        },
    }

    if suppressed:
        expiry = store.suppression[(alert.service, winner.id)]
        result["suppression_reason"] = (
            f"Alert for service '{alert.service}' on route '{winner.id}' "
            f"suppressed until {expiry.isoformat()}"
        )

    if not dry_run:
        store.alerts[alert.id] = result
        store.alert_inputs[alert.id] = alert
        if not suppressed and winner.suppression_window_seconds > 0:
            expiry = alert.timestamp + timedelta(seconds=winner.suppression_window_seconds)
            store.suppression[(alert.service, winner.id)] = expiry
        store.stats.record(alert.severity, alert.service, winner.id, suppressed)

    return result
