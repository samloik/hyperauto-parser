"""
Парсер товаров с сайта Hyperauto.ru.

Считывает данные из Excel файла (колонки 'Бренд' и 'Артикул'),
парсит цены и информацию о наличии, сохраняет результаты в Excel.
"""
import asyncio
import pandas as pd
from datetime import datetime
from time import perf_counter

from loguru import logger

from config import config
from models import ParseResult, ParseStats, Product
from browser import BrowserSession
from parser import Parser
from utils import (
    setup_logger,
    format_time,
    save_error_files,
    clear_errors_dir,
    adjust_excel_column_widths,
)
from error_handler import error_metrics, save_error_report
from utils import save_cookies
from health_check import full_health_check, ParserNetworkError


async def main_async() -> None:
    """Основная функция парсера."""
    setup_logger()
    config.init_dirs()

    logger.info("=== Запуск парсера Гиперавто (Playwright) ===")
    logger.info(f"Текущая папка: {config.INPUT_FILE.parent.resolve()}")
    logger.info(f"Ищем файл: {config.INPUT_FILE}")

    # Проверяем входной файл
    if not config.INPUT_FILE.exists():
        logger.error(f"ОШИБКА: файл {config.INPUT_FILE} НЕ НАЙДЕН")
        logger.info("Создайте файл с колонками 'Бренд' и 'Артикул'")
        return

    # Валидируем конфигурацию
    config_errors = config.validate()
    if config_errors:
        for error in config_errors:
            logger.error(f"Ошибка конфигурации: {error}")
        return

    # Читаем входной файл
    logger.info("Файл найден → читаем...")
    try:
        df = pd.read_excel(config.INPUT_FILE)
        logger.info(f"Прочитано строк: {len(df)}")
        logger.info(df.head().to_string())
    except Exception as e:
        logger.error(f"Ошибка чтения Excel: {e}")
        return

    if 'Бренд' not in df.columns or 'Артикул' not in df.columns:
        logger.error("ОШИБКА: в файле нет колонок 'Бренд' и/или 'Артикул'")
        return

    logger.info("Колонки в порядке → запускаем браузер...")

    # Очищаем папку ошибок
    clear_errors_dir()

    # Health-check сайта перед запуском
    try:
        health_ok = await full_health_check()
        if not health_ok:
            logger.error("✗ Сайт недоступен. Запуск парсера отменён.")
            return
    except Exception as e:
        logger.warning(f"⚠ Не удалось выполнить health-check: {e}")
        logger.info("  Продолжаем запуск...")

    # Статистика с порогом алерта из конфига
    stats = ParseStats(error_threshold=config.ERROR_THRESHOLD)
    all_results = []

    # Запускаем браузер
    async with BrowserSession() as session:
        parser = Parser(session.page)

        total_start = perf_counter()
        total_len = len(df)

        for idx, row in df.iterrows():
            brand = str(row['Бренд']).strip()
            article = str(row['Артикул']).strip()
            start = perf_counter()

            # Парсим товар
            result = await parser.parse_product(brand, article)
            result.elapsed_time = perf_counter() - start

            # Обновляем статистику
            stats.add_result(result)

            # Преобразуем в строки для Excel
            rows = result.to_excel_rows(idx, total_len)
            all_results.extend(rows)

            # Вывод на экран
            _log_result(result, idx + 1, total_len)

            # Сохраняем ошибки
            if result.has_errors:
                html_file, screenshot_file = await save_error_files(
                    session.page, result, idx + 1
                )
                if html_file:
                    if screenshot_file:
                        logger.info(
                            f"  → Сохранено: {html_file} + {screenshot_file}")
                    else:
                        logger.info(f"  → Сохранено: {html_file}")

            # Задержка между запросами
            await session.page.wait_for_timeout(int(config.DELAY * 1000))

        total_elapsed = perf_counter() - total_start
        stats.total_time = total_elapsed

        # Сохраняем обновлённую сессию cookies после завершения парсинга
        logger.info("💾 Сохранение обновлённой сессии cookies...")
        storage_state = await session.context.storage_state()
        save_cookies(storage_state)

    # Создаём DataFrame из результатов
    df_results = pd.DataFrame(all_results)

    # Переупорядочиваем колонки
    columns_order = [
        '№', 'Бренд', 'Артикул', 'Бренд_карточка', 'Артикул_карточка',
        'Цена_Гиперавто_КнА', 'Дата и время', 'Выполнение запроса',
        'Наличие', 'Наименование', 'Ссылка'
    ]
    df_results = df_results[columns_order]

    # Сохраняем в Excel
    timestamp = datetime.now().strftime('%Y%m%d_%H%M')
    output_file = f"{config.OUTPUT_FILE_PREFIX}_{timestamp}.xlsx"
    df_results.to_excel(output_file, index=False)

    # Настраиваем ширину колонок и закрепляем шапку
    try:
        from openpyxl import load_workbook
        wb = load_workbook(output_file)
        ws = wb.active

        # Закрепляем первую строку (шапку)
        ws.freeze_panes = 'A2'

        adjust_excel_column_widths(wb, df_results)
        wb.save(output_file)
        wb.close()
    except Exception as e:
        logger.warning(f"Warning: Could not adjust column widths: {e}")

    logger.info(f"\nСохранено → {output_file}")
    logger.info(f"\n⏱ Всего: {format_time(total_elapsed)} | "
                f"Среднее на позицию: {format_time(stats.avg_time)}")
    logger.info(f"✓ Успешно: {stats.success_items}/{stats.total_items} "
                f"({stats.success_rate:.1f}%)")

    # Выводим метрики ошибок
    metrics_summary = error_metrics.get_summary()
    logger.info(f"📊 Метрики ошибок: {metrics_summary['total_errors']}/{metrics_summary['total_requests']} "
                f"({metrics_summary['error_rate']:.1f}%)")

    # Сохраняем отчёт по ошибкам если были ошибки
    if metrics_summary['total_errors'] > 0:
        save_error_report()


def _log_result(result: ParseResult, row_num: int, total_len: int) -> None:
    """Выводит результат парсинга в лог."""
    total_width = len(str(total_len))

    for idx, product in enumerate(result.products):
        # Формируем префикс в формате [номер/всего] или [номер/всего][подномер]
        if len(result.products) > 1:
            prefix = f"[{row_num:0{total_width}d}/{total_len}][{idx + 1}]"
        else:
            prefix = f"[{row_num:0{total_width}d}/{total_len}] "

        if product.is_price:
            name_display = f"{result.brand}/{result.article}"[:25]
            price_display = f"{product.price:,.2f}"[:10]
            product_name_display = (
                product.product_name[:70] if len(product.product_name) > 70
                else product.product_name
            )
            availability_display = product.availability[:
                                                        20] if product.availability else ""
            brand_display = product.item_brand[:
                                               10] if product.item_brand else ""
            article_display = product.item_article[:
                                                   20] if product.item_article else ""

            logger.info(
                f"{prefix:<14} {brand_display:<10} | {article_display:<20} | "
                f"{name_display:<25} | {price_display:>10} | "
                f"{result.elapsed_time:>6.1f} сек | {availability_display:<20} | "
                f"{product_name_display}"
            )
        else:
            name_display = f"{result.brand}/{result.article}"[:25]
            product_name_display = (
                product.product_name[:70] if len(product.product_name) > 70
                else product.product_name
            )
            availability_display = product.availability[:
                                                        20] if product.availability else ""
            brand_display = product.item_brand[:
                                               10] if product.item_brand else ""
            article_display = product.item_article[:
                                                   20] if product.item_article else ""

            logger.info(
                f"{prefix:<14} {brand_display:<10} | {article_display:<20} | "
                f"{name_display:<25} | {'✗':>10} | "
                f"{result.elapsed_time:>6.1f} сек | {availability_display:<20} | "
                f"{product_name_display}"
            )


if __name__ == "__main__":
    asyncio.run(main_async())
