"""Модуль бизнес-логики и сервисного слоя.

Содержит два класса:
- UrlCheckerService — асинхронная параллельная
  проверка доступности URL-адресов;
- DirectService — оркестратор для получения данных
  из Яндекс.Директа и формирования отчётов.
"""

import asyncio
from typing import Any, Dict, List

import aiohttp
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import user_repository
from app.yandex_config import yandex_auth


class UrlCheckerService:
    """Сервис асинхронной проверки доступности URL.

    Ограничивает количество одновременных соединений
    через asyncio.Semaphore для предотвращения
    перегрузки сети и блокировок со стороны серверов.
    """

    def __init__(self, limit: int = 10) -> None:
        """Инициализирует сервис с заданным лимитом.

        Args:
            limit: Максимальное число параллельных
                   HTTP-соединений (по умолчанию 10).

        """
        self.semaphore = asyncio.Semaphore(limit)

    async def check_single_url(self, url: str) -> Dict[str, Any]:
        """Проверяет один URL на доступность (HTTP 200).

        Выполняет GET-запрос с таймаутом 8 секунд,
        следуя редиректам. Считает ссылку рабочей
        только при статусе 200.

        Args:
            url: Адрес для проверки.

        Returns:
            Словарь с полями:
            - url: исходный адрес;
            - status: HTTP-статус или строка 'Error';
            - is_ok: True только при статусе 200.

        """
        async with self.semaphore:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        url, timeout=8, allow_redirects=True
                    ) as response:
                        is_ok = response.status == 200
                        return {
                            'url': url,
                            'status': response.status,
                            'is_ok': is_ok,
                        }
            except Exception as e:
                logger.debug(f'Ошибка при проверке {url}: {e}')
                return {
                    'url': url,
                    'status': 'Error',
                    'is_ok': False,
                }

    async def check_list_of_urls(
        self, urls: List[str]
    ) -> List[Dict[str, Any]]:
        """Запускает параллельную проверку списка URL.

        Дедуплицирует входной список перед проверкой,
        чтобы не делать повторных запросов к одному адресу.

        Args:
            urls: Список URL для проверки (может содержать
                  дубликаты).

        Returns:
            Список словарей с результатами проверки
            каждого уникального URL.

        """
        unique_urls = list(set(urls))
        tasks = [self.check_single_url(url) for url in unique_urls]
        return await asyncio.gather(*tasks)


class DirectService:
    """Оркестратор данных Яндекс.Директа.

    Координирует получение кампаний, объявлений
    и быстрых ссылок через yandex_auth, а затем
    запускает проверку URL и формирует текстовый отчёт.
    """

    def __init__(self, db_session: AsyncSession) -> None:
        """Инициализирует сервис с сессией БД.

        Args:
            db_session: Асинхронная сессия SQLAlchemy
                        для выполнения запросов к БД.

        """
        self.db = db_session
        self.checker = url_checker

    async def register_user_by_code(self, auth_code: str) -> str:
        """Регистрирует пользователя в БД по коду OAuth.

        Обменивает код на токен, получает логин
        и сохраняет (или обновляет) запись в БД.

        Args:
            auth_code: Код подтверждения от Яндекс OAuth.

        Returns:
            Логин зарегистрированного пользователя.

        """
        token = await yandex_auth.get_token_by_code(auth_code)
        login = await yandex_auth.get_passport_login(token)
        await user_repository.upsert_user(self.db, login, token)
        return login

    async def delete_user_by_login(self, login: str) -> None:
        """Удаляет пользователя из базы данных.

        Args:
            login: Логин пользователя для удаления.

        """
        await user_repository.delete_by_login(self.db, login)

    async def get_urls_from_campaigns(
        self,
        token: str,
        client_login: str,
        campaign_ids: List[int],
    ) -> List[str]:
        """Извлекает все URL из указанных кампаний.

        Делает запросы к API Ads и Sitelinks
        порциями по 10 кампаний, собирая ссылки из
        TextAd.Href и из всех наборов быстрых ссылок.

        Args:
            token: OAuth-токен пользователя.
            client_login: Логин клиента Яндекс.Директа.
            campaign_ids: ID кампаний для извлечения URL.

        Returns:
            Список всех найденных URL (с дубликатами).

        """
        if not campaign_ids:
            return []

        all_urls: List[str] = []
        chunk_size = 10
        for i in range(0, len(campaign_ids), chunk_size):
            chunk = campaign_ids[i : i + chunk_size]
            ads = await yandex_auth.get_ads_data(token, client_login, chunk)

            sitelink_ids: List[int] = []
            for ad in ads:
                text_ad = ad.get('TextAd')
                if text_ad and text_ad.get('Href'):
                    all_urls.append(text_ad['Href'])

                s_id = text_ad.get('SitelinkSetId') if text_ad else None
                if s_id:
                    sitelink_ids.append(s_id)

            if sitelink_ids:
                sitelinks_data = await yandex_auth.get_sitelinks_hrefs(
                    token,
                    client_login,
                    list(set(sitelink_ids)),
                )
                for set_item in sitelinks_data:
                    for link in set_item.get('Sitelinks', []):
                        if link.get('Href'):
                            all_urls.append(link['Href'])

        return all_urls

    async def check_urls_and_generate_report(
        self, urls: List[str], report_title: str
    ) -> str:
        """Проверяет URL и формирует текстовый отчёт.

        Запускает параллельную проверку через
        UrlCheckerService. В отчёт включает только
        первые 15 нерабочих ссылок.

        Args:
            urls: Список URL для проверки.
            report_title: Заголовок отчёта.

        Returns:
            Форматированная строка отчёта в Markdown.

        """
        if not urls:
            return f'{report_title}: Ссылок не найдено.'

        results = await self.checker.check_list_of_urls(urls)

        bad_links = [r for r in results if not r['is_ok']]
        total_checked = len(results)

        report = f'📊 **{report_title}**\n'
        report += f'Проверено уникальных ссылок: {total_checked}\n'

        if not bad_links:
            report += '✅ Все ссылки доступны (200 OK).'
        else:
            report += f'❌ Найдено ошибок: {len(bad_links)}\n\n'
            for link in bad_links[:15]:
                report += f'• {link["url"]} — Статус: {link["status"]}\n'

            if len(bad_links) > 15:
                report += f'\n...и еще {len(bad_links) - 15} ошибок.'

        return report

    async def check_specific_campaigns(
        self,
        login: str,
        subclient_login: str,
        campaign_ids: List[int],
    ) -> str:
        """Проверяет только выбранные кампании клиента.

        Args:
            login: Логин основного аккаунта (владельца токена).
            subclient_login: Логин клиента, чьи кампании
                             проверяются.
            campaign_ids: Список ID кампаний для проверки.

        Returns:
            Текстовый отчёт в формате Markdown.

        """
        user = await user_repository.get_user_by_login(self.db, login)
        if not user:
            return f'Аккаунт {login} не найден в базе.'

        token = user.token
        all_urls = await self.get_urls_from_campaigns(
            token, subclient_login, campaign_ids
        )
        title = (
            f'Отчет для {subclient_login}'
            if login != subclient_login
            else f'Отчет для {login}'
        )
        return await self.check_urls_and_generate_report(all_urls, title)

    async def check_all_for_subclient(
        self, login: str, subclient_login: str
    ) -> str:
        """Проверяет все активные кампании субклиента.

        Args:
            login: Логин основного аккаунта (владельца токена).
            subclient_login: Логин клиента для проверки.

        Returns:
            Текстовый отчёт в формате Markdown.

        """
        user = await user_repository.get_user_by_login(self.db, login)
        if not user:
            return f'Аккаунт {login} не найден в базе.'

        token = user.token
        campaigns = await yandex_auth.get_active_campaigns(
            token, subclient_login
        )
        camp_ids = [c['Id'] for c in campaigns]

        all_urls = await self.get_urls_from_campaigns(
            token, subclient_login, camp_ids
        )
        title = (
            f'Отчет для {subclient_login}'
            if login != subclient_login
            else f'Отчет для {login}'
        )
        return await self.check_urls_and_generate_report(all_urls, title)

    async def check_all_agency_clients(self, login: str) -> str:
        """Проверяет всех активных субклиентов агентства.

        Собирает URL по всем субклиентам и кампаниям
        и возвращает единый сводный отчёт.

        Args:
            login: Логин аккаунта агентства.

        Returns:
            Сводный текстовый отчёт в формате Markdown.

        """
        user = await user_repository.get_user_by_login(self.db, login)
        if not user:
            return f'Аккаунт {login} не найден в базе.'

        token = user.token
        subclients = await yandex_auth.get_agency_clients(token, login)

        if not subclients:
            return f'Агентство {login}: активных клиентов не найдено.'

        all_urls: List[str] = []
        for sub_login in subclients:
            campaigns = await yandex_auth.get_active_campaigns(
                token, sub_login
            )
            camp_ids = [c['Id'] for c in campaigns]
            urls = await self.get_urls_from_campaigns(
                token, sub_login, camp_ids
            )
            all_urls.extend(urls)

        title = f'Сводный отчет для агентства {login}'
        return await self.check_urls_and_generate_report(all_urls, title)


# Глобальный экземпляр для переиспользования лимита
url_checker = UrlCheckerService(limit=15)
