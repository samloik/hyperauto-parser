import os
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"

from playwright.sync_api import sync_playwright

print("Тест с глобальным путём...")

try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        print("SUCCESS!")
        print("Версия:", browser.version)
        browser.close()
except Exception as e:
    print("Ошибка:", str(e))