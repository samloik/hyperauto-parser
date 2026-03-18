📄 Описание кода
Это парсер цен автозапчастей с сайта hyperauto.ru.

Основная логика:
Читает Excel-файл товары.xlsx с колонками Бренд и Артикул
Для каждой пары бренд/артикул:
Формирует поисковый URL вида https://hyperauto.ru/{city}/search/{brand}/{article}/
Открывает страницу в браузере через Playwright
Парсит карточки товаров из списка .product-list__item
Извлекает: цену, наличие, наименование, бренд и артикул из карточки
Фильтрует только те карточки, где бренд и артикул совпадают с запросом
Сохраняет результаты в Excel с timestamp
При ошибках сохраняет HTML страницы в папку Errors/
Технические особенности:
Асинхронный (asyncio + playwright.async_api)
Использует сохранение сессии (cookies.json) для обхода капчи
Логирование через loguru с ротацией 30 дней
Поддержка Docker (headless режим)
Обход детектов ботов (navigator.webdriver)


=====

📁 Структура проекта:

hyperauto-parser/
├── main.py           # Основная логика (180 строк вместо 569)
├── config.py         # Все настройки
├── models.py         # Класс Product + функции проверки
├── utils.py          # Утилиты (форматирование, cookies)
├── browser.py        # BrowserManager класс
├── parser.py         # ProductParser класс
├── Dockerfile        # Обновлён
└── requirements.txt

🔧 Улучшения:
Настройки вынесены в config.py
Классы вместо кортежей — Product dataclass
Модульность — разделение ответственности:
browser.py — управление браузером
parser.py — логика парсинга
models.py — модели данных
utils.py — вспомогательные функции

=====

Все 53 теста прошли успешно.

✅ Выполненные улучшения по тестируемости:
1. Unit-тесты на функции проверки бренд/артикул (40 тестов):
tests/
├── test_models.py          # Тесты моделей и функций проверки
│   ├── TestNormalizeArticle
│   ├── TestValidateArticleMatch
│   ├── TestCheckBrandArticleInName
│   ├── TestCheckBrandArticleInFields
│   ├── TestProduct
│   └── TestParametrized
├── test_parser.py          # Тесты парсера с моками
│   ├── TestProductParser
│   ├── TestHealthCheck
│   ├── TestExtractProductsData
│   └── TestSafeGetHtml
├── conftest.py             # Общие фикстуры
└── __init__.py
2. Моки для Playwright (13 тестов):
mock_page — мок страницы с методами goto, evaluate, query_selector_all
mock_browser, mock_browser_context — моки браузера
Тесты кэширования, health-check, обработки ошибок
3. Запуск тестов:
# Все тесты
pytest tests/ -v

# Только модели
pytest tests/test_models.py -v

# Только парсер
pytest tests/test_parser.py -v

# С покрытием
pytest tests/ --cov=. --cov-report=html
4. Интеграционные тесты:
Для интеграционных тестов с локальным сервером можно использовать pytest с маркером @pytest.mark.integration и запускать их отдельно:

pytest tests/ -m integration


====


