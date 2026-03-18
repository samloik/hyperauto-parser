"""
Модуль парсинга товаров с сайта Hyperauto.
"""
import random
from datetime import datetime
from typing import Optional

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from config import config
from models import Product, ParseResult
from utils import logger
from error_handler import (
    ErrorMetrics,
    handle_parse_errors,
    error_metrics,
    log_error_json,
    retry_async,
)
from exceptions import ParserTimeoutError, ParserError
from card_parser import ProductCardParser


class Parser:
    """
    Класс для парсинга товаров с сайта Hyperauto.

    Отвечает за:
    - навигацию по страницам
    - управление сессией
    - обработку ошибок и retry-логику

    Парсинг карточек делегирован классу ProductCardParser.

    Attributes:
        page: Объект страницы Playwright.
        card_parser: Парсер карточек товаров.
        metrics: Метрики ошибок (для DI).
    """

    def __init__(self, page: Page, metrics: Optional[ErrorMetrics] = None):
        self.page = page
        self.card_parser = ProductCardParser(page)
        self.metrics = metrics  # Внедрение зависимостей

    @retry_async(
        max_retries=config.MAX_RETRIES,
        delay=config.RETRY_DELAY,
        exceptions=(PlaywrightTimeoutError, Exception)
    )
    async def parse_product(
        self,
        brand: str,
        article: str
    ) -> ParseResult:
        """
        Парсит информацию о товаре по бренду и артикулу.
        Использует retry-декоратор для автоматических повторных попыток.

        Args:
            brand: Бренд товара.
            article: Артикул товара.

        Returns:
            ParseResult с результатами парсинга.
        """
        # Обработка ошибок с внедрёнными метриками
        return await self._parse_product_impl(brand, article)

    async def _parse_product_impl(
        self,
        brand: str,
        article: str
    ) -> ParseResult:
        """
        Реализация парсинга с обработкой ошибок.

        Вызывается из parse_product через декоратор retry_async.
        """
        metrics_to_use = self.metrics if self.metrics is not None else error_metrics

        try:
            return await self._do_parse(brand, article)
        except ParserError as e:
            metrics_to_use.record_error(
                error_type=e.__class__.__name__,
                brand=brand,
                article=article,
                **e.context
            )
            log_error_json(e, brand, article, e.context)

            result = ParseResult(
                brand=brand,
                article=article,
                error_message=e.message
            )
            result.products.append(Product(price_text=e.message))
            return result

        except Exception as e:
            metrics_to_use.record_error(
                error_type=e.__class__.__name__,
                brand=brand,
                article=article,
                exception_message=str(e)[:200]
            )
            log_error_json(e, brand, article)

            result = ParseResult(
                brand=brand,
                article=article,
                error_message=str(e)[:100]
            )
            error_msg = f"ошибка: {str(e)[:50]}"
            result.products.append(Product(price_text=error_msg))
            return result

    async def _do_parse(self, brand: str, article: str) -> ParseResult:
        """Основная логика парсинга без обработки ошибок."""
        metrics_to_use = self.metrics if self.metrics is not None else error_metrics

        result = ParseResult(
            brand=brand,
            article=article,
            timestamp=datetime.now()
        )

        # Формируем URL поиска
        query = f"{brand}/{article}".strip()
        search_url = (
            f"{config.BASE_URL}/{config.CITY_SLUG}/search/{query.replace(' ', '%20')}/"
        )
        result.url = search_url

        # Переходим на страницу с явным ожиданием domcontentloaded
        await self.page.goto(
            search_url,
            wait_until="domcontentloaded",
            timeout=config.TIMEOUT
        )

        # Рандомизированная задержка (2-2.5 сек)
        delay_ms = 2000 + int(config.DELAY * 1000 * 0.3 * random.random())
        await self.page.wait_for_timeout(delay_ms)

        # Закрываем попапы/куки
        await self._close_popups()

        # Ждём появления товаров с явными ожиданиями
        products_found = await self._wait_for_products()
        if not products_found:
            html_content = await self.page.content()
            result.products.append(Product(
                price_text="таймаут ожидания карточек",
                html_content=html_content
            ))
            result.error_message = "таймаут"
            metrics_to_use.record_error(
                error_type="ParserTimeoutError",
                brand=brand,
                article=article
            )
            return result

        # Парсим карточки товаров через ProductCardParser
        total_items_ref = {'value': 0}
        products = await self.card_parser.parse_cards(
            brand, article, total_items_ref
        )
        result.total_items = total_items_ref['value']

        if products:
            result.products = products
            result.matched_items = len(products)
            metrics_to_use.record_success()
            return result
        else:
            # Нет подходящих карточек
            html_content = await self.page.content()
            result.products.append(Product(
                price_text="элементы не найдены",
                html_content=html_content
            ))
            result.error_message = "элементы не найдены"
            metrics_to_use.record_error(
                error_type="ParseNoResultsError",
                brand=brand,
                article=article
            )
            return result

    async def _close_popups(self) -> None:
        """Пытается закрыть попапы и cookie-баннеры."""
        try:
            await self.page.locator(
                'button:has-text("Принять"), button:has-text("OK"), '
                '[aria-label*="принять"], [data-dismiss*="cookie"]'
            ).click(timeout=5000)
        except BaseException:
            pass

    async def _wait_for_products(self) -> bool:
        """
        Ждёт появления карточек товаров с использованием явных ожиданий.

        Returns:
            True если карточки найдены, False если таймаут.
        """
        # Селекторы для поиска товаров в порядке приоритета
        selectors = [
            '.product-list__item',  # Основной селектор
            '.product-card',
            '.catalog-item',
            'article[class*="product"]',
            '[data-product-id]',
        ]

        for selector in selectors:
            try:
                await self.page.wait_for_selector(
                    selector,
                    timeout=config.PAGE_LOAD_TIMEOUT
                )
                logger.debug(f"  Найден товар по селектору: {selector}")
                return True
            except PlaywrightTimeoutError:
                continue

        # Проверяем наличие сообщения "Ничего не найдено"
        try:
            await self.page.wait_for_selector(
                ':has-text("ничего не найдено"), :has-text("Нет товаров"), .empty-results',
                timeout=5000
            )
            logger.warning("  Получено сообщение 'Ничего не найдено'")
            return True  # Это не ошибка, просто нет товаров
        except PlaywrightTimeoutError:
            pass

        logger.warning("    Таймаут ожидания карточек")
        return False
