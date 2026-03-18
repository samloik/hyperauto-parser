# ===========================================
# Dockerfile для Hyperauto Parser
# ===========================================

FROM mcr.microsoft.com/playwright/python:v1.58.0-jammy

WORKDIR /app

# Копируем зависимости и устанавливаем их глобально
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Создаём необходимые папки
RUN mkdir -p /app/logs /app/Errors /app/output

# Копируем код приложения
COPY main.py ./
COPY config.py ./
COPY models.py ./
COPY utils.py ./
COPY browser.py ./
COPY parser.py ./
COPY card_parser.py ./
COPY error_handler.py ./
COPY health_check.py ./
COPY exceptions.py ./

# Копируем шаблон .env (опционально)
COPY .env.example ./.env.example

# Создаём пустой файл cookies.json
RUN touch cookies.json || true

# Устанавливаем PLAYWRIGHT_BROWSERS_PATH
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Headless режим для Docker
ENV DOCKER_ENV=1

# Метаданные
LABEL maintainer="hyperauto-parser"
LABEL description="Парсер товаров с сайта hyperauto.ru"
LABEL version="1.0"

# Запуск приложения
CMD ["python", "main.py"]
