"""Модуль репозитория пользователей (CRUD).

Предоставляет статические методы для создания,
чтения и удаления записей пользователей
в базе данных SQLite через SQLAlchemy.
"""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


class UserRepository:
    """Слой работы с данными пользователей в БД.

    Все методы являются статическими и принимают
    сессию явным образом, что упрощает тестирование
    и не требует создания экземпляра.
    """

    @staticmethod
    async def upsert_user(
        session: AsyncSession, login: str, token: str
    ) -> User:
        """Обновляет токен или создаёт нового пользователя.

        Если пользователь с таким логином уже существует —
        обновляет его токен. Иначе создаёт новую запись.

        Args:
            session: Асинхронная сессия SQLAlchemy.
            login: Логин пользователя Яндекс.
            token: OAuth-токен пользователя.

        Returns:
            Обновлённый или созданный объект User.

        """
        result = await session.execute(select(User).where(User.login == login))
        user = result.scalar_one_or_none()

        if user:
            user.token = token
        else:
            user = User(login=login, token=token)
            session.add(user)

        await session.commit()
        await session.refresh(user)

        return user

    @staticmethod
    async def get_user_by_login(
        session: AsyncSession, login: str
    ) -> User | None:
        """Получает объект пользователя по его логину.

        Args:
            session: Асинхронная сессия SQLAlchemy.
            login: Логин пользователя Яндекс.

        Returns:
            Объект User или None, если не найден.

        """
        result = await session.execute(select(User).where(User.login == login))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_all_logins(session: AsyncSession) -> list[str]:
        """Возвращает список всех логинов из базы данных.

        Args:
            session: Асинхронная сессия SQLAlchemy.

        Returns:
            Список строк с логинами всех пользователей.

        """
        result = await session.execute(select(User))
        return [u.login for u in result.scalars().all()]

    @staticmethod
    async def delete_by_login(session: AsyncSession, login: str) -> None:
        """Удаляет пользователя по его логину.

        Args:
            session: Асинхронная сессия SQLAlchemy.
            login: Логин пользователя для удаления.

        """
        await session.execute(delete(User).where(User.login == login))
        await session.commit()


user_repository = UserRepository()
