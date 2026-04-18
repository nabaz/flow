# Plan: Configurable Alert Routing Engine

## Context
Take-home exercise. Build a containerized alert routing service in Python + FastAPI that ingests alerts, evaluates them against user-defined routing rules, and returns structured routing decisions. Automated test suite hits port 8080 — the API contract is fixed and must be exact.

---

## Stack
- Python 3.12 + FastAPI + Uvicorn
- Pydantic v2 for models and validation
- `zoneinfo` (stdlib) for timezone handling
- `fnmatch` (stdlib) for glob matching
- `tzdata` pip package (IANA timezone data on slim Docker images)
- In-memory dicts for all state (no DB needed; `/reset` just clears them)

---

## File Structure

```
app/
  main.py        # FastAPI app factory, include routers
  models.py      # All Pydantic models
  store.py       # In-memory state + reset helper
  engine.py      # Core routing logic
  api/
    routes.py    # /routes CRUD
    alerts.py    # POST /alerts, GET /alerts, GET /alerts/{id}
    system.py    # GET /stats, POST /test, POST /reset
Dockerfile
requirements.txt
```

---

## Data Models (`models.py`)

### Input models
```python
class AlertInput(BaseModel):
    id: str
    severity: Literal["critical", "warning", "info"]
    service: str
    group: str
    description: str | None = None
    timestamp: datetime          # validated ISO 8601, must be tz-aware
    labels: dict[str, str] = {}

class ActiveHours(BaseModel):
    timezone: str                # validated IANA via zoneinfo.ZoneInfo
    start: str                   # validated HH:MM
    end: str                     # validated HH:MM

class RouteConditions(BaseModel):
    severity: list[str] | None = None
    service: list[str] | None = None   # supports glob patterns
    group: list[str] | None = None
    labels: dict[str, str] | None = None

class RouteTarget(BaseModel):
    type: Literal["slack", "email", "pagerduty", "webhook"]
    channel: str | None = None       # slack
    address: str | None = None       # email
    service_key: str | None = None   # pagerduty
    url: str | None = None           # webhook
    headers: dict[str, str] | None = None  # webhook optional

class RouteInput(BaseModel):
    id: str
    conditions: RouteConditions
    target: RouteTarget
    priority: int
    suppression_window_seconds: int = 0   # must be >= 0
    active_hours: ActiveHours | None = None
```

### Response models
```python
class EvaluationDetails(BaseModel):
    total_routes_evaluated: int
    routes_matched: int
    routes_not_matched: int
    suppression_applied: bool

class AlertResult(BaseModel):
    alert_id: str
    routed_to: dict | None           # {route_id, target} or null
    suppressed: bool
    suppression_reason: str | None = None
    matched_routes: list[str]        # IDs of all matched routes (after active_hours filter)
    evaluation_details: EvaluationDetails
```

**Validation rules (raise 400 on failure):**
- `severity` must be critical/warning/info
- `target.type` must be slack/email/pagerduty/webhook; required type-specific field must be present
- `active_hours.timezone` must resolve via `zoneinfo.ZoneInfo(tz)` (catch `ZoneInfoNotFoundError`)
- `active_hours.start/end` must match `^\d{2}:\d{2}$` and be valid times
- `timestamp` must be ISO 8601 and timezone-aware (Pydantic handles most of this)
- `suppression_window_seconds` must be >= 0

---

## In-Memory Store (`store.py`)

```python
class Store:
    routes: dict[str, RouteInput]          # route_id -> route
    alerts: dict[str, AlertResult]         # alert_id -> result
    alert_inputs: dict[str, AlertInput]    # alert_id -> raw input (for filters)
    # suppression: (service, route_id) -> expiry_datetime (tz-aware)
    suppression: dict[tuple[str, str], datetime]
    stats: StatsAccumulator                # mutable counters

    def reset(self): ...  # clears all dicts and counters
```

`StatsAccumulator` tracks: total_processed, total_routed, total_suppressed, total_unrouted, by_severity, by_route (per-route matched/routed/suppressed), by_service.

---

## Routing Engine (`engine.py`)

### `match_conditions(alert: AlertInput, route: RouteInput) -> bool`
All specified condition fields must match:
- `severity`: `alert.severity in route.conditions.severity`
- `service`: any pattern in list matches via `fnmatch.fnmatch(alert.service, pattern)`
- `group`: `alert.group in route.conditions.group`
- `labels`: every k/v in condition labels exists in alert.labels

### `is_active(alert: AlertInput, route: RouteInput) -> bool`
- If no `active_hours`, return True
- Convert `alert.timestamp` to the route's timezone: `alert.timestamp.astimezone(ZoneInfo(tz))`
- Compare `time(H, M)` against `[start_time, end_time)` — use **alert timestamp**, not wall clock

### `is_suppressed(service, route_id, alert_timestamp, store) -> bool`
- Look up `store.suppression[(service, route_id)]`
- If exists and `alert_timestamp < expiry`, return True (suppressed)
- Expired entries can be cleaned on lookup

### `evaluate_alert(alert, store, dry_run=False) -> AlertResult`
1. Collect all routes that pass `match_conditions` AND `is_active` → `matched`
2. Sort `matched` by priority descending
3. `winner = matched[0]` if any, else unrouted
4. If winner: check `is_suppressed(alert.service, winner.id, alert.timestamp, store)`
5. If not dry_run:
   - Upsert `store.alerts[alert.id]`
   - If winner and not suppressed: set `store.suppression[(service, winner.id)] = alert.timestamp + timedelta(seconds=window)`
   - Update stats
6. Return `AlertResult` with all required fields

---

## API Endpoints

### `POST /routes` → 201
- Upsert `store.routes[route.id]`
- Return `{"id": ..., "created": True/False}`

### `GET /routes` → 200
- Return `{"routes": list(store.routes.values())}`

### `DELETE /routes/{id}` → 200 / 404
- Pop from store or return `{"error": "route not found"}`

### `POST /alerts` → 200
- Call `evaluate_alert(alert, store, dry_run=False)`

### `GET /alerts/{id}` → 200 / 404
- Return stored `AlertResult` or `{"error": "alert not found"}`

### `GET /alerts?service=&severity=&routed=&suppressed=` → 200
- Filter `store.alerts.values()` against query params
- `routed=true` → `routed_to is not None`
- `suppressed=true` → `suppressed == True`
- Return `{"alerts": [...], "total": n}`

### `GET /stats` → 200
- Return accumulated stats from `store.stats`

### `POST /test` → 200
- Call `evaluate_alert(alert, store, dry_run=True)` — no side effects

### `POST /reset` → 200
- `store.reset()` → return `{"status": "ok"}`

---

## Dockerfile

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

```
# requirements.txt
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
pydantic>=2.0.0
tzdata
```

---

## Critical Correctness Details

| Risk | How to handle |
|---|---|
| Active hours uses alert timestamp, not `now()` | `alert.timestamp.astimezone(ZoneInfo(tz))` — never call `datetime.now()` in routing |
| Glob on service field only | `fnmatch.fnmatch(alert.service, pattern)` for each pattern in list |
| `matched_routes` in response | IDs of ALL routes that matched (conditions + active_hours), not just winner |
| Suppression expiry calculation | `alert.timestamp + timedelta(seconds=window)` — use alert time, not wall clock |
| `POST /alerts` re-submission | Re-evaluate fully; overwrite existing result; suppression state from prior submission persists |
| Stats `by_route` | Only updated when a route is the **winner** (not just matched). `total_matched = total_routed + total_suppressed` |
| 400 vs 422 | FastAPI returns 422 by default for Pydantic errors; override via `exception_handler` to return `{"error": "..."}` with 400 |

---

## Build Order
1. `models.py` — all Pydantic models with validators
2. `store.py` — in-memory state and reset
3. `engine.py` — matching, active_hours, suppression, evaluate_alert
4. `api/routes.py`, `api/alerts.py`, `api/system.py`
5. `main.py` — wire together, custom 422→400 handler
6. `Dockerfile` + `requirements.txt`
7. Smoke test: `docker build`, `docker run -p 8080:8080`, hit endpoints manually

---

## Verification
```bash
# Build and run
docker build -t alert-engine .
docker run -p 8080:8080 alert-engine

# Smoke tests
curl -X POST localhost:8080/routes -H 'Content-Type: application/json' -d '{...}'
curl -X POST localhost:8080/alerts -H 'Content-Type: application/json' -d '{...}'
curl localhost:8080/stats
curl -X POST localhost:8080/reset
```
