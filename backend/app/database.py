from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_size=20,
    max_overflow=10,
    # W1-S5: Azure Postgres 空闲 ~30min 会被服务器侧切断，下一个拿到
    # 死连接的请求会报 OperationalError (500)。
    # - pool_pre_ping: 每次 checkout 前 SELECT 1，死连接立即丢弃重建
    # - pool_recycle=1800s (30min): 超过阈值的闲连接主动 recycle赶
    #   在云端切断之前
    # 注：SQLite (单元测默认 driver) 不走 pool，这些参数无从被
    # 在测试中验证；依靠 SQLAlchemy 官方语义保证。
    pool_pre_ping=True,
    pool_recycle=1800,
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
