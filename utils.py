"""
Вспомогательные утилиты для парсера Hyperauto.
"""
import json
import random
from pathlib import Path
from datetime import datetime
from loguru import logger

import config


def format_time(seconds: float) -> str:
    """
    Форматирует время в читаемый формат: часы:минуты:секунды сек.

    Args:
        seconds: Время в секундах.

    Returns:
        Отформатированная строка времени.
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d} сек"
    elif minutes > 0:
        return f"{minutes}:{secs:02d} сек"
    else:
        return f"{secs} сек"


def format_prefix(idx: int, result_idx: int | None = None, total_results: int = 1) -> str:
    """
    Форматирует префикс строки с динамической шириной.

    Args:
        idx: Индекс строки в DataFrame.
        result_idx: Индекс результата внутри запроса (если несколько).
        total_results: Общее количество результатов в запросе.

    Returns:
        Отформатированный префикс.
    """
    total_len = len(str(idx + 1))
    if total_results > 1 and result_idx is not None:
        return f"[{idx + 1:0{total_len}d}][{result_idx + 1}]"
    else:
        return f"[{idx + 1:0{total_len}d}] "


def get_random_delay() -> int:
    """
    Возвращает случайную задержку для рандомизации запросов.

    Returns:
        Задержка в миллисекундах.
    """
    base_delay = config.BASE_DELAY
    random_component = int(config.DELAY * 1000 * config.RANDOM_DELAY_FACTOR)
    return base_delay + random_component


def sanitize_filename(text: str, max_length: int = 50) -> str:
    """
    Очищает строку для использования в имени файла.

    Args:
        text: Исходный текст.
        max_length: Максимальная длина результата.

    Returns:
        Безопасная строка для имени файла.
    """
    unsafe_chars = [':', '/', '\\', '<', '>', '"', '|', '?', '*']
    result = text
    for char in unsafe_chars:
        result = result.replace(char, '_')
    return result[:max_length]


def save_html_error(html_content: str, brand: str, article: str, error_name: str, position: int) -> str:
    """
    Сохраняет HTML страницы при ошибке.

    Args:
        html_content: HTML содержимое страницы.
        brand: Бренд товара.
        article: Артикул товара.
        error_name: Название ошибки для имени файла.
        position: Позиция в списке товаров.

    Returns:
        Имя сохранённого файла.
    """
    config.ERRORS_DIR.mkdir(exist_ok=True)

    safe_error_name = sanitize_filename(error_name)
    html_filename = f"{position}-{brand}-{article}-{safe_error_name}.html"
    html_filepath = config.ERRORS_DIR / html_filename

    with open(html_filepath, 'w', encoding='utf-8') as f:
        f.write(html_content)

    return html_filename


def load_cookies() -> dict | None:
    """
    Загружает cookies из файла сессии.

    Returns:
        Словарь с cookies или None если файл не найден или невалиден.
    """
    if not Path(config.COOKIES_FILE).exists():
        logger.warning(f"⚠ Файл {config.COOKIES_FILE} не найден — сессия не будет загружена")
        logger.info("  После первого запуска (с ручным прохождением капчи) сессия сохранится автоматически")
        return None

    try:
        with open(config.COOKIES_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if 'cookies' in data:
            for cookie in data['cookies']:
                # Нормализуем sameSite
                if 'sameSite' in cookie:
                    if cookie['sameSite'] not in ('Strict', 'Lax', 'None'):
                        del cookie['sameSite']
                # Нормализуем domain
                if 'domain' in cookie:
                    cookie['domain'] = cookie['domain'].lstrip('http').lstrip('s').lstrip(':').lstrip('/')

        logger.info(f"✓ Загружаем сессию из {config.COOKIES_FILE}")
        return data

    except Exception as e:
        logger.warning(f"⚠ Ошибка загрузки {config.COOKIES_FILE}: {e}")
        logger.info("  Удалите файл и запустите заново для создания новой сессии")
        return None


def save_cookies(storage_state: dict) -> None:
    """
    Сохраняет cookies в файл сессии.

    Args:
        storage_state: Состояние хранилища для сохранения.
    """
    with open(config.COOKIES_FILE, 'w', encoding='utf-8') as f:
        json.dump(storage_state, f, ensure_ascii=False, indent=2)
    logger.info(f"✓ Сессия сохранена в {config.COOKIES_FILE}")


def is_docker_env() -> bool:
    """
    Проверяет, запущен ли скрипт в Docker.

    Returns:
        True если запущен в Docker.
    """
    import os
    return os.environ.get(config.DOCKER_ENV_VAR, '0') == '1'


def get_timestamp() -> str:
    """
    Возвращает текущую дату и время в формате для имени файла.

    Returns:
        Строка с датой и временем.
    """
    return datetime.now().strftime('%Y%m%d_%H%M')


def get_datetime_str() -> str:
    """
    Возвращает текущую дату и время в формате для Excel.

    Returns:
        Строка с датой и временем.
    """
    return datetime.now().strftime('%Y-%m-%d %H:%M')
