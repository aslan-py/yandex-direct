"""
Модуль предоставляет функциональность для работы с API Яндекс.Директ,
управления базой данных SQLite и проверки URL-адресов в рекламных объявлениях.

Основные возможности:
- Инициализация и управление базой данных SQLite
- Авторизация и работа с API Яндекс.Директ
- Получение данных о кампаниях, объявлениях и быстрых ссылках
- Проверка работоспособности URL-адресов
- Логирование операций с ротацией лог-файлов

Основные компоненты:

Функции работы с базой данных:
- initialize_database() - создание таблицы для хранения токенов
- get_all_logins_and_tokens() - загрузка пользователей из БД

Функции API Яндекс.Директ:
- get_api_response() - базовый запрос к API кампаний
- get_ads_api_response() - запрос данных об объявлениях
- get_sitelinks_api_response() - запрос данных о быстрых ссылках

Функции проверки ответов:
- check_response() - валидация ответов API
- parse_companies_response() - обработка данных кампаний
- parse_ads_response() - обработка данных объявлений
- parse_sitelinks_response() - обработка быстрых ссылок

Функции проверки URL:
- check_url_status() - проверка доступности URL с кэшированием

Логирование:
- setup_logging() - настройка системы логирования
- logger - глобальный объект логгера

Константы (импортируются из constants.py):
- COPMPAIGNS_URL, ADDS_URL, FAST_LINKS - endpoint'ы API
- GET_COM_JSON - стандартный JSON для запросов

Особенности работы:
- Использует OAuth 2.0 для авторизации в API
- Поддерживает обработку ошибок и повторные попытки
- Обеспечивает ротацию лог-файлов (10MB max, 3 файла)
- Кэширует результаты проверки URL в течение сессии

Требования:
- Python 3.12.7
- Библиотеки: requests, sqlite3, logging, os

Автор: [Лигус Аслан]
Версия: 1.0
Дата создания: [2025.09.24]
"""
import logging
import os
import requests
import sqlite3

from logging.handlers import RotatingFileHandler

from constants import (
    COPMPAIGNS_URL, GET_COM_JSON, ADDS_URL, FAST_LINKS
    )


def initialize_database() -> bool:
    """Создает таблицу в базе данных, если она не существует."""
    try:
        with sqlite3.connect('direct.sqlite') as con:
            cur = con.cursor()
            query = '''
                CREATE TABLE IF NOT EXISTS logins_tokens(
                    id INTEGER PRIMARY KEY,
                    login TEXT UNIQUE,
                    token TEXT
                );
            '''
            cur.execute(query)
            logger.info("База данных успешно инициализирована")
            return True
    except Exception as error:
        logger.error(f"Ошибка при создании таблицы в базе данных: {error}")
        return False


def get_all_logins_and_tokens(DB: dict) -> tuple[bool, str]:
    """
    Загружает логины и токены пользователей из базы данных в словарь DB.

    Returns:
        tuple[bool, str]: (статус, сообщение)
            - (True, "успешное сообщение") - успех
            - (False, "ошибка") - ошибка
    """

    try:
        with sqlite3.connect('direct.sqlite') as con:
            cur = con.cursor()
            results = cur.execute(
                '''SELECT login, token FROM logins_tokens;''')
            all_results = results.fetchall()

        if not all_results:
            msg = 'В базе данных нет пользователей для проверки'
            logger.warning(msg)
            return False, msg

        for login, token in all_results:
            DB[login] = {
                'token_info': token,
                'company_id': [],
                'adds_id': [],
                'adds_href': [],
                'sitelinks_id': [],
                'sitelinks_href': [],
                'failed_urls': {},
                'failed_sitelinks_urls': {}
            }
        msg = (
            f'Данные из БД выгружены для : {len(all_results)} пользователей  '
            f' - начинаю обработку'
        )
        logger.info(msg)
        return True, msg
    except Exception as error:
        msg = f'Ошибка при выгрузке логина и токена из базы: {error}'
        logger.error(msg)
        return False, msg


def get_api_response(token: str, login: str) -> requests.Response | None:
    """
    Выполняет базовый API запрос к Яндекс.Директ.

    Отправляет POST запрос к API campaigns с стандартными параметрами
        для получения
    списка кампаний пользователя. Используется как основа для
        последующих запросов.

    Parameters:
        token (str): OAuth-токен для авторизации в API
        login (str): Логин клиента в Яндекс.Директ (Client-Login)

    Returns:
        requests.Response | None:
            - Response object при успешном запросе
            - None в случае возникновения исключения

    Behavior:
        - Использует предопределенный JSON шаблон GET_COM_JSON
        - Устанавливает заголовки авторизации и локализации
        - Применяет таймаут 30 секунд для запроса
        - Логирует ошибки при выполнении запроса

    Note:
        Запрос возвращает базовую информацию о кампаниях: Id, Name, State
    """

    try:
        response = requests.post(
            COPMPAIGNS_URL,
            headers={
                'Authorization': f'Bearer {token}',
                'Accept-Language': 'ru',
                'Content-Type': 'application/json; charset=utf-8',
                'Client-Login': login
            },
            json=GET_COM_JSON,
            timeout=30
        )
        return response
    except Exception as error:
        logger.error(f'Ошибка при выполнении API запроса:для {login}: {error}')
        return False


def check_response(
        response: requests.Response | None, login: str,
        api_type: str = 'компаний'
) -> tuple[bool, str]:
    """
    Проверяет корректность ответа от API Яндекс.Директ.

    Parameters:
        response (requests.Response | None): Response object для проверки
        login (str): Логин пользователя для идентификации в логах
        api_type (str): Тип API запроса для логирования

    Returns:
        tuple[bool, str]:
            - (True, 'успешное сообщение') - ответ корректен
            - (False, 'ошибка') - любая ошибка (критическая или бизнес-логика)
    """

    try:
        if not response:
            error_text = (
                f'Пустой ответ API {api_type} для пользователя {login}')
            logger.error(error_text)
            return False, error_text

        if response.status_code != 200:
            error_text = (
                f'Неверный статус {response.status_code} для API {api_type},'
                f' пользователя {login}'
            )
            logger.error(error_text)
            return False, error_text

        response_json = response.json()

        if not isinstance(response_json, dict):
            error_text = (
                f'Ответ API {api_type} не является словарем :'
                f' для пользователя {login}'
            )
            logger.error(error_text)
            return False, error_text

        if response_json.get('error'):
            error_text = (
                f'Пользователя {login} нет в Директе'
            )
            logger.warning(error_text)
            return False, error_text

        if not response_json.get('result'):
            error_text = (
                f'В ответе API {api_type} нет ключа "result" для {login}'
            )
            logger.error(error_text)
            return False, error_text

        #  Если успех.
        success_text = (f'Ответ API {api_type}  корректен')
        logger.info(f'🟡 - {success_text}')
        return True, success_text

    except ValueError as error:
        error_text = (
                f'Ошибка парсинга JSON для API {api_type} пользователя'
                f' пользователя {login}: {error}'
            )
        logger.error(error_text)
        return False, error_text

    except Exception as error:
        error_text = (
                f'Непредвиденная ошибка при проверке ответа API {api_type} '
                f'для {login}: {error} '
            )
        logger.error(error_text)
        return False, error_text


def parse_companies_response(
        response_data: requests.Response, login: str, DB: dict
        ) -> tuple[bool, str]:
    """
    Парсит ответ API Яндекс.Директ с данными о кампаниях и сохраняет в DB.

    Returns:
        tuple[bool, str]:
            - (True, 'успешное сообщение') - успех
            - (False, 'ошибка') - любая ошибка (критическая или нет кампаний)
    """

    try:
        response_data = response_data.json()
        companies = response_data['result'].get('Campaigns', [])
        if not companies:
            msg = f'У пользователя {login} нет кампаний в Директе'
            logger.warning(msg)
            return False, msg

        active_count = 0
        for company in companies:
            campaign_id = company.get('Id')
            company_state = company.get('State')

            if campaign_id and company_state == 'ON':
                DB[login]['company_id'].append(campaign_id)
                active_count += 1
            else:
                logger.debug(
                    f'Пропускаем компанию {campaign_id} - '
                    f'статус: {company_state}'
                )
        logger.info(
            f'Добавлено {active_count} активных компаний из {len(companies)} '
            f' для {login}'
        )
        if active_count == 0:
            msg = f'У пользователя {login} нет активных кампаний, пропускаем'
            logger.warning(msg)
            return False, msg
        return True, f'Найдено {active_count} активных кампаний'

    except Exception as error:
        msg = f'Ошибка парсинга компаний для {login}: {error}'
        logger.error(msg)
        return False, msg

#  ----------------Для запроса по объявлениям-----------------------------


def get_ads_api_response(
        token: str, login: str, campaign_ids: list
) -> requests.Response | None:
    """
    Выполняет API запрос к Яндекс.Директ для получения данных об объявлениях.

    Отправляет серию POST запросов к API ads с разбивкой campaign_ids на чанки
    по 10 элементов для избежания превышения лимитов API.

    Parameters:
        token (str): OAuth-токен для авторизации в API
        login (str): Логин клиента в Яндекс.Директ (Client-Login)
        campaign_ids (list): Список идентификаторов кампаний для фильтрации

    Returns:
        MockResponse | None:
            - MockResponse object с объединенными данными из всех чанков
            - None в случае возникновения исключения

    Behavior:
        - Автоматически преобразует одиночный campaign_id в список
        - Разбивает campaign_ids на чанки по 10 элементов
        - Для каждого чанка выполняет отдельный API запрос
        - Объединяет результаты всех запросов в MockResponse
        - Включает данные для различных типов объявлений

    Note:
        Использует MockResponse для эмуляции стандартного response object
    """

    try:
        # Если campaign_ids не массив, делаем его массивом
        if not isinstance(campaign_ids, list):
            campaign_ids = [campaign_ids]

        # Разбиваем на chunks по 10 ID
        chunk_size = 10
        all_ads = []

        for i in range(0, len(campaign_ids), chunk_size):
            chunk = campaign_ids[i:i + chunk_size]
            chunk_number = i // chunk_size + 1
            total_chunks = (len(campaign_ids) - 1) // chunk_size + 1
            logger.debug(
                f'Обрабатываем chunk {chunk_number}/{total_chunks}: '
                f'{len(chunk)} кампаний'
            )
            json_data = {
                "method": "get",
                "params": {
                    "SelectionCriteria": {"CampaignIds": chunk},
                    "FieldNames": ["CampaignId", "Id", "Type", "State"],
                    "TextAdFieldNames": ["Href", "SitelinkSetId"],
                    "DynamicTextAdFieldNames": ["SitelinkSetId"],
                    "TextImageAdFieldNames": ["Href"],
                    "TextAdBuilderAdFieldNames": ["Href"],
                    "CpcVideoAdBuilderAdFieldNames": ["Href"],
                    "CpmBannerAdBuilderAdFieldNames": ["Href"],
                    "CpmVideoAdBuilderAdFieldNames": ["Href"],
                }
            }

            response = requests.post(
                ADDS_URL,
                headers={
                    'Authorization': f'Bearer {token}',
                    'Accept-Language': 'ru',
                    'Content-Type': 'application/json; charset=utf-8',
                    'Client-Login': login
                },
                json=json_data,
                timeout=30
            )

            if response and response.status_code == 200:
                response_data = response.json()
                all_ads.extend(response_data['result'].get('Ads', []))
            else:
                logger.warning(f"Ошибка для chunk {chunk}")

        # Создаем mock response с объединенными данными
        class MockResponse:
            def __init__(self, ads):
                self.status_code = 200
                self.ads = ads

            def json(self):
                return {'result': {'Ads': self.ads}}

        return MockResponse(all_ads)

    except Exception as error:
        logger.error(f'Ошибка API запроса объявлений для {login}: {error}')
        return None


def parse_ads_response(
        response_data: requests.Response, login: str, DB: dict
) -> tuple[bool, str]:
    """
    Парсит ответ API Яндекс.Директ с данными об объявлениях и сохраняет в DB.

    Returns:
        tuple[bool, str]:
            - (True, 'успешное сообщение') - успех
            - (False, 'ошибка') - любая ошибка
    """

    try:
        response_data = response_data.json()
        ads = response_data['result'].get('Ads', [])

        if not ads:
            msg = f'Нет объявлений для пользователя {login}'
            logger.warning(msg)
            return False, msg

        active_count = 0
        for ad in ads:
            ad_id = ad.get('Id')
            ad_state = ad.get('State')

            # Добавляем только активные объявления (ON)
            if ad_id and ad_state == 'ON':
                href = None
                sitelink_set_id = None

                # Ищем ссылку в различных типах объявлений
                for ad_type in ['TextAd', 'TextImageAd', 'TextAdBuilderAd',
                                'CpcVideoAdBuilderAd', 'CpmBannerAdBuilderAd',
                                'CpmVideoAdBuilderAd']:
                    if ad.get(ad_type):
                        href = ad[ad_type].get('Href')
                        sitelink_set_id = ad[ad_type].get('SitelinkSetId')
                        break

                if ad.get('DynamicTextAd'):
                    sitelink_set_id = ad['DynamicTextAd'].get('SitelinkSetId')

                DB[login]['adds_id'].append(ad_id)
                if href:
                    DB[login]['adds_href'].append(href)
                if sitelink_set_id:
                    DB[login]['sitelinks_id'].append(sitelink_set_id)
                active_count += 1
            else:
                logger.debug(
                    f'Пропускаем объявление {ad_id} - статус: {ad_state}')

        if active_count == 0:
            msg = f'У пользователя {login} нет активных объявлений'
            logger.warning(msg)
            return False, msg

        logger.info(
            f'Обнаружено {active_count} id компаний и добавлено '
            f'{len(DB[login]['adds_href'])} ссылок на объявления из '
            f'{len(ads)} для {login}'
        )
        return True, f'Найдено {active_count} активных объявлений'

    except Exception as error:
        msg = f'Ошибка парсинга объявлений для {login}: {error}'
        logger.error(msg)
        return False, msg

#  ----------------Для запроса по быстрым ссылкам--------------------------


def get_sitelinks_api_response(
        token: str, login: str, sitelink_set_id: list
) -> requests.Response | None:
    """
    Выполняет API запрос к Яндекс.Директ для получения данных
        о быстрых ссылках.

    Отправляет POST запрос к API sitelinks для получения информации
    о конкретном наборе быстрых ссылок по его идентификатору.

    Parameters:
        token (str): OAuth-токен для авторизации в API
        login (str): Логин клиента в Яндекс.Директ (Client-Login)
        sitelink_set_id (list): Список идентификаторов наборов быстрых ссылок

    Returns:
        requests.Response | None:
            - Response object при успешном запросе
            - None в случае возникновения исключения

    Raises:
        requests.exceptions.RequestException: При ошибках сетевого запроса
        Exception: При прочих непредвиденных ошибках

    Note:
        Запрос выполняется с таймаутом 30 секунд и русской локализацией
    """

    try:
        response = requests.post(
            FAST_LINKS,
            headers={
                'Authorization': f'Bearer {token}',
                'Accept-Language': 'ru',
                'Content-Type': 'application/json; charset=utf-8',
                'Client-Login': login
            },
            json={
                "method": "get",
                "params": {
                    "SelectionCriteria": {'Ids': sitelink_set_id},
                    "FieldNames": ["Id"],
                    "SitelinkFieldNames": ["Title", "Href"]
                }
            },
            timeout=30
        )
        return response
    except Exception as error:
        logger.error(
            f"Ошибка при выполнении API запроса быстрых ссылок: {error}")
        return None


def parse_sitelinks_response(response_data, login, DB) -> tuple[bool, str]:
    """
    Парсит ответ API Яндекс.Директ с быстрыми ссылками и сохраняет в DB.

    Returns:
        tuple[bool, str]:
            - (True, 'успешное сообщение') - успех
            - (False, 'ошибка') - любая ошибка
    """

    try:
        response_data = response_data.json()
        sitelinks_sets = response_data['result'].get('SitelinksSets', [])

        if not sitelinks_sets:
            msg = f'Нет быстрых ссылок для пользователя {login}'
            logger.warning(msg)
            return False, msg

        added_count = 0
        for sitelink_set in sitelinks_sets:
            for sitelink in sitelink_set.get('Sitelinks', []):
                href = sitelink.get('Href')
                if href:
                    DB[login]['sitelinks_href'].append(href)
                    added_count += 1
        if added_count == 0:
            msg = f'Не найдено рабочих быстрых ссылок для {login}'
            logger.warning(msg)
            return False, msg
        logger.info(
            f'Обнаружено {len(DB[login]['sitelinks_href'])} id быстрых ссылок '
            f'и добавлено {added_count} быстрых ссылок для {login}'
            )
        return True, f'Найдено {added_count} быстрых ссылок'

    except Exception as error:
        msg = f'Ошибка парсинга быстрых ссылок для {login}: {error}'
        logger.error(msg)
        return False, msg


#  ----------------Проверка ссылок и формирование отчета--------------------
def check_url_status(urls, login, DB, url_type='ad') -> bool | str:
    """
    Проверяет статус URL-адресов и формирует отчет о проверке.

    Функция выполняет проверку доступности URL-адресов с учетом дубликатов.
    Рабочие ссылки кэшируются в течение одной сессии проверки для избежания
    повторных запросов. Нерабочие ссылки сохраняются в словаре
    DB с счетчиком дублей.

    Parameters:
        urls (list): Список URL-адресов для проверки
        login (str): Логин пользователя для идентификации в DB
        DB (dict): Словарь с данными пользователей
        url_type (str): Тип ссылок ('ad' - объявления, иное - быстрые ссылки)

    Returns:
        Union[bool, str]:
            - False если передан пустой список URLs
            - str с отчетом о проверке в остальных случаях

    Behavior:
        - Для каждого URL проверяется наличие в словаре нерабочих ссылок
        - Дубли нерабочих ссылок увеличивают счетчик без повторной проверки
        - Рабочие ссылки кэшируются в памяти на время выполнения функции
        - Новые ссылки проверяются HTTP-запросом с таймаутом 8 секунд
        - Формируется подробный отчет со статистикой и списком проблемных URL
    """

    if not urls:
        logger.debug('Пустые URLs, пропускаем проверку')
        return False

    # Инициализируем кэш рабочих ссылок если не передан
    working_urls_cache = set()

    # Определяем target_dict в зависимости от типа ссылки
    if url_type == 'ad':
        target_dict = DB[login]['failed_urls']
        url_source = 'обычных ссылок'
    else:
        target_dict = DB[login]['failed_sitelinks_urls']
        url_source = 'быстрых ссылок'

    logger.info(
        f'Начинаем проверку {len(urls)} {url_source} для логина {login}')

    processed = 0
    skipped_failed = 0
    skipped_working = 0
    new_checked = 0

    # Словарь для хранения статусов нерабочих ссылок
    failed_urls_statuses = {}

    for i, url in enumerate(urls, 1):
        if not url:
            logger.debug(f'🔵{i}. Пустой URL, пропускаем')
            continue
        processed += 1

        # Проверяем, есть ли уже URL в failed словаре
        if url in target_dict:
            target_dict[url] += 1  # Увеличиваем счетчик дублей
            skipped_failed += 1
            logger.debug(
                f'🟡Ссылка {url} для {url_type} уже в failed, увеличиваем  '
                f'счетчик: {target_dict[url]}'
            )
            continue
        if url in working_urls_cache:
            skipped_working += 1
            logger.debug(
                f'Ссылка {url} для {url_type} уже проверена и работает')
            continue
        new_checked += 1

        logger.info(f'{i}. 🔎 Проверяем новую ссылку: {url}')
        try:
            response = requests.get(
                url,
                timeout=8,
                headers={'User-Agent': 'Mozilla/5.0'},
                allow_redirects=False
            )
            status_ok = response.status_code == 200

            if not status_ok:
                target_dict[url] = 1
                failed_urls_statuses[url] = response.status_code
                logger.warning(
                    f'🔴Добавлена неработающая ссылка: {url} (статус: '
                    f'{response.status_code})'
                )
            else:
                working_urls_cache.add(url)
                logger.info(
                    f'{url} - РАБОТАЕТ (статус: {response.status_code})')

        except Exception as e:
            logger.warning(f'Ошибка при проверке {url_type} ссылки {url}: {e}')

            target_dict[url] = 1
            failed_urls_statuses[url] = 'ERROR'
            logger.debug(f"🔴Добавлена неработающая ссылка (ошибка): {url}")

    report_lines = [
        f'Обработано: {processed} {url_source}',
        f'Всего нерабочих ссылок: {len(target_dict)} \n'

    ]
    report_lines_for_logger = [
        f'==============',
        f'======= Отчет для {login} =======',
        f'Обработано: {processed} {url_source}',
        f'Новых проверено: {new_checked}',
        f'Пропущено кривых: {skipped_failed}',
        f'Пропущено рабочих: {skipped_working}',
        f'Всего нерабочих ссылок: {len(target_dict)} \n'
        f'  {target_dict}'
    ]

    logger.info('\n'.join(report_lines_for_logger))

    if target_dict:
        report_lines.append('Нерабочие ссылки:')
        for url, count in target_dict.items():
            status = failed_urls_statuses.get(url, 'UNKNOWN')
            report_lines.append(
                f'  {url} (дублей: {count}, статус: {status})')
    # else:
    #     report_lines.append('Нерабочих ссылок не найдено')

    # Объединяем все в одну строку с переносами
    report = '\n'.join(report_lines)
    logger.info(f'Отчет для {login} готов')

    return report


#  ----------------Логирование----------------------------------------------


def setup_logging():
    """
    Инициализирует и настраивает систему логирования приложения.

    Конфигурация включает:
    - Файловый обработчик с ротацией (max 10MB, 3 файла)
    - Консольный обработчик для immediate feedback
    - Поддержку Unicode (UTF-8 encoding)
    - Автоматическое создание директории logs/

    Log Levels:
        File: DEBUG и выше (полная отладка)
        Console: INFO и выше (ключевая информация)

    Formats:
        File:    '2023-12-01 14:30:00 - INFO - module.py:42
            - function_name - message'
        Console: 'INFO - message'

    Returns:
        logging.Logger: Сконфигурированный корневой логгер
    """
    # Создаем папку для логов если ее нет
    if not os.path.exists('logs'):
        os.makedirs('logs')

    # Формат логов: дата, уровень, имя файла, номер строки, функция, сообщение
    log_format = (
        '%(asctime)s - %(levelname)s - '
        '%(filename)s:%(lineno)d - %(funcName)s - %(message)s'
    )

    # Настраиваем root logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    # Очищаем существующие обработчики
    logger.handlers.clear()

    # Файловый обработчик с ротацией
    file_handler = RotatingFileHandler(
        'logs/main_log.log',
        maxBytes=10*1024*1024,  # 10 MB
        backupCount=2,          # 2 backup файла + основной = 3 файла
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(log_format))

    # Консольный обработчик
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(
        '%(levelname)s - %(message)s'))

    # Добавляем обработчики
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


# Создаем глобальный логгер
logger = setup_logging()
