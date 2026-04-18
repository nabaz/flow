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

## Future Improvements

The current implementation is an MVP optimized for correctness under a 2-hour time-box. Taking it to production would involve these changes:

### Persistence

In-memory state disappears on container restart and can't be shared across replicas. Two stores with different access patterns:

- **PostgreSQL for routes and alert history.** Routes are a small, read-heavy dataset with structured queries — a `routes` table with a JSONB `conditions` column and a partial index on `priority DESC` covers all current filters. Alert history is append-mostly with filter queries on `service`, `severity`, and `routed`/`suppressed` booleans — a single table with composite indexes on those columns handles it. Keeping the evaluation logic pure (same inputs → same output) means the DB layer can be swapped in without touching `engine.py`.
- **Redis for suppression state.** Suppression is the one piece of state that's both hot-path and naturally TTL-bound. `SET service:route_id 1 EX <window> NX` is atomic, auto-expires, and avoids a background cleanup job. The `(service, route_id)` key maps cleanly to a Redis string. Alternative: `pg_cron` on a `suppressions` table with `expires_at` — slower but one less service to operate.

### Horizontal Scaling & Distributed Locking

Running multiple replicas behind a load balancer introduces a classic race: two alerts for the same `(service, route)` arrive at different replicas simultaneously — both check suppression, both see "not suppressed," both notify. The Redis approach above solves this cleanly: `SET ... NX` returns success to exactly one caller, the other receives `nil` and treats the alert as suppressed. No separate lock service needed.

For route evaluation itself, each request is independent and can run on any replica — no coordination required. Stats counters would move to Redis `INCR` (atomic) or be computed on read from the alert history table (slower but always consistent).

If alert delivery becomes async (a notifier worker pulls routed alerts off a queue), use a durable queue (SQS, Redis Streams, or Postgres `FOR UPDATE SKIP LOCKED`) for at-least-once delivery with idempotency keys on the (alert_id, route_id) tuple.

### API Contract & OpenAPI

FastAPI already serves an auto-generated OpenAPI spec at `/openapi.json` and Swagger UI at `/docs`. To productionize:

- **Explicit response models.** Today the engine returns dicts; replacing them with Pydantic response models surfaces the full shape in the OpenAPI spec and catches drift at compile time.
- **Spec export to the repo.** Committing `openapi.json` lets downstream consumers generate clients (`openapi-generator`, `orval`) and enables contract tests (`schemathesis`) in CI.
- **Versioned endpoints.** `/v1/alerts` from day one so breaking changes can ship without coordination.

### Other Production Concerns

- **Structured logging and tracing** — JSON logs with request IDs, OpenTelemetry spans around `evaluate_alert` to profile matching on large route counts.
- **Metrics** — Prometheus counters (alerts processed, routed, suppressed by route) exposed at `/metrics`.
- **Actual notification delivery** — the `target` field currently describes where to send but the service doesn't deliver. A separate notifier service consuming routed alerts from a queue keeps the routing engine fast and decouples failure modes.
- **AuthZ/AuthN** — at minimum, API keys on the admin endpoints (`POST /routes`, `POST /reset`).
- **Rate limiting** on `POST /alerts` per-service to prevent noisy neighbors from overwhelming the matcher.

## AI-Native Workflow

This project was built using an AI-native workflow — Claude as a genuine co-builder, not an autocomplete. The approach:

- **Incremental decomposition** rather than one big prompt. Spec → plan file → one file at a time (models → store → engine → API → tests → polish). Each step reviewed, committed, and pushed before moving on.
- **Targeted delegation**: boilerplate, repetitive test cases, and mechanical validators went to Claude; architecture decisions (in-memory vs SQLite, sync vs async handlers, suppression keying, exclusive-end active hours) were deliberate human calls.
- **Iterative course correction**: when smoke tests revealed issues (e.g. `suppression_reason` outputting `+00:00` instead of `Z`, `GET /routes` leaking null fields), they were fed back into the conversation rather than patched silently.
- **Git as a feedback loop**: every stable checkpoint was committed and pushed, so course corrections had clear rollback points.

The full conversation history is preserved in the submission.

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
