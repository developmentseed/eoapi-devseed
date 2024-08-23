from collections.abc import AsyncGenerator
from sqlalchemy.orm import sessionmaker
from business.logic.config import ModeEnum, Settings
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.pool import NullPool, AsyncAdaptedQueuePool

settings = Settings()

engine = create_async_engine(
    str(settings.async_database_uri),
    poolclass=NullPool
    if settings.mode == ModeEnum.testing
    else AsyncAdaptedQueuePool,  # Asincio pytest works with NullPool
    echo=settings.mode == ModeEnum.development,
)


async def get_session() -> AsyncGenerator:
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
