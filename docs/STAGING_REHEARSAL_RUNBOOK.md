# Staging Mock Rehearsal — Weekly Runbook (D-044)

> Source of truth for the weekly mock-environment rehearsal. ADR background:
> [`docs/adr/ADR-0030-staging-mock-environment.md`](adr/ADR-0030-staging-mock-environment.md).

## What this is

A fully sandboxed **mock staging stack** (Postgres, Redis, backend, nginx,
mock-pay-stub, mock-sms-stub) plus a host-side replay script that drives
the full patient journey through the public nginx entrypoint. The goal is
to catch regressions in the order/payment/companion/review/refund flow
**before** they touch any real money or SMS provider.

All services live in `deploy/staging/` and only nginx publishes a host
port (`127.0.0.1:18080`). The dev compose stack in `backend/` is left
untouched.

## Schedule

- **When**: every Wednesday 14:00 (Asia/Shanghai, GMT+8) — `0 6 * * 3` UTC
- **Primary owner**: Ops on-call
- **Backup**: Architect on-call
- **Channel for results**: `#yiluan-ops` (paste the markdown report)

If GitHub Actions runs it (see "Automation" below), the artefact is the
markdown report. The owner still needs to:

1. Open the artefact within 24h.
2. If RED, file an issue tagged `staging-rehearsal` and `regression`,
   ping the corresponding feature owner.
3. Commit the report into `deploy/staging/reports/` if it was a manual
   local run (CI artefacts are kept for 30d, no auto-commit).

## Local procedure (manual run)

From a clean checkout on `main`:

```powershell
# 1. start the stack (Windows)
cd deploy\staging
.\up.ps1
```

```bash
# 1. start the stack (Linux/macOS)
cd deploy/staging
./up.sh
```

Wait until `docker compose -p yiluan-staging ps` shows
`backend-staging` as `healthy` (1–2 min on a cold cache, ~30 s warm).
`up.ps1` already polls for this, but feel free to spot-check.

```powershell
# 2. (optional) seed fixtures explicitly. The replay script will call
#    seed_staging.py itself unless you pass --skip-seed.
python seed_staging.py

# 3. drive the journey
python replay\run-weekly-rehearsal.py
```

```bash
# Linux/macOS equivalents
python3 seed_staging.py
python3 replay/run-weekly-rehearsal.py
```

Inspect the generated report:

```
deploy/staging/reports/rehearsal-YYYY-MM-DD.md
```

Each step row is ✅ or ❌ with timing and a short detail. Failures
include a full traceback at the bottom.

```powershell
# 4. tear it down
.\down.ps1
```

```bash
./down.sh
```

`down.sh` / `down.ps1` only removes the staging compose project — **it
does not delete the named volume `yiluan-staging-pgdata`** so re-runs
are fast. To start truly clean:

```powershell
docker compose -p yiluan-staging -f docker-compose.staging.yml down -v
```

## What the replay script exercises

In order (each step prints OK/FAIL + ms in stdout):

1. patient OTP login (`000000` dev bypass)
2. list hospitals → pick the first
3. create order (`full_accompany`, +7 days appointment)
4. `POST /api/v1/orders/{id}/pay` → returns prepay info
5. `POST /__staging/mock-pay/__trigger-callback` → mock-pay-stub fires
   the wechat-pay callback into the backend
6. poll order until `status=paid`
7. companion OTP login (`13800000101`, pre-approved by `seed_staging.py`)
8. companion accepts the order
9. companion `request-start` → patient `confirm-start` (with fallback
   to direct `/start` if the project is on the legacy state machine)
10. companion `complete`
11. patient submits a multidimensional review (4 axes + content)
12. admin OTP login (`13900000000`) → `POST /api/v1/admin/orders/{id}/admin-refund?refund_ratio=1.0`

Every patient is created with a fresh phone (`139` + HHMMSSff) so
re-runs never collide on `unique(order_id)` for reviews or unique
phone constraints.

## Reports & archival

- Reports land in `deploy/staging/reports/rehearsal-YYYY-MM-DD.md`.
- Commit them weekly (PR title: `ops(staging): rehearsal report YYYY-MM-DD`).
- Keep at least the last 12 weeks; older reports may be pruned.
- The first baseline run sits at `rehearsal-2026-04-27.md`.

## Automation

`.github/workflows/staging-rehearsal.yml` runs the same procedure on
`ubuntu-latest` weekly. If the runner cannot build the mock stubs (no
egress / docker-in-docker quirks), the workflow is currently **gated
off** with `if: false` and a comment pointing here; ops must run the
rehearsal locally until we move it onto a self-hosted runner (see
D-039 for the parallel pattern).

## Failure triage

When the report is RED, work top→down — earlier steps fail more often
and cascade.

1. **Login (step 1 / 7 / 12) fails** → backend is up but `ENVIRONMENT`
   isn't `development`, so the `000000` OTP bypass is off. Check
   `docker compose -p yiluan-staging exec backend-staging env | grep ENV`.
2. **Hospital list empty (step 2)** → `seed_staging.py` didn't run or
   the `/api/v1/hospitals/seed` endpoint changed shape. Re-run with
   `python seed_staging.py` and inspect stdout.
3. **Pay callback (step 5) returns ok=false** → mock-pay-stub couldn't
   reach `backend-staging:8000`. Likely the bridge network is wrong.
   Check `docker logs yiluan-staging-mock-pay-stub-1`.
4. **Order never reaches `paid` (step 6)** → callback was accepted but
   the backend's `OrderStatus` transition died. `docker logs
   yiluan-staging-backend-staging-1 --tail 200` and look for
   `payment_callback` or `OrderService.handle_payment_callback`.
5. **Accept / start / complete (steps 8-10)** → the mixin order
   service split (PR #35) may have broken state-machine wiring; this
   is a real backend regression, not a mock issue. File an issue
   against `services/order/`.
6. **Review (step 11) 422** → schema regression in `CreateReviewRequest`
   (`punctuality_rating`, `professionalism_rating`,
   `communication_rating`, `attitude_rating`).
7. **Admin refund (step 12)** → either the admin user doesn't have the
   `admin` role (re-run seed) or `/api/v1/admin/orders/{id}/admin-refund`
   was renamed; grep `backend/app/api/v1/admin/__init__.py`.

For "is it the mock or the backend?": call the mock control plane
directly through nginx and check it answered `200`:

```bash
curl -s http://127.0.0.1:18080/__staging/mock-pay/__sent | jq .
curl -s http://127.0.0.1:18080/__staging/mock-sms/health
```

If those are healthy and the request log shows the call landed, the
fault is downstream in the backend.

## Known issues

_none yet — append here as we learn._

## Change log

- 2026-04-27 — initial runbook (D-044, ADR-0030).
