"""
Модуль парсинга товаров с сайта Hyperauto.
"""
import re
import random
from datetime import datetime
from typing import Optional

from playwright.async_api import (
    Locator,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)

from config import config
from models import Product, ParseResult
from utils import logger
from error_handler import handle_parse_errors, error_metrics, log_error_json, retry_async
from exceptions import ParserTimeoutError, ParserError


class Parser:
    """
    Класс для парсинга товаров с сайта Hyperauto.

    Attributes:
        page: Объект страницы Playwright.
    """

    def __init__(self, page: Page):
        self.page = page

    @handle_parse_errors
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
            # Записываем в метрики
            error_metrics.record_error(
                error_type="ParserTimeoutError",
                brand=brand,
                article=article
            )
            return result

        # Парсим карточки товаров
        total_items_ref = {'value': 0}
        products = await self._parse_product_cards(brand, article, total_items_ref)
        result.total_items = total_items_ref['value']

        if products:
            result.products = products
            result.matched_items = len(products)
            # Записываем успех в метрики
            error_metrics.record_success()
            return result
        else:
            # Нет подходящих карточек
            html_content = await self.page.content()
            result.products.append(Product(
                price_text="элементы не найдены",
                html_content=html_content
            ))
            result.error_message = "элементы не найдены"
            error_metrics.record_error(
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

    async def _parse_product_cards(
        self,
        brand: str,
        article: str,
        total_items_ref: dict
    ) -> list[Product]:
        """
        Парсит карточки товаров со страницы.

        Args:
            brand: Запрошенный бренд.
            article: Запрошенный артикул.
            total_items_ref: Словарь для передачи total_items (по ссылке).

        Returns:
            Список найденных товаров.
        """
        # Находим контейнер со списком товаров через locator
        product_list_locator = self.page.locator(
            '.product-list.product-list_row'
        )
        product_list_count = await product_list_locator.count()

        if product_list_count > 0:
            # Используем первый элемент
            product_list = product_list_locator.first
            all_items: list[Locator] = []
            item_count = await product_list.locator(
                ':scope > .product-list__item'
            ).count()

            for i in range(item_count):
                item = product_list.locator(
                    ':scope > .product-list__item'
                ).nth(i)
                # Пропускаем рекламные элементы
                item_class = await item.get_attribute('class') or ''
                if 'product-list__item__search_related' not in item_class:
                    all_items.append(item)
        else:
            # Fallback: ищем напрямую на странице
            fallback_locator = self.page.locator(
                '.product-list__item, article, div[class*="card"], '
                'div[class*="item"], .product-card, .catalog-item, div.product'
            )
            all_items = []
            item_count = await fallback_locator.count()
            for i in range(item_count):
                all_items.append(fallback_locator.nth(i))

        total_items_ref['value'] = len(all_items)

        # Собираем все карточки
        all_products = []
        for item in all_items:
            product = await self._parse_single_card(item)
            if product:
                all_products.append(product)

        # Фильтруем по бренду и артикулу
        matched_products = []
        for product in all_products:
            if self._check_brand_article_in_name(
                product.product_name, brand, article
            ):
                matched_products.append(product)
            elif product.item_brand and product.item_article:
                if self._validate_brand_article(
                    product.item_brand, product.item_article, brand, article
                ):
                    matched_products.append(product)

        return matched_products

    async def _parse_single_card(self, item: Locator) -> Optional[Product]:
        """
        Парсит одну карточку товара.

        Args:
            item: Локатор карточки товара.

        Returns:
            Product или None.
        """
        product = Product()

        # Извлекаем наименование
        product.product_name = await self._extract_product_name(item)

        # Извлекаем бренд и артикул из карточки
        product.item_brand, product.item_article = (
            await self._extract_brand_article(item)
        )

        # Извлекаем наличие
        product.availability = await self._extract_availability(item)

        # Извлекаем цену
        product.price, product.price_text, product.is_price = (
            await self._extract_price(item)
        )

        return product

    async def _extract_product_name(self, item: Locator) -> str:
        """Извлекает наименование товара из карточки."""
        all_links = item.locator('a')
        link_count = await all_links.count()

        for i in range(link_count):
            link = all_links.nth(i)
            href = await link.get_attribute('href')
            link_class = await link.get_attribute('class') or ''

            # Пропускаем ссылки на отзывы
            if 'rating__feedback' in link_class:
                continue

            if href and '/product/' in href:
                product_name = (
                    await link.get_attribute('title') or await link.inner_text()
                )
                if product_name:
                    return product_name

        return ""

    async def _extract_brand_article(self, item: Locator) -> tuple[str, str]:
        """Извлекает бренд и артикул из карточки."""
        brand = ""
        article = ""

        dotted_items = item.locator('.dotted-list__item')
        dotted_count = await dotted_items.count()

        for i in range(dotted_count):
            dotted_item = dotted_items.nth(i)
            title_attr = await dotted_item.get_attribute('title')

            if title_attr == 'Бренд':
                value_el = dotted_item.locator('.dotted-list__item-value')
                if await value_el.count() > 0:
                    brand = (await value_el.first.inner_text()).strip()

            elif title_attr == 'Артикул':
                value_el = dotted_item.locator('.dotted-list__item-value')
                if await value_el.count() > 0:
                    article = (await value_el.first.inner_text()).strip()

        return brand, article

    async def _extract_availability(self, item: Locator) -> str:
        """Извлекает информацию о наличии."""
        # Ищем "В наличии" в ссылках
        all_links = item.locator('a')
        link_count = await all_links.count()

        for i in range(link_count):
            link = all_links.nth(i)
            b_element = link.locator('b')
            if await b_element.count() > 0:
                b_text = await b_element.first.inner_text()
                if 'В наличии' in b_text or 'на складе' in b_text.lower():
                    return ' '.join(b_text.split()).strip()

            link_text = await link.inner_text()
            if 'В наличии' in link_text or 'на складе' in link_text.lower():
                return ' '.join(link_text.split()).strip()

        # Ищем дату доставки через JavaScript
        delivery_info = await item.evaluate('''
            (el) => {
                const deliveryBlocks = el.querySelectorAll('.block-delivery__variant-main');
                for (const block of deliveryBlocks) {
                    const label = block.querySelector('b.mr-4');
                    if (label && label.textContent.includes('Доставка')) {
                        let sibling = block.nextElementSibling;
                        while (sibling) {
                            const next_b = sibling.querySelector('b');
                            if (next_b && next_b.textContent.trim()) {
                                return next_b.textContent.trim();
                            }
                            sibling = sibling.nextElementSibling;
                        }
                        const parent = block.parentElement;
                        if (parent) {
                            const all_bs = parent.querySelectorAll('b');
                            for (const b of all_bs) {
                                const text = b.textContent.trim();
                                if (text && !text.includes('Доставка') && !text.includes('При заказе')) {
                                    return text;
                                }
                            }
                        }
                    }
                }
                return null;
            }
        ''')

        if delivery_info:
            return f"Доставка: {' '.join(delivery_info.split()).strip()}"

        return ""

    async def _extract_price(self, item: Locator) -> tuple[float, str, bool]:
        """
        Извлекает цену из карточки.

        Returns:
            Кортеж (числовое значение, текст, флаг успеха).
        """
        price_val = 0.0
        price_text = ""
        is_price = False

        # Приоритет 1: .price.price_big.price_green
        price_green_locator = item.locator('.price.price_big.price_green')
        green_count = await price_green_locator.count()

        for i in range(green_count):
            el = price_green_locator.nth(i)
            text = (await el.inner_text()).strip()
            price_val, is_price = self._parse_price_text(text)
            if is_price:
                price_text = text.strip()
                return price_val, price_text, is_price

        # Приоритет 2: .product-price-new__price_main
        price_locator = item.locator('.product-price-new__price_main')
        price_count = await price_locator.count()

        for i in range(price_count):
            el = price_locator.nth(i)
            text = (await el.inner_text()).strip()
            price_val, is_price = self._parse_price_text(text)
            if is_price:
                price_text = text.strip()
                return price_val, price_text, is_price

        return price_val, price_text, is_price

    def _parse_price_text(self, text: str) -> tuple[float, bool]:
        """
        Парсит текст цены в число.

        Args:
            text: Текст цены (например, "1 234 ₽").

        Returns:
            Кортеж (число, успех).
        """
        price_str = (
            text
            .replace(' ', '')
            .replace(',', '.')
            .replace('\u2009', '')
            .replace('\xa0', '')
            .replace('₽', '')
        )

        price_str_list = price_str.split('\n')
        price_str = price_str_list[1] if len(
            price_str_list) > 1 else price_str_list[0]

        try:
            return float(price_str), True
        except ValueError:
            return 0.0, False

    def _check_brand_article_in_name(
        self,
        product_name: str,
        brand: str,
        article: str
    ) -> bool:
        """
        Проверяет наличие бренда и артикула в наименовании товара.
        Использует регулярные выражения для точной проверки границ артикула.

        Args:
            product_name: Наименование товара.
            brand: Запрошенный бренд.
            article: Запрошенный артикул.

        Returns:
            True если оба найдены.
        """
        if not product_name:
            return False

        name_upper = product_name.upper()
        brand_upper = brand.upper()

        # Проверяем бренд
        has_brand = brand_upper in name_upper
        if not has_brand:
            return False

        # Проверяем артикул с учётом границ слова
        # \b не работает с кириллицей, поэтому используем свой паттерн
        # Ищем артикул, за которым следует не-буквенно-цифровой символ или конец строки
        article_upper = article.upper().replace('-', '')
        
        # Экранируем специальные символы regex
        article_escaped = re.escape(article_upper)
        
        # Паттерн: артикул, за которым следует граница (не буква/цифра или конец строки)
        # Также проверяем, что перед артикулом не буква/цифра
        pattern = rf'(?<![A-Z0-9]){article_escaped}(?![A-Z0-9])'
        
        has_article = bool(re.search(pattern, name_upper))

        return has_article and has_brand

    def _validate_brand_article(
        self,
        item_brand: str,
        item_article: str,
        brand: str,
        article: str
    ) -> bool:
        """
        Валидирует бренд и артикул из карточки товара.

        Args:
            item_brand: Бренд из карточки.
            item_article: Артикул из карточки.
            brand: Запрошенный бренд.
            article: Запрошенный артикул.

        Returns:
            True если совпадает.
        """
        # Проверяем бренд
        if item_brand.upper() != brand.upper():
            return False

        # Валидируем артикул с помощью regex
        item_article_upper = item_article.upper().replace('-', '')
        article_upper = article.upper().replace('-', '')
        
        # Экранируем специальные символы regex
        article_escaped = re.escape(article_upper)
        
        # Паттерн: артикул, за которым следует граница (не буква/цифра или конец строки)
        pattern = rf'(?<![A-Z0-9]){article_escaped}(?![A-Z0-9])'
        
        return bool(re.search(pattern, item_article_upper))
