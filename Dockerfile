FROM ghcr.io/astral-sh/uv:python3.12-slim

WORKDIR /app

ENV UV_PROJECT_ENVIRONMENT="/usr/local"

COPY pyproject.toml uv.lock ./

# Устанавливаем зависимости
RUN uv sync --no-dev --no-install-project --frozen

# Копируем код приложения
COPY . .

# Создаем папку для SQLite (если она будет монтироваться как volume)
RUN mkdir -p /app/data

# Запуск бота через модуль
CMD ["python", "-m", "app.main"]
