# main.py
import asyncio
import pandas as pd
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from datetime import datetime, timedelta
import os
from time import perf_counter
from pathlib import Path
from loguru import logger
import sys

# Настройка логгера
logger.remove()  # Удаляем стандартный обработчик

# Создаём папку для логов
logs_dir = Path('logs')
logs_dir.mkdir(exist_ok=True)

logger.add(sys.stdout, format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}", level="INFO")
logger.add(logs_dir / "logs-{time:YYYY-MM-DD-HH-mm-ss}.txt", format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}", level="INFO", retention=timedelta(days=30))

# ================= НАСТРОЙКИ =================
INPUT_FILE = 'товары.xlsx'
OUTPUT_FILE_PREFIX = 'цены_гиперавто'
CITY_SLUG = 'komsomolsk'
DELAY = 5.0               # сек между товарами
TIMEOUT = 25000           # ms
COOKIES_FILE = 'cookies.json'  # файл с сессией (cookies)
ERRORS_DIR = 'Errors'      # папка для сохранения HTML при ошибках

def format_time(seconds):
    """Форматирует время в часы:минуты:секунды сек"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d} сек"
    elif minutes > 0:
        return f"{minutes}:{secs:02d} сек"
    else:
        return f"{secs} сек"


async def get_price_async(page, brand: str, article: str) -> (list, str, int, int):
    """
    Возвращает:
    - list кортежей (price, is_price, price_text, product_name, html_content, availability)
    - error_message (если общая ошибка)
    - total_items (общее количество на странице)
    - matched_items (количество совпавших)
    """
    max_retries = 3
    retry_count = 0

    while retry_count < max_retries:
        try:
            query = f"{brand}/{article}".strip()
            search_url = f"https://hyperauto.ru/{CITY_SLUG}/search/{query.replace(' ', '%20')}/"

            await page.goto(search_url, wait_until="domcontentloaded", timeout=TIMEOUT)
            await page.wait_for_timeout(2000 + int(DELAY * 1000 * 0.3))  # рандомизация

            # Пытаемся закрыть возможные попапы/куки
            try:
                await page.locator('button:has-text("Принять"), button:has-text("OK"), [aria-label*="принять"], [data-dismiss*="cookie"]').click(timeout=5000)
            except:
                pass

            # Ждём появления хотя бы одного товара или сообщения
            try:
                await page.wait_for_selector('.product-card, .catalog-item, article, [data-product-id], .price', timeout=15000)
            except PlaywrightTimeoutError:
                logger.warning(f"    Таймаут ожидания карточек для {brand}/{article}")
                html_content = await page.content()
                return [(0.0, False, "таймаут ожидания карточек", "", html_content, "", "", "")], "таймаут", 0, 0

            # Находим контейнер со списком товаров
            product_list = await page.query_selector('.product-list.product-list_row')
            
            # Если нашли список - берём элементы внутри него
            if product_list:
                # Ищем .product-list__item как основные контейнеры
                all_items = await product_list.query_selector_all(':scope > .product-list__item')
                # Пропускаем элементы с рекламой (класс product-list__item__search_related)
                product_list_items = []
                for item in all_items:
                    item_class = await item.get_attribute('class') or ''
                    if 'product-list__item__search_related' not in item_class:
                        product_list_items.append(item)
            else:
                product_list_items = await page.query_selector_all('.product-list__item, article, div[class*="card"], div[class*="item"], .product-card, .catalog-item, div.product')

            total_items = len(product_list_items)

            # Проверяем наличие бренда и артикула в наименовании
            def check_brand_article_in_name(product_name: str, brand: str, article: str) -> bool:
                if not product_name:
                    return False
                # Удаляем все '-' из наименования
                name_upper = product_name.upper().replace('-', '')
                brand_upper = brand.upper()
                # Добавляем пробел перед артикулом для поиска
                article_upper = ' ' + article.upper()
                # Проверяем наличие обоих: бренд И артикул (с пробелом) в наименовании
                has_brand = brand_upper in name_upper
                has_article = article_upper in name_upper
                
                # Если артикул найден, проверяем что после него нет дополнительных букв/цифр
                if has_article:
                    article_pos = name_upper.find(article_upper)
                    if article_pos >= 0:
                        # Проверяем символ после артикула
                        after_article_pos = article_pos + len(article_upper)
                        if after_article_pos < len(name_upper):
                            next_char = name_upper[after_article_pos]
                            # После артикула допускаем только не-алфанумерические символы
                            if next_char.isalnum():
                                has_article = False
                
                return has_brand and has_article

            results = []
            matched_count = 0

            # Сначала собираем все карточки с product_name
            all_products = []
            for item_idx, item in enumerate(product_list_items):
                # Извлекаем наименование товара из карточки
                product_name = ""
                # Ищем все ссылки и находим ту, что ведёт на товар (не отзыв)
                all_links = await item.query_selector_all('a')
                for link in all_links:
                    href = await link.get_attribute('href')
                    link_class = await link.get_attribute('class') or ''
                    # Пропускаем ссылки на отзывы
                    if 'rating__feedback' in link_class:
                        continue
                    if href and '/product/' in href:
                        product_name = await link.get_attribute('title') or await link.inner_text()
                        if product_name:
                            break

                # Извлекаем бренд и артикул из карточки
                item_brand = ""
                item_article = ""
                
                # Ищем блоки с информацией о товаре
                dotted_items = await item.query_selector_all('.dotted-list__item')
                for dotted_item in dotted_items:
                    title_attr = await dotted_item.get_attribute('title')
                    if title_attr == 'Бренд':
                        value_el = await dotted_item.query_selector('.dotted-list__item-value')
                        if value_el:
                            item_brand = (await value_el.inner_text()).strip()
                    elif title_attr == 'Артикул':
                        value_el = await dotted_item.query_selector('.dotted-list__item-value')
                        if value_el:
                            item_article = (await value_el.inner_text()).strip()

                # Проверяем наличие товара (ищем <b>В наличии</b> внутри <a>)
                availability = ""
                all_links = await item.query_selector_all('a')
                for link in all_links:
                    b_element = await link.query_selector('b')
                    if b_element:
                        b_text = await b_element.inner_text()
                        if 'В наличии' in b_text or 'на складе' in b_text.lower():
                            availability = ' '.join(b_text.split()).strip()
                            break
                    link_text = await link.inner_text()
                    if 'В наличии' in link_text or 'на складе' in link_text.lower():
                        availability = ' '.join(link_text.split()).strip()
                        break

                # Если не нашли "В наличии", ищем дату доставки
                if not availability:
                    # Ищем блок доставки и дату в следующем sibling элементе
                    delivery_info = await item.evaluate('''
                        (el) => {
                            // Ищем .block-delivery__variant-main с "Доставка"
                            const deliveryBlocks = el.querySelectorAll('.block-delivery__variant-main');
                            for (const block of deliveryBlocks) {
                                const label = block.querySelector('b.mr-4');
                                if (label && label.textContent.includes('Доставка')) {
                                    // Ищем следующий sibling с <b>
                                    let sibling = block.nextElementSibling;
                                    while (sibling) {
                                        const next_b = sibling.querySelector('b');
                                        if (next_b && next_b.textContent.trim()) {
                                            return next_b.textContent.trim();
                                        }
                                        sibling = sibling.nextElementSibling;
                                    }
                                    // Если не нашли в sibling, ищем внутри parent
                                    const parent = block.parentElement;
                                    if (parent) {
                                        const all_bs = parent.querySelectorAll('b');
                                        for (const b of all_bs) {
                                            const text = b.textContent.trim();
                                            if (text && !text.includes('Доставка') && !text.includes('При заказе')) {
                                                return text;
                                            }
                                        }
                                    }
                                }
                            }
                            return null;
                        }
                    ''')
                    if delivery_info:
                        availability = f"Доставка: {' '.join(delivery_info.split()).strip()}"

                # Ищем цену в элементе
                price_val = 0.0
                price_text = ""
                is_price = False

                # search_context — это сам item
                search_context = item

                # Приоритет 1: ищем цену в .price.price_big.price_green внутри карточки
                price_green_elements = await search_context.query_selector_all('.price.price_big.price_green')
                for el in price_green_elements:
                    text = (await el.inner_text()).strip()
                    price_str = text.replace(' ', '').replace(',', '.').replace('\u2009', '').replace('\xa0', '').replace('₽', '')
                    price_str_list = price_str.split('\n')
                    price_str = price_str_list[1] if len(price_str_list) > 1 else price_str_list[0]
                    try:
                        price_val = float(price_str)
                        price_text = text.strip()
                        is_price = True
                        break
                    except ValueError:
                        continue

                # Приоритет 2: ищем цену в .product-price-new__price_main внутри карточки
                if not is_price:
                    price_elements = await search_context.query_selector_all('.product-price-new__price_main')
                    for el in price_elements:
                        text = (await el.inner_text()).strip()
                        price_str = text.replace(' ', '').replace(',', '.').replace('\u2009', '').replace('\xa0', '').replace('₽', '')
                        price_str_list = price_str.split('\n')
                        price_str = price_str_list[1] if len(price_str_list) > 1 else price_str_list[0]
                        try:
                            price_val = float(price_str)
                            price_text = text.strip()
                            is_price = True
                            break
                        except ValueError:
                            continue

                if product_name:
                    all_products.append((price_val, is_price, price_text, product_name, availability, item_brand, item_article))

            # Теперь фильтруем только подходящие по бренду и артикулу
            results = []
            matched_count = 0
            for price_val, is_price, price_text, product_name, availability, item_brand, item_article in all_products:
                # Сначала проверяем по наименованию
                if check_brand_article_in_name(product_name, brand, article):
                    matched_count += 1
                    results.append((price_val, is_price, price_text, product_name, "", availability, item_brand, item_article))
                # Если не найдено в наименовании, проверяем по данным из карточки
                elif item_brand and item_article:
                    # Проверяем бренд из карточки
                    if item_brand.upper() == brand.upper():
                        # Валидируем артикул из карточки (аналогично проверке в наименовании)
                        item_article_upper = item_article.upper().replace('-', '')
                        article_upper = article.upper()
                        
                        # Ищем артикул в артикуле из карточки
                        if article_upper in item_article_upper:
                            # Проверяем что после артикула нет букв/цифр
                            article_pos = item_article_upper.find(article_upper)
                            if article_pos >= 0:
                                after_article_pos = article_pos + len(article_upper)
                                if after_article_pos >= len(item_article_upper):
                                    # Артикул найден и это конец строки - подходит
                                    matched_count += 1
                                    results.append((price_val, is_price, price_text, product_name, "", availability, item_brand, item_article))
                                else:
                                    next_char = item_article_upper[after_article_pos]
                                    if not next_char.isalnum():
                                        # После артикула допустимый символ - подходит
                                        matched_count += 1
                                        results.append((price_val, is_price, price_text, product_name, "", availability, item_brand, item_article))

            # Возвращаем все найденные позиции и количество совпавших
            if results:
                return results, "", total_items, matched_count
            else:
                # Если нет подходящих карточек
                html_content = await page.content()
                return [(0.0, False, "элементы не найдены", "", html_content, "", "", "")], "элементы не найдены", 0, 0

        except Exception as e:
            logger.error(f"    Ошибка при {brand} {article}: {str(e)[:120]}...")
            retry_count += 1
            if retry_count < max_retries:
                await page.wait_for_timeout(3000)
                continue
            try:
                html_content = await page.content()
            except:
                html_content = "<html><body>Не удалось получить HTML</body></html>"
            return [(0.0, False, f"ошибка: {str(e)[:50]}", "", html_content, "", "", "")], f"ошибка: {str(e)[:50]}", 0, 0

    return [(0.0, False, "превышено число попыток", "", "", "", "", "")], "превышено число попыток", 0, 0


async def main_async():

    # Определяем режим запуска (headless для Docker)
    headless = os.environ.get('DOCKER_ENV', '0') == '1'

    logger.info("Попытка запуска браузера Playwright...")
    try:
        async with async_playwright() as p:
            logger.info("Playwright инициализирован")
            browser = await p.chromium.launch(headless=headless, slow_mo=500)
            logger.info("Браузер запущен")
            # ... дальше контекст и страница
    except Exception as e:
        logger.error(f"Критическая ошибка Playwright: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()


    logger.info("=== Запуск парсера Гиперавто (Playwright) ===")
    logger.info(f"Текущая папка: {os.getcwd()}")
    logger.info(f"Ищем файл: {INPUT_FILE}")

    if not os.path.exists(INPUT_FILE):
        logger.error(f"ОШИБКА: файл {INPUT_FILE} НЕ НАЙДЕН в {os.getcwd()}")
        logger.info("Создайте файл с колонками 'Бренд' и 'Артикул'")
        return

    logger.info("Файл найден → читаем...")
    try:
        df = pd.read_excel(INPUT_FILE)
        logger.info(f"Прочитано строк: {len(df)}")
        logger.info(df.head().to_string())
    except Exception as e:
        logger.error(f"Ошибка чтения Excel: {e}")
        return

    if 'Бренд' not in df.columns or 'Артикул' not in df.columns:
        logger.error("ОШИБКА: в файле нет колонок 'Бренд' и/или 'Артикул'")
        return

    logger.info("Колонки в порядке → запускаем браузер...")

    df['Цена_Гиперавто_КнА'] = None
    df['Дата и время'] = datetime.now().strftime('%Y-%m-%d %H:%M')
    df['Выполнение запроса'] = None
    df['Наличие'] = None
    df['Наименование'] = None
    df['Ссылка'] = None
    df['№'] = None
    df['Бренд_карточка'] = None
    df['Артикул_карточка'] = None

    # Проверяем наличие сохранённой сессии
    storage_state = None
    if os.path.exists(COOKIES_FILE):
        try:
            # Проверяем валидность файла
            import json
            with open(COOKIES_FILE, 'r', encoding='utf-8') as f:
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
                        cookie['domain'] = cookie['domain'].lstrip('http').lstrip('s').lstrip(':').lstrip('/')
                storage_state = data
            logger.info(f"✓ Загружаем сессию из {COOKIES_FILE}")
        except Exception as e:
            logger.warning(f"⚠ Ошибка загрузки {COOKIES_FILE}: {e}")
            logger.info("  Удалите файл и запустите заново для создания новой сессии")
    else:
        logger.warning(f"⚠ Файл {COOKIES_FILE} не найден — сессия не будет загружена")
        logger.info("  После первого запуска (с ручным прохождением капчи) сессия сохранится автоматически")

    # Определяем режим запуска (headless для Docker)
    headless = os.environ.get('DOCKER_ENV', '0') == '1'

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            storage_state=storage_state,  # dict или None
            viewport={'width': 1280, 'height': 900},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            locale='ru-RU',
            timezone_id='Asia/Vladivostok',
        )
        page = await context.new_page()

        # Обход детектов
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)

        # Если сессии не было — даём время пройти капчу и сохраняем
        if storage_state is None:
            logger.info("\n>>> Открой https://hyperauto.ru в этой вкладке и пройди капчу!")
            logger.info(">>> После этого нажми Enter в консоли...")
            input()
            await page.goto("https://hyperauto.ru/", wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)
            await context.storage_state(path=COOKIES_FILE)
            logger.info(f"✓ Сессия сохранена в {COOKIES_FILE}")
            logger.info("  Следующие запуски пройдут без капчи!\n")

        total_start = perf_counter()
        times = []

        # Создаём папку для ошибок и очищаем её
        errors_path = Path(ERRORS_DIR)
        if errors_path.exists():
            # Удаляем все файлы в папке
            for f in errors_path.iterdir():
                if f.is_file():
                    f.unlink()
        else:
            errors_path.mkdir(exist_ok=True)

        # Определяем ширину для нумерации
        total_len = len(str(len(df)))
        
        def format_prefix(idx, result_idx=None, total_results=1):
            """Форматирует префикс с динамической шириной"""
            if total_results > 1:
                return f"[{idx+1:0{total_len}d}/{len(df)}][{result_idx+1}]"
            else:
                return f"[{idx+1:0{total_len}d}/{len(df)}] "
        
        # Список для хранения всех строк результатов
        all_results = []

        for idx, row in df.iterrows():
            brand = str(row['Бренд']).strip()
            article = str(row['Артикул']).strip()
            start = perf_counter()

            results, error_msg, total_items, matched_items = await get_price_async(page, brand, article)

            elapsed = perf_counter() - start

            # Обрабатываем результаты
            has_errors = False

            for result_idx, (price, is_price, price_text, product_name, html_content, availability, item_brand, item_article) in enumerate(results):
                # Формируем префикс
                if len(results) > 1:
                    prefix = format_prefix(idx, result_idx, len(results))
                else:
                    prefix = format_prefix(idx, None, 1)
                
                # Для общего времени считаем только первую позицию каждого запроса
                if result_idx == 0:
                    times.append(elapsed)
                
                # Создаём строку для Excel
                result_row = {
                    '№': prefix,
                    'Бренд': brand,
                    'Артикул': article,
                    'Цена_Гиперавто_КнА': price if is_price else None,
                    'Дата и время': datetime.now().strftime('%Y-%m-%d %H:%M'),
                    'Выполнение запроса': f"{elapsed:.1f} сек",
                    'Наличие': availability if availability else "",
                    'Наименование': product_name if product_name else (price_text if not is_price else ""),
                    'Ссылка': f"https://hyperauto.ru/{CITY_SLUG}/search/{brand}/{article}/",
                    'Бренд_карточка': item_brand,
                    'Артикул_карточка': item_article
                }
                all_results.append(result_row)
                
                # Вывод на экран
                if is_price is not False:
                    name_display = f"{brand}/{article}"[:25]
                    price_display = f"{price:,.2f}"[:10]
                    product_name_display = product_name[:70] if len(product_name) > 70 else product_name
                    availability_display = availability[:20] if availability else ""
                    brand_display = item_brand[:10] if item_brand else ""
                    article_display = item_article[:20] if item_article else ""
                    logger.info(f"{prefix:<14} {brand_display:<10} | {article_display:<20} | {name_display:<25} | {price_display:>10} | {elapsed:>6.1f} сек | {availability_display:<20} | {product_name_display}")
                else:
                    name_display = f"{brand}/{article}"[:25]
                    product_name_display = product_name[:70] if len(product_name) > 70 else product_name
                    availability_display = availability[:20] if availability else ""
                    brand_display = item_brand[:10] if item_brand else ""
                    article_display = item_article[:20] if item_article else ""
                    logger.info(f"{prefix:<14} {brand_display:<10} | {article_display:<20} | {name_display:<25} | {'✗':>10} | {elapsed:>6.1f} сек | {availability_display:<20} | {product_name_display}")
                    has_errors = True

            # Сохраняем HTML при ошибках (один файл на итерацию)
            if has_errors and results:
                # Берём HTML из первого результата с ошибкой
                for price, is_price, price_text, product_name, html_content, availability, item_brand, item_article in results:
                    if is_price is False and html_content:
                        # Номер позиции в общем списке
                        position_num = idx + 1
                        # Очищаем название ошибки для имени файла
                        error_name = price_text.replace(':', '').replace('/', '_').replace('\\', '_').replace('<', '_').replace('>', '_').replace('"', '_').replace('|', '_').replace('?', '_').replace('*', '_')[:50]
                        html_filename = f"{position_num}-{brand}-{article}-{error_name}.html"
                        html_filepath = errors_path / html_filename
                        with open(html_filepath, 'w', encoding='utf-8') as f:
                            f.write(html_content)
                        logger.info(f"  → Сохранено: {html_filename}")
                        break

            await page.wait_for_timeout(int(DELAY * 1000))

        total_elapsed = perf_counter() - total_start
        avg_time = sum(times) / len(times) if times else 0

        await browser.close()

    # Создаём DataFrame из всех результатов
    df = pd.DataFrame(all_results)

    # Переупорядочиваем колонки
    df = df[['№', 'Бренд', 'Артикул', 'Бренд_карточка', 'Артикул_карточка', 'Цена_Гиперавто_КнА', 'Дата и время', 'Выполнение запроса', 'Наличие', 'Наименование', 'Ссылка']]

    timestamp = datetime.now().strftime('%Y%m%d_%H%M')
    out = f"{OUTPUT_FILE_PREFIX}_{timestamp}.xlsx"
    df.to_excel(out, index=False)
    
    # Устанавливаем ширину колонок по максимальному содержимому
    try:
        from openpyxl import load_workbook
        wb = load_workbook(out)
        ws = wb.active
        
        # Вычисляем максимальную длину текста в каждой колонке
        for col_idx, col_name in enumerate(df.columns, 1):
            col_letter = chr(64 + col_idx)  # A=65, B=66, etc.
            
            # Находим максимальную длину текста в колонке
            max_length = 0
            for value in df[col_name]:
                if pd.notna(value):
                    text_length = len(str(value))
                    if text_length > max_length:
                        max_length = text_length
            
            # Устанавливаем ширину колонки (максимум 80, минимум 10)
            col_width = min(max(max_length + 2, 10), 80)
            ws.column_dimensions[col_letter].width = col_width
        
        wb.save(out)
        wb.close()
    except Exception as e:
        logger.warning(f"Warning: Could not adjust column widths: {e}")
    
    logger.info(f"\nСохранено → {out}")
    logger.info(f"\n⏱ Всего: {format_time(total_elapsed)} | Среднее на позицию: {format_time(avg_time)}")


if __name__ == "__main__":
    asyncio.run(main_async())
