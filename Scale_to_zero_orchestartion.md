# Scale To Zero Orchestration

## Goal
Allow the full stack to scale to zero for idle periods, then wake on demand when a user opens the app or starts a run.

## Why This Is Hard
- `aiuxtester` (web) can auto-start from HTTP traffic.
- `aiuxtester-db` and `aiuxtester-redis` do not auto-start from browser traffic.
- Worker startup must happen only after Redis and DB are reachable.
- Concurrent requests need lock/coordination to prevent duplicate wake flows.

## Proposed Flow
1. User hits app.
2. App checks dependencies (`db`, `redis`, `worker`) readiness.
3. If not ready, app triggers warmup:
   - Start `aiuxtester-db` machine via Fly Machines API.
   - Start `aiuxtester-redis` machine via Fly Machines API.
   - Poll until both are healthy (real connection checks, not only machine state).
   - Start `aiuxtester` worker machine (or scale worker group to 1).
   - Poll until queue worker is ready.
4. UI shows “warming up platform” status until ready.
5. App releases login/session actions.

## API Endpoints Needed
- `POST /system/warmup`
- `GET /system/warmup/status`
- Optional: `POST /system/cooldown` for manual stop.

## Backend Components
- `warmup_service.py`:
  - Fly API client.
  - Start/stop machine operations.
  - Health checks:
    - MariaDB: open connection + `SELECT 1`.
    - Redis: auth + `PING`.
    - Worker: queue ping/heartbeat.
- Distributed lock:
  - Use DB advisory lock or redis lock key (if redis is up), with timeout.
  - Prevent duplicate warmups under parallel user traffic.

## Frontend UX
- Startup gate screen:
  - “Waking services…”
  - Steps:
    - Database
    - Redis
    - Worker
  - Retry button and diagnostics if warmup fails.

## Cooldown Strategy
- Keep all services alive for an inactivity window (example: 20-30 min).
- If no active sessions and no user traffic:
  - Scale worker to 0 first.
  - Stop app machine(s) next (or let Fly auto-stop).
  - Stop Redis and DB machines last.

## Security
- Store Fly API token in app secrets with minimal scope.
- Never expose Fly token to frontend.
- Warmup endpoints should require admin role or trusted internal trigger.

## Failure Handling
- If DB fails to warm:
  - Surface clear user message and retry option.
- If Redis warms but worker does not:
  - Keep app in degraded mode (read-only dashboard).
- Add circuit breaker to avoid retry storms.

## Cost Impact
- Maximum savings when fully idle.
- Tradeoff is cold-start delay and added orchestration complexity.
- Most practical intermediate model:
  - App and worker scale down aggressively.
  - Keep DB and Redis on tiny always-on machines.
