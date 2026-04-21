"""Модуль констант и настроек приложения.

Содержит переменные окружения, URL-адреса API
Яндекс.Директа, параметры OAuth и текстовые
сообщения Telegram-бота.
"""

import os

from dotenv import load_dotenv

load_dotenv()

REDIS_HOST = os.getenv('REDIS_HOST')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))


class DbSettings:
    """Константы для подключения к базе данных.

    Хранит URL базы данных SQLite и ограничения
    длины строковых полей.
    """

    DATABASE_URL = 'sqlite+aiosqlite:///./direct.sqlite'
    LOGIN_STR = 100
    TOKEN_STR = 255


TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')


class YaSettings:
    """Константы для работы с API Яндекс.Директа.

    Хранит URL-адреса эндпоинтов, параметры
    OAuth-авторизации и шаблоны JSON-запросов.
    """

    ADDS_URL = 'https://api.direct.yandex.com/json/v5/ads'
    COPMPAIGNS_URL = 'https://api.direct.yandex.com/json/v5/campaigns'
    ADDS_GROUP = 'https://api.direct.yandex.com/json/v5/adgroups'
    FAST_LINKS = 'https://api.direct.yandex.com/json/v5/sitelinks'
    DATABASE_URL = os.getenv('DATABASE_UR')

    CLIENT_ID = os.getenv('CLIENT_ID')
    CLIENT_SECRET = os.getenv('CLIENT_SECRET')

    REDIRECT_URL = 'https://oauth.yandex.ru/verification_code'
    USER_INFO_URL = 'https://login.yandex.ru/info'
    AUTH_URL = 'https://oauth.yandex.ru/authorize'
    TOKEN_URL = 'https://oauth.yandex.ru/token'
    GET_LINK_PARAMS = {
        'response_type': 'code',
        'client_id': CLIENT_ID,
        'redirect_uri': REDIRECT_URL,
        'force_confirm': 'yes',
    }
    GET_TOKEN_PARAMS = {
        'grant_type': 'authorization_code',
        'code': '',
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'redirect_uri': REDIRECT_URL,
    }
    GET_COM_JSON = {
        'method': 'get',
        'params': {
            'SelectionCriteria': {},
            'FieldNames': ['Id', 'Name', 'State', 'Status'],
        },
    }
    BASE_HEADERS = {
        'Accept-Language': 'ru',
        'Content-Type': 'application/json; charset=utf-8',
    }

    GET_ADS_PAYLOAD_TEMPLATE = {
        'method': 'get',
        'params': {
            'SelectionCriteria': {
                'CampaignIds': [],
                'States': ['ON'],
            },
            'FieldNames': ['Id', 'State'],
            'TextAdFieldNames': ['Href', 'SitelinkSetId'],
            'DynamicTextAdFieldNames': ['SitelinkSetId'],
            'TextImageAdFieldNames': ['Href'],
            'TextAdBuilderAdFieldNames': ['Href'],
            'CpcVideoAdBuilderAdFieldNames': ['Href'],
            'CpmBannerAdBuilderAdFieldNames': ['Href'],
            'CpmVideoAdBuilderAdFieldNames': ['Href'],
        },
    }

    GET_SITELINKS_PAYLOAD_TEMPLATE = {
        'method': 'get',
        'params': {
            'SelectionCriteria': {'Ids': []},
            'SitelinkFieldNames': ['Href'],
        },
    }


class BotMessages:
    """Текстовые сообщения и метки кнопок Telegram-бота.

    Все строки вынесены сюда для удобного редактирования
    без изменения логики обработчиков.
    """

    HELP_TEXT = (
        '🤖 **Главное меню**\n\nИспользуйте кнопки ниже для управления ботом.'
    )

    MENU_LOGIN = '➕ Привязать аккаунт'
    MENU_CHECK = '🚀 Проверить ссылки'
    MENU_DELETE = '🗑 Удалить аккаунт'
    MENU_CLEAR = '🧹 Очистить экран'

    LOGIN_START = (
        'Перейдите по ссылке, нажмите «Разрешить» и пришлите мне код:'
    )
    LOGIN_BTN = '🔐 Авторизоваться'
    LOGIN_SUCCESS = '✅ Аккаунт **{}** успешно привязан!'
    LOGIN_ERROR = '❌ Ошибка авторизации: {}'

    DELETE_EMPTY = 'Список аккаунтов пуст.'
    DELETE_CHOOSE = 'Выберите аккаунт для удаления:'
    DELETE_BTN = '❌ Удалить {}'
    DELETE_CONFIRM = '🗑 Аккаунт **{}** удален.'
    DELETE_ERROR = 'Ошибка при удалении: {}'

    CHECK_START = '⏳ Начинаю сбор ссылок и проверку...'
    CHECK_ERROR = '❌ Ошибка выполнения: {}'
    CHECK_NO_ACCOUNTS = 'В базе пока нет аккаунтов. Привяжите новый аккаунт.'

    CHOOSE_ACCOUNT = 'Выбор аккаунта для проверки:'
    CHOOSE_SUBCLIENT = (
        'Выберите суб-клиента для проверки (или проверьте всех):'
    )
    CHECK_ALL_SUBCLIENTS = '🌐 Проверить всех клиентов'

    CHOOSE_CAMPAIGNS = 'Выберите кампании для проверки:'
    CHECK_ALL_CAMPAIGNS = '📁 Проверить все кампании'
    CHECK_SELECTED = '✅ Запустить проверку выбранных'

    REPORT_CACHED_PREFIX = '🔔 (Результат из кэша)\n'

    CLEAR_SUCCESS = '🧹 Экран очищен.'
    BACK_BTN = '🔙 Назад'
    NEXT_PAGE = '▶️ Вперед'
    PREV_PAGE = '◀️ Назад'
