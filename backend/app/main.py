import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app as _make_metrics_app
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.v1.health import prime_alembic_head_cache
from app.api.v1.openapi_meta import API_DESCRIPTION, TAGS_METADATA
from app.api.v1.router import api_v1_router
from app.config import settings
from app.core.logging import setup_logging
from app.core.rate_limit import limiter
from app.core.redis import init_redis
from app.tasks.scheduler import shutdown_scheduler, start_scheduler
from app.ws.pubsub import (
    start_ws_chat_pubsub,
    start_ws_pubsub,
    start_ws_share_pubsub,
    stop_ws_chat_pubsub,
    stop_ws_pubsub,
    stop_ws_share_pubsub,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    setup_logging()
    logger.info("Starting %s v%s", settings.app_name, settings.app_version)
    # Warm the alembic head cache so /readiness probes do not pay the
    # alembic-import cost on every call (TD-OPS-02).
    try:
        prime_alembic_head_cache()
    except Exception as exc:  # pragma: no cover - never block boot on this
        logger.warning("prime_alembic_head_cache failed: %s", exc)
    app.state.redis = init_redis()
    # S3-DEV-002-HOT-RELOAD: 启动 AI blocklist Redis pub/sub subscriber.
    # Subscribe topic ai_blocklist_reload, 收事件调 load_blocklist() 重 init.
    # Redis 不可用 / disabled → subscriber 不启, 仅 rolling deploy 才 reload (cold fallback).
    try:
        from app.services.ai_blocklist_pubsub import (
            start_ai_blocklist_reload_subscriber,
        )

        await start_ai_blocklist_reload_subscriber(app)
    except Exception as exc:  # pragma: no cover - never block boot on subscriber
        logger.warning("ai_blocklist_reload subscriber start failed: %s", exc)
    # S2-DEV-012 (ADR-0040 Phase 1) 注入分布式 CB 的 redis client
    # 使用 sync redis client（CB.allow_request 是 sync 接口，不能 await）
    # 与业务侧 async redis 同连一个 Redis 实例，不引入新依赖
    # Redis 不可用时 distributed CB 自动降级到纯本地 CB（不阻断业务）
    try:
        from app.core.redis import init_redis_sync
        from app.utils.distributed_circuit_breaker import (
            set_distributed_redis_client,
        )
        app.state.redis_sync = init_redis_sync()
        set_distributed_redis_client(app.state.redis_sync)
    except Exception as exc:  # pragma: no cover - never block boot on CB wire-up
        logger.warning(
            "distributed CB redis wire-up failed (will degrade to local CB): %s", exc
        )
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
    # ADR-0036 §2.4 family-share broker：独立 channel，只读 fanout
    try:
        await start_ws_share_pubsub(
            app,
            enabled=settings.ws_share_pubsub_enabled,
            channel=settings.ws_share_pubsub_channel,
        )
    except Exception as exc:  # pragma: no cover
        logger.exception("Failed to start ws share pubsub broker: %s", exc)
    # APScheduler (D-018): 开启后台定时任务（过期订单自动扫描）
    if settings.scheduler_enabled:
        try:
            start_scheduler(app)
        except Exception as exc:  # pragma: no cover - 不阻塞启动
            logger.exception("Failed to start scheduler: %s", exc)
    # S3-DEV-002-PROMPT-VERSIONING AC#3: prompt_versions DB ↔ git fail-fast
    # 校验。失败直接 raise （不 try/except 吞）让 lifespan 报错 boot
    # 挂掉——防止上线后以梨名 prompt 版本生成 LLM 调用.
    if settings.prompt_versions_validate_on_startup:
        from app.database import async_session
        from app.services.prompt_versioning import (
            validate_prompt_versions_on_startup,
        )
        async with async_session() as session:
            await validate_prompt_versions_on_startup(
                session,
                repo_root=settings.prompt_versions_repo_root,
            )
    # S3-DEV-004 (ADR-0049 §10.1) feedback startup healthcheck.
    # strict=true (production/staging): 任一检查失败 → raise 令 worker exit 1
    #   (拒接流量; 避免 alembic 未 upgrade / s4 enabled 误启用 → backend healthy 但
    #    500 用户请求).
    # strict=false (dev/test): 仅 warning, 不阻本地开发.
    # 详 ADR-0049 §10.1 "拒绝启动口径".
    from app.database import engine as db_engine
    from app.services.feedback_startup_healthcheck import (
        FeedbackStartupHealthcheck,
    )
    healthcheck = FeedbackStartupHealthcheck(
        engine=db_engine,
        strict=settings.s3_startup_healthcheck_strict,
    )
    await healthcheck.run()
    yield
    # Shutdown
    await shutdown_scheduler()
    await stop_ws_share_pubsub(app)
    await stop_ws_chat_pubsub(app)
    await stop_ws_pubsub(app)
    if app.state.redis:
        await app.state.redis.aclose()
    # S2-DEV-012: 同步关闭 sync redis client（distributed CB 专用）
    redis_sync = getattr(app.state, "redis_sync", None)
    if redis_sync is not None:
        try:
            redis_sync.close()
        except Exception:  # pragma: no cover
            pass
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=API_DESCRIPTION,
        openapi_tags=TAGS_METADATA,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        lifespan=lifespan,
        contact={
            "name": "YiLuAn 后端团队",
            "email": "backend@yiluan.example.com",
        },
        license_info={"name": "Proprietary"},
    )

    # Rate limiting
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # CORS
    # Defense-in-depth: 当 origins 含通配 '*' 时，强制 allow_credentials=False。
    # 背景：Starlette CORSMiddleware 在 '*' + credentials=True 时会把
    # Access-Control-Allow-Origin 反射为请求 Origin，等价于「任意源 + 可带凭证」。
    # config.validate_production_config 已在 environment=production 时拦截该组合，
    # 这里再加一道运行时保险，避免 staging/dev 或环境字段错配时绕过。
    _cors_origins = settings.cors_origins or []
    _cors_allow_credentials = True
    if "*" in _cors_origins:
        _cors_allow_credentials = False
        logger.warning(
            "CORS allow_origins contains '*'; forcing allow_credentials=False "
            "to prevent Origin reflection (env=%s)",
            settings.environment,
        )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=_cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request logging middleware
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start = time.time()
        # X-Request-Id propagation: trust client-supplied id (capped to 64
        # chars to avoid log injection / unbounded memory) and echo it back
        # in the response so end-to-end correlation works without forcing
        # every log line to carry a server-generated id.
        req_id = (request.headers.get("x-request-id") or "")[:64]
        response: Response = await call_next(request)
        duration_ms = (time.time() - start) * 1000
        if req_id:
            response.headers["X-Request-Id"] = req_id
        # Canary 5xx rollback gate metric (S2-OPS-001). Low cardinality:
        # method + status class only, never the raw path.
        try:
            from app.observability.http_metrics import (
                HTTP_REQUESTS_TOTAL,
                status_class,
            )

            HTTP_REQUESTS_TOTAL.labels(
                method=request.method,
                status_class=status_class(response.status_code),
            ).inc()
        except Exception:  # metrics never break request serving
            pass
        logger.info(
            "%s %s %s %.1fms rid=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            req_id or "-",
        )
        return response

    # Prometheus metrics endpoint (no auth — K8s scrape)
    metrics_app = _make_metrics_app()
    app.mount("/metrics", metrics_app)

    # Routers
    app.include_router(api_v1_router, prefix="/api/v1")

    # Health check (liveness) — 进程活着即 200，不查依赖
    @app.get(
        "/health",
        summary="健康检查（liveness, root）",
        description="根路径 liveness 探针，仅返回进程存活状态。",
        tags=["health"],
    )
    async def health_check():
        return {"status": "healthy", "version": settings.app_version}

    # Readiness probe (root path, 对齐 ACA/K8s 默认探针惯例)
    # 复用 app.api.v1.health 中的检查逻辑，避免逻辑分叉
    from app.api.v1.health import _readiness_response, _run_readiness_checks

    @app.get(
        "/readiness",
        summary="就绪检查（readiness, root）",
        description=(
            "根路径就绪探针，等价于 /api/v1/readiness："
            "检查 DB + Redis。任一失败 → 503。"
        ),
        tags=["health"],
    )
    async def readiness_root(request: Request):
        all_ok, checks = await _run_readiness_checks(request)
        return _readiness_response(all_ok, checks)

    return app


app = create_app()
