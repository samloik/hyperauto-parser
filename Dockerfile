# ===========================================
# Multi-stage Dockerfile для Hyperauto Parser
# ===========================================

# -------------------------------------------
# Stage 1: Build stage
# -------------------------------------------
FROM mcr.microsoft.com/playwright/python:v1.58.0-jammy AS builder

WORKDIR /build

# Копируем только зависимости сначала (для кэширования слоёв)
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir --user -r requirements.txt

# -------------------------------------------
# Stage 2: Production stage
# -------------------------------------------
FROM mcr.microsoft.com/playwright/python:v1.58.0-jammy AS production

# Проверяем существует ли уже пользователь appuser
# Если нет - создаём non-root пользователя для безопасности
RUN if ! id -u appuser >/dev/null 2>&1; then \
        groupadd --gid 1001 appgroup && \
        useradd --uid 1001 --gid appgroup --shell /bin/bash --create-home appuser; \
    fi

WORKDIR /app

# Создаём необходимые папки
RUN mkdir -p /app/logs /app/Errors /app/output && \
    chown -R appuser:appgroup /app

# Копируем установленные пакеты из builder stage
COPY --from=builder /root/.local /home/appuser/.local

# Копируем код приложения
COPY main.py ./
COPY config.py ./
COPY models.py ./
COPY utils.py ./
COPY browser.py ./
COPY parser.py ./
COPY error_handler.py ./
COPY health_check.py ./
COPY exceptions.py ./

# Копируем шаблон .env (опционально)
COPY .env.example ./.env.example

# Создаём пустой файл cookies.json если не существует
RUN touch cookies.json || true

# Устанавливаем права доступа для non-root пользователя
RUN chown -R appuser:appgroup /app && \
    chmod -R 755 /app

# Переключаемся на non-root пользователя
USER appuser

# Добавляем .local/bin в PATH для установленных пакетов
ENV PATH=/home/appuser/.local/bin:$PATH
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# По умолчанию запускаем в headless режиме для Docker
ENV DOCKER_ENV=1

# Метаданные
LABEL maintainer="hyperauto-parser"
LABEL description="Парсер товаров с сайта hyperauto.ru"
LABEL version="1.0"

# Запуск приложения
CMD ["python", "main.py"]
