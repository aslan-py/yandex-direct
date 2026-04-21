"""Модуль ORM-моделей базы данных.

Определяет таблицу пользователей для хранения
OAuth-токенов Яндекс.Директа.
"""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.constants import DbSettings
from app.db import Base


class User(Base):
    """Модель таблицы пользователей.

    Хранит логин и OAuth-токен каждого
    привязанного аккаунта Яндекс.Директа.
    """

    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    login: Mapped[str] = mapped_column(
        String(DbSettings.LOGIN_STR), unique=True, nullable=False
    )
    token: Mapped[str] = mapped_column(
        String(DbSettings.TOKEN_STR), nullable=False
    )

    def __repr__(self) -> str:
        """Возвращает строковое представление объекта."""
        return f'<User(id={self.id}, login={self.login})>'
