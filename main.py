# main.py
import asyncio
import pandas as pd
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from datetime import datetime
import re
import os
import time
from time import perf_counter

# ================= НАСТРОЙКИ =================
INPUT_FILE = 'товары.xlsx'
OUTPUT_FILE_PREFIX = 'цены_гиперавто'
CITY_SLUG = 'komsomolsk'
DELAY = 5.0               # сек между товарами
TIMEOUT = 25000           # ms
COOKIES_FILE = 'cookies.json'  # файл с сессией (cookies)

# Регулярка для цены
PRICE_RE = re.compile(r'(\d[\d\s.,]*)\s*₽')

async def get_price_async(page, brand: str, article: str) -> (float, bool):
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
            print(f"    Таймаут ожидания карточек для {brand} {article}")
            return (0.0, False)

        # Собираем все потенциальные блоки с ценой
        price_elements = await page.query_selector_all('.price, .current-price, .product-price, [class*="price"], span.price, div.price-amount')
        
        for el in price_elements:
            text = (await el.inner_text()).strip()
            match = PRICE_RE.search(text)
            if match:
                # price_str = match.group(1).replace(' ', '').replace(',', '.').replace('\u2009', '').split('\n')[1]
                price_str_list = match.group(1).replace(' ', '').replace(',', '.').replace('\u2009', '').replace('\xa0', '').split('\n')  # убираем пробелы и переносы
                if len(price_str_list)>1:
                    price_str = price_str_list[1]
                else:
                    price_str = price_str_list[0]
                # print(f'[!] {match=}   |||  {price_str=}')
                try:
                    price_val = float(price_str)
                    # Дополнительная проверка — артикул должен быть где-то рядом
                    parent_text = await el.evaluate('el => el.closest("article, div[class*=\'card\'], div[class*=\'item\']").innerText')
                    if parent_text and (article.upper() in parent_text.upper() or brand.upper() in parent_text.upper()):
                        return (price_val, True)
                except ValueError:
                    continue

        # Запасной вариант — ищем цену по всей странице
        page_text = await page.inner_text('body')
        match = PRICE_RE.search(page_text)
        if match:
            # price_str = match.group(1).replace(' ', '').replace(',', '.').replace('\u2009', '').split('\n')[1]
            price_str_list = match.group(1).replace(' ', '').replace(',', '.').replace('\u2009', '').replace('\xa0', '').split('\n')  # убираем пробелы и переносы
            if len(price_str_list)>1:
                price_str = price_str_list[1]
            else:
                price_str = price_str_list[0]
            # print(f'[+] {match=}   |  [{price_str=}]')
            return (float(price_str), True)

        return (0.0, False)

    except Exception as e:
        print(f"    Ошибка при {brand} {article}: {str(e)[:120]}...")
        # print(f'[?] {match=}   |||  {price_str=}')
        return (0.0, False)


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

        for idx, row in df.iterrows():
            brand = str(row['Бренд']).strip()
            article = str(row['Артикул']).strip()
            start = perf_counter()
            print(f"[{idx+1}/{len(df)}] {brand}/{article}", end=" ... ")

            price, is_price = await get_price_async(page, brand, article)

            elapsed = perf_counter() - start
            times.append(elapsed)

            if is_price is not False:
                df.at[idx, 'Цена_Гиперавто_КнА'] = price
                print(f"{price} ₽ [{elapsed:.1f} сек]")
            else:
                print(f"✗ не найдено [{elapsed:.1f} сек]")

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
