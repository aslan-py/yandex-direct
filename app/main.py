import asyncio
import threading

import telebot
from loguru import logger
from telebot import types

from app.constants import TELEGRAM_BOT_TOKEN, BotMessages
from app.crud import user_repository
from app.db import async_session_factory, init_models
from app.loguru_config import setup_logging
from app.redis_config import redis_client
from app.service import DirectService
from app.yandex_config import yandex_auth

setup_logging()

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
loop = asyncio.new_event_loop()


def _start_background_loop(l: asyncio.AbstractEventLoop) -> None:
    """Запускает бесконечный цикл событий asyncio в отдельном потоке.

    Args:
        l: Экземпляр цикла событий (Event Loop).
    """
    asyncio.set_event_loop(l)
    l.run_forever()


threading.Thread(
    target=_start_background_loop, args=(loop,), daemon=True
).start()


def run_async(coro):
    """Выполняет асинхронную корутину в фоновом цикле событий и ждет результат.

    Args:
        coro: Корутина для выполнения.

    Returns:
        Результат выполнения корутины.
    """
    return asyncio.run_coroutine_threadsafe(coro, loop).result()


def track_message(chat_id: int, message_id: int):
    """Сохраняет ID сообщения в Redis для последующей очистки истории чата.

    Args:
        chat_id: ID чата Telegram.
        message_id: ID сообщения.
    """
    try:
        run_async(redis_client.lpush(f'messages:{chat_id}', message_id))
    except Exception as e:
        logger.error(f'Error tracking message: {e}')


def send_tracked_message(chat_id: int, text: str, reply_markup=None, **kwargs):
    """Отправляет сообщение и регистрирует его ID в Redis для отслеживания.

    Args:
        chat_id: ID чата Telegram.
        text: Текст сообщения.
        reply_markup: Клавиатура (опционально).
        **kwargs: Дополнительные параметры telebot.send_message.

    Returns:
        Объект отправленного сообщения.
    """
    msg = bot.send_message(chat_id, text, reply_markup=reply_markup, **kwargs)
    track_message(chat_id, msg.message_id)
    return msg


@bot.message_handler(commands=['start', 'help', 'menu'])
def start_help(message: types.Message) -> None:
    """Обработчик команд старта, помощи и вызова меню.

    Args:
        message: Объект сообщения от пользователя.
    """
    track_message(message.chat.id, message.message_id)
    show_main_menu(message.chat.id)


def show_main_menu(chat_id: int):
    """Отображает главное меню бота в виде Inline-кнопок.

    Args:
        chat_id: ID чата Telegram.
    """
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(
            BotMessages.MENU_CHECK, callback_data='menu:check'
        ),
        types.InlineKeyboardButton(
            BotMessages.MENU_LOGIN, callback_data='menu:login'
        ),
        types.InlineKeyboardButton(
            BotMessages.MENU_DELETE, callback_data='menu:delete'
        ),
        types.InlineKeyboardButton(
            BotMessages.MENU_CLEAR, callback_data='menu:clear'
        ),
    )
    send_tracked_message(
        chat_id,
        BotMessages.HELP_TEXT,
        reply_markup=markup,
        parse_mode='Markdown',
    )


@bot.message_handler(commands=['login'])
def cmd_login(message: types.Message) -> None:
    """Обработчик прямой команды /login.

    Args:
        message: Объект сообщения от пользователя.
    """
    track_message(message.chat.id, message.message_id)
    handle_login(message.chat.id)


def handle_login(chat_id: int):
    """Инициирует процесс OAuth-авторизации, отправляя ссылку пользователю.

    Args:
        chat_id: ID чата Telegram.
    """
    auth_link = yandex_auth.get_link()
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton(BotMessages.LOGIN_BTN, url=auth_link)
    )
    msg = send_tracked_message(
        chat_id, BotMessages.LOGIN_START, reply_markup=markup
    )
    bot.register_next_step_handler(msg, save_user_token)


def save_user_token(message: types.Message) -> None:
    """Принимает код авторизации и регистрирует пользователя в системе.

    Args:
        message: Объект сообщения, содержащий код.
    """
    track_message(message.chat.id, message.message_id)
    if not message.text:
        return
    code = message.text.strip()

    async def process_registration() -> str:
        async with async_session_factory() as session:
            service = DirectService(session)
            return await service.register_user_by_code(code)

    try:
        login_name = run_async(process_registration())
        send_tracked_message(
            message.chat.id,
            BotMessages.LOGIN_SUCCESS.format(login_name),
            parse_mode='Markdown',
        )
        show_main_menu(message.chat.id)
    except Exception as e:
        logger.error(f'Ошибка регистрации: {e}')
        send_tracked_message(
            message.chat.id, BotMessages.LOGIN_ERROR.format(e)
        )
        show_main_menu(message.chat.id)


@bot.message_handler(commands=['clear'])
def cmd_clear(message: types.Message) -> None:
    """Обработчик прямой команды /clear.

    Args:
        message: Объект сообщения от пользователя.
    """
    track_message(message.chat.id, message.message_id)
    handle_clear(message.chat.id)


def handle_clear(chat_id: int):
    """Удаляет все сообщения бота, ID которых были сохранены в Redis.

    Args:
        chat_id: ID чата Telegram.
    """
    async def do_clear():
        msg_ids = await redis_client.lrange(f'messages:{chat_id}', 0, -1)
        logger.debug(
            f'Found {len(msg_ids)} messages to clear for chat {chat_id}'
        )
        for mid in msg_ids:
            try:
                msg_id_val = (
                    mid.decode('utf-8') if isinstance(mid, bytes) else str(mid)
                )
                msg_id_int = int(msg_id_val)
                bot.delete_message(chat_id, msg_id_int)
                logger.debug(f'Deleted message {msg_id_int}')
            except Exception as e:
                logger.debug(f'Failed to delete message {mid}: {e}')
        await redis_client.delete(f'messages:{chat_id}')

    run_async(do_clear())
    msg = bot.send_message(chat_id, BotMessages.CLEAR_SUCCESS)
    track_message(chat_id, msg.message_id)
    show_main_menu(chat_id)


@bot.callback_query_handler(func=lambda call: call.data.startswith('menu:'))
def menu_callback(call: types.CallbackQuery):
    """Маршрутизатор для действий главного меню.

    Args:
        call: Объект обратного вызова (Callback Query).
    """
    action = call.data.split(':')[1]
    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass

    if action == 'login':
        handle_login(call.message.chat.id)
    elif action == 'clear':
        handle_clear(call.message.chat.id)
    elif action == 'delete':
        show_delete_menu(call.message.chat.id)
    elif action == 'check':
        show_accounts_for_check(call.message.chat.id)


def show_delete_menu(chat_id: int):
    """Отображает список подключенных аккаунтов для их удаления.

    Args:
        chat_id: ID чата Telegram.
    """
    async def get_users() -> list[str]:
        async with async_session_factory() as session:
            return await user_repository.get_all_logins(session)

    logins = run_async(get_users())
    if not logins:
        send_tracked_message(chat_id, BotMessages.DELETE_EMPTY)
        show_main_menu(chat_id)
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    for login_name in logins:
        markup.add(
            types.InlineKeyboardButton(
                BotMessages.DELETE_BTN.format(login_name),
                callback_data=f'del_confirm:{login_name}',
            )
        )
    markup.add(
        types.InlineKeyboardButton(
            BotMessages.BACK_BTN, callback_data='back:menu'
        )
    )

    send_tracked_message(
        chat_id, BotMessages.DELETE_CHOOSE, reply_markup=markup
    )


@bot.callback_query_handler(
    func=lambda call: call.data.startswith('del_confirm:')
)
def confirm_delete(call: types.CallbackQuery) -> None:
    """Выполняет удаление аккаунта после подтверждения пользователем.

    Args:
        call: Объект обратного вызова (Callback Query).
    """
    login_name = call.data.split(':')[1]

    async def delete_user() -> None:
        async with async_session_factory() as session:
            service = DirectService(session)
            await service.delete_user_by_login(login_name)

    try:
        run_async(delete_user())
        bot.edit_message_text(
            BotMessages.DELETE_CONFIRM.format(login_name),
            call.message.chat.id,
            call.message.message_id,
            parse_mode='Markdown',
        )
        show_main_menu(call.message.chat.id)
    except Exception as e:
        logger.error(f'Ошибка подтверждения удаления: {e}')
        bot.answer_callback_query(call.id, BotMessages.DELETE_ERROR.format(e))


def show_accounts_for_check(chat_id: int):
    """Показывает список всех аккаунтов для запуска проверки ссылок.

    Args:
        chat_id: ID чата Telegram.
    """
    async def get_users() -> list[str]:
        async with async_session_factory() as session:
            return await user_repository.get_all_logins(session)

    logins = run_async(get_users())
    if not logins:
        send_tracked_message(chat_id, BotMessages.CHECK_NO_ACCOUNTS)
        show_main_menu(chat_id)
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(
            '🌐 Проверить все аккаунты', callback_data='run_all_accounts'
        )
    )
    for login_name in logins:
        markup.add(
            types.InlineKeyboardButton(
                f'👤 {login_name}', callback_data=f'chk_acc:{login_name}'
            )
        )
    markup.add(
        types.InlineKeyboardButton(
            BotMessages.BACK_BTN, callback_data='back:menu'
        )
    )

    send_tracked_message(
        chat_id, BotMessages.CHOOSE_ACCOUNT, reply_markup=markup
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith('chk_acc:'))
def check_account_selected(call: types.CallbackQuery):
    """Определяет роль выбранного аккаунта и переходит к выбору клиентов или кампаний.

    Args:
        call: Объект обратного вызова (Callback Query).
    """
    logger.debug(f'chk_acc triggered with: {call.data}')
    login = call.data.split(':')[1]
    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass
    bot.edit_message_reply_markup(
        call.message.chat.id, call.message.message_id, reply_markup=None
    )

    async def check_role_and_next():
        async with async_session_factory() as session:
            user = await user_repository.get_user_by_login(session, login)
            if not user:
                return 'error'
            role = await yandex_auth.get_user_role(user.token, login)
            return role

    role = run_async(check_role_and_next())
    if role == 'error':
        send_tracked_message(call.message.chat.id, 'Аккаунт не найден.')
        return

    if role == 'AGENCY':
        show_subclients(call.message.chat.id, login, page=0)
    else:
        show_campaigns(call.message.chat.id, login, login, page=0)


def show_subclients(chat_id: int, login: str, page: int):
    """Отображает список субклиентов агентского аккаунта с пагинацией.

    Args:
        chat_id: ID чата Telegram.
        login: Логин агентства.
        page: Текущая страница.
    """
    async def get_subs():
        async with async_session_factory() as session:
            user = await user_repository.get_user_by_login(session, login)
            return await yandex_auth.get_agency_clients(user.token, login)

    send_tracked_message(chat_id, '⏳ Получаю список клиентов...')
    subs = run_async(get_subs())

    if not subs:
        send_tracked_message(
            chat_id, f'У агентства {login} нет активных клиентов.'
        )
        show_main_menu(chat_id)
        return

    per_page = 10
    total_pages = (len(subs) + per_page - 1) // per_page
    page_subs = subs[page * per_page : (page + 1) * per_page]

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(
            BotMessages.CHECK_ALL_SUBCLIENTS,
            callback_data=f'run_all_ag:{login}',
        )
    )

    for sub in page_subs:
        markup.add(
            types.InlineKeyboardButton(
                f'🏢 {sub}', callback_data=f'chk_sub:{login}:{sub}'
            )
        )

    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            types.InlineKeyboardButton(
                BotMessages.PREV_PAGE,
                callback_data=f'page_sub:{login}:{page - 1}',
            )
        )
    if page < total_pages - 1:
        nav_buttons.append(
            types.InlineKeyboardButton(
                BotMessages.NEXT_PAGE,
                callback_data=f'page_sub:{login}:{page + 1}',
            )
        )

    if nav_buttons:
        markup.row(*nav_buttons)

    markup.add(
        types.InlineKeyboardButton(
            BotMessages.BACK_BTN, callback_data='back:accs'
        )
    )

    send_tracked_message(
        chat_id,
        BotMessages.CHOOSE_SUBCLIENT
        + f'\n\nСтраница {page + 1}/{total_pages}',
        reply_markup=markup,
    )


@bot.callback_query_handler(
    func=lambda call: call.data.startswith('page_sub:')
)
def page_subclients(call: types.CallbackQuery):
    """Обрабатывает переключение страниц списка субклиентов.

    Args:
        call: Объект обратного вызова (Callback Query).
    """
    _, login, page_str = call.data.split(':')
    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass
    bot.delete_message(call.message.chat.id, call.message.message_id)
    show_subclients(call.message.chat.id, login, int(page_str))


@bot.callback_query_handler(func=lambda call: call.data.startswith('chk_sub:'))
def subclient_selected(call: types.CallbackQuery):
    """Переходит к выбору кампаний для конкретного субклиента.

    Args:
        call: Объект обратного вызова (Callback Query).
    """
    _, login, subclient = call.data.split(':')
    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass
    bot.edit_message_reply_markup(
        call.message.chat.id, call.message.message_id, reply_markup=None
    )
    show_campaigns(call.message.chat.id, login, subclient, page=0)


def show_campaigns(
    chat_id: int, login: str, subclient: str, page: int, msg_id: int = None
):
    """Отображает список активных кампаний клиента с возможностью выбора.

    Args:
        chat_id: ID чата Telegram.
        login: Логин основного аккаунта.
        subclient: Логин субклиента.
        page: Текущая страница.
        msg_id: ID сообщения для редактирования (опционально).
    """
    async def get_camps():
        async with async_session_factory() as session:
            user = await user_repository.get_user_by_login(session, login)
            return await yandex_auth.get_active_campaigns(
                user.token, subclient
            )

    if not msg_id:
        send_tracked_message(chat_id, '⏳ Получаю список кампаний...')

    camps = run_async(get_camps())

    if not camps:
        if msg_id:
            bot.edit_message_text(
                f'У клиента {subclient} нет активных кампаний.',
                chat_id,
                msg_id,
            )
        else:
            send_tracked_message(
                chat_id, f'У клиента {subclient} нет активных кампаний.'
            )
        show_main_menu(chat_id)
        return

    state_key = f'state:{chat_id}:camps'
    per_page = 10
    total_pages = (len(camps) + per_page - 1) // per_page
    page_camps = camps[page * per_page : (page + 1) * per_page]

    selected_bytes = run_async(redis_client.smembers(state_key))
    selected = [int(x) for x in selected_bytes] if selected_bytes else []
    
    logger.debug(f'show_campaigns: selected = {selected}')

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(
            BotMessages.CHECK_ALL_CAMPAIGNS,
            callback_data=f'run_all_cl:{login}:{subclient}',
        )
    )

    for camp in page_camps:
        camp_id = camp['Id']
        camp_name = camp.get('Name', str(camp_id))
        is_sel = camp_id in selected
        btn_text = f'✅ {camp_name}' if is_sel else f'◻️ {camp_name}'
        markup.add(
            types.InlineKeyboardButton(
                btn_text,
                callback_data=f'tgl_camp:{login}:{subclient}:{camp_id}:{page}',
            )
        )

    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            types.InlineKeyboardButton(
                BotMessages.PREV_PAGE,
                callback_data=f'page_camp:{login}:{subclient}:{page - 1}',
            )
        )
    if page < total_pages - 1:
        nav_buttons.append(
            types.InlineKeyboardButton(
                BotMessages.NEXT_PAGE,
                callback_data=f'page_camp:{login}:{subclient}:{page + 1}',
            )
        )

    if nav_buttons:
        markup.row(*nav_buttons)

    if selected:
        markup.add(
            types.InlineKeyboardButton(
                BotMessages.CHECK_SELECTED,
                callback_data=f'run_sel:{login}:{subclient}',
            )
        )

    markup.add(
        types.InlineKeyboardButton(
            BotMessages.BACK_BTN,
            callback_data=f'back:subc:{login}'
            if login != subclient
            else 'back:accs',
        )
    )

    text = (
        BotMessages.CHOOSE_CAMPAIGNS + f'\n\nСтраница {page + 1}/{total_pages}'
    )
    if msg_id:
        try:
            bot.edit_message_text(text, chat_id, msg_id, reply_markup=markup)
        except Exception as e:
            logger.debug(f'edit_message_text failed: {e}')
    else:
        bot.send_message(chat_id, text, reply_markup=markup)


@bot.callback_query_handler(
    func=lambda call: call.data.startswith('page_camp:')
)
def page_campaigns(call: types.CallbackQuery):
    """Обрабатывает переключение страниц списка кампаний.

    Args:
        call: Объект обратного вызова (Callback Query).
    """
    _, login, subclient, page_str = call.data.split(':')
    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass
    bot.delete_message(call.message.chat.id, call.message.message_id)
    show_campaigns(call.message.chat.id, login, subclient, int(page_str))


@bot.callback_query_handler(
    func=lambda call: call.data.startswith('tgl_camp:')
)
def toggle_campaign(call: types.CallbackQuery):
    """Переключает статус выбора кампании в Redis.

    Args:
        call: Объект обратного вызова (Callback Query).
    """
    logger.debug(f'tgl_camp triggered with: {call.data}')
    try:
        _, login, subclient, camp_id, page_str = call.data.split(':')
        state_key = f'state:{call.message.chat.id}:camps'

        async def toggle():
            is_member = await redis_client.sismember(state_key, camp_id)
            if is_member:
                await redis_client.srem(state_key, camp_id)
            else:
                await redis_client.sadd(state_key, camp_id)

        run_async(toggle())
        try:
            bot.answer_callback_query(call.id)
        except Exception:
            pass

        show_campaigns(
            call.message.chat.id,
            login,
            subclient,
            int(page_str),
            msg_id=call.message.message_id,
        )
    except Exception as e:
        logger.exception(f'Error in toggle_campaign: {e}')
        bot.answer_callback_query(call.id, f'Ошибка: {e}')


@bot.callback_query_handler(func=lambda call: call.data.startswith('back:'))
def back_handler(call: types.CallbackQuery):
    """Обрабатывает нажатие кнопок 'Назад' на разных уровнях меню.

    Args:
        call: Объект обратного вызова (Callback Query).
    """
    data = call.data.split(':')
    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass
    bot.delete_message(call.message.chat.id, call.message.message_id)

    if data[1] == 'menu':
        show_main_menu(call.message.chat.id)
    elif data[1] == 'accs':
        show_accounts_for_check(call.message.chat.id)
    elif data[1] == 'subc':
        show_subclients(call.message.chat.id, data[2], 0)


@bot.callback_query_handler(func=lambda call: call.data.startswith('run_'))
def execute_check(call: types.CallbackQuery):
    """Выполняет запуск проверки ссылок (всех аккаунтов, агентства или выбранных кампаний).

    Args:
        call: Объект обратного вызова (Callback Query).
    """
    logger.debug(f'execute_check triggered with: {call.data}')
    data = call.data.split(':')
    action = data[0]
    chat_id = call.message.chat.id

    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass
    try:
        bot.edit_message_reply_markup(
            chat_id, call.message.message_id, reply_markup=None
        )
    except Exception:
        pass

    progress_msg = send_tracked_message(chat_id, BotMessages.CHECK_START)

    async def run_logic():
        try:
            async with async_session_factory() as session:
                service = DirectService(session)

                if action == 'run_all_accounts':
                    logins = await user_repository.get_all_logins(session)
                    reports = []
                    for login in logins:
                        user = await user_repository.get_user_by_login(
                            session, login
                        )
                        role = await yandex_auth.get_user_role(
                            user.token, login
                        )
                        if role == 'AGENCY':
                            r = await service.check_all_agency_clients(login)
                        else:
                            r = await service.check_all_for_subclient(
                                login, login
                            )
                        reports.append(r)
                    return '\n\n'.join(reports)

                if action == 'run_all_ag':
                    login = data[1]
                    return await service.check_all_agency_clients(login)

                elif action == 'run_all_cl':
                    login = data[1]
                    subclient = data[2]
                    return await service.check_all_for_subclient(
                        login, subclient
                    )

                elif action == 'run_sel':
                    login = data[1]
                    subclient = data[2]
                    state_key = f'state:{chat_id}:camps'
                    selected_bytes = await redis_client.smembers(state_key)
                    # Исправление: убран decode, так как x уже str
                    camp_ids = [int(x) for x in selected_bytes]
                    report = await service.check_specific_campaigns(
                        login, subclient, camp_ids
                    )
                    await redis_client.delete(state_key)
                    return report

        except Exception as e:
            logger.exception(f'Error in execute_check logic: {e}')
            return BotMessages.CHECK_ERROR.format(e)

    report = run_async(run_logic())

    try:
        bot.edit_message_text(
            report, chat_id, progress_msg.message_id, parse_mode='Markdown'
        )
    except Exception as e:
        logger.debug(f'Failed to edit progress message: {e}')
        send_tracked_message(chat_id, report, parse_mode='Markdown')

    show_main_menu(chat_id)


@bot.message_handler(func=lambda message: True)
def unknown_message(message: types.Message) -> None:
    """Обработчик всех неопознанных сообщений.

    Args:
        message: Объект сообщения от пользователя.
    """
    track_message(message.chat.id, message.message_id)
    show_main_menu(message.chat.id)


def main() -> None:
    """Инициализация БД и запуск бесконечного цикла опроса Telegram."""
    run_async(init_models())
    logger.info('Бот запущен и готов к работе...')
    bot.infinity_polling()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.warning('Бот остановлен пользователем.')
    finally:
        loop.close()