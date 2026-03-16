# main.py
import asyncio
import pandas as pd
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from datetime import datetime
import os
from time import perf_counter
from pathlib import Path

# ================= НАСТРОЙКИ =================
INPUT_FILE = 'товары.xlsx'
OUTPUT_FILE_PREFIX = 'цены_гиперавто'
CITY_SLUG = 'komsomolsk'
DELAY = 5.0               # сек между товарами
TIMEOUT = 25000           # ms
COOKIES_FILE = 'cookies.json'  # файл с сессией (cookies)
ERRORS_DIR = 'Errors'      # папка для сохранения HTML при ошибках


async def get_price_async(page, brand: str, article: str) -> (list, str, int, int):
    """
    Возвращает:
    - list кортежей (price, is_price, price_text, product_name, html_content)
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
                print(f"    Таймаут ожидания карточек для {brand}/{article}")
                html_content = await page.content()
                return [(0.0, False, "таймаут ожидания карточек", "", html_content)], "таймаут", 0, 0

            # Находим контейнер со списком товаров
            product_list = await page.query_selector('.product-list.product-list_row')
            
            # Если нашли список - берём элементы внутри него, иначе ищем все карточки на странице
            if product_list:
                # Ищем .product-list__item как основные карточки
                product_cards = await product_list.query_selector_all(':scope > .product-list__item')
            else:
                product_cards = await page.query_selector_all('.product-list__item, article, div[class*="card"], div[class*="item"], .product-card, .catalog-item, div.product')
            
            total_items = len(product_cards)

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
                return brand_upper in name_upper and article_upper in name_upper

            results = []
            matched_count = 0

            for card in product_cards:
                # Извлекаем наименование товара из карточки
                product_name = ""
                # Ищем ссылку внутри .product-card__title или по атрибутам
                name_element = await card.query_selector('.product-card__title a, a[title], a[href*="/product/"]')
                if name_element:
                    product_name = await name_element.get_attribute('title') or await name_element.inner_text()

                # Ищем цену в карточке
                price_val = 0.0
                price_text = ""
                is_price = False

                # Находим .product-card внутри .product-list__item (если это .product-list__item)
                product_card = await card.query_selector('.product-card')
                search_context = product_card if product_card else card

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
                        if text.strip() == "Стоимость:":
                            continue
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

                # Проверяем соответствие бренда и артикула
                if check_brand_article_in_name(product_name, brand, article):
                    matched_count += 1
                    results.append((price_val, is_price, price_text, product_name, ""))
                elif product_name:  # Если есть наименование, но нет совпадения
                    # Добавляем в результаты как позицию без цены (ошибка)
                    results.append((0.0, False, "нет Бренда и Артикула", product_name, ""))

            # Возвращаем все найденные позиции и количество совпавших
            if results:
                return results, "", total_items, matched_count
            else:
                # Если карточки не найдены
                html_content = await page.content()
                return [(0.0, False, "элементы не найдены", "", html_content)], "элементы не найдены", 0, 0

        except Exception as e:
            print(f"    Ошибка при {brand} {article}: {str(e)[:120]}...")
            retry_count += 1
            if retry_count < max_retries:
                await page.wait_for_timeout(3000)
                continue
            try:
                html_content = await page.content()
            except:
                html_content = "<html><body>Не удалось получить HTML</body></html>"
            return [(0.0, False, f"ошибка: {str(e)[:50]}", "", html_content)], f"ошибка: {str(e)[:50]}", 0, 0

    return [(0.0, False, "превышено число попыток", "", "")], "превышено число попыток", 0, 0


async def main_async():

    # Определяем режим запуска (headless для Docker)
    headless = os.environ.get('DOCKER_ENV', '0') == '1'

    print("Попытка запуска браузера Playwright...")
    try:
        async with async_playwright() as p:
            print("Playwright инициализирован")
            browser = await p.chromium.launch(headless=headless, slow_mo=500)
            print("Браузер запущен")
            # ... дальше контекст и страница
    except Exception as e:
        print(f"Критическая ошибка Playwright: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()


    print("=== Запуск парсера Гиперавто (Playwright) ===")
    print(f"Текущая папка: {os.getcwd()}")
    print(f"Ищем файл: {INPUT_FILE}")
    
    if not os.path.exists(INPUT_FILE):
        print(f"ОШИБКА: файл {INPUT_FILE} НЕ НАЙДЕН в {os.getcwd()}")
        print("Создайте файл с колонками 'Бренд' и 'Артикул'")
        return
    
    print("Файл найден → читаем...")
    try:
        df = pd.read_excel(INPUT_FILE)
        print(f"Прочитано строк: {len(df)}")
        print(df.head().to_string())
    except Exception as e:
        print(f"Ошибка чтения Excel: {e}")
        return
    
    if 'Бренд' not in df.columns or 'Артикул' not in df.columns:
        print("ОШИБКА: в файле нет колонок 'Бренд' и/или 'Артикул'")
        return
    
    print("Колонки в порядке → запускаем браузер...")

    df['Цена_Гиперавто_КнА'] = None
    df['Дата'] = datetime.now().strftime('%Y-%m-%d %H:%M')

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
            print(f"✓ Загружаем сессию из {COOKIES_FILE}")
        except Exception as e:
            print(f"⚠ Ошибка загрузки {COOKIES_FILE}: {e}")
            print("  Удалите файл и запустите заново для создания новой сессии")
    else:
        print(f"⚠ Файл {COOKIES_FILE} не найден — сессия не будет загружена")
        print("  После первого запуска (с ручным прохождением капчи) сессия сохранится автоматически")

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
            print("\n>>> Открой https://hyperauto.ru в этой вкладке и пройди капчу!")
            print(">>> После этого нажми Enter в консоли...")
            input()
            await page.goto("https://hyperauto.ru/", wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)
            await context.storage_state(path=COOKIES_FILE)
            print(f"✓ Сессия сохранена в {COOKIES_FILE}")
            print("  Следующие запуски пройдут без капчи!\n")

        total_start = perf_counter()
        times = []

        # Создаём папку для ошибок
        errors_path = Path(ERRORS_DIR)
        errors_path.mkdir(exist_ok=True)

        for idx, row in df.iterrows():
            brand = str(row['Бренд']).strip()
            article = str(row['Артикул']).strip()
            start = perf_counter()
            info = f"[{idx+1}/{len(df)}] {brand}/{article}"
            print(f"{info:<80}", end=" | ")

            results, error_msg, total_items, matched_items = await get_price_async(page, brand, article)

            elapsed = perf_counter() - start
            times.append(elapsed)

            # Выводим информацию о количестве позиций
            if total_items > 0:
                count_info = f"[{matched_items}/{total_items}]"
            else:
                count_info = ""

            # Обрабатываем результаты
            first_price_set = False
            has_errors = False

            for result_idx, (price, is_price, price_text, product_name, html_content) in enumerate(results):
                if is_price is not False:
                    if not first_price_set:
                        # Первую цену записываем в DataFrame
                        df.at[idx, 'Цена_Гиперавто_КнА'] = price
                        first_price_set = True

                    name_display = f"{brand}/{article}"[:40]
                    price_display = f"{price:,.2f}"[:10]
                    price_text_display = price_text[:20] if len(price_text) > 20 else price_text
                    product_name_display = product_name[:50] if len(product_name) > 50 else product_name
                    # Если несколько позиций, добавляем номер
                    if len(results) > 1:
                        print(f"{count_info}[{result_idx+1}] {name_display:<40} | {price_display:>10} | {price_text_display:<20} | {elapsed:>10.1f} сек | {product_name_display}")
                    else:
                        print(f"{count_info} {name_display:<40} | {price_display:>10} | {price_text_display:<20} | {elapsed:>10.1f} сек | {product_name_display}")
                else:
                    name_display = f"{brand}/{article}"[:40]
                    price_text_display = price_text[:20] if len(price_text) > 20 else price_text
                    product_name_display = product_name[:50] if len(product_name) > 50 else product_name
                    # Если несколько позиций, добавляем номер
                    if len(results) > 1:
                        print(f"{count_info}[{result_idx+1}] {name_display:<40} | {'✗':>10} | {price_text_display:<20} | {elapsed:>10.1f} сек | {product_name_display}")
                    else:
                        print(f"{count_info} {name_display:<40} | {'✗':>10} | {price_text_display:<20} | {elapsed:>10.1f} сек | {product_name_display}")
                    has_errors = True

            # Сохраняем HTML при ошибках (один файл на итерацию)
            if has_errors and results:
                # Берём HTML из первого результата с ошибкой
                for price, is_price, price_text, product_name, html_content in results:
                    if is_price is False and html_content:
                        # Номер позиции в общем списке
                        position_num = idx + 1
                        # Очищаем название ошибки для имени файла
                        error_name = price_text.replace(':', '').replace('/', '_').replace('\\', '_').replace('<', '_').replace('>', '_').replace('"', '_').replace('|', '_').replace('?', '_').replace('*', '_')[:50]
                        html_filename = f"{position_num}-{brand}-{article}-{error_name}.html"
                        html_filepath = errors_path / html_filename
                        with open(html_filepath, 'w', encoding='utf-8') as f:
                            f.write(html_content)
                        print(f"  → Сохранено: {html_filename}")
                        break

            await page.wait_for_timeout(int(DELAY * 1000))

        total_elapsed = perf_counter() - total_start
        avg_time = sum(times) / len(times) if times else 0

        await browser.close()

    timestamp = datetime.now().strftime('%Y%m%d_%H%M')
    out = f"{OUTPUT_FILE_PREFIX}_{timestamp}.xlsx"
    df.to_excel(out, index=False)
    print(f"\nСохранено → {out}")
    print(f"\n⏱ Всего: {total_elapsed:.1f} сек | Среднее на позицию: {avg_time:.1f} сек")


if __name__ == "__main__":
    asyncio.run(main_async())
