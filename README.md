# Alert Routing Engine

A containerized alert routing service. Ingests monitoring alerts, evaluates them against configurable routing rules, and returns structured routing decisions.

## Build & Run

```bash
docker build -t alert-engine .
docker run -p 8080:8080 alert-engine
```

Service listens on **port 8080**. Interactive API docs available at `http://localhost:8080/docs`.

## Run Tests

```bash
docker run --rm alert-engine python -m pytest tests/ -v
```

## API Overview

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/routes` | Create or replace a routing rule |
| `GET` | `/routes` | List all routing rules |
| `DELETE` | `/routes/{id}` | Delete a routing rule |
| `POST` | `/alerts` | Submit an alert for routing |
| `GET` | `/alerts/{id}` | Get routing result for an alert |
| `GET` | `/alerts` | List alerts (filterable by service, severity, routed, suppressed) |
| `GET` | `/stats` | Aggregate routing statistics |
| `POST` | `/test` | Dry-run an alert without side effects |
| `POST` | `/reset` | Clear all state |
| `GET` | `/health` | Health check |

## Key Behaviours

- **Glob matching** on `service` conditions (e.g. `payment-*` matches `payment-api`)
- **Timezone-aware scheduling** via `active_hours` — evaluated against the alert's own timestamp, not wall clock
- **Suppression windows** per `(service, route)` pair — deduplicates noisy alerts
- **Priority-based routing** — highest priority matching route wins; lower matches are recorded but not notified
- **Dry-run** via `POST /test` — reads suppression state but writes nothing
