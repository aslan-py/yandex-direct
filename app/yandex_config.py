"""Модуль интеграции с API Яндекс.Директа и OAuth.

Содержит класс YandexDirectAuth, реализующий:
- генерацию ссылки OAuth-авторизации;
- обмен кода подтверждения на токен;
- запросы к API Яндекс.Директа (кампании,
  объявления, быстрые ссылки, клиенты агентства).
"""

import json
from typing import Any, List

import aiohttp
from loguru import logger

from app.constants import YaSettings


class YandexDirectAuth:
    """Клиент для работы с API Яндекс.Директа и OAuth.

    Инкапсулирует всю логику HTTP-взаимодействия
    с серверами Яндекса: авторизацию, получение
    данных о пользователях, кампаниях и объявлениях.
    """

    def __init__(self) -> None:
        """Инициализирует клиент с настройками из YaSettings."""
        self.settings = YaSettings

    def get_link(self) -> str:
        """Генерирует ссылку для OAuth-авторизации.

        Returns:
            URL-строка для перехода пользователя
            на страницу авторизации Яндекс.

        """
        params = '&'.join([
            f'{k}={v}' for k, v in self.settings.GET_LINK_PARAMS.items()
        ])
        return f'{self.settings.AUTH_URL}?{params}'

    async def get_token_by_code(self, code: str) -> str:
        """Обменивает код подтверждения на OAuth-токен.

        Args:
            code: Код подтверждения, полученный от
                  пользователя после авторизации.

        Returns:
            Строка с access_token.

        Raises:
            Exception: Если API вернуло ошибку вместо токена.

        """
        data = self.settings.GET_TOKEN_PARAMS.copy()
        data['code'] = code

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.settings.TOKEN_URL, data=data
            ) as resp:
                result = await resp.json()
                if 'access_token' not in result:
                    error_desc = result.get('error_description', result)
                    raise Exception(f'Ошибка получения токена: {error_desc}')
                return result['access_token']

    async def get_passport_login(self, token: str) -> str:
        """Получает логин пользователя через Яндекс ID.

        Args:
            token: OAuth-токен пользователя.

        Returns:
            Строка с логином пользователя Яндекс.

        """
        headers = {'Authorization': f'Bearer {token}'}
        async with aiohttp.ClientSession() as session:
            async with session.get(
                self.settings.USER_INFO_URL, headers=headers
            ) as resp:
                result = await resp.json()
                return result.get('login')

    async def get_full_client_info(
        self, token: str, login: str
    ) -> dict[str, Any]:
        """Получает полную информацию о клиенте из API.

        Делает запрос к эндпоинту /clients и возвращает
        первого клиента из списка результатов.

        Args:
            token: OAuth-токен пользователя.
            login: Логин клиента в Яндекс.Директе.

        Returns:
            Словарь с полями клиента или пустой dict.

        """
        headers = {
            'Authorization': f'Bearer {token}',
            'Client-Login': login,
            'Accept-Language': 'ru',
            'Content-Type': 'application/json; charset=utf-8',
        }
        payload = {
            'method': 'get',
            'params': {'FieldNames': ['Login', 'Type', 'ClientInfo']},
        }
        async with aiohttp.ClientSession() as session:
            url = 'https://api.direct.yandex.com/json/v5/clients'
            async with session.post(
                url, json=payload, headers=headers
            ) as resp:
                result = await resp.json()
                if 'error' in result:
                    logger.error(f'API Error (Clients): {result["error"]}')
                    return result
                clients = result.get('result', {}).get('Clients', [])
                return clients[0] if clients else {}

    async def get_user_role(self, token: str, login: str) -> str:
        """Определяет роль пользователя по полю Type.

        Args:
            token: OAuth-токен пользователя.
            login: Логин клиента в Яндекс.Директе.

        Returns:
            Строка с ролью: 'AGENCY', 'CLIENT' и т.д.
            При ошибке возвращает 'UNKNOWN'.

        """
        info = await self.get_full_client_info(token, login)
        return info.get('Type', 'UNKNOWN')

    async def get_agency_clients(self, token: str, login: str) -> List[str]:
        """Получает список логинов суб-клиентов агентства.

        При ошибке кода 53/54 повторяет запрос без
        заголовка Client-Login.

        Args:
            token: OAuth-токен агентства.
            login: Логин агентства в Яндекс.Директе.

        Returns:
            Список строк с логинами активных клиентов.

        """
        headers = {
            'Authorization': f'Bearer {token}',
            'Client-Login': login,
            'Accept-Language': 'ru',
            'Content-Type': 'application/json; charset=utf-8',
        }
        payload = {
            'method': 'get',
            'params': {
                'SelectionCriteria': {'Archived': 'NO'},
                'FieldNames': ['Login', 'Archived'],
            },
        }
        logger.debug(f'Calling AgencyClients.get for {login}...')
        async with aiohttp.ClientSession() as session:
            url = 'https://api.direct.yandex.com/json/v5/agencyclients'
            async with session.post(
                url, json=payload, headers=headers
            ) as resp:
                result = await resp.json()
                logger.debug(
                    f'AgencyClients result for {login}: '
                    f'{json.dumps(result, ensure_ascii=False)}'
                )

                # Повторяем без Client-Login при ошибках 53/54
                err_code = (
                    result.get('error', {}).get('error_code')
                    if 'error' in result
                    else None
                )
                if err_code in (53, 54):
                    logger.debug('Retrying without Client-Login header...')
                    del headers['Client-Login']
                    async with session.post(
                        url, json=payload, headers=headers
                    ) as resp2:
                        result = await resp2.json()
                        logger.debug(
                            f'Retry AgencyClients result: '
                            f'{json.dumps(result, ensure_ascii=False)}'
                        )

                if 'error' in result:
                    logger.error(
                        f'API Error (AgencyClients): {result["error"]}'
                    )
                    return []

                clients = result.get('result', {}).get('Clients', [])
                logger.debug(
                    f'Found {len(clients)} agency clients for {login}'
                )
                return [c['Login'] for c in clients if c.get('Login')]

    async def get_active_campaigns(self, token: str, login: str) -> List[dict]:
        """Получает список активных кампаний (Id и Name).

        Запрашивает только кампании со статусом States=['ON'].

        Args:
            token: OAuth-токен пользователя или агентства.
            login: Логин клиента в Яндекс.Директе.

        Returns:
            Список словарей с полями Id и Name кампаний.

        """
        headers = {
            'Authorization': f'Bearer {token}',
            'Client-Login': login,
            'Accept-Language': 'ru',
            'Content-Type': 'application/json; charset=utf-8',
        }
        payload = {
            'method': 'get',
            'params': {
                'SelectionCriteria': {'States': ['ON']},
                'FieldNames': ['Id', 'Name'],
            },
        }
        logger.debug(f'Calling Campaigns.get for {login}...')
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.settings.COPMPAIGNS_URL,
                json=payload,
                headers=headers,
            ) as resp:
                result = await resp.json()
                logger.debug(
                    f'Campaigns result for {login}: '
                    f'{json.dumps(result, ensure_ascii=False)}'
                )
                if 'error' in result:
                    logger.error(f'API Error (Campaigns): {result["error"]}')
                    return []
                camps = result.get('result', {}).get('Campaigns', [])
                logger.debug(
                    f'Found {len(camps)} active campaigns for {login}'
                )
                return camps

    async def get_ads_data(
        self, token: str, login: str, campaign_ids: List[int]
    ) -> List[dict]:
        """Получает данные объявлений для указанных кампаний.

        Использует шаблон GET_ADS_PAYLOAD_TEMPLATE и
        подставляет в него переданные ID кампаний.

        Args:
            token: OAuth-токен пользователя.
            login: Логин клиента в Яндекс.Директе.
            campaign_ids: Список ID кампаний для запроса.

        Returns:
            Список словарей с данными объявлений.

        """
        headers = {
            'Authorization': f'Bearer {token}',
            'Client-Login': login,
            'Accept-Language': 'ru',
            'Content-Type': 'application/json; charset=utf-8',
        }

        # Копируем шаблон и подставляем ID кампаний
        payload = json.loads(
            json.dumps(self.settings.GET_ADS_PAYLOAD_TEMPLATE)
        )
        payload['params']['SelectionCriteria']['CampaignIds'] = campaign_ids

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.settings.ADDS_URL,
                json=payload,
                headers=headers,
            ) as resp:
                result = await resp.json()
                if 'error' in result:
                    logger.error(f'API Error (Ads): {result["error"]}')
                    return []
                return result.get('result', {}).get('Ads', [])

    async def get_sitelinks(
        self,
        token: str,
        login: str,
        sitelink_set_ids: List[int],
    ) -> List[dict]:
        """Получает ссылки из наборов быстрых ссылок.

        Args:
            token: OAuth-токен пользователя.
            login: Логин клиента в Яндекс.Директе.
            sitelink_set_ids: Список ID наборов быстрых ссылок.

        Returns:
            Список словарей с данными наборов сайтлинков.
            Возвращает пустой список при пустом вводе.

        """
        if not sitelink_set_ids:
            return []

        headers = {
            'Authorization': f'Bearer {token}',
            'Client-Login': login,
            'Accept-Language': 'ru',
            'Content-Type': 'application/json; charset=utf-8',
        }

        payload = json.loads(
            json.dumps(self.settings.GET_SITELINKS_PAYLOAD_TEMPLATE)
        )
        payload['params']['SelectionCriteria']['Ids'] = sitelink_set_ids

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.settings.FAST_LINKS,
                json=payload,
                headers=headers,
            ) as resp:
                result = await resp.json()
                if 'error' in result:
                    logger.error(f'API Error (Sitelinks): {result["error"]}')
                    return []
                return result.get('result', {}).get('Sitelinks', [])

    async def get_sitelinks_hrefs(
        self,
        token: str,
        login: str,
        sitelink_set_ids: List[int],
    ) -> List[dict]:
        """Псевдоним для get_sitelinks.

        Обеспечивает обратную совместимость вызовов
        в модуле service.py.

        Args:
            token: OAuth-токен пользователя.
            login: Логин клиента в Яндекс.Директе.
            sitelink_set_ids: Список ID наборов сайтлинков.

        Returns:
            Результат вызова get_sitelinks.

        """
        return await self.get_sitelinks(token, login, sitelink_set_ids)


# Экземпляр для импорта в другие модули
yandex_auth = YandexDirectAuth()
