# ADR — Admin MVP Scope (B4)

Status: **Accepted** — 2026-04-27
Owner: Backend
Tracks: `TASK_BREAKDOWN.md` §B4

## Context

The platform needs an internal operations console covering 3 domains:

1. **Companion verification** (already shipped as B1, lives in
   `backend/app/api/v1/admin/companions.py`).
2. **Order management** — query / force-status / refund.
3. **User management** — list / disable / enable.

Two auth styles existed in the tree:

- `X-Admin-Token` header → `app.core.admin_auth.require_admin_token`
  (used by companions).
- Role-based JWT → `get_admin_user` defined inline in
  `backend/app/api/v1/admin/__init__.py` (used by the orders / users
  skeleton).

That inconsistency is the root cause of this ADR.

## Decision

### 1. Auth — single method: `X-Admin-Token`

- All `/api/v1/admin/**` endpoints require the `X-Admin-Token` header,
  validated against `settings.admin_api_token`.
- The legacy `get_admin_user` dependency is **removed**.
- JWT / OAuth2 admin login is explicitly out of scope and tracked as
  the v2 follow-up (B5).

Trade-off accepted: token-based auth has no concept of "current admin
user", so audit log entries record the operator as the literal string
`"admin-token"`. Self-protection rules (e.g. "admin cannot disable
self") are deferred to v2.

### 2. Module layout

```
backend/app/api/v1/admin/
    __init__.py        # router root + sub-router includes only
    companions.py      # B1 (already shipped)
    orders.py          # B4 — order management
    users.py           # B4 — user management
```

`__init__.py` declares no business endpoints; it only mounts the three
sub-routers under the `/admin` prefix and applies
`Depends(require_admin_token)` at the parent-router level so every
nested route inherits the same guard.

### 3. Endpoints

#### Orders (`/api/v1/admin/orders`)

| Method | Path                                | Purpose                                  |
| ------ | ----------------------------------- | ---------------------------------------- |
| GET    | `/`                                 | Paginated list, filters: `status`, `patient_id`, `companion_id`, `date_from`, `date_to` |
| GET    | `/{order_id}`                       | Order detail                             |
| POST   | `/{order_id}/force-status`          | Body `{status, reason}` — set arbitrary status (audit logged) |
| POST   | `/{order_id}/refund`                | Body `{amount, reason}` — initiate refund via `PaymentService.create_refund` (audit logged) |

Refund rules:
- Order status must be one of `paid`-equivalent (`accepted`,
  `in_progress`, `completed`, `reviewed`) — i.e. there must be a
  successful `payment_type=pay` Payment row.
- `amount` must be > 0 and ≤ original paid amount.
- Idempotent: a successful refund row for the order short-circuits any
  further refund attempts (existing constraint in `PaymentService`).

#### Users (`/api/v1/admin/users`)

| Method | Path                          | Purpose                                  |
| ------ | ----------------------------- | ---------------------------------------- |
| GET    | `/`                           | Paginated list, filters: `role`, `is_active`, `phone` |
| GET    | `/{user_id}`                  | User detail                              |
| POST   | `/{user_id}/disable`          | Body `{reason}` — `is_active=False` + audit |
| POST   | `/{user_id}/enable`           | `is_active=True` + audit                 |

Self-protection: not enforceable under token auth; v2 JWT migration
will revisit (a docstring TODO is left in the code).

### 4. Audit logging

All mutating endpoints (force-status / refund / disable / enable) write
an `AdminAuditLog` row via `AdminAuditService`. The `target_type` is
`"order"` or `"user"` accordingly; the `operator` field stores
`"admin-token"`.

### 5. Migration impact

`User.is_active` already exists on the model with a backing column;
no Alembic revision is required for B4.

## Consequences

- Frontend admin console talks to a single, predictable surface using
  one shared header.
- Tests use the same fixture pattern as the companions module
  (raw header injection, no JWT bootstrapping).
- The pre-existing JWT-flavoured admin tests in `tests/test_admin.py`
  are migrated to the token-based flow as part of this change.
