# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

YiLuAn (医路安) — Medical companion service (陪诊) platform. Connects patients needing hospital accompaniment with professional companions. Three service types: full accompany (全程陪诊 ¥299), half accompany (半程陪诊 ¥199), errand (代办跑腿 ¥149).

**Monorepo with three clients + one backend:**
- `backend/` — Python FastAPI async API server (see `backend/CLAUDE.md` for detailed backend docs)
- `wechat/` — WeChat Mini Program (native WXML/WXSS/JS)
- `ios/YiLuAn/` — iOS app (SwiftUI + MVVM, iOS 17+)

## Commands

### Backend

```bash
cd backend

# Install
pip install -r requirements.txt

# Dev server (hot reload)
uvicorn app.main:app --reload

# Full stack via Docker (API + PostgreSQL 15 + Redis 7)
docker compose up -d

# Tests (SQLite in-memory + FakeRedis, no external services)
pytest                                    # all tests
pytest tests/test_orders.py               # single file
pytest tests/test_orders.py -k "test_create_order"  # single test

# Lint
ruff check app/
black --check app/

# Database migrations
python -m alembic upgrade head
python -m alembic revision --autogenerate -m "description"

# Seed data
curl -X POST http://localhost:8000/api/v1/hospitals/seed   # via API
psql -U postgres -d yiluan < seed.sql                       # direct SQL
```

### WeChat Mini Program

```bash
cd wechat
npm install
npm test                   # Jest (77 tests)
npm test -- --verbose      # detailed output
```

Open `wechat/` directory in WeChat DevTools for development. Check "不校验合法域名" for local dev.

### iOS

Open `ios/YiLuAn.xcodeproj` in Xcode. Target: iOS 17+, iPhone 15 Pro simulator.

## Architecture

### Backend (FastAPI)

```
Request → API Router (Pydantic v2) → Service (business logic) → Repository (DB) → SQLAlchemy 2.0 Model → PostgreSQL
```

- **`app/api/v1/`** — Route handlers. Each file is a router mounted under `/api/v1`.
- **`app/services/`** — Business logic. Takes `AsyncSession`, instantiates own repos.
- **`app/repositories/`** — Data access. `BaseRepository[T]` generic CRUD + domain-specific queries.
- **`app/models/`** — SQLAlchemy 2.0 declarative models. UUID PKs, UTC timestamps.
- **`app/schemas/`** — Pydantic v2 request/response models. All use `from_attributes = True`.

Dependency injection via `Annotated` types in `app/dependencies.py`:
- `DBSession = Annotated[AsyncSession, Depends(get_db)]`
- `CurrentUser = Annotated[User, Depends(get_current_user)]`

### WeChat Mini Program

- **`services/api.js`** — Central HTTP client. Bearer JWT auth, transparent 401 refresh queue (concurrent requests wait for single refresh).
- **`store/index.js`** — Observer-pattern global state (`getState`, `setState`, `subscribe`, `reset`).
- **`utils/constants.js`** — `SERVICE_TYPES` and `ORDER_STATUS` enums. **Must stay in sync with backend `SERVICE_PRICES`.**
- **`config/index.js`** — `API_BASE_URL` and `WS_BASE_URL` per environment.
- **Custom tab bars** — No native `tabBar`. Uses `components/patient-tab-bar` and `components/companion-tab-bar`, navigation via `wx.reLaunch`.
- **27 pages** organized by role: `pages/patient/*`, `pages/companion/*`, plus shared `pages/profile/*`, `pages/chat/*`, etc.

### iOS

SwiftUI + MVVM. `Core/Networking/APIClient.swift` for HTTP, `Core/Networking/WebSocketClient.swift` for real-time chat. `Features/` organized by domain (Auth, Patient, Companion, Order, Chat, Review, Notifications, Profile).

## Key Design Decisions

- **No ORM relationships** — Foreign keys are bare UUID columns; joins done manually in repos/services.
- **User roles as comma-string** — `User.roles = "patient,companion"` with `has_role()`, `get_roles()`, `add_role()` helpers. No junction table.
- **Order state machine** — `ORDER_TRANSITIONS` dict in `app/models/order.py`: `created → accepted → in_progress → completed → reviewed`, with cancel branches from multiple states.
- **Denormalization** — `avg_rating`/`total_orders` on companion profiles; `hospital_name`/`patient_name`/`companion_name` on orders. Updated by service-layer triggers.
- **Mock payments** — Always succeed. No real payment gateway (MVP).
- **Dev auth bypass** — OTP code `000000` and WeChat code `dev_test_code` accepted in development environment.

## Cross-Stack Sync Points

These must stay synchronized when modified:

| Concept | Backend | WeChat | iOS |
|---------|---------|--------|-----|
| Service types & prices | `app/services/order.py` `SERVICE_PRICES` | `utils/constants.js` `SERVICE_TYPES` | `Core/Models/Order.swift` `ServiceType` |
| Order statuses | `app/models/order.py` `OrderStatus` | `utils/constants.js` `ORDER_STATUS` | `Core/Models/Order.swift` `OrderStatus` |
| API endpoints | `app/api/v1/router.py` | `services/*.js` | `Core/Networking/APIEndpoint.swift` |
| WebSocket message format | `app/api/v1/ws.py` | `services/websocket.js` | `Core/Networking/WebSocketClient.swift` |

## Testing

| Platform | Framework | Config |
|----------|-----------|--------|
| Backend | pytest + pytest-asyncio | `asyncio_mode = "auto"` in `pyproject.toml`. SQLite in-memory DB, FakeRedis mock. Fixtures in `tests/conftest.py`. |
| WeChat | Jest | Config in `wechat/jest.config.js`. Global `wx` mock in `__tests__/setup.js`. |

Backend test fixtures: `seed_user`, `seed_hospital`, `seed_order`, `authenticated_client` (patient role), `companion_client`.

## Code Style

- **Backend**: Black (100 char line length, py311 target) + Ruff (rules: E, F, I, W). Configured in `pyproject.toml`.
- **WeChat**: No linter configured. Standard WeChat Mini Program conventions.

## Environment

Backend config via pydantic-settings from `.env`. Key vars: `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET_KEY`, `WECHAT_APP_ID`, `WECHAT_APP_SECRET`, `SMS_PROVIDER` (mock/aliyun), `ENVIRONMENT` (development/production).

Docker Compose (`backend/docker-compose.yaml`) provides PostgreSQL 15 on port 5432 and Redis 7 on port 6379.
