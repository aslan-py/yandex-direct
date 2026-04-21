"""Модуль Pydantic-схем приложения.

Определяет модели данных для валидации ответов
от Яндекс OAuth API и внутреннего представления
пользователей в базе данных.
"""

from pydantic import BaseModel


class YandexTokenResponse(BaseModel):
    """Схема ответа от Яндекс.ID при получении токена.

    Поля соответствуют структуре JSON-ответа
    на запрос обмена кода на токен.
    """

    access_token: str
    expires_in: int
    token_type: str = 'Bearer'


class YandexUserInfo(BaseModel):
    """Схема данных пользователя из Яндекс.Паспорта.

    Используется для десериализации ответа
    от эндпоинта /info Яндекс.ID.
    """

    login: str
    id: str | int


class UserDB(BaseModel):
    """Схема для внутреннего представления пользователя.

    Используется при чтении и записи данных
    пользователя в базу данных SQLite.
    """

    id: int | None = None
    login: str
    token: str

    class Config:
        """Настройка совместимости с ORM-объектами."""

        from_attributes = True
