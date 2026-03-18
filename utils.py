"""
Вспомогательные утилиты для парсера Hyperauto.
"""
import json
import sys
from datetime import timedelta
from pathlib import Path
from typing import Optional

from loguru import logger

from config import config
from models import Product, ParseResult


def setup_logger() -> None:
    """
    Настраивает логгер loguru.
    Удаляет стандартные обработчики и добавляет свои.
    """
    logger.remove()
    
    # Консольный вывод
    logger.add(
        sys.stdout,
        format=config.LOG_FORMAT,
        level=config.LOG_LEVEL
    )
    
    # Файловый вывод с ротацией
    logger.add(
        config.LOGS_DIR / "logs-{time:YYYY-MM-DD-HH-mm-ss}.txt",
        format=config.LOG_FORMAT,
        level=config.LOG_LEVEL,
        retention=timedelta(days=config.LOG_RETENTION_DAYS)
    )


def format_time(seconds: float) -> str:
    """
    Форматирует время в читаемый формат.
    
    Args:
        seconds: Время в секундах.
        
    Returns:
        Строка в формате "ЧЧ:ММ:СС сек", "ММ:СС сек" или "СС сек".
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


def sanitize_filename(name: str, max_length: int = 50) -> str:
    """
    Очищает строку для использования в имени файла.
    
    Args:
        name: Исходная строка.
        max_length: Максимальная длина результата.
        
    Returns:
        Безопасная строка для имени файла.
    """
    # Заменяем проблемные символы
    for char in [':', '/', '\\', '<', '>', '"', '|', '?', '*']:
        name = name.replace(char, '_')
    
    # Обрезаем до максимальной длины
    return name[:max_length]


async def save_error_files(
    page,
    result: ParseResult,
    position_num: int
) -> tuple[str, Optional[str]]:
    """
    Сохраняет HTML и скриншот при ошибке.
    
    Args:
        page: Объект страницы Playwright.
        result: Результат парсинга с ошибкой.
        position_num: Номер позиции в списке.
        
    Returns:
        Кортеж (имя HTML файла, имя файла скриншота или None).
    """
    # Находим первый продукт с ошибкой и HTML
    error_product: Optional[Product] = None
    for product in result.products:
        if product.has_error and product.html_content:
            error_product = product
            break
    
    if not error_product:
        return "", None
    
    # Формируем имя файла
    error_name = sanitize_filename(error_product.price_text)
    html_filename = (
        f"{position_num}-{result.brand}-{result.article}-{error_name}.html"
    )
    html_filepath = config.ERRORS_DIR / html_filename
    
    # Сохраняем HTML
    with open(html_filepath, 'w', encoding='utf-8') as f:
        f.write(error_product.html_content)
    
    # Сохраняем скриншот
    screenshot_filename = (
        f"{position_num}-{result.brand}-{result.article}-{error_name}.jpg"
    )
    screenshot_path = config.ERRORS_DIR / screenshot_filename
    
    try:
        await page.screenshot(
            path=str(screenshot_path),
            type='jpeg',
            quality=80,
            full_page=True
        )
        return html_filename, screenshot_filename
    except Exception as e:
        logger.warning(f"  ⚠ Не удалось сделать скриншот: {e}")
        return html_filename, None


def load_cookies() -> Optional[dict]:
    """
    Загружает cookies из файла.
    
    Returns:
        Словарь с cookies или None если файл не найден/невалиден.
    """
    if not config.COOKIES_FILE.exists():
        return None
    
    try:
        with open(config.COOKIES_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Нормализуем cookies для Playwright
        if 'cookies' in data:
            for cookie in data['cookies']:
                # sameSite должен быть Strict|Lax|None или отсутствовать
                if 'sameSite' in cookie:
                    if cookie['sameSite'] not in ('Strict', 'Lax', 'None'):
                        del cookie['sameSite']
                
                # domain не должен начинаться с http
                if 'domain' in cookie:
                    cookie['domain'] = (
                        cookie['domain']
                        .lstrip('http')
                        .lstrip('s')
                        .lstrip(':')
                        .lstrip('/')
                    )
        
        return data
    except Exception as e:
        logger.warning(f"⚠ Ошибка загрузки {config.COOKIES_FILE}: {e}")
        logger.info("  Удалите файл и запустите заново для создания новой сессии")
        return None


def save_cookies(storage_state: dict) -> None:
    """
    Сохраняет cookies в файл.
    
    Args:
        storage_state: Состояние хранения Playwright.
    """
    with open(config.COOKIES_FILE, 'w', encoding='utf-8') as f:
        json.dump(storage_state, f, indent=2, ensure_ascii=False)
    logger.info(f"✓ Сессия сохранена в {config.COOKIES_FILE}")


def clear_errors_dir() -> None:
    """Очищает папку с ошибками перед новым запуском."""
    if config.ERRORS_DIR.exists():
        for f in config.ERRORS_DIR.iterdir():
            if f.is_file():
                f.unlink()
    else:
        config.ERRORS_DIR.mkdir(exist_ok=True)


def adjust_excel_column_widths(workbook, df) -> None:
    """
    Настраивает ширину колонок в Excel файле.
    
    Args:
        workbook: Объект Workbook из openpyxl.
        df: DataFrame с данными.
    """
    ws = workbook.active
    
    for col_idx, col_name in enumerate(df.columns, 1):
        col_letter = chr(64 + col_idx)
        
        # Находим максимальную длину текста в колонке
        max_length = 0
        for value in df[col_name]:
            if value is not None:
                text_length = len(str(value))
                if text_length > max_length:
                    max_length = text_length
        
        # Устанавливаем ширину колонки
        col_width = min(
            max(max_length + 2, config.EXCEL_COLUMN_WIDTH_MIN),
            config.EXCEL_COLUMN_WIDTH_MAX
        )
        ws.column_dimensions[col_letter].width = col_width
