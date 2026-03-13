# main.py
import asyncio
import pandas as pd
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from datetime import datetime
import re
import os
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"
import time

# ================= НАСТРОЙКИ =================
INPUT_FILE = 'товары.xlsx'
OUTPUT_FILE_PREFIX = 'цены_гиперавто'
CITY_SLUG = 'komsomolsk'
DELAY = 5.0               # сек между товарами
TIMEOUT = 25000           # ms

# Регулярка для цены
PRICE_RE = re.compile(r'(\d[\d\s.,]*)\s*₽')

async def get_price_async(page, brand: str, article: str) -> float | None:
    try:
        query = f"{brand} {article}".strip()
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
            return None

        # Собираем все потенциальные блоки с ценой
        price_elements = await page.query_selector_all('.price, .current-price, .product-price, [class*="price"], span.price, div.price-amount')
        
        for el in price_elements:
            text = (await el.inner_text()).strip()
            match = PRICE_RE.search(text)
            if match:
                price_str = match.group(1).replace(' ', '').replace(',', '.').replace('\u2009', '')
                # print(f'[!] {match=}   |||  {price_str=}')
                try:
                    price_val = float(price_str)
                    # Дополнительная проверка — артикул должен быть где-то рядом
                    parent_text = await el.evaluate('el => el.closest("article, div[class*=\'card\'], div[class*=\'item\']").innerText')
                    if parent_text and (article.upper() in parent_text.upper() or brand.upper() in parent_text.upper()):
                        return price_val
                except ValueError:
                    continue

        # Запасной вариант — ищем цену по всей странице
        page_text = await page.inner_text('body')
        match = PRICE_RE.search(page_text)
        if match:
            price_str = match.group(1).replace(' ', '').replace(',', '.').replace('\u2009', '')
            # print(f'[+] {match=}   |  [{price_str=}]')
            return float(price_str)

        return None

    except Exception as e:
        print(f"    Ошибка при {brand} {article}: {str(e)[:120]}...")
        # print(f'[?] {match=}   |||  {price_str=}')
        return None


async def main_async():
    # print("=== Парсер Гиперавто (Playwright) — Комсомольск-на-Амуре ===")

    # if not os.path.exists(INPUT_FILE):
    #     print(f"Файл {INPUT_FILE} не найден!")
    #     return

    # df = pd.read_excel(INPUT_FILE)
    # if 'Бренд' not in df.columns or 'Артикул' not in df.columns:
    #     print("Нужны колонки 'Бренд' и 'Артикул'")
    #     return

    print("Попытка запуска браузера Playwright...")
    try:
        async with async_playwright() as p:
            print("Playwright инициализирован")
            browser = await p.chromium.launch(headless=False, slow_mo=500)
            print("Браузер запущен (видимый режим)")
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
    # ... остальной код без изменений

    df['Цена_Гиперавто_КнА'] = None
    df['Дата'] = datetime.now().strftime('%Y-%m-%d %H:%M')

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # visible для отладки; потом True
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 900},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            locale='ru-RU',
            timezone_id='Asia/Vladivostok',
        )
        page = await context.new_page()

        # Обход некоторых детектов
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)

        for idx, row in df.iterrows():
            brand = str(row['Бренд']).strip()
            article = str(row['Артикул']).strip()
            print(f"[{idx+1}/{len(df)}] {brand} {article}")

            price = await get_price_async(page, brand, article)

            if price is not None:
                df.at[idx, 'Цена_Гиперавто_КнА'] = price
                print(f"    → {price} ₽")
            else:
                print("    ✗ не найдено")

            await page.wait_for_timeout(int(DELAY * 1000))

        await browser.close()

    timestamp = datetime.now().strftime('%Y%m%d_%H%M')
    out = f"{OUTPUT_FILE_PREFIX}_{timestamp}.xlsx"
    df.to_excel(out, index=False)
    print(f"\nСохранено → {out}")


if __name__ == "__main__":
    asyncio.run(main_async())
