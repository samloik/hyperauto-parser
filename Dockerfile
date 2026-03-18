FROM mcr.microsoft.com/playwright/python:v1.58.0-jammy

WORKDIR /app

# Копируем зависимости и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код приложения
COPY main.py ./
COPY cookies.json ./

# Указываем путь к браузерам, которые уже установлены в образе
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
# Флаг для запуска в headless режиме
ENV DOCKER_ENV=1

# Запуск приложения
CMD ["python", "main.py"]
