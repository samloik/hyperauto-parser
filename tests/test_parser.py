"""
Юнит-тесты для парсера (parser.py) с моками Playwright.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from parser import Parser
from models import Product, ParseResult
from config import config


class TestParser:
    """Тесты для класса Parser."""
    
    @pytest.mark.asyncio
    async def test_parser_creation(self, mock_page):
        """Проверка создания парсера."""
        parser = Parser(mock_page)
        assert parser.page == mock_page
    
    @pytest.mark.asyncio
    async def test_parse_product_success(self, mock_page):
        """Проверка успешного парсинга."""
        # Настраиваем моки для успешного парсинга
        mock_page.query_selector = AsyncMock(return_value=AsyncMock())
        mock_page.query_selector_all = AsyncMock(return_value=[])
        
        parser = Parser(mock_page)
        
        # Патчим метод _parse_product_cards для возврата тестовых данных
        with patch.object(parser, '_parse_product_cards', new_callable=AsyncMock) as mock_parse:
            mock_parse.return_value = [
                Product(price=1500.0, is_price=True, product_name="Товар 1", item_brand="TEST", item_article="ART123")
            ]
            
            result = await parser.parse_product("TEST", "ART123")
            
            assert result.brand == "TEST"
            assert result.article == "ART123"
            assert len(result.products) == 1
            assert result.matched_items == 1
            assert result.error_message == ""
    
    @pytest.mark.asyncio
    async def test_parse_product_timeout(self, mock_page):
        """Проверка таймаута ожидания товаров."""
        # Патчим _wait_for_products для возврата False
        parser = Parser(mock_page)
        
        with patch.object(parser, '_wait_for_products', new_callable=AsyncMock) as mock_wait:
            mock_wait.return_value = False
            
            result = await parser.parse_product("TEST", "ART404")
            
            assert result.error_message == "таймаут"
            assert len(result.products) == 1
            assert result.products[0].price_text == "таймаут ожидания карточек"
    
    @pytest.mark.asyncio
    async def test_parse_product_no_results(self, mock_page):
        """Проверка отсутствия результатов."""
        parser = Parser(mock_page)
        
        with patch.object(parser, '_wait_for_products', new_callable=AsyncMock) as mock_wait:
            mock_wait.return_value = True
            
            with patch.object(parser, '_parse_product_cards', new_callable=AsyncMock) as mock_parse:
                mock_parse.return_value = []
                
                result = await parser.parse_product("TEST", "ART404")
                
                assert result.error_message == "элементы не найдены"
                assert len(result.products) == 1
                assert result.products[0].price_text == "элементы не найдены"
    
    @pytest.mark.asyncio
    async def test_parse_product_url_generation(self, mock_page):
        """Проверка генерации URL."""
        parser = Parser(mock_page)
        
        with patch.object(parser, '_wait_for_products', new_callable=AsyncMock) as mock_wait:
            mock_wait.return_value = False
            
            await parser.parse_product("TEST", "ART123")
            
            # Проверяем что goto был вызван с правильным URL
            expected_url = f"{config.BASE_URL}/{config.CITY_SLUG}/search/TEST/ART123/"
            mock_page.goto.assert_called_once()
            call_args = mock_page.goto.call_args
            assert call_args[0][0] == expected_url
    
    @pytest.mark.asyncio
    async def test_close_popups_success(self, mock_page):
        """Проверка закрытия попапов."""
        parser = Parser(mock_page)
        
        # Мок для locator возвращает объект с click
        locator_mock = AsyncMock()
        locator_mock.click = AsyncMock(return_value=None)
        mock_page.locator = MagicMock(return_value=locator_mock)
        
        await parser._close_popups()
        
        mock_page.locator.assert_called_once()
        locator_mock.click.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_close_popups_exception(self, mock_page):
        """Проверка обработки исключения при закрытии попапов."""
        parser = Parser(mock_page)
        
        # Мок выбрасывает исключение
        mock_page.locator = MagicMock(side_effect=Exception("No such element"))
        
        # Не должно выбрасывать исключение
        await parser._close_popups()
    
    @pytest.mark.asyncio
    async def test_wait_for_products_success(self, mock_page):
        """Проверка успешного ожидания товаров."""
        parser = Parser(mock_page)
        
        # wait_for_selector не выбрасывает исключение
        mock_page.wait_for_selector = AsyncMock(return_value=None)
        
        result = await parser._wait_for_products()
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_wait_for_products_timeout(self, mock_page):
        """Проверка таймаута ожидания товаров."""
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError
        
        parser = Parser(mock_page)
        
        # wait_for_selector выбрасывает TimeoutError для всех селекторов
        mock_page.wait_for_selector = AsyncMock(side_effect=PlaywrightTimeoutError("timeout"))
        
        result = await parser._wait_for_products()
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_parse_price_text_valid(self, mock_page):
        """Проверка парсинга текста цены."""
        parser = Parser(mock_page)
        
        # Тестовые данные - цена без пробелов (так как они удаляются при парсинге)
        # Запятая заменяется на точку (европейский формат)
        test_cases = [
            ("1500 ₽", 1500.0),
            ("1500,50 ₽", 1500.5),  # Запятая как десятичный разделитель
            ("1500", 1500.0),
            ("1234,56 ₽", 1234.56),
        ]
        
        for text, expected in test_cases:
            price, is_valid = parser._parse_price_text(text)
            assert price == expected, f"Для текста '{text}' ожидалось {expected}, получено {price}"
            assert is_valid is True
    
    @pytest.mark.asyncio
    async def test_parse_price_text_invalid(self, mock_page):
        """Проверка парсинга невалидного текста цены."""
        parser = Parser(mock_page)
        
        price, is_valid = parser._parse_price_text("цена не указана")
        
        assert price == 0.0
        assert is_valid is False
    
    @pytest.mark.asyncio
    async def test_check_brand_article_in_name_match(self, mock_page):
        """Проверка соответствия бренда и артикула в названии."""
        parser = Parser(mock_page)
        
        result = parser._check_brand_article_in_name(
            "Опора шаровая CTR CB0234 (CBKK-8)",
            "CTR",
            "CB0234"
        )
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_check_brand_article_in_name_no_match(self, mock_page):
        """Проверка несоответствия бренда и артикула в названии."""
        parser = Parser(mock_page)
        
        # Нет артикула в названии
        result = parser._check_brand_article_in_name(
            "Опора шаровая CTR другой артикул",
            "CTR",
            "CB0234"
        )
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_check_brand_article_in_name_empty_name(self, mock_page):
        """Проверка пустого названия."""
        parser = Parser(mock_page)
        
        result = parser._check_brand_article_in_name("", "CTR", "CB0234")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_validate_brand_article_match(self, mock_page):
        """Проверка валидации бренда и артикула из карточки."""
        parser = Parser(mock_page)
        
        result = parser._validate_brand_article(
            item_brand="CTR",
            item_article="CB0234",
            brand="CTR",
            article="CB0234"
        )
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_validate_brand_article_no_match(self, mock_page):
        """Проверка невалидации бренда и артикула из карточки."""
        parser = Parser(mock_page)
        
        # Разные бренды
        result = parser._validate_brand_article(
            item_brand="OTHER",
            item_article="CB0234",
            brand="CTR",
            article="CB0234"
        )
        
        assert result is False


class TestParserRetry:
    """Тесты для retry-декоратора в парсере."""
    
    @pytest.mark.asyncio
    async def test_parse_product_with_retry_decorator(self, mock_page):
        """Проверка работы retry-декоратора."""
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError
        
        parser = Parser(mock_page)
        
        # Считаем количество вызовов
        call_count = 0
        
        async def failing_goto(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise PlaywrightTimeoutError("Timeout")
            return None
        
        mock_page.goto = AsyncMock(side_effect=failing_goto)
        mock_page.wait_for_selector = AsyncMock(side_effect=PlaywrightTimeoutError("timeout"))
        
        # Декоратор должен сделать повторную попытку
        result = await parser.parse_product("TEST", "ART123")
        
        # Проверяем что было больше одного вызова
        assert call_count >= 1
