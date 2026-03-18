"""
Юнит-тесты для моделей (models.py).
"""
import pytest
from datetime import datetime

from models import Product, ParseResult, ParseStats


class TestProduct:
    """Тесты для класса Product."""
    
    def test_product_creation(self, sample_product):
        """Проверка создания продукта."""
        assert sample_product.price == 1500.0
        assert sample_product.is_price is True
        assert sample_product.price_text == "1 500 ₽"
        assert sample_product.product_name == "Товар тестовый"
        assert sample_product.availability == "В наличии"
        assert sample_product.item_brand == "TEST"
        assert sample_product.item_article == "ART123"
    
    def test_product_has_error_false(self, sample_product):
        """Проверка has_error для продукта с ценой."""
        assert sample_product.has_error is False
    
    def test_product_has_error_true(self, sample_product_error):
        """Проверка has_error для продукта с ошибкой."""
        assert sample_product_error.has_error is True
    
    def test_product_to_dict(self, sample_product):
        """Проверка метода to_dict."""
        result = sample_product.to_dict()
        assert result['price'] == 1500.0
        assert result['price_text'] == "1 500 ₽"
        assert result['product_name'] == "Товар тестовый"
        assert result['availability'] == "В наличии"
        assert result['item_brand'] == "TEST"
        assert result['item_article'] == "ART123"
    
    def test_product_default_values(self):
        """Проверка значений по умолчанию."""
        product = Product()
        assert product.price == 0.0
        assert product.is_price is False
        assert product.price_text == ""
        assert product.product_name == ""
        assert product.has_error is True  # Нет цены и имени


class TestParseResult:
    """Тесты для класса ParseResult."""
    
    def test_parse_result_creation(self, sample_parse_result):
        """Проверка создания результата парсинга."""
        assert sample_parse_result.brand == "TEST"
        assert sample_parse_result.article == "ART123"
        assert len(sample_parse_result.products) == 2
        assert sample_parse_result.total_items == 2
        assert sample_parse_result.matched_items == 2
        assert sample_parse_result.error_message == ""
    
    def test_parse_result_has_errors_false(self, sample_parse_result):
        """Проверка has_errors при успешном парсинге."""
        assert sample_parse_result.has_errors is False
    
    def test_parse_result_has_errors_true(self, sample_parse_result_error):
        """Проверка has_errors при ошибке парсинга."""
        # has_errors возвращает error_message или False
        assert sample_parse_result_error.has_errors  # "элементы не найдены" - truthy
    
    def test_parse_result_to_excel_rows(self, sample_parse_result):
        """Проверка метода to_excel_rows."""
        rows = sample_parse_result.to_excel_rows(row_number=0, total_len=10)
        
        assert len(rows) == 2  # Два продукта
        
        # Проверка первой строки
        assert rows[0]['Бренд'] == "TEST"
        assert rows[0]['Артикул'] == "ART123"
        # Формат префикса: [01/10][1] для первого продукта из 2
        assert "/10]" in rows[0]['№']
        assert "][1]" in rows[0]['№']
        
        # Проверка второй строки (с подномером)
        sample_parse_result.products.append(Product(price=3000.0, is_price=True))
        rows = sample_parse_result.to_excel_rows(row_number=0, total_len=10)
        assert len(rows) == 3
        assert "/10]" in rows[1]['№']
        assert "][2]" in rows[1]['№']
    
    def test_parse_result_empty_products(self):
        """Проверка с пустым списком продуктов."""
        result = ParseResult(brand="TEST", article="ART123")
        assert result.has_errors is False  # Нет продуктов - нет ошибок
        assert result.to_excel_rows(0, 10) == []


class TestParseStats:
    """Тесты для класса ParseStats."""
    
    def test_parse_stats_creation(self, sample_parse_stats):
        """Проверка создания статистики."""
        assert sample_parse_stats.total_items == 10
        assert sample_parse_stats.success_items == 8
        assert sample_parse_stats.error_items == 2
    
    def test_parse_stats_avg_time(self, sample_parse_stats):
        """Проверка среднего времени."""
        assert sample_parse_stats.avg_time == 5.5  # (1+2+...+10)/10
    
    def test_parse_stats_success_rate(self, sample_parse_stats):
        """Проверка процента успеха."""
        assert sample_parse_stats.success_rate == 80.0  # 8/10 * 100
    
    def test_parse_stats_error_rate(self, sample_parse_stats):
        """Проверка процента ошибок."""
        assert sample_parse_stats.error_rate == 20.0  # 2/10 * 100
    
    def test_parse_stats_add_result_success(self):
        """Проверка добавления успешного результата."""
        stats = ParseStats()
        result = ParseResult(brand="TEST", article="ART123", products=[Product(price=100.0, is_price=True)])
        result.elapsed_time = 5.0
        
        stats.add_result(result)
        
        assert stats.total_items == 1
        assert stats.success_items == 1
        assert stats.error_items == 0
        assert 5.0 in stats.times
    
    def test_parse_stats_add_result_error(self):
        """Проверка добавления результата с ошибкой."""
        stats = ParseStats()
        result = ParseResult(brand="TEST", article="ART404", products=[Product(price_text="error")])
        result.error_message = "error"
        result.elapsed_time = 10.0
        
        stats.add_result(result)
        
        assert stats.total_items == 1
        assert stats.success_items == 0
        assert stats.error_items == 1
    
    def test_parse_stats_alert_threshold(self):
        """Проверка срабатывания алерта при превышении порога."""
        stats = ParseStats(error_threshold=50.0)
        
        # Добавляем 5 ошибок из 5 (100% > 50%)
        for i in range(5):
            result = ParseResult(
                brand="TEST",
                article=f"ART{i}",
                products=[Product(price_text="error")],
                error_message="error"
            )
            stats.add_result(result)
        
        assert stats.should_alert() is True
    
    def test_parse_stats_alert_under_threshold(self):
        """Проверка отсутствия алерта при пороге ниже 5 запросов."""
        stats = ParseStats(error_threshold=50.0)
        
        # Добавляем 3 ошибки из 3 (100% но меньше 5 запросов)
        for i in range(3):
            result = ParseResult(
                brand="TEST",
                article=f"ART{i}",
                products=[Product(price_text="error")],
                error_message="error"
            )
            stats.add_result(result)
        
        assert stats.should_alert() is False
    
    def test_parse_stats_get_summary(self, sample_parse_stats):
        """Проверка метода get_summary."""
        summary = sample_parse_stats.get_summary()
        
        assert summary['total_items'] == 10
        assert summary['success_items'] == 8
        assert summary['error_items'] == 2
        assert summary['success_rate'] == 80.0
        assert summary['error_rate'] == 20.0
        assert summary['avg_time'] == 5.5
        assert summary['alert_triggered'] is False
    
    def test_parse_stats_empty(self):
        """Проверка статистики с нулевыми значениями."""
        stats = ParseStats()
        
        assert stats.avg_time == 0.0
        assert stats.success_rate == 0.0
        assert stats.error_rate == 0.0
