## Описание

Direct Checker Bot - Telegram бот для автоматической проверки работоспособности ссылок в рекламных объявлениях Яндекс.Директ. Бот предоставляет удобный интерфейс для мониторинга статуса всех URL-адресов в кампаниях, объявлениях и быстрых ссылках.

## Основные возможности:
🔐 Авторизация через OAuth Яндекс

📊 Комплексная проверка всех рекламных материалов

🔍 Проверка статуса ссылок (статус 200 = рабочая)

📋 Детальные отчеты по каждому пользователю

🗂️ Управление базой данных токенов

## Как пользоваться чайнику:
- Устанавливаем Visual Code https://code.visualstudio.com/Download
- Ставим python 3.12 https://www.python.org/downloads/release/python-3127/
- ставим git bash(командная строка) https://gitforwindows.org/
- Создаем папку где удобно и заходим в неё с помощью Visual Studio
- Запускаем терминал и копируем скрипт с репозитория GIT HUB

```bash
git clone  git@github.com:aslan-py/yandex-direct.git

```

## Установка зависимостей и запуск бэкенда
- сначала создай .env файл по примеру файла .env.example туда нужно добавить твои  CLIENT_ID, CLIENT_SECRET, TELEGRAM_BOT_TOKEN
```bash
# Переход в папку с ботом
cd yandex-direct

# Создание виртуального окружения
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate  # Windows

# Установка зависимостей
pip install -r requirements.txt

# Запуск бота
python main.py
```

## Запуск как сервис на сервере Linux
```linux
# Создайте сервисный файл
sudo nano /etc/systemd/system/direct-bot.service

[Unit]
Description=Yandex Direct Checker Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/path/to/your/bot
ExecStart=/path/to/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target

# Запуск сервиса
sudo systemctl daemon-reload
sudo systemctl enable direct-bot
sudo systemctl start direct-bot
```

## Описание модулей и функций
🔑 Модуль: token_and_login.py
Назначение: Управление OAuth-авторизацией и работой с базой данных токенов.

Функции:

- check_services_availability() -> tuple[bool, str]
Проверяет доступность сервисов Яндекса перед началом авторизации

- get_auth_link() -> tuple[bool, str]
Генерирует URL для OAuth-авторизации пользователя в Яндекс

- get_token_data(auth_code: str) -> tuple[bool, str]
Обменивает код подтверждения на access token для API Яндекс.Директ

- get_user_login(token: str) -> tuple[bool, str]
Получает логин пользователя по OAuth токену

- save_to_database(login, token) -> tuple[bool, str]
Сохраняет или обновляет токен пользователя в SQLite базе данных

🔧 Модуль: support_methods.py
Назначение: Бизнес-логика работы с API Яндекс.Директ и проверки ссылок.

Функции работы с БД:

- initialize_database() -> bool
Создает таблицу logins_tokens для хранения токенов пользователей

- get_all_logins_and_tokens(DB: dict) -> tuple[bool, str]
Загружает всех пользователей из БД в оперативную память для проверки

Функции API Яндекс.Директ:

- get_api_response(token: str, login: str) -> requests.Response | None
Базовый запрос к API кампаний Яндекс.Директ

- get_ads_api_response(token: str, login: str, campaign_ids: list)
Получает объявления для списка кампаний (с разбивкой на чанки)

- get_sitelinks_api_response(token: str, login: str, sitelink_set_id: list)
Получает данные о быстрых ссылках (sitelinks)

Функции проверки ответов:

- check_response(response, login: str, api_type: str) -> tuple[bool, str]
Валидирует ответы от API Яндекс.Директ

- parse_companies_response(response_data, login: str, DB: dict)
Извлекает ID активных кампаний (State = 'ON')

- parse_ads_response(response_data, login: str, DB: dict)
Извлекает данные объявлений и быстрых ссылок

- parse_sitelinks_response(response_data, login: str, DB: dict)
Извлекает URL быстрых ссылок из наборов

Функции проверки URL:

- check_url_status(urls, login, DB, url_type='ad') -> bool | str
Проверяет доступность URL и формирует отчет (статус 200 = рабочий)

Система логирования:

- setup_logging()
Настраивает систему логирования с ротацией файлов

🤖 Модуль: main.py
Назначение: Telegram бот - пользовательский интерфейс и координация процессов.

Обработчики команд:

- send_welcome(message) - команда /start
Приветственное сообщение и описание возможностей бота

- start_login(message) - команда /login
Запускает процесс OAuth-авторизации в Яндекс.Директ

- handle_auth_code(message)
Обрабатывает код подтверждения от пользователя и сохраняет токен

- start_check(message) - команда /go
Запускает комплексную проверку Яндекс.Директ

- delete_database(message) - команда /delete
Удаляет базу данных с подтверждением пользователя

Основной процесс проверки:

- run_direct_check(chat_id)
Выполняет полный цикл проверки: загрузка пользователей → получение кампаний → получение объявлений → проверка быстрых ссылок → проверка URL → формирование отчета

- :)
