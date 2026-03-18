"""
Парсер цен автозапчастей с сайта Hyperauto.ru.

Читает товары из Excel файла (колонки 'Бренд' и 'Артикул'),
парсит цены с сайта и сохраняет результаты в новый Excel файл.
"""
import asyncio
import pandas as pd
from time import perf_counter
from pathlib import Path
from loguru import logger
import sys

import config
from models import Product, SearchResult, ParserResult
from browser import BrowserManager
from parser import ProductParser
import utils


def setup_logging() -> None:
    """Настраивает логирование."""
    logger.remove()

    config.LOGS_DIR.mkdir(exist_ok=True)

    logger.add(
        sys.stdout,
        format=config.LOG_FORMAT,
        level=config.LOG_LEVEL
    )
    logger.add(
        config.LOGS_DIR / "logs-{time:YYYY-MM-DD-HH-mm-ss}.txt",
        format=config.LOG_FORMAT,
        level=config.LOG_LEVEL,
        retention=config.LOG_RETENTION
    )


def load_input_file() -> pd.DataFrame | None:
    """
    Загружает входной Excel файл.

    Returns:
        DataFrame с данными или None при ошибке.
    """
    logger.info("=== Запуск парсера Гиперавто (Playwright) ===")
    logger.info(f"Текущая папка: {Path.cwd()}")
    logger.info(f"Ищем файл: {config.INPUT_FILE}")

    if not Path(config.INPUT_FILE).exists():
        logger.error(f"ОШИБКА: файл {config.INPUT_FILE} НЕ НАЙДЕН в {Path.cwd()}")
        logger.info("Создайте файл с колонками 'Бренд' и 'Артикул'")
        return None

    logger.info("Файл найден → читаем...")
    try:
        df = pd.read_excel(config.INPUT_FILE)
        logger.info(f"Прочитано строк: {len(df)}")
        logger.info(df.head().to_string())
        return df
    except Exception as e:
        logger.error(f"Ошибка чтения Excel: {e}")
        return None


def validate_dataframe(df: pd.DataFrame) -> bool:
    """
    Проверяет наличие требуемых колонок.

    Args:
        df: DataFrame для проверки.

    Returns:
        True если валиден.
    """
    required_columns = ['Бренд', 'Артикул']
    for col in required_columns:
        if col not in df.columns:
            logger.error(f"ОШИБКА: в файле нет колонки '{col}'")
            return False
    return True


async def process_products(
    df: pd.DataFrame,
    browser: BrowserManager,
    parser: ProductParser
) -> list[dict]:
    """
    Обрабатывает все товары из DataFrame.

    Args:
        df: DataFrame с товарами.
        browser: Менеджер браузера.
        parser: Парсер товаров.

    Returns:
        Список результатов для Excel.
    """
    total_start = perf_counter()
    times = []
    all_results = []

    # Очищаем папку ошибок
    if config.ERRORS_DIR.exists():
        for f in config.ERRORS_DIR.iterdir():
            if f.is_file():
                f.unlink()
    else:
        config.ERRORS_DIR.mkdir(exist_ok=True)

    total_len = len(str(len(df)))

    for idx, row in df.iterrows():
        brand = str(row['Бренд']).strip()
        article = str(row['Артикул']).strip()
        start = perf_counter()

        # Поиск товара
        search_result = await parser.search_product(brand, article)
        elapsed = perf_counter() - start
        times.append(elapsed)

        # Обработка результатов
        products = search_result.products if search_result.products else []

        for result_idx, product in enumerate(products):
            prefix = utils.format_prefix(idx, result_idx, len(products))

            result = ParserResult(
                row_number=prefix,
                brand=brand,
                article=article,
                brand_from_card=product.item_brand,
                article_from_card=product.item_article,
                price=product.price if product.has_price else None,
                datetime=utils.get_datetime_str(),
                execution_time=f"{elapsed:.1f} сек",
                availability=product.availability,
                product_name=product.product_name or product.price_text,
                link=f"https://hyperauto.ru/{config.CITY_SLUG}/search/{brand}/{article}/"
            )
            all_results.append(result.to_dict())

            # Логирование
            log_product_result(
                prefix=prefix,
                brand=brand,
                article=article,
                product=product,
                elapsed=elapsed
            )

        # Сохранение HTML при ошибках
        if search_result.has_error and products:
            for product in products:
                if not product.has_price and product.html_content:
                    html_filename = utils.save_html_error(
                        html_content=product.html_content,
                        brand=brand,
                        article=article,
                        error_name=product.price_text,
                        position=idx + 1
                    )
                    logger.info(f"  → Сохранено: {html_filename}")
                    break

        # Задержка между запросами
        await browser.wait(int(config.DELAY * 1000))

    total_elapsed = perf_counter() - total_start
    avg_time = sum(times) / len(times) if times else 0

    logger.info(f"\n⏱ Всего: {utils.format_time(total_elapsed)} | Среднее на позицию: {utils.format_time(avg_time)}")

    return all_results


def log_product_result(
    prefix: str,
    brand: str,
    article: str,
    product: Product,
    elapsed: float
) -> None:
    """
    Выводит результат в лог.

    Args:
        prefix: Префикс строки.
        brand: Бренд.
        article: Артикул.
        product: Распарсенный товар.
        elapsed: Время выполнения.
    """
    name_display = f"{brand}/{article}"[:25]

    if product.has_price:
        price_display = f"{product.price:,.2f}"[:10]
        product_name_display = product.product_name[:70] if len(product.product_name) > 70 else product.product_name
        availability_display = product.availability[:20] if product.availability else ""
        brand_display = product.item_brand[:10] if product.item_brand else ""
        article_display = product.item_article[:20] if product.item_article else ""

        logger.info(
            f"{prefix:<14} {brand_display:<10} | {article_display:<20} | "
            f"{name_display:<25} | {price_display:>10} | {elapsed:>6.1f} сек | "
            f"{availability_display:<20} | {product_name_display}"
        )
    else:
        product_name_display = product.product_name[:70] if len(product.product_name) > 70 else product.product_name
        availability_display = product.availability[:20] if product.availability else ""
        brand_display = product.item_brand[:10] if product.item_brand else ""
        article_display = product.item_article[:20] if product.item_article else ""

        logger.info(
            f"{prefix:<14} {brand_display:<10} | {article_display:<20} | "
            f"{name_display:<25} | {'✗':>10} | {elapsed:>6.1f} сек | "
            f"{availability_display:<20} | {product_name_display}"
        )


def save_results(results: list[dict]) -> str:
    """
    Сохраняет результаты в Excel файл.

    Args:
        results: Список результатов.

    Returns:
        Имя сохранённого файла.
    """
    df = pd.DataFrame(results)

    # Переупорядочиваем колонки
    column_order = [
        '№', 'Бренд', 'Артикул', 'Бренд_карточка', 'Артикул_карточка',
        'Цена_Гиперавто_КнА', 'Дата и время', 'Выполнение запроса',
        'Наличие', 'Наименование', 'Ссылка'
    ]
    df = df[column_order]

    timestamp = utils.get_timestamp()
    output_file = f"{config.OUTPUT_FILE_PREFIX}_{timestamp}.xlsx"
    df.to_excel(output_file, index=False)

    # Настраиваем ширину колонок
    adjust_column_widths(output_file, df)

    logger.info(f"\nСохранено → {output_file}")
    return output_file


def adjust_column_widths(filepath: str, df: pd.DataFrame) -> None:
    """
    Настраивает ширину колонок Excel файла.

    Args:
        filepath: Путь к файлу.
        df: DataFrame с данными.
    """
    try:
        from openpyxl import load_workbook
        wb = load_workbook(filepath)
        ws = wb.active

        for col_idx, col_name in enumerate(df.columns, 1):
            col_letter = chr(64 + col_idx)

            max_length = 0
            for value in df[col_name]:
                if pd.notna(value):
                    text_length = len(str(value))
                    if text_length > max_length:
                        max_length = text_length

            col_width = min(max(max_length + 2, 10), 80)
            ws.column_dimensions[col_letter].width = col_width

        wb.save(filepath)
        wb.close()
    except Exception as e:
        logger.warning(f"Warning: Could not adjust column widths: {e}")


async def main_async() -> None:
    """Основная функция парсера."""
    setup_logging()

    # Загружаем входной файл
    df = load_input_file()
    if df is None:
        return

    if not validate_dataframe(df):
        return

    logger.info("Колонки в порядке → запускаем браузер...")

    # Инициализация браузера
    browser_manager = BrowserManager()
    try:
        await browser_manager.initialize()
        await browser_manager.setup_session()

        # Создаём парсер
        product_parser = ProductParser(browser_manager)

        # Обрабатываем товары
        results = await process_products(df, browser_manager, product_parser)

        # Сохраняем результаты
        save_results(results)

    except Exception as e:
        logger.error(f"Критическая ошибка: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()

    finally:
        await browser_manager.close()


if __name__ == "__main__":
    asyncio.run(main_async())
