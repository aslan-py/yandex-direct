"""
Получение Токена и Логина пользователя.

Сначала генерируем ссылку для получения верификанционого кода от Яндекс.
Копируем код вносим (к примеру через тг бот)
Время действия токена примено год(эта величина может меняться).
По токену получаем логин пользователя.
Токен и логин сохраняем в БД sqlite3.
Использовал документацию https://yandex.ru/dev/id/doc/ru/codes/code-url#code и
https://yandex.ru/dev/id/doc/ru/user-information.
"""
import requests
import sqlite3

from support_methods import logger

from constants import (
    CLIENT_ID, CLIENT_SECRET, REDIRECT_URL, USER_INFO_URL,
    AUTH_URL, TOKEN_URL
)


def check_services_availability() -> tuple[bool, str]:
    """Проверяет доступность сервисов Яндекса."""
    try:
        response1 = requests.get(REDIRECT_URL, timeout=10)
        response2 = requests.get(AUTH_URL, timeout=10)
        if response1.status_code != 200 or response2.status_code != 200:
            return False, f'Недоступны сыслки {REDIRECT_URL} либо {AUTH_URL}'
        return True, '✅ Сервисы Яндекса доступны'
    except Exception as error:
        return False, f'Сбой при проверке сервисов: {error}'


def get_auth_link() -> tuple[bool, str]:
    """Возвращает ссылку для авторизации"""
    try:
        params = {
            'response_type': 'code',
            'client_id': CLIENT_ID,
            'redirect_uri': REDIRECT_URL,
            'force_confirm': 'yes'
        }

        from urllib.parse import urlencode
        query_string = urlencode(params)
        auth_link = f'{AUTH_URL}?{query_string}'

        return True, auth_link
    except Exception as error:
        return False, f'Ошибка формирования ссылки: {error}'


def get_token_data(auth_code: str) -> tuple[bool, str]:
    """Получает данные токена по коду верификации."""
    if not auth_code:
        return False, 'Не получен код верификации'

    try:
        data = {
            'grant_type': 'authorization_code',
            'code': auth_code,
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'redirect_uri': REDIRECT_URL
        }

        response = requests.post(TOKEN_URL, data=data, timeout=30)
        response.raise_for_status()
        token_data = response.json()

        if not token_data.get('access_token'):
            return False, 'Ответ API не содержит токена'
        return True, token_data['access_token']

    except requests.exceptions.HTTPError as e:
        return False, f'Ошибка HTTP: {e}'
    except Exception as e:
        return False, f'Неожиданная ошибка: {e}'


def get_user_login(token: str) -> tuple[bool, str]:
    """Получает логин пользователя по токену."""
    if not token:
        return False, 'Не получен токен'

    try:
        response = requests.get(
            USER_INFO_URL,
            headers={'Authorization': f'OAuth {token}'},
            params={'format': 'json'},
            timeout=30
        )
        response.raise_for_status()
        user_info = response.json()

        login_info = user_info.get('login')
        if not login_info:
            return False, 'Ответ API не содержит логина пользователя'

        logger.debug(f"Логин пользователя получен: {login_info}")
        return True, user_info['login']

    except requests.exceptions.HTTPError as e:
        return False, f'Ошибка HTTP: {e}'
    except Exception as e:
        return False, f'Ошибка при получении логина: {e}'


def save_to_database(login, token) -> tuple[bool, str]:
    """Сохраняет или обновляет данные пользователя в базе."""
    if not login or not token:
        return False, 'Недостаточно данных для сохранения в базу'

    try:
        con = sqlite3.connect('direct.sqlite')
        cur = con.cursor()

        cur.execute('SELECT id FROM logins_tokens WHERE login = ?', (login,))
        existing_user = cur.fetchone()

        if existing_user:
            cur.execute(
                'UPDATE logins_tokens SET token = ? WHERE login = ?',
                (token, login)
            )
            message = f'Данные для {login} обновлены.'
        else:
            cur.execute(
                'INSERT INTO logins_tokens (login, token) VALUES (?, ?)',
                (login, token)
            )
            message = f'Пользователь {login} добавлен в базу.'

        con.commit()
        con.close()
        return True, message

    except sqlite3.Error as e:
        return False, f'Ошибка БД: {e}'
