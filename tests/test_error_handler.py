"""
Юнит-тесты для обработчика ошибок (error_handler.py).
"""
import pytest
from unittest.mock import AsyncMock, patch

from error_handler import (
    retry_async,
    ErrorMetrics,
    error_metrics,
    log_error_json,
    handle_parse_errors,
    save_error_report
)
from exceptions import ParserError, ParserTimeoutError
from models import ParseResult, Product


class TestRetryAsync:
    """Тесты для декоратора retry_async."""
    
    @pytest.mark.asyncio
    async def test_retry_async_success_first_try(self):
        """Проверка успешного выполнения с первой попытки."""
        call_count = 0
        
        @retry_async(max_retries=3, delay=0.1)
        async def successful_func():
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = await successful_func()
        
        assert result == "success"
        assert call_count == 1
    
    @pytest.mark.asyncio
    async def test_retry_async_success_after_retries(self):
        """Проверка успешного выполнения после повторных попыток."""
        call_count = 0
        
        @retry_async(max_retries=3, delay=0.1)
        async def failing_then_success_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Temporary error")
            return "success"
        
        result = await failing_then_success_func()
        
        assert result == "success"
        assert call_count == 3
    
    @pytest.mark.asyncio
    async def test_retry_async_all_retries_fail(self):
        """Проверка исчерпания всех попыток."""
        call_count = 0
        
        @retry_async(max_retries=3, delay=0.1)
        async def always_failing_func():
            nonlocal call_count
            call_count += 1
            raise ValueError("Permanent error")
        
        with pytest.raises(ValueError):
            await always_failing_func()
        
        assert call_count == 3
    
    @pytest.mark.asyncio
    async def test_retry_async_specific_exceptions(self):
        """Проверка обработки только указанных исключений."""
        call_count = 0
        
        @retry_async(max_retries=3, delay=0.1, exceptions=(ValueError,))
        async def specific_exception_func():
            nonlocal call_count
            call_count += 1
            raise TypeError("Wrong type")
        
        with pytest.raises(TypeError):
            await specific_exception_func()
        
        # Не должно быть повторных попыток для TypeError
        assert call_count == 1


class TestErrorMetrics:
    """Тесты для класса ErrorMetrics."""
    
    def test_error_metrics_creation(self):
        """Проверка создания метрик."""
        metrics = ErrorMetrics(error_threshold=50.0)
        
        assert metrics.total_requests == 0
        assert metrics.total_errors == 0
        assert metrics.error_threshold == 50.0
        assert metrics.alert_triggered is False
    
    def test_error_metrics_record_error(self):
        """Проверка записи ошибки."""
        metrics = ErrorMetrics()
        metrics.record_error(error_type="TestError", brand="TEST", article="ART123")
        
        assert metrics.total_requests == 1
        assert metrics.total_errors == 1
        assert "TestError" in metrics.errors_by_type
        assert metrics.errors_by_type["TestError"] == 1
        assert "TEST/ART123" in metrics.errors_by_brand_article
    
    def test_error_metrics_record_success(self):
        """Проверка записи успеха."""
        metrics = ErrorMetrics()
        metrics.record_success()
        
        assert metrics.total_requests == 1
        assert metrics.total_errors == 0
    
    def test_error_metrics_get_error_rate(self):
        """Проверка расчёта процента ошибок."""
        metrics = ErrorMetrics()
        
        assert metrics.get_error_rate() == 0.0
        
        metrics.record_error(error_type="Error1")
        assert metrics.get_error_rate() == 100.0
        
        metrics.record_success()
        metrics.record_success()
        metrics.record_success()
        assert metrics.get_error_rate() == 25.0  # 1/4
    
    def test_error_metrics_alert_threshold(self):
        """Проверка срабатывания алерта при пороге."""
        metrics = ErrorMetrics(error_threshold=50.0)
        
        # Меньше 5 запросов - алерт не срабатывает
        for i in range(4):
            metrics.record_error(error_type="Error")
        
        assert metrics.alert_triggered is False
        
        # 5 запросов с 100% ошибок - алерт должен сработать
        metrics.record_error(error_type="Error")
        
        assert metrics.alert_triggered is True
    
    def test_error_metrics_get_summary(self):
        """Проверка получения сводки."""
        metrics = ErrorMetrics(error_threshold=30.0)
        metrics.record_error(error_type="Error1", brand="TEST", article="ART1")
        metrics.record_success()
        
        summary = metrics.get_summary()
        
        assert summary['total_requests'] == 2
        assert summary['total_errors'] == 1
        assert summary['success_count'] == 1
        assert summary['error_rate'] == 50.0
        assert summary['errors_by_type'] == {"Error1": 1}
        # error_threshold не включается в summary


class TestHandleParseErrors:
    """Тесты для декоратора handle_parse_errors."""
    
    @pytest.mark.asyncio
    async def test_handle_parse_errors_success(self):
        """Проверка успешного выполнения."""
        @handle_parse_errors
        async def successful_parse(brand, article):
            return ParseResult(
                brand=brand,
                article=article,
                products=[Product(price=100.0, is_price=True)]
            )
        
        result = await successful_parse("TEST", "ART123")
        
        assert result.brand == "TEST"
        assert result.article == "ART123"
        assert len(result.products) == 1
    
    @pytest.mark.asyncio
    async def test_handle_parse_errors_parser_error(self):
        """Проверка обработки ParserError."""
        @handle_parse_errors
        async def failing_parse(brand, article):
            raise ParserError("Test error", brand=brand, article=article)
        
        result = await failing_parse("TEST", "ART123")
        
        assert isinstance(result, ParseResult)
        assert result.brand == "TEST"
        assert result.error_message == "Test error"
    
    @pytest.mark.asyncio
    async def test_handle_parse_errors_generic_exception(self):
        """Проверка обработки обычного исключения."""
        @handle_parse_errors
        async def failing_parse(brand, article):
            raise ValueError("Unexpected error")
        
        result = await failing_parse("TEST", "ART123")
        
        assert isinstance(result, ParseResult)
        assert result.brand == "TEST"
        assert "Unexpected error" in result.error_message


class TestLogErrorJson:
    """Тесты для функции log_error_json."""
    
    def test_log_error_json_basic(self):
        """Проверка базового логирования ошибки."""
        error = ValueError("Test error")
        
        # Просто проверяем что функция не выбрасывает исключение
        log_error_json(error, brand="TEST", article="ART123")
    
    def test_log_error_json_with_context(self):
        """Проверка логирования ошибки с контекстом."""
        error = ParserTimeoutError("Timeout")
        
        # Просто проверяем что функция не выбрасывает исключение
        log_error_json(error, brand="TEST", article="ART123", context={"retry": 2})


class TestSaveErrorReport:
    """Тесты для функции save_error_report."""
    
    def test_save_error_report(self, tmp_path):
        """Проверка сохранения отчёта."""
        # Записываем некоторые ошибки
        error_metrics.record_error(error_type="TestError", brand="TEST", article="ART1")
        error_metrics.record_success()
        
        report_path = tmp_path / "test_report.json"
        
        # Патчим config.ERRORS_DIR
        with patch('error_handler.config.ERRORS_DIR', tmp_path):
            save_error_report(report_path)
        
        assert report_path.exists()
        
        import json
        with open(report_path, 'r', encoding='utf-8') as f:
            report = json.load(f)
        
        assert 'generated_at' in report
        assert 'metrics' in report
        assert report['metrics']['total_errors'] >= 1
