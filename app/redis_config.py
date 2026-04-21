"""Модуль конфигурации Redis-клиента.

Создаёт глобальный асинхронный клиент Redis
для хранения временного состояния бота.
"""

import redis.asyncio as redis

from app.constants import REDIS_HOST, REDIS_PORT

redis_client = redis.Redis(
    host=REDIS_HOST, port=REDIS_PORT, decode_responses=True
)
