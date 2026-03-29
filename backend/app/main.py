from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_v1_router
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app.state.redis = aioredis.from_url(
        settings.redis_url, encoding="utf-8", decode_responses=True
    )
    yield
    # Shutdown
    await app.state.redis.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    app.include_router(api_v1_router, prefix="/api/v1")

    # Health check
    @app.get("/health")
    async def health_check():
        return {"status": "healthy", "version": settings.app_version}

    return app


app = create_app()
