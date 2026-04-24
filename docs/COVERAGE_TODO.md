# Coverage TODO – W18 Push to ≥ 98%

## Status snapshot
| Stage | Coverage | Misses | Tests added |
|---|---|---|---|
| Baseline (test/coverage-98 HEAD) | **80%** | 832 | – |
| After `test_coverage_boost_repos.py` | 84% | 677 | 23 |
| After `test_coverage_boost_services.py` | 91% | 373 | 91 |
| After `test_coverage_boost_api.py` (this commit) | **92%** | 324 | 48 |
| **Target** | **≥ 98%** | **≤ 85** | – |

Net delta this branch: **+12 pp** (80 → 92), **+162 new tests**, **3 new test
files**. Remaining gap: **6 pp / ~239 misses** to hit the 98% gate.

The 96 % figure cited in the task description does not match the actual
baseline measured on `test/coverage-98` HEAD (80 %). All numbers in this
report are reproducible via:

```
cd backend && python -m pytest --cov=app --cov-report=term-missing -q
```

## Remaining miss hotspots (after this commit)

Sorted by `misses × business risk`:

| File | Misses | Why uncovered | Recommended fix |
|---|---|---|---|
| `app/api/v1/ws.py` | 39 | Two WebSocket endpoints; needs `httpx-ws` style harness or `starlette.testclient.TestClient` (sync) wrapper to drive `accept` / `send_text` / `disconnect` and exercise pubsub broker register/unregister/replace branches. | Add `tests/test_ws.py` with `TestClient.websocket_connect`. Cover: missing token (4001), invalid token type, malformed UUID sub, ws_max_connections_per_user eviction (4008), JSON parse error skip, ping→pong, chat order-not-found (4004), non-participant (4003), user-not-found, message persist + broadcast, msg_type fallback, content trimming. Est: +30 lines. |
| `app/services/order.py` | 36 | Long-tail of state-machine guards: deny transitions (`ForbiddenException`), `NotExpirableOrderError`, completion bonus path, broadcast notify path, refund unsuccessful, distributed-lock contention. | Already covered ~90 %; remaining lines are mostly: 343-353 (lock failure path), 479-480 (broadcast), 534-537 (cancel-by-companion), 572 (final-state guard). Add focused tests in `test_coverage_boost_services.py::TestOrderService` driving each branch. Est: +8 tests. |
| `app/services/providers/payment/wechat.py` | 33 | Real-credential branches (`_post`, `_call_wechat_api`, full v3 sign verify happy path). | Patch `httpx.AsyncClient` with `FakeClient` (same pattern as `test_wechat_login`) and exercise `create_order`/`refund` with credentials configured. Generate a 2048-bit RSA key in `tmp_path`, set `wechat_pay_private_key_path`, then `_rsa_sign` real path is hit. Est: +6 tests. |
| `app/api/v1/admin/__init__.py` | 31 | Force-status DENIED branch, refund failures with custom ratio out of range, list pagination filters. | Need `target_status` denied combos (e.g. completed→created), `refund_ratio` 0/>1 → 400. Est: +6 tests. |
| `app/api/v1/payment_callback.py` | 31 | Inner branches inside `_handle_pay_callback` / `_handle_refund_callback` between lines 106-168 / 225-248: trade_state non-SUCCESS, payment row not found, idempotent re-entry after success. | Add tests posting `trade_state=FAIL`, `out_trade_no` referencing missing payment, callback for already-`success` payment. Est: +5 tests. |
| `app/api/v1/notifications.py` | 10 | Permission/edge branches: marking another user's notification (403/404), invalid uuid path. | +3 tests in `TestNotificationsAPI`. |
| `app/api/v1/users.py` | 6 | `switch-role` happy path (multi-role user), avatar upload error branches. | Seed user with `roles="patient,companion"` then POST `/users/me/switch-role`. +2 tests. |
| `app/api/v1/hospitals.py` | 8 | Distance sort branch when both lat/lng present, error when invalid coordinates. | +2 tests. |
| `app/dependencies.py` | 10 | `get_current_user` exceptions: missing sub, malformed UUID, deleted, inactive. | Currently exercised indirectly; add direct tests calling the dependency with crafted JWTs. +5 tests. |
| `app/services/auth.py` | 13 | Lines 98-111: SMS provider failure fallback, refresh-token revocation list. | +4 tests. |
| `app/tasks/log_retention.py` | 14 | Cron schedule branches; not invoked by API tests. | Add unit tests that call `run_log_retention()` directly with frozen time + seeded log rows. +4 tests. |
| `app/services/patient_profile.py` | 8 | Service is a thin wrapper – uncovered branches are validation errors. | +3 tests. |
| `app/api/v1/admin/companions.py` | 2 | Approve/reject of already-approved profile. | +2 tests. |
| `app/api/v1/health.py` | 3 | DB / Redis ping failure paths. | Patch `engine.connect` to raise. +2 tests. |
| `app/services/notification.py` | 6 | Lines 177-191 (broadcast helper for completed orders). | +2 tests. |
| `app/database.py` | 8 | `get_db()` exception path is bypassed by test session override. | Inject a failing session via `app.dependency_overrides`. +1 test. |

Total estimated effort to close: **~85 new test functions, ~6-8 hours**.

## Hard-to-test residue (justifies docs over `# pragma: no cover`)

These lines are reachable only with real external services and should
either be marked with a justified `# pragma: no cover` in a dedicated
follow-up PR, or be left uncovered with this document as the rationale:

- `app/services/providers/payment/wechat.py` lines 184-218: real platform
  cert AES-GCM decrypt requires a genuine WeChat Pay platform certificate.
- `app/services/providers/sms/aliyun.py` line 109-110: SDK-level network
  exception swallow.
- `app/config.py` lines 92-135: production secret loaders gated on
  `ENVIRONMENT=production`.

## How to resume

1. `git checkout test/coverage-98 && git pull`
2. Pick the next hotspot from the table.
3. Use existing fixtures (`authenticated_client`, `admin_client`,
   `seed_user`, `seed_hospital`, `seed_order`, `seed_payment`,
   `test_session_factory`, `FakeRedis`).
4. Run the targeted file with `python -m pytest tests/<file> -q --no-cov`,
   then a full coverage pass.
5. Repeat until `python -m pytest --cov=app --cov-fail-under=98 -q` passes.

## Constraints honoured by this branch

- No business code edits (only `tests/` additions).
- No `# pragma: no cover`.
- No mocking of the function under test (only outbound deps:
  `httpx.AsyncClient`, `MockPaymentProvider.verify_callback`).
- Every new test function carries a docstring.
- All test data is built via `pytest` fixtures from `tests/conftest.py`.
