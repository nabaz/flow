# Alert Routing Engine

A configurable alert routing service. Ingests monitoring alerts via REST API, evaluates them against routing rules, and returns structured routing decisions.

## Build & Run

```bash
docker build -t alert-router . && docker run -p 8080:8080 alert-router
```

Service listens on **port 8080** and is ready within ~4 seconds of `docker run`.

Interactive API docs: `http://localhost:8080/docs`

## Run Tests

```bash
docker run --rm alert-router python -m pytest tests/ -v
```

## Language & Framework

**Python 3.12 + FastAPI + Pydantic v2**

- **FastAPI** gives us automatic request validation, clean route declarations, and Swagger UI for free — all with near-zero boilerplate. For an API-first service under time pressure it's the right call.
- **Pydantic v2** handles all input validation (required fields, type coercion rejection, enum values, custom validators for timezone and HH:MM format) with precise error messages. The `field_validator` and `model_validator` hooks make the routing config constraints easy to express and test.
- **Standard library only for core logic** — `zoneinfo` for IANA timezone handling, `fnmatch` for glob matching, `datetime` for suppression windows. No extra dependencies for the things that matter most.
- **In-memory state** rather than SQLite or Redis. The spec requires a `POST /reset` endpoint that clears everything — in-memory is the simplest correct choice and eliminates an entire class of persistence bugs.

## Design Decisions

**Routing uses alert timestamp, not wall clock**
Active hours and suppression windows are evaluated against `alert.timestamp`, not `datetime.now()`. This makes routing deterministic and testable — the same alert always produces the same decision regardless of when it's processed.

**Suppression is keyed on `(service, route_id)`**
The spec suppresses duplicates per service per route. This means two different services can both trigger the same route within the window without suppressing each other, and the same service on a lower-priority route is unaffected.

**Only the winning route updates suppression state**
Lower-priority matching routes are recorded in `matched_routes` for observability but don't open suppression windows. This matches the spec's intent: suppression tracks notifications sent, not route evaluations.

**`POST /test` is fully read-only**
The dry-run endpoint reads current suppression state (so it gives an accurate prediction) but writes nothing — no alert stored, no suppression window opened, no stats updated.

**400 errors include the field name**
Rather than forwarding Pydantic's raw message, errors are formatted as `"field: reason"` (e.g. `"severity: Input should be 'critical', 'warning' or 'info'"`). This makes the error immediately actionable without needing to parse a nested detail object.

## API Overview

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/routes` | Create or replace a routing rule (201) |
| `GET` | `/routes` | List all routing rules |
| `DELETE` | `/routes/{id}` | Delete a routing rule |
| `POST` | `/alerts` | Submit an alert for routing |
| `GET` | `/alerts/{id}` | Get routing result for a specific alert |
| `GET` | `/alerts` | List alerts (`?service=`, `?severity=`, `?routed=`, `?suppressed=`) |
| `GET` | `/stats` | Aggregate routing statistics |
| `POST` | `/test` | Dry-run an alert (no side effects) |
| `POST` | `/reset` | Clear all state |
| `GET` | `/health` | Health check |
