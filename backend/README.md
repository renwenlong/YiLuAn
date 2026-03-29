# YiLuAn Backend

Medical Companion Service API.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
uvicorn app.main:app --reload

# Run with Docker
docker compose up -d

# Run tests
pytest
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL async URL | `sqlite+aiosqlite:///./dev.db` |
| `REDIS_URL` | Redis connection URL | `redis://localhost:6379` |
| `SECRET_KEY` | JWT signing key | (required) |
| `WECHAT_APP_ID` | WeChat Mini Program AppID | `""` |
| `WECHAT_APP_SECRET` | WeChat Mini Program AppSecret | `""` |

## API Endpoints

### Auth
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/v1/auth/send-otp` | No | Send OTP to phone |
| POST | `/api/v1/auth/verify-otp` | No | Verify OTP and get tokens |
| POST | `/api/v1/auth/refresh` | No | Refresh access token |
| POST | `/api/v1/auth/wechat-login` | No | WeChat Mini Program login |
| POST | `/api/v1/auth/bind-phone` | Bearer | Bind phone to WeChat account |

## API Docs

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health Check: http://localhost:8000/health
