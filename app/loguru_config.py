"""Модуль настройки системы логирования.

Конфигурирует Loguru для вывода логов в консоль
и в файлы с ротацией: общий debug-лог и отдельный
файл для ошибок уровня ERROR и выше.
"""

import os
import sys

from loguru import logger


def setup_logging() -> None:
    """Конфигурирует Loguru для всего проекта.

    Создаёт директорию logs при её отсутствии,
    затем добавляет три обработчика:
    - вывод в stderr (уровень INFO, с цветом);
    - файл logs/app_debug.log (уровень DEBUG,
      ротация 10 МБ, хранение 3 дня, сжатие zip);
    - файл logs/errors.log (уровень ERROR,
      ротация 5 МБ).
    """
    if not os.path.exists('logs'):
        os.makedirs('logs')

    logger.remove()

    logger.add(
        sys.stderr,
        format=(
            '<green>{time:YYYY-MM-DD HH:mm:ss}</green> | '
            '<level>{level: <8}</level> | '
            '<cyan>{name}</cyan>:<cyan>{function}</cyan>:'
            '<cyan>{line}</cyan> -'
            ' <level>{message}</level>'
        ),
        level='INFO',
        colorize=True,
    )

    logger.add(
        'logs/app_debug.log',
        format=(
            '{time:YYYY-MM-DD HH:mm:ss} | '
            '{level: <8} | {name}:{function}:{line}'
            ' - {message}'
        ),
        level='DEBUG',
        rotation='10 MB',
        retention='3 days',
        compression='zip',
        encoding='utf-8',
    )
    logger.add(
        'logs/errors.log',
        format=(
            '{time:YYYY-MM-DD HH:mm:ss} | '
            '{level: <8} | {name}:{function}:{line}'
            ' - {message}'
        ),
        level='ERROR',
        rotation='5 MB',
        encoding='utf-8',
    )


setup_logging()

__all__ = ['logger']
