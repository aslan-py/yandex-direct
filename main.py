"""
Telegram бот для проверки Яндекс.Директа

Основное назначение:
Telegram бот для автоматической проверки работоспособности ссылок
в рекламных объявлениях Яндекс.Директ.
Ссылка считается рабочей если её статус = 20. Бот предоставляет интерфейс
для управления проверками через чат Telegram.

Функциональные возможности:
- Авторизация пользователей через OAuth Яндекс
- Запуск комплексной проверки объявлений
- Управление базой данных с токенами
- Генерация отчетов о проверке
- Интерактивное взаимодействие через кнопки

Архитектура бота:
1. Командный интерфейс - обработка команд /start, /login, /go, /delete
2. Конечный автомат - управление состояниями пользователя (auth_states)
3. Интеграция с API - взаимодействие с Яндекс.Директ через support_methods
4. Управление базой данных - работа с SQLite через token_and_login

Основные команды:
/start  - начало работы, приветственное сообщение
/login  - процесс авторизации в Яндекс.Директе
/go     - запуск комплексной проверки объявлений
/delete - удаление базы данных (очистка)

Процесс проверки (команда /go):
1. Загрузка пользователей из базы данных
2. Получение списка кампаний для каждого пользователя
3. Сбор данных об объявлениях активных кампаний
4. Получение информации о быстрых ссылках
5. Проверка работоспособности всех URL-адресов
6. Формирование и отправка отчета

Состояния пользователя (auth_states):
- waiting_code: ожидание кода подтверждения OAuth
- waiting_delete_confirmation: ожидание подтверждения удаления базы

Зависимости:
- telebot: библиотека для работы с Telegram Bot API
- support_methods: модуль для работы с API Яндекс.Директ
- token_and_login: модуль для OAuth авторизации и работы с БД
- constants: конфигурационные константы и настройки

Особенности реализации:
- Поддержка длительных операций (проверка может занимать несколько минут)
- Обработка больших отчетов (разбивка на части при превышении лимита Telegram)
- Интерактивные клавиатуры для подтверждения действий
- Логирование всех операций для отладки
- Обработка ошибок с уведомлением пользователя

Безопасность:
- Токены хранятся в локальной SQLite базе данных
- OAuth авторизация через официальный API Яндекс
- Нет хранения чувствительных данных в открытом виде

Требования:
- Python 3.12.7
- Библиотеки: pyTelegramBotAPI, requests, sqlite3
- Действующий токен Telegram бота
- OAuth приложение в Яндекс.Директе

Переменные окружения (через .env):
- TELEGRAM_BOT_TOKEN: токен бота от BotFather
- CLIENT_ID: OAuth client_id от Яндекс
- CLIENT_SECRET: OAuth client_secret от Яндекс

Автор: [Лигус Аслан]
Версия: 1.0
Дата создания: [2025.09.24]
"""
import time
import os
import sqlite3

from telebot import types, TeleBot

from support_methods import (
    get_all_logins_and_tokens, initialize_database,
    get_api_response, check_response, parse_companies_response,
    get_ads_api_response, parse_ads_response, get_sitelinks_api_response,
    parse_sitelinks_response, check_url_status, logger
)
from constants import TELEGRAM_BOT_TOKEN

from token_and_login import (
    check_services_availability, get_auth_link,
    get_token_data, get_user_login, save_to_database
)

# Инициализация бота
bot = TeleBot(TELEGRAM_BOT_TOKEN)

# Словарь для хранения состояния авторизации пользователей
auth_states = {}


def run_direct_check(chat_id):
    """Запускает весь процесс проверки Директа и возвращает отчет"""
    try:
        DB = {}

        #  0.Распаковка БД - direct.sqlite и создали словарь DB.
        status, message = get_all_logins_and_tokens(DB)
        if not status:
            bot.send_message(chat_id, f"❌ {message}")
            return message

        #  1.Получаем компании,проверяем компании и парсим их в словрь DB.
        successful_users = 0
        for login, user_data in list(DB.items()):
            token = user_data.get('token_info')
            if not token:
                msg = f'❌ У пользователя {login} отсутствует токен'
                bot.send_message(chat_id, msg)
                del DB[login]
                continue
            response = get_api_response(token, login)
            status, message = check_response(response, login, 'компаний')
            if not status:
                bot.send_message(chat_id, f'❌ {login}: {message}')
                del DB[login]
                continue
            status, message = parse_companies_response(response, login, DB)
            if not status:
                bot.send_message(chat_id, f'❌ {message}')
                del DB[login]
                continue
            else:
                successful_users += 1
            # Итог первого этапа
            if successful_users == 0:
                bot.send_message(
                    chat_id,
                    '❌ Нет пользователей директа, проверку завершаю.'
                )
                return 'Проверка остановлена: нет данных для продолжения'

        # 2. ВТОРОЙ ЦИКЛ: Получаем объявления,проверяем  и парсим  в словрь DB.
        successful_ads_users = 0

        for login, user_data in list(DB.items()):
            token = user_data.get('token_info')
            campaign_ids = user_data.get('company_id', [])
            if not campaign_ids:
                msg = (
                    f'⚠️ У пользователя {login} нет кампаний для '
                    f' проверки объявлений'
                )
                bot.send_message(chat_id, msg)
                continue
            ads_response = get_ads_api_response(token, login, campaign_ids)
            status, message = check_response(ads_response, login, 'объявлений')
            if not status:
                bot.send_message(chat_id, f'❌ {login}: {message}')
                continue
            status, message = parse_ads_response(ads_response, login, DB)
            if not status:
                bot.send_message(chat_id, f'❌ {login}: {message}')
            else:
                successful_ads_users += 1

        # Итог третьего этапа
        if successful_ads_users == 0:
            bot.send_message(
                chat_id,
                '❌ Не удалось получить объявления ни у одного пользователя'
            )
            return 'Проверка остановлена: нет объявлений для проверки'

        # 3.ТРЕТИЙ ЦИКЛ:Получаем быстрые ссылик,проверяем и парсим в словрь DB.
        successful_sitelinks_users = 0

        for login, user_data in list(DB.items()):
            token = user_data.get('token_info')
            sitelink_ids = user_data.get('sitelinks_id', [])
            if not sitelink_ids:
                msg = f'⚠️ У пользователя {login} нет быстрых ссылок'
                bot.send_message(chat_id, msg)
                continue

            sitelink_response = get_sitelinks_api_response(
                    token, login, sitelink_ids)
            status, message = check_response(
                    sitelink_response, login, 'быстрых ссылок')
            if not status:
                bot.send_message(
                    chat_id,
                    f'❌ {login}: Ошибка быстрой ссылки {message}')
                continue

            status, message = parse_sitelinks_response(
                    sitelink_response, login, DB)
            if not status:
                bot.send_message(chat_id, f' - {message}')
            else:
                successful_sitelinks_users += 1

        # Итог третьего этапа
        if successful_sitelinks_users == 0:
            bot.send_message(
                chat_id,
                '⚠️ Не получили быстрые ссылки ни у одного пользователя')

        # 5. ЧЕТВЕРТЫЙ ЦИКЛ: Проверяем обычные ссылки и отдельно -  быстрые.
        total_reports = []
        for login, user_data in list(DB.items()):
            user_report = f"\n=== ОТЧЕТ ДЛЯ {login} ===\n"

            #  Сначала обычные.
            ads_urls = user_data.get('adds_href', [])
            if ads_urls:
                ads_report = check_url_status(ads_urls, login, DB, 'ad')
                if ads_report:
                    user_report += f'\n📊 ОБЪЯВЛЕНИЯ:\n{ads_report}\n'
            else:
                bot.send_message(
                    chat_id,
                    f'ℹ️ У {login} нет ссылок объявлений для проверки')

            #  Теперь быстрые.
            sitelinks_urls = user_data.get('sitelinks_href', [])
            if sitelinks_urls:
                sitelinks_report = check_url_status(
                    sitelinks_urls, login, DB, 'sitelink')
                if sitelinks_report:
                    user_report += (
                        f'\n⚡ БЫСТРЫЕ ССЫЛКИ:\n{sitelinks_report}\n')
            else:
                bot.send_message(
                    chat_id,
                    f'ℹ️ У {login} нет быстрых ссылок для проверки')
            total_reports.append(user_report)

        # ФИНАЛ
        final_report = "🎉 ПРОВЕРКА ЗАВЕРШЕНА!\n\n" + "\n".join(total_reports)
        if len(final_report) > 4000:
            # Разбиваем на части
            parts = []
            current_part = ""
            for line in final_report.split('\n'):
                if len(current_part + line + '\n') > 4000:
                    parts.append(current_part)
                    current_part = line + '\n'
                else:
                    current_part += line + '\n'
            if current_part:
                parts.append(current_part)
            return parts
        else:
            return final_report

    except Exception as e:
        error_msg = f'❌ Критическая ошибка при выполнении проверки: {str(e)}'
        logger.exception(error_msg)
        bot.send_message(chat_id, error_msg)
        return error_msg


@bot.message_handler(commands=['start'])
def send_welcome(message):
    """Обработчик команды /start"""
    try:
        user_id = message.chat.id
        username = message.chat.username
        logger.debug(f'Команда /start от пользователя {username}')

        welcome_text = (
            "👋 Привет! Я бот для проверки Яндекс.Директа.\n"
            "📊 Я могу проверить статус всех ссылок в ваших объявлениях.\n"
            "🔐 Для авторизации используйте /login\n"
            "🚀 Для запуска проверки используйте команду /go\n"
            "🗑️ Для очистки базы используйте /delete\n"
        )
        bot.send_message(user_id, welcome_text)
        logger.info(f'Отправлено приветствие пользователю {user_id}')

    except Exception as e:
        logger.exception(f'Ошибка в send_welcome: {e}')
        bot.send_message(message.chat.id, '❌ Произошла ошибка команды start')


@bot.message_handler(commands=['login'])
def start_login(message):
    """Начинает процесс авторизации"""
    try:
        user_id = message.chat.id
        username = message.chat.username
        logger.debug(f'Запуск авторизации для пользователя {user_id}')

        # Проверяем доступность сервисов для получения токена.
        success, result = check_services_availability()
        if not success:
            logger.error(f'Ошибка: {result}')
            bot.send_message(user_id, '❌ {result}')
            return
        logger.debug(result)

        # Получаем ссылку для авторизации
        success, auth_link = get_auth_link()
        if not success:
            logger.error(f'Ошибка формирования ссылки: {auth_link}')
            bot.send_message(user_id, '❌ Ошибка формирования ссылки')
            return
        logger.debug('Ссылка для авторизации сформирована')

        # Сохраняем состояние пользователя
        auth_states[user_id] = {'step': 'waiting_code'}
        logger.debug(
            f'Состояние пользователя {username} установлено: waiting_code')

        # Создаем inline-кнопку
        markup = types.InlineKeyboardMarkup()
        auth_button = types.InlineKeyboardButton(
            '🔐 Авторизоваться в Яндекс', url=auth_link)

        markup.add(auth_button)

        # Отправляем сообщение с кнопкой
        login_text = (
            "🔐 Процесс авторизации:\n\n"
            "1. Нажми кнопку ниже для авторизации\n"
            "2. Согласись на добавление приложения kitty_asla\n"
            "3. Скопируй код подтверждения\n"
            "4. Отправь его мне в ответном сообщении"
        )

        bot.send_message(user_id, login_text, reply_markup=markup)
        bot.send_message(
            user_id, '📋 После авторизации пришли мне код подтверждения:')
        logger.info(
            f'Пользователю {username} отправлена ссылка для авторизации')

    except Exception as e:
        logger.exception(f'Ошибка в start_login: {e}')
        bot.send_message(
            message.chat.id, '❌ Произошла ошибка при запуске авторизации')


@bot.message_handler(
        func=lambda message: message.chat.id in auth_states
        and auth_states[message.chat.id]['step'] == 'waiting_code'
        )
def handle_auth_code(message):
    """Обрабатывает код подтверждения от пользователя"""
    try:
        user_id = message.chat.id
        auth_code = message.text.strip()
        username = message.chat.username
        logger.debug(f'Получен код подтверждения от пользователя {username}')

        bot.send_message(user_id, '🔄 Обрабатываю код подтверждения...')

        # Получаем токен
        success, result = get_token_data(auth_code)
        if not success:
            logger.error(
                f'Ошибка получения токена  {username}: {result}')
            bot.send_message(user_id, f'❌ Ошибка получения токена: {result}')
            del auth_states[user_id]
            return

        logger.debug(f'Токен успешно получен для пользователя {username}')
        token = result

        # Получаем логин
        success, result = get_user_login(token)
        if not success:
            logger.error(
                f'Ошибка получения логина {username}: {result}')
            bot.send_message(user_id, f"❌ Ошибка получения логина: {result}")
            del auth_states[user_id]
            return

        logger.debug(f"Логин успешно получен для пользователя {username}")
        login = result

        # Сохраняем в базу
        success, result = save_to_database(login, token)
        if not success:
            logger.error(
                f'Ошибка сохранения в БД для пользователя {login}: {result}')
            bot.send_message(user_id, f'❌ Ошибка сохранения: {result}')
        else:
            logger.info(f'Данные пользователя {login} успешно сохранены в БД')

        # Завершаем процесс авторизации
        del auth_states[user_id]
        logger.info(f'Авторизация успешно завершена для пользователя {login}')
        bot.send_message(
            user_id, '🎉 Авторизация завершена успешно! '
            'Теперь можно использовать /go для проверки'
        )

    except Exception as e:
        logger.exception(f'Ошибка в handle_auth_code: {e}')
        bot.send_message(
            message.chat.id, '❌ Произошла ошибка при обработке кода')
        if message.chat.id in auth_states:
            del auth_states[message.chat.id]


@bot.message_handler(commands=['go'])
def start_check(message):
    """Обработчик команды /go - запускает проверку"""
    try:
        user_id = message.chat.id
        username = message.chat.username
        logger.info(f'Запуск проверки Директа для пользователя {username}')

        bot.send_message(
            user_id,
            '🔄 Запускаю проверку Яндекс.Директа...\n'
            '⏱ Это может занять несколько минут.\n'
            '📊 Я пришлю отчет по завершении.'
        )

        report = run_direct_check(user_id)

        # Отправляем финальный отчет
        if isinstance(report, list):
            # Если отчет разбит на части
            for i, part in enumerate(report, 1):
                if i == 1:
                    part = '📋 ФИНАЛЬНЫЙ ОТЧЕТ:\n\n' + part
                bot.send_message(user_id, part)
                time.sleep(1)  # Чтобы не превысить лимиты Telegram
        else:
            # Если отчет одной частью
            bot.send_message(user_id, f'📋 ФИНАЛЬНЫЙ ОТЧЕТ:\n\n{report}')

        logger.info(f'Проверка завершена для пользователя {username}')

    except Exception as e:
        logger.exception(f'Ошибка в start_check: {e}')
        bot.send_message(
            message.chat.id, '❌ Произошла ошибка при выполнении проверки')


@bot.message_handler(commands=['delete'])
def delete_database(message):
    """Удаляет базу данных для начала с чистого листа"""
    try:
        user_id = message.chat.id
        username = message.chat.username

        # Создаем клавиатуру с подтверждением
        markup = types.ReplyKeyboardMarkup(
            resize_keyboard=True,
            one_time_keyboard=True
        )
        markup.add('✅ Да, удалить базу', '❌ Нет, отменить')

        # Сохраняем состояние ожидания подтверждения
        auth_states[user_id] = {'step': 'waiting_delete_confirmation'}

        # Проверяем существование базы
        db_exists = os.path.exists('direct.sqlite')

        message_text = (
            '⚠️ **ВНИМАНИЕ!**\n\n'
            'Вы действительно хотите удалить базу данных?\n\n'
        )

        if db_exists:
            message_text += (
                '🗑️ Это удалит ВСЕ сохраненные токены и настройки.\n')
        else:
            message_text += 'ℹ️ База данных в данный момент не существует.\n'

        message_text += (
            '🔁 После удаления нужно будет снова авторизоваться '
            'через /login\n\nВыберите действие:'
            )

        bot.send_message(user_id, message_text, reply_markup=markup)
        logger.info(
            f'Пользователь {username} запросил удаление базы данных. '
            f'База существует: {db_exists}'
        )

    except Exception as e:
        logger.exception(f'Ошибка в delete_database: {e}')
        bot.send_message(user_id, '❌ Ошибка при запросе удаления базы')


@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    """Обработчик всех сообщений"""
    try:
        user_id = message.chat.id
        username = message.chat.username
        text = message.text

        # Проверяем состояние пользователя
        if user_id in auth_states:
            state = auth_states[user_id].get('step')

            if state == 'waiting_delete_confirmation':
                # Обрабатываем подтверждение удаления
                choice = text.strip()
                db_exists = os.path.exists('direct.sqlite')

                # Удаляем состояние
                del auth_states[user_id]

                # Убираем клавиатуру
                markup = types.ReplyKeyboardRemove()

                if choice == '✅ Да, удалить базу':
                    if db_exists:
                        try:
                            sqlite3.connect('direct.sqlite').close()
                            os.remove('direct.sqlite')
                            bot.send_message(
                                user_id,
                                '✅ База данных успешно удалена!\n\n'
                                '🗂️ Теперь вы можете начать с чистого листа.\n'
                                '🔐 Для добавления аккаунта используйте /login',
                                reply_markup=markup
                            )
                            logger.info(
                                f'База данных удалена по запросу пользователя '
                                f'{username}'
                            )
                        except Exception as e:
                            bot.send_message(
                                user_id,
                                f'❌ Ошибка при удалении базы: {e}',
                                reply_markup=markup
                            )
                            logger.error(
                                f'Ошибка удаления базы для {username}: {e}')
                    else:
                        bot.send_message(
                            user_id,
                            'ℹ️ База данных уже была удалена ранее',
                            reply_markup=markup
                        )
                        logger.info(
                            f'Пользователь {username} пытался удалить '
                            f'несуществующую базу'
                        )

                elif choice == '❌ Нет, отменить':
                    bot.send_message(
                        user_id,
                        '❌ Удаление базы данных отменено',
                        reply_markup=markup
                    )
                    logger.info(
                        f'Пользователь {username} отменил удаление базы данных'
                    )
                else:
                    bot.send_message(
                        user_id,
                        ('❌ Неверный выбор. '
                            'Используйте кнопки для подтверждения'),
                        reply_markup=markup
                    )
                return

            elif state == 'waiting_code':
                # Это сообщение должно обработаться handle_auth_code
                return

        # Если не обработано выше - стандартная обработка команд
        if text and text.startswith('/'):
            if text == '/start':
                send_welcome(message)
            elif text == '/login':
                start_login(message)
            elif text == '/go':
                start_check(message)
            elif text == '/delete':
                delete_database(message)
            else:
                bot.send_message(
                    user_id, '🤖 Неизвестная команда. Используйте /start')
        else:
            bot.send_message(
                user_id, '🤖 Я не понимаю эту команду. Используйте /start')

    except Exception as e:
        logger.exception(f'Ошибка в handle_all_messages: {e}')
        bot.send_message(user_id, '❌ Произошла ошибка')


if __name__ == '__main__':
    try:
        logger.info('🚀 Запуск Telegram бота для проверки Яндекс.Директа')
        print('Бот запущен! Остановите его сочетанием клавиш Ctrl+C')

        # Инициализация базы данных
        if initialize_database():
            print('✅ База данных инициализирована')
        else:
            print('⚠️ Предупреждение: проблемы с базой данных')

        print('🟢 Бот запущен и ожидает сообщений...')
        print('💡 Напишите /start в Telegram для начала работы')

        # Запуск бота
        bot.infinity_polling(timeout=60, long_polling_timeout=60)

    except KeyboardInterrupt:
        print('\n🛑 Бот остановлен пользователем')
        logger.info('Бот остановлен по команде пользователя')
    except Exception as e:
        logger.exception(f'Критическая ошибка при запуске бота: {e}')
        print(f'❌ Критическая ошибка: {e}')
