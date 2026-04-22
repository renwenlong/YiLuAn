import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from prometheus_client import make_asgi_app as _make_metrics_app

from app.api.v1.router import api_v1_router
from app.config import settings
from app.core.logging import setup_logging
from app.core.rate_limit import limiter
from app.core.redis import init_redis
from app.tasks.scheduler import shutdown_scheduler, start_scheduler
from app.ws.pubsub import (
    start_ws_chat_pubsub,
    start_ws_pubsub,
    stop_ws_chat_pubsub,
    stop_ws_pubsub,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    setup_logging()
    logger.info("Starting %s v%s", settings.app_name, settings.app_version)
    app.state.redis = init_redis()
    # WebSocket Pub/Sub broker (D-019): 多副本通知跨副本 fanout
    try:
        await start_ws_pubsub(
            app,
            enabled=settings.ws_pubsub_enabled,
            channel=settings.ws_pubsub_channel,
        )
    except Exception as exc:  # pragma: no cover
        logger.exception("Failed to start ws pubsub broker: %s", exc)
    # 聊天房间 Pub/Sub broker（D-019 Update）: 多副本聊天跨副本 fanout
    try:
        await start_ws_chat_pubsub(
            app,
            enabled=settings.ws_chat_pubsub_enabled,
            channel=settings.ws_chat_pubsub_channel,
        )
    except Exception as exc:  # pragma: no cover
        logger.exception("Failed to start ws chat pubsub broker: %s", exc)
    # APScheduler (D-018): 开启后台定时任务（过期订单自动扫描）
    if settings.scheduler_enabled:
        try:
            start_scheduler(app)
        except Exception as exc:  # pragma: no cover - 不阻塞启动
            logger.exception("Failed to start scheduler: %s", exc)
    yield
    # Shutdown
    await shutdown_scheduler()
    await stop_ws_chat_pubsub(app)
    await stop_ws_pubsub(app)
    if app.state.redis:
        await app.state.redis.aclose()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        lifespan=lifespan,
    )

    # Rate limiting
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request logging middleware
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start = time.time()
        response: Response = await call_next(request)
        duration_ms = (time.time() - start) * 1000
        logger.info(
            "%s %s %s %.1fms",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response

    # Prometheus metrics endpoint (no auth — K8s scrape)
    metrics_app = _make_metrics_app()
    app.mount("/metrics", metrics_app)

    # Routers
    app.include_router(api_v1_router, prefix="/api/v1")

    # Health check (liveness) — 进程活着即 200，不查依赖
    @app.get("/health")
    async def health_check():
        return {"status": "healthy", "version": settings.app_version}

    # Readiness probe (root path, 对齐 ACA/K8s 默认探针惯例)
    # 复用 app.api.v1.health 中的检查逻辑，避免逻辑分叉
    from app.api.v1.health import _run_readiness_checks, _readiness_response

    @app.get("/readiness")
    async def readiness_root(request: Request):
        all_ok, checks = await _run_readiness_checks(request)
        return _readiness_response(all_ok, checks)

    return app


app = create_app()
