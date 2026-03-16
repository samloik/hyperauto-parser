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


async def get_price_async(page, brand: str, article: str) -> (float, bool, str, str, str):
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
                return (0.0, False, "таймаут ожидания карточек", "", html_content)

            # Приоритет 1: ищем цену в .price.price_big.price_green
            price_green_elements = await page.query_selector_all('.price.price_big.price_green')
            
            # Извлекаем наименование товара
            product_name = ""
            name_element = await page.query_selector('a[title*="' + article + '"], a[title*="' + brand + '"]')
            if name_element:
                product_name = await name_element.get_attribute('title') or await name_element.inner_text()

            for el in price_green_elements:
                text = (await el.inner_text()).strip()
                # Очищаем текст от лишних символов
                price_str = text.replace(' ', '').replace(',', '.').replace('\u2009', '').replace('\xa0', '').replace('₽', '')
                price_str_list = price_str.split('\n')
                if len(price_str_list) > 1:
                    price_str = price_str_list[1]
                else:
                    price_str = price_str_list[0]
                try:
                    price_val = float(price_str)
                    parent_text = await el.evaluate('el => el.closest("article, div[class*=\'card\'], div[class*=\'item\'], .product-card, .catalog-item").innerText')
                    if parent_text and (article.upper() in parent_text.upper() or brand.upper() in parent_text.upper()):
                        return (price_val, True, text.strip(), product_name, "")
                except ValueError:
                    continue

            # Приоритет 2: ищем цену в .product-price-new__price_main
            price_elements = await page.query_selector_all('.product-price-new__price_main')

            last_text = ""
            for el in price_elements:
                text = (await el.inner_text()).strip()
                last_text = text.strip()

                # Проверяем на "Стоимость:" — нужно подождать и попробовать снова
                if text.strip() == "Стоимость:":
                    retry_count += 1
                    if retry_count < max_retries:
                        print(f"  [Попытка {retry_count}/{max_retries}] Найдено 'Стоимость:', ждём и пробуем снова...")
                        await page.wait_for_timeout(3000)
                        break  # выходим из цикла for, переходим на следующую попытку while
                    else:
                        html_content = await page.content()
                        return (0.0, False, "Стоимость: (превышено число попыток)", "", html_content)

                # Очищаем текст от лишних символов
                price_str = text.replace(' ', '').replace(',', '.').replace('\u2009', '').replace('\xa0', '').replace('₽', '')
                price_str_list = price_str.split('\n')
                if len(price_str_list) > 1:
                    price_str = price_str_list[1]
                else:
                    price_str = price_str_list[0]
                try:
                    price_val = float(price_str)
                    # Для точного селектора .product-price-new__price_main возвращаем цену сразу
                    if await el.evaluate('el => el.matches(".product-price-new__price_main")'):
                        return (price_val, True, text.strip(), product_name, "")
                    # Для запасных селекторов проверяем наличие артикула в родительском контейнере
                    parent_text = await el.evaluate('el => el.closest("article, div[class*=\'card\'], div[class*=\'item\'], .product-card, .catalog-item").innerText')
                    if parent_text and (article.upper() in parent_text.upper() or brand.upper() in parent_text.upper()):
                        return (price_val, True, text.strip(), product_name, "")
                except ValueError:
                    continue

            # Если вышли из цикла for из-за "Стоимость:", продолжаем while
            if last_text == "Стоимость:":
                continue

            # Запасной вариант — ищем цену по всей странице
            page_text = await page.inner_text('body')
            # Очищаем текст и ищем цену
            price_str = page_text.replace(' ', '').replace(',', '.').replace('\u2009', '').replace('\xa0', '').replace('₽', '')
            price_str_list = price_str.split('\n')
            if len(price_str_list) > 1:
                price_str = price_str_list[1]
            else:
                price_str = price_str_list[0]
            try:
                return (float(price_str), True, price_str, product_name, "")
            except ValueError:
                pass

            # Возвращаем текст последнего просмотренного элемента
            html_content = await page.content()
            return (0.0, False, last_text if last_text else "элементы цены не найдены", "", html_content)

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
            return (0.0, False, f"ошибка: {str(e)[:50]}", "", html_content)

    return (0.0, False, "превышено число попыток", "", "")


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

        error_counter = 0

        for idx, row in df.iterrows():
            brand = str(row['Бренд']).strip()
            article = str(row['Артикул']).strip()
            start = perf_counter()
            info = f"[{idx+1}/{len(df)}] {brand}/{article}"
            print(f"{info:<80}", end=" | ")

            price, is_price, price_text, product_name, html_content = await get_price_async(page, brand, article)

            elapsed = perf_counter() - start
            times.append(elapsed)

            if is_price is not False:
                df.at[idx, 'Цена_Гиперавто_КнА'] = price
                name_display = f"{brand}/{article}"[:40]
                price_display = f"{price:,.2f}"[:10]
                price_text_display = price_text[:20] if len(price_text) > 20 else price_text
                product_name_display = product_name[:50] if len(product_name) > 50 else product_name
                print(f"{name_display:<40} | {price_display:>10} | {price_text_display:<20} | {elapsed:>10.1f} сек | {product_name_display}")
            else:
                name_display = f"{brand}/{article}"[:40]
                price_text_display = price_text[:20] if len(price_text) > 20 else price_text
                print(f"{name_display:<40} | {'✗':>10} | {price_text_display:<20} | {elapsed:>10.1f} сек | {price_text_display}")
                
                # Сохраняем HTML при ошибках
                if html_content:
                    error_counter += 1
                    # Очищаем название ошибки для имени файла
                    error_name = price_text.replace(':', '').replace('/', '_').replace('\\', '_').replace('<', '_').replace('>', '_').replace('"', '_').replace('|', '_').replace('?', '_').replace('*', '_')[:50]
                    html_filename = f"{error_counter}-{brand}-{article}-{error_name}.html"
                    html_filepath = errors_path / html_filename
                    with open(html_filepath, 'w', encoding='utf-8') as f:
                        f.write(html_content)
                    print(f"  → Сохранено: {html_filename}")

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
