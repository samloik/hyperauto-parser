"""
Фикстуры для тестов парсера Hyperauto.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, PropertyMock
from datetime import datetime

from models import Product, ParseResult, ParseStats
from config import config


# ==================== Фикстуры для моделей ====================

@pytest.fixture
def sample_product():
    """Создаёт тестовый продукт."""
    return Product(
        price=1500.0,
        is_price=True,
        price_text="1 500 ₽",
        product_name="Товар тестовый",
        availability="В наличии",
        item_brand="TEST",
        item_article="ART123",
        html_content=""
    )


@pytest.fixture
def sample_product_error():
    """Создаёт тестовый продукт с ошибкой."""
    return Product(
        price=0.0,
        is_price=False,
        price_text="элементы не найдены",
        product_name="",
        availability="",
        item_brand="",
        item_article="",
        html_content="<html>error</html>"
    )


@pytest.fixture
def sample_parse_result():
    """Создаёт тестовый результат парсинга."""
    return ParseResult(
        brand="TEST",
        article="ART123",
        products=[
            Product(price=1500.0, is_price=True, price_text="1 500 ₽", product_name="Товар 1"),
            Product(price=2000.0, is_price=True, price_text="2 000 ₽", product_name="Товар 2"),
        ],
        error_message="",
        total_items=2,
        matched_items=2,
        elapsed_time=5.5,
        timestamp=datetime.now(),
        url="https://hyperauto.ru/komsomolsk/search/TEST/ART123/"
    )


@pytest.fixture
def sample_parse_result_error():
    """Создаёт тестовый результат парсинга с ошибкой."""
    return ParseResult(
        brand="TEST",
        article="ART404",
        products=[Product(price_text="элементы не найдены")],
        error_message="элементы не найдены",
        total_items=0,
        matched_items=0,
        elapsed_time=10.0,
        timestamp=datetime.now(),
        url="https://hyperauto.ru/komsomolsk/search/TEST/ART404/"
    )


@pytest.fixture
def sample_parse_stats():
    """Создаёт тестовую статистику."""
    stats = ParseStats(error_threshold=50.0)
    stats.total_items = 10
    stats.success_items = 8
    stats.error_items = 2
    stats.times = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    stats.total_time = 55.0
    return stats


# ==================== Фикстуры для Playwright ====================

@pytest.fixture
def mock_page():
    """Создаёт мок страницы Playwright."""
    page = AsyncMock()
    
    # Настраиваем основные методы
    page.goto = AsyncMock(return_value=None)
    page.wait_for_timeout = AsyncMock(return_value=None)
    page.wait_for_selector = AsyncMock(return_value=None)
    page.content = AsyncMock(return_value="<html><body>test</body></html>")
    page.screenshot = AsyncMock(return_value=None)
    
    # Мок для locator
    locator_mock = AsyncMock()
    locator_mock.click = AsyncMock(return_value=None)
    page.locator = MagicMock(return_value=locator_mock)
    
    # Мок для query_selector
    async def mock_query_selector(selector):
        element = AsyncMock()
        element.get_attribute = AsyncMock(return_value=None)
        element.inner_text = AsyncMock(return_value="")
        element.query_selector = AsyncMock(return_value=None)
        element.query_selector_all = AsyncMock(return_value=[])
        return element
    
    page.query_selector = AsyncMock(side_effect=mock_query_selector)
    page.query_selector_all = AsyncMock(return_value=[])
    
    # Мок для add_init_script
    page.add_init_script = AsyncMock(return_value=None)
    
    return page


@pytest.fixture
def mock_browser_context():
    """Создаёт мок контекста браузера."""
    context = AsyncMock()
    context.storage_state = AsyncMock(return_value={'cookies': []})
    context.new_page = AsyncMock()
    return context


@pytest.fixture
def mock_browser():
    """Создаёт мок браузера."""
    browser = AsyncMock()
    browser.new_context = AsyncMock()
    browser.close = AsyncMock(return_value=None)
    return browser


@pytest.fixture
def mock_playwright():
    """Создаёт мок Playwright."""
    playwright = AsyncMock()
    playwright.chromium = AsyncMock()
    playwright.chromium.launch = AsyncMock()
    playwright.stop = AsyncMock(return_value=None)
    return playwright


# ==================== Фикстуры для конфигурации ====================

@pytest.fixture
def test_config():
    """Создаёт тестовую конфигурацию."""
    class TestConfig:
        INPUT_FILE = config.INPUT_FILE
        OUTPUT_FILE_PREFIX = "test_output"
        COOKIES_FILE = config.COOKIES_FILE
        CITY_SLUG = "test-city"
        BASE_URL = "https://test.hyperauto.ru"
        DELAY = 1.0
        TIMEOUT = 5000
        PAGE_LOAD_TIMEOUT = 3000
        MAX_RETRIES = 2
        RETRY_DELAY = 1.0
        ERROR_THRESHOLD = 50.0
    
    return TestConfig()


# ==================== Фикстуры для aiohttp ====================

@pytest.fixture
def mock_aiohttp_session():
    """Создаёт мок aiohttp сессии."""
    session = AsyncMock()
    
    response = AsyncMock()
    response.status = 200
    response.text = AsyncMock(return_value="<html>test</html>")
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=None)
    
    session.get = MagicMock(return_value=response)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    
    return session
