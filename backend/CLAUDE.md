# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

YiLuAn (医路安) — Medical companion service (陪诊) platform. This is the **FastAPI backend**. The sibling `../wechat/` directory contains the WeChat Mini Program frontend.

## Commands

```bash
# Install
pip install -r requirements.txt

# Run dev server
uvicorn app.main:app --reload

# Run all tests (uses SQLite in-memory + FakeRedis, no external services needed)
pytest

# Run a single test file
pytest tests/test_orders.py

# Run a single test by name
pytest tests/test_orders.py -k "test_create_order"

# Lint
ruff check app/
black --check app/

# Database migrations
python -m alembic upgrade head
python -m alembic revision --autogenerate -m "description"

# Seed hospital data (server must be running)
curl -X POST http://localhost:8000/api/v1/hospitals/seed

# Seed dev data (users, orders, etc.) directly to DB
psql -U postgres -d yiluan < seed.sql

# Docker
docker compose up -d
```

## Architecture

### Layered structure

```
Request → API Router → Service → Repository → SQLAlchemy Model → PostgreSQL
            ↓              ↓           ↓
        Pydantic       Business    BaseRepository[T]
        Schemas        Logic       (generic CRUD)
```

- **`app/api/v1/`** — FastAPI route handlers. Each file is a router mounted under `/api/v1`.
- **`app/services/`** — Business logic. Each service takes `AsyncSession` in constructor, instantiates its own repos.
- **`app/repositories/`** — DB access. `BaseRepository[ModelType]` provides generic CRUD; concrete repos add domain queries.
- **`app/models/`** — SQLAlchemy 2.0 declarative models with `Mapped`/`mapped_column`. UUID primary keys, UTC timestamps.
- **`app/schemas/`** — Pydantic v2 request/response models. All responses use `from_attributes = True`.

### Key design decisions

- **No ORM relationships** — Foreign keys are bare UUID columns. Joins are done manually in repositories/services.
- **User roles as comma-string** — `User.roles = "patient,companion"` with helper methods `has_role()`, `get_roles()`, `add_role()`. No junction table.
- **Order state machine** — Transitions defined in `ORDER_TRANSITIONS` dict in `app/models/order.py`: `created → accepted → in_progress → completed → reviewed`, with cancel branches.
- **Service prices hardcoded** — `SERVICE_PRICES` dict in `app/services/order.py`: full_accompany=299, half_accompany=199, errand=149.
- **Mock payments** — Always succeed. No real payment gateway.
- **Hospital seed data** — `app/data/hospitals.json` (97 hospitals) loaded via `POST /hospitals/seed`. `seed.sql` has a smaller set for direct DB seeding.

### Dependency injection

```python
DBSession = Annotated[AsyncSession, Depends(get_db)]     # app/dependencies.py
CurrentUser = Annotated[User, Depends(get_current_user)]  # extracts JWT → loads User
```

### Auth flow

1. WeChat Mini Program: `POST /auth/wechat-login` with `code` → backend calls WeChat `code2session` → returns JWT pair
2. Phone OTP: `POST /auth/send-otp` → `POST /auth/verify-otp` → JWT pair
3. Dev mode (`ENVIRONMENT=development`): OTP bypass code is `000000`, WeChat bypass code is `dev_test_code`

### WebSocket

`WS /api/v1/ws/chat/{order_id}?token=<jwt>` — Auth via query param. In-memory connection map (single-instance only). Heartbeat ping/pong every 30s.

### Config

`app/config.py` — Pydantic `Settings(BaseSettings)` loaded from `.env`. Key vars: `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET_KEY`, `WECHAT_APP_ID`, `WECHAT_APP_SECRET`, `SMS_PROVIDER` (mock/aliyun), `ENVIRONMENT`.

## Testing

Tests in `tests/` use pytest-asyncio with `asyncio_mode = "auto"`.

- **DB**: SQLite in-memory (`sqlite+aiosqlite:///:memory:`), tables recreated per test via `autouse` fixture
- **Redis**: `FakeRedis` dict-based mock injected via `app.state.redis`
- **HTTP**: `httpx.AsyncClient` with `ASGITransport` — full integration tests, no real HTTP server
- **Fixtures**: `conftest.py` provides `seed_user`, `seed_hospital`, `seed_order`, `authenticated_client` (patient), `companion_client`, etc.

## Frontend (WeChat Mini Program)

The `../wechat/` directory is the WeChat Mini Program. Key points for backend developers:

- **API base**: `http://localhost:8000/api/v1` (dev), configured in `wechat/config/index.js`
- **Auth**: JWT Bearer token in headers, with transparent token refresh queue in `wechat/services/api.js`
- **No native tabBar** — uses custom `patient-tab-bar` and `companion-tab-bar` components, navigation via `wx.reLaunch`
- **Frontend tests**: Jest in `wechat/__tests__/`, run with `cd ../wechat && npx jest`
- **Service types constant**: defined in `wechat/utils/constants.js` — must stay in sync with backend `SERVICE_PRICES`
