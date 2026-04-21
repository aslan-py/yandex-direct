"""Модуль настройки движка и сессий базы данных.

Создаёт асинхронный движок SQLAlchemy, фабрику
сессий и базовый класс для ORM-моделей.
"""

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.constants import DbSettings


class Base(DeclarativeBase):
    """Базовый класс для всех ORM-моделей.

    Определён здесь для избежания циклических
    импортов между модулями models и db.
    """

    pass


engine = create_async_engine(DbSettings.DATABASE_URL, echo=False)

async_session_factory = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)


async def init_models() -> None:
    """Создаёт все таблицы в базе данных.

    Импорт моделей происходит внутри функции,
    чтобы избежать Circular Import Error при старте
    приложения.
    """
    async with engine.begin() as conn:
        from app.models import User  # noqa: F401

        await conn.run_sync(Base.metadata.create_all)
