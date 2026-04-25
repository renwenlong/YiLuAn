# E2E Tests

End-to-end backend API tests. They exercise the **full FastAPI app** —
auth, orders, payments (mock), chat, admin audit — over the in-process
`httpx.AsyncClient` against the same SQLite + FakeRedis harness used by
the unit suite. The goal is to validate **user journeys**, not isolated
units.

## Layout

| File | Coverage |
| --- | --- |
| `test_e2e_patient_full_journey.py` | OTP register → browse → order → pay (mock) → chat → start → complete → review |
| `test_e2e_companion_full_journey.py` | OTP register → apply → admin approve → accept → start → complete → stats; reject path |
| `test_e2e_auth_flows.py` | OTP send/verify, refresh round-trip, garbage-token rejection, Apple Sign-In (mock verify) |
| `test_e2e_admin_audit.py` | `X-Admin-Token` companion approval flow + JWT-based admin role on `/admin/orders` |
| `test_e2e_order_cancel_refund.py` | Cancel before/after payment, companion reject, double-pay idempotency (xfailed where state machine still WIP) |
| `test_e2e_chat_websocket.py` | REST chat send/list/pagination + outsider forbidden + WS bidirectional (skipped if `websockets` missing) |
| `test_payment_real.py` | (gated) WeChat Pay real-credential smoke — runs when `WECHATPAY_REAL_CREDS=1` |
| `test_sms_real.py` | (gated) Real SMS provider smoke — gated on env vars |

All e2e files are auto-marked `@pytest.mark.e2e` by `conftest.py`.

## Running locally

```bash
cd backend
python -m pytest tests/e2e/ -m e2e -v
```

That's it — no docker required. The e2e `conftest.py` reuses the parent
`client` / `fake_redis` / `seed_*` fixtures from `tests/conftest.py`,
which set up an in-memory SQLite + FakeRedis. Two extra tweaks live in
`tests/e2e/conftest.py`:

* `_disable_slowapi_limiter` — turns off the per-IP `5/min` cap on
  `/auth/send-otp` (every test request shares `127.0.0.1`).
* `_redirect_app_async_session` — points the few services that open
  their own `app.database.async_session()` (e.g. SMS logging wrapper)
  at the same in-memory engine so they don't try to talk to the
  configured Postgres.

### Running against real Postgres + Redis (parity)

If you want to run the suite against a real PG/Redis (matching what the
production deploy would see), spin up ephemeral docker containers and
point the app at them:

```powershell
docker run -d --rm --name e2e-pg -e POSTGRES_PASSWORD=postgres `
    -e POSTGRES_DB=yiluan -p 55436:5432 postgres:15-alpine
docker run -d --rm --name e2e-redis -p 56379:6379 redis:7-alpine

$env:DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:55436/yiluan"
$env:DATABASE_SYNC_URL = "postgresql+psycopg://postgres:postgres@localhost:55436/yiluan"
$env:REDIS_URL = "redis://localhost:56379/0"
$env:DEBUG = "true"
$env:ENVIRONMENT = "development"
$env:SMS_PROVIDER = "mock"
$env:PAYMENT_PROVIDER = "mock"

python -m alembic upgrade head
python -m pytest tests/e2e/ -m e2e -v

docker stop e2e-pg e2e-redis
```

Note that under this mode `_redirect_app_async_session` becomes a
no-op for services that read the URL from `settings`, but it still
keeps everything coherent.

## Adding a new case

1. Drop a new file under `tests/e2e/` named `test_e2e_<scenario>.py`.
2. Use the existing fixtures: `e2e_client`, `login_via_otp`,
   `seed_hospital_e2e`, `admin_headers`, `assign_role_e2e`,
   `patient_phone`, `companion_phone`.
3. `pytestmark = pytest.mark.e2e` at the top so direct invocation
   without `-m e2e` still works under filtering.
4. Keep cases **under 30s each** and the **whole suite under 5 min**.

## Flaky-test playbook

* `429 Rate limit exceeded`: the slowapi limiter wasn't disabled.
  Confirm `_disable_slowapi_limiter` is loaded (it's `autouse=True,
  scope=session`).
* `another operation is in progress` (asyncpg): a service is opening
  its own `app.database.async_session()` outside the request scope and
  hitting a connection that's mid-flight. Add the service path to
  `_redirect_app_async_session` or open it with `async with` properly.
* `User does not have role: ...`: pass `role="patient"` or
  `role="companion"` to `login_via_otp(...)` so the conftest will boot
  the role at the DB layer and re-issue the JWT.
* `Apple Sign-In test fails with 401`: confirm
  `settings.apple_mock_verify=True` is in scope (the auth-flow tests
  fixture handles this).

## CI

Wired into `.github/workflows/test.yml` as a follow-up step in the
existing `backend` job:

```yaml
- name: Run e2e tests
  run: cd backend && python -m pytest tests/e2e/ -m e2e -v --timeout=30
  timeout-minutes: 5
```

The unit suite still runs the `-m 'not smoke'` default; the e2e step
is explicit and bounded.
