"""
Централизованная обработка ошибок для парсера Hyperauto.
"""
import asyncio
import json
from datetime import datetime
from functools import wraps
from typing import Optional, Callable, Any
from pathlib import Path

from loguru import logger

from config import config
from exceptions import ParserError


def retry_async(
    max_retries: int = 3,
    delay: float = 3.0,
    exceptions: tuple = (Exception,),
    logger_func: Optional[Callable] = None
):
    """
    Декоратор для автоматических повторных попыток асинхронных функций.

    Args:
        max_retries: Максимальное количество попыток.
        delay: Задержка между попытками (секунды).
        exceptions: Кортеж исключений для обработки.
        logger_func: Функция для логирования (по умолчанию logger.warning).

    Returns:
        Декоратор для асинхронных функций.

    Пример:
        @retry_async(max_retries=3, delay=2.0)
        async def fetch_data():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            log_func = logger_func or logger.warning

            for attempt in range(1, max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        log_func(
                            f"Попытка {attempt}/{max_retries} не удалась: "
                            f"{func.__name__}: {str(e)[:100]}... "
                            f"(повтор через {delay} сек)"
                        )
                        await asyncio.sleep(delay)
                    else:
                        log_func(
                            f"Все {max_retries} попыток исчерпаны для {func.__name__}"
                        )

            # Должны выбросить последнее исключение
            if last_exception:
                raise last_exception

        return wrapper
    return decorator


class ErrorMetrics:
    """
    Счётчик ошибок для мониторинга и алертов.

    Отслеживает:
    - Общее количество ошибок
    - Количество ошибок по типам
    - Процент ошибок
    - Время последней ошибки
    """

    def __init__(self, error_threshold: float = 50.0):
        """
        Args:
            error_threshold: Порог срабатывания алерта (процент ошибок).
        """
        self.total_requests = 0
        self.total_errors = 0
        self.errors_by_type: dict[str, int] = {}
        self.errors_by_brand_article: dict[str, int] = {}
        self.last_error_time: Optional[datetime] = None
        self.error_threshold = error_threshold
        self.alert_triggered = False

    def record_error(
        self,
        error_type: str,
        brand: str = "",
        article: str = "",
        **kwargs
    ) -> None:
        """
        Записывает ошибку в метрики.

        Args:
            error_type: Тип ошибки.
            brand: Бренд товара.
            article: Артикул товара.
            kwargs: Дополнительные данные.
        """
        self.total_requests += 1
        self.total_errors += 1
        self.last_error_time = datetime.now()

        # Считаем по типам
        if error_type not in self.errors_by_type:
            self.errors_by_type[error_type] = 0
        self.errors_by_type[error_type] += 1

        # Считаем по товарам
        if brand or article:
            key = f"{brand}/{article}"
            if key not in self.errors_by_brand_article:
                self.errors_by_brand_article[key] = 0
            self.errors_by_brand_article[key] += 1

        # Проверяем порог для алерта
        self._check_alert()

    def record_success(self) -> None:
        """Записывает успешный запрос."""
        self.total_requests += 1

    def _check_alert(self) -> None:
        """Проверяет порог ошибок и triggering алерт."""
        if self.total_requests == 0:
            return

        # Не срабатываем раньше чем после 5 запросов
        min_requests_for_alert = 5
        if self.total_requests < min_requests_for_alert:
            return

        error_rate = (self.total_errors / self.total_requests) * 100

        if error_rate >= self.error_threshold and not self.alert_triggered:
            self.alert_triggered = True
            self._send_alert(error_rate)

    def _send_alert(self, error_rate: float) -> None:
        """
        Отправляет алерт о высоком проценте ошибок.

        Args:
            error_rate: Текущий процент ошибок.
        """
        alert_msg = (
            f"🚨 ALERT: Высокий процент ошибок! "
            f"{error_rate:.1f}% ({self.total_errors}/{self.total_requests})"
        )
        logger.error(alert_msg)

        # Логируем детали
        errors_json = json.dumps(self.errors_by_type, ensure_ascii=False)
        logger.error(f"  Ошибки по типам: {errors_json}")

        # Топ-5 товаров с ошибками
        top_errors = sorted(
            self.errors_by_brand_article.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]
        if top_errors:
            logger.error(f"  Топ товаров с ошибками: {dict(top_errors)}")

    def get_error_rate(self) -> float:
        """Возвращает текущий процент ошибок."""
        if self.total_requests == 0:
            return 0.0
        return (self.total_errors / self.total_requests) * 100

    def get_summary(self) -> dict:
        """Возвращает сводку по метрикам."""
        return {
            "total_requests": self.total_requests,
            "total_errors": self.total_errors,
            "success_count": self.total_requests - self.total_errors,
            "error_rate": self.get_error_rate(),
            "errors_by_type": self.errors_by_type,
            "last_error_time": (
                self.last_error_time.isoformat() if self.last_error_time else None
            ),
            "alert_triggered": self.alert_triggered,
        }


# Глобальный экземпляр метрик
error_metrics = ErrorMetrics()


def log_error_json(
    error: Exception,
    brand: str = "",
    article: str = "",
    context: Optional[dict] = None
) -> None:
    """
    Логирует ошибку в JSON формате.

    Args:
        error: Объект исключения.
        brand: Бренд товара.
        article: Артикул товара.
        context: Дополнительный контекст.
    """
    error_data = {
        "timestamp": datetime.now().isoformat(),
        "level": "ERROR",
        "error_type": error.__class__.__name__,
        "message": str(error)[:200],  # Ограничиваем длину
        "brand": brand,
        "article": article,
        **(context or {})
    }

    # Логируем в JSON формате
    logger.error(f"ERROR_JSON: {json.dumps(error_data, ensure_ascii=False)}")

    # Также логируем в обычном формате для удобства чтения
    logger.error(
        f"  {brand}/{article}: {error.__class__.__name__}: {str(error)[:120]}...")


def handle_parse_errors(func: Callable) -> Callable:
    """
    Декоратор для централизованной обработки ошибок парсинга.

    Автоматически:
    - Ловит исключения
    - Логирует в JSON формате
    - Обновляет метрики
    - Возвращает стандартный ответ при ошибке

    Args:
        func: Функция для декорирования.

    Returns:
        Обёрнутая функция.
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Извлекаем бренд и артикул из аргументов
        brand = kwargs.get('brand', '')
        article = kwargs.get('article', '')

        # Если переданы позиционные аргументы
        if len(args) >= 2:
            brand = brand or args[0]
            article = article or args[1]

        try:
            return await func(*args, **kwargs)
        except ParserError as e:
            # Кастомные исключения парсера
            error_metrics.record_error(
                error_type=e.__class__.__name__,
                brand=brand,
                article=article,
                **e.context
            )
            log_error_json(e, brand, article, e.context)

            # Возвращаем стандартный ответ с ошибкой
            from models import ParseResult, Product
            result = ParseResult(
                brand=brand,
                article=article,
                error_message=e.message
            )
            result.products.append(Product(price_text=e.message))
            return result

        except Exception as e:
            # Общие исключения
            error_metrics.record_error(
                error_type=e.__class__.__name__,
                brand=brand,
                article=article,
                exception_message=str(e)[:200]
            )
            log_error_json(e, brand, article)

            # Возвращаем стандартный ответ с ошибкой
            from models import ParseResult, Product
            result = ParseResult(
                brand=brand,
                article=article,
                error_message=str(e)[:100]
            )
            error_msg = f"ошибка: {str(e)[:50]}"
            result.products.append(Product(price_text=error_msg))
            return result

    return wrapper


def save_error_report(filepath: Optional[Path] = None) -> None:
    """
    Сохраняет отчёт по ошибкам в JSON файл.

    Args:
        filepath: Путь к файлу отчёта.
    """
    if filepath is None:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filepath = config.ERRORS_DIR / f"error_report_{timestamp}.json"

    report = {
        "generated_at": datetime.now().isoformat(),
        "metrics": error_metrics.get_summary(),
        "config": {
            "error_threshold": error_metrics.error_threshold,
        }
    }

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    logger.info(f"📊 Отчёт по ошибкам сохранён: {filepath}")
