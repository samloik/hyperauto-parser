"""
Конфигурация парсера Hyperauto.
"""
from pathlib import Path
from datetime import timedelta

# ================= ФАЙЛЫ =================
INPUT_FILE = 'товары.xlsx'
OUTPUT_FILE_PREFIX = 'цены_гиперавто'
COOKIES_FILE = 'cookies.json'

# ================= ПАРАМЕТРЫ ПАРСИНГА =================
CITY_SLUG = 'komsomolsk'
DELAY = 5.0               # секунды между запросами товаров
TIMEOUT = 25000           # таймаут загрузки страницы (ms)
MAX_RETRIES = 3           # максимальное число попыток при ошибке
RETRY_DELAY = 3000        # задержка между попытками (ms)

# ================= СЕЛЕКТОРЫ =================
# Основной контейнер списка товаров
PRODUCT_LIST_SELECTOR = '.product-list.product-list_row'
# Элемент товара в списке
PRODUCT_ITEM_SELECTORS = [
    ':scope > .product-list__item',
    '.product-list__item',
    'article',
    'div[class*="card"]',
    'div[class*="item"]',
    '.product-card',
    '.catalog-item',
    'div.product'
]
# Селекторы для элементов внутри карточки
SELECTORS = {
    'price_green': '.price.price_big.price_green',
    'price_main': '.product-price-new__price_main',
    'product_link': 'a[href*="/product/"]',
    'dotted_item': '.dotted-list__item',
    'dotted_value': '.dotted-list__item-value',
    'availability_link': 'a',
    'availability_bold': 'b',
    'delivery_variant': '.block-delivery__variant-main',
    'delivery_label': 'b.mr-4',
}

# ================= ПАПКИ =================
LOGS_DIR = Path('logs')
ERRORS_DIR = Path('Errors')

# ================= ЛОГИРОВАНИЕ =================
LOG_RETENTION = timedelta(days=30)
LOG_FORMAT = "{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
LOG_LEVEL = "INFO"

# ================= БРАУЗЕР =================
VIEWPORT_WIDTH = 1280
VIEWPORT_HEIGHT = 900
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
LOCALE = 'ru-RU'
TIMEZONE_ID = 'Asia/Vladivostok'
SLOW_MO = 500  # задержка для отладки (ms)

# ================= DOCKER =================
DOCKER_ENV_VAR = 'DOCKER_ENV'
PLAYWRIGHT_BROWSERS_PATH_ENV = 'PLAYWRIGHT_BROWSERS_PATH'
DOCKER_BROWSERS_PATH = '/ms-playwright'

# ================= ПРОЧЕЕ =================
RANDOM_DELAY_FACTOR = 0.3  # фактор рандомизации задержки (30% от DELAY)
BASE_DELAY = 2000  # базовая задержка после загрузки страницы (ms)
