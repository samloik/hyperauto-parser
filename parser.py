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
from error_handler import handle_parse_errors, error_metrics, log_error_json
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
    async def parse_product(
        self,
        brand: str,
        article: str
    ) -> ParseResult:
        """
        Парсит информацию о товаре по бренду и артикулу.

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

        max_retries = config.MAX_RETRIES
        retry_count = 0

        while retry_count < max_retries:
            try:
                # Формируем URL поиска
                query = f"{brand}/{article}".strip()
                search_url = (
                    f"{config.BASE_URL}/{config.CITY_SLUG}/search/{query.replace(' ', '%20')}/"
                )
                result.url = search_url

                # Переходим на страницу
                await self.page.goto(
                    search_url,
                    wait_until="domcontentloaded",
                    timeout=config.TIMEOUT
                )

                # Рандомизированная задержка
                delay_ms = 2000 + int(config.DELAY * 1000 * 0.3 * random.random())
                await self.page.wait_for_timeout(delay_ms)

                # Закрываем попапы/куки
                await self._close_popups()

                # Ждём появления товаров
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
                    
            except Exception as e:
                logger.error(
                    f"    Ошибка при {brand} {article}: {str(e)[:120]}..."
                )
                retry_count += 1

                if retry_count < max_retries:
                    await self.page.wait_for_timeout(int(config.RETRY_DELAY * 1000))
                    continue

                # Все попытки исчерпаны
                try:
                    html_content = await self.page.content()
                except:
                    html_content = "<html><body>Не удалось получить HTML</body></html>"

                result.products.append(Product(
                    price_text=f"ошибка: {str(e)[:50]}",
                    html_content=html_content
                ))
                result.error_message = f"ошибка: {str(e)[:50]}"
                
                # Логируем в JSON и записываем в метрики
                log_error_json(e, brand, article, {"retry_count": retry_count})
                error_metrics.record_error(
                    error_type=e.__class__.__name__,
                    brand=brand,
                    article=article,
                    retry_count=retry_count
                )
                return result

        # Превышено число попыток
        result.products.append(Product(
            price_text="превышено число попыток"
        ))
        result.error_message = "превышено число попыток"
        error_metrics.record_error(
            error_type="MaxRetriesExceeded",
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
        except:
            pass
    
    async def _wait_for_products(self) -> bool:
        """
        Ждёт появления карточек товаров.
        
        Returns:
            True если карточки найдены, False если таймаут.
        """
        try:
            await self.page.wait_for_selector(
                '.product-card, .catalog-item, article, '
                '[data-product-id], .price',
                timeout=config.PAGE_LOAD_TIMEOUT
            )
            return True
        except PlaywrightTimeoutError:
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
        # Находим контейнер со списком товаров
        product_list = await self.page.query_selector(
            '.product-list.product-list_row'
        )
        
        if product_list:
            all_items = await product_list.query_selector_all(
                ':scope > .product-list__item'
            )
            # Пропускаем рекламные элементы
            product_list_items = []
            for item in all_items:
                item_class = await item.get_attribute('class') or ''
                if 'product-list__item__search_related' not in item_class:
                    product_list_items.append(item)
        else:
            product_list_items = await self.page.query_selector_all(
                '.product-list__item, article, div[class*="card"], '
                'div[class*="item"], .product-card, .catalog-item, div.product'
            )
        
        total_items_ref['value'] = len(product_list_items)
        
        # Собираем все карточки
        all_products = []
        for item in product_list_items:
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
    
    async def _parse_single_card(self, item) -> Optional[Product]:
        """
        Парсит одну карточку товара.
        
        Args:
            item: Элемент карточки товара.
            
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
    
    async def _extract_product_name(self, item) -> str:
        """Извлекает наименование товара из карточки."""
        all_links = await item.query_selector_all('a')
        
        for link in all_links:
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
    
    async def _extract_brand_article(self, item) -> tuple[str, str]:
        """Извлекает бренд и артикул из карточки."""
        brand = ""
        article = ""
        
        dotted_items = await item.query_selector_all('.dotted-list__item')
        
        for dotted_item in dotted_items:
            title_attr = await dotted_item.get_attribute('title')
            
            if title_attr == 'Бренд':
                value_el = await dotted_item.query_selector(
                    '.dotted-list__item-value'
                )
                if value_el:
                    brand = (await value_el.inner_text()).strip()
                    
            elif title_attr == 'Артикул':
                value_el = await dotted_item.query_selector(
                    '.dotted-list__item-value'
                )
                if value_el:
                    article = (await value_el.inner_text()).strip()
        
        return brand, article
    
    async def _extract_availability(self, item) -> str:
        """Извлекает информацию о наличии."""
        # Ищем "В наличии" в ссылках
        all_links = await item.query_selector_all('a')
        
        for link in all_links:
            b_element = await link.query_selector('b')
            if b_element:
                b_text = await b_element.inner_text()
                if 'В наличии' in b_text or 'на складе' in b_text.lower():
                    return ' '.join(b_text.split()).strip()
            
            link_text = await link.inner_text()
            if 'В наличии' in link_text or 'на складе' in link_text.lower():
                return ' '.join(link_text.split()).strip()
        
        # Ищем дату доставки
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
    
    async def _extract_price(self, item) -> tuple[float, str, bool]:
        """
        Извлекает цену из карточки.
        
        Returns:
            Кортеж (числовое значение, текст, флаг успеха).
        """
        price_val = 0.0
        price_text = ""
        is_price = False
        
        # Приоритет 1: .price.price_big.price_green
        price_green_elements = await item.query_selector_all(
            '.price.price_big.price_green'
        )
        
        for el in price_green_elements:
            text = (await el.inner_text()).strip()
            price_val, is_price = self._parse_price_text(text)
            if is_price:
                price_text = text.strip()
                return price_val, price_text, is_price
        
        # Приоритет 2: .product-price-new__price_main
        price_elements = await item.query_selector_all(
            '.product-price-new__price_main'
        )
        
        for el in price_elements:
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
        price_str = price_str_list[1] if len(price_str_list) > 1 else price_str_list[0]
        
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
        
        Args:
            product_name: Наименование товара.
            brand: Запрошенный бренд.
            article: Запрошенный артикул.
            
        Returns:
            True если оба найдены.
        """
        if not product_name:
            return False
        
        name_upper = product_name.upper().replace('-', '')
        brand_upper = brand.upper()
        article_upper = ' ' + article.upper()
        
        has_brand = brand_upper in name_upper
        has_article = article_upper in name_upper
        
        # Проверяем что после артикула нет букв/цифр
        if has_article:
            article_pos = name_upper.find(article_upper)
            if article_pos >= 0:
                after_article_pos = article_pos + len(article_upper)
                if after_article_pos < len(name_upper):
                    next_char = name_upper[after_article_pos]
                    if next_char.isalnum():
                        has_article = False
        
        return has_brand and has_article
    
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
        
        # Валидируем артикул
        item_article_upper = item_article.upper().replace('-', '')
        article_upper = article.upper()
        
        if article_upper not in item_article_upper:
            return False
        
        # Проверяем что после артикула нет букв/цифр
        article_pos = item_article_upper.find(article_upper)
        if article_pos >= 0:
            after_article_pos = article_pos + len(article_upper)
            if after_article_pos >= len(item_article_upper):
                return True
            
            next_char = item_article_upper[after_article_pos]
            return not next_char.isalnum()
        
        return False
