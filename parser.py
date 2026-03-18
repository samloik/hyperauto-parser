"""
Модуль парсинга товаров с сайта Hyperauto.
"""
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError
from loguru import logger
from time import perf_counter

import config
from models import Product, SearchResult
from browser import BrowserManager


class ProductParser:
    """
    Парсер товаров для поиска по бренду и артикулу.
    """

    def __init__(self, browser_manager: BrowserManager):
        self.browser = browser_manager
        self.page: Page = browser_manager.page

    async def search_product(self, brand: str, article: str) -> SearchResult:
        """
        Ищет товар по бренду и артикулу.

        Args:
            brand: Бренд товара.
            article: Артикул товара.

        Returns:
            Результат поиска.
        """
        max_retries = config.MAX_RETRIES
        retry_count = 0

        while retry_count < max_retries:
            try:
                return await self._perform_search(brand, article)
            except Exception as e:
                logger.error(f"    Ошибка при {brand} {article}: {str(e)[:120]}...")
                retry_count += 1
                if retry_count < max_retries:
                    await self.browser.wait(config.RETRY_DELAY)
                    continue

                return self._create_error_result(brand, article, f"ошибка: {str(e)[:50]}")

        return self._create_error_result(brand, article, "превышено число попыток")

    async def _perform_search(self, brand: str, article: str) -> SearchResult:
        """
        Выполняет поиск товара.

        Args:
            brand: Бренд товара.
            article: Артикул товара.

        Returns:
            Результат поиска.
        """
        start_time = perf_counter()
        query = f"{brand}/{article}".strip()
        search_url = f"https://hyperauto.ru/{config.CITY_SLUG}/search/{query.replace(' ', '%20')}/"

        await self.browser.goto(search_url)
        await self.browser.wait()

        # Закрываем попапы/куки
        await self._close_popups()

        # Ждём появления товаров
        if not await self._wait_for_products():
            html_content = await self.page.content()
            return SearchResult(
                brand=brand,
                article=article,
                error_message="таймаут ожидания карточек",
                products=[Product(
                    price=0.0,
                    has_price=False,
                    price_text="таймаут ожидания карточек",
                    product_name="",
                    html_content=html_content
                )]
            )

        # Находим товары
        product_items = await self._find_product_items()
        total_items = len(product_items)

        # Парсим карточки товаров
        all_products = await self._parse_product_cards(product_items)

        # Фильтруем подходящие товары
        matched_products = self._filter_matched_products(all_products, brand, article)
        matched_count = len(matched_products)

        elapsed = perf_counter() - start_time

        if matched_products:
            return SearchResult(
                brand=brand,
                article=article,
                products=matched_products,
                total_items_on_page=total_items,
                matched_items=matched_count,
                elapsed_seconds=elapsed
            )
        else:
            html_content = await self.page.content()
            return SearchResult(
                brand=brand,
                article=article,
                error_message="элементы не найдены",
                products=[Product(
                    price=0.0,
                    has_price=False,
                    price_text="элементы не найдены",
                    product_name="",
                    html_content=html_content
                )],
                total_items_on_page=total_items,
                matched_items=0,
                elapsed_seconds=elapsed
            )

    async def _close_popups(self) -> None:
        """Пытается закрыть попапы и уведомления о cookies."""
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
            True если товары найдены.
        """
        try:
            await self.page.wait_for_selector(
                '.product-card, .catalog-item, article, [data-product-id], .price',
                timeout=15000
            )
            return True
        except PlaywrightTimeoutError:
            logger.warning(f"    Таймаут ожидания карточек")
            return False

    async def _find_product_items(self) -> list:
        """
        Находит элементы товаров на странице.

        Returns:
            Список элементов товаров.
        """
        product_list = await self.page.query_selector(config.PRODUCT_LIST_SELECTOR)

        if product_list:
            all_items = await product_list.query_selector_all(':scope > .product-list__item')
            # Фильтруем рекламные элементы
            product_items = []
            for item in all_items:
                item_class = await item.get_attribute('class') or ''
                if 'product-list__item__search_related' not in item_class:
                    product_items.append(item)
            return product_items
        else:
            # Альтернативные селекторы
            items = []
            for selector in config.PRODUCT_ITEM_SELECTORS:
                items = await self.page.query_selector_all(selector)
                if items:
                    break
            return items

    async def _parse_product_cards(self, product_items: list) -> list[Product]:
        """
        Парсит карточки товаров.

        Args:
            product_items: Список элементов товаров.

        Returns:
            Список распарсенных товаров.
        """
        all_products = []

        for item in product_items:
            product = await self._parse_single_card(item)
            if product.product_name:
                all_products.append(product)

        return all_products

    async def _parse_single_card(self, item) -> Product:
        """
        Парсит одну карточку товара.

        Args:
            item: Элемент карточки товара.

        Returns:
            Распарсенный товар.
        """
        product_name = await self._extract_product_name(item)
        item_brand, item_article = await self._extract_brand_article(item)
        availability = await self._extract_availability(item)
        price, has_price, price_text = self._extract_price(item)

        return Product(
            price=price,
            has_price=has_price,
            price_text=price_text,
            product_name=product_name,
            availability=availability,
            item_brand=item_brand,
            item_article=item_article
        )

    async def _extract_product_name(self, item) -> str:
        """Извлекает наименование товара из карточки."""
        all_links = await item.query_selector_all('a')
        for link in all_links:
            href = await link.get_attribute('href')
            link_class = await link.get_attribute('class') or ''
            if 'rating__feedback' in link_class:
                continue
            if href and '/product/' in href:
                return await link.get_attribute('title') or await link.inner_text()
        return ""

    async def _extract_brand_article(self, item) -> tuple[str, str]:
        """Извлекает бренд и артикул из карточки."""
        item_brand = ""
        item_article = ""

        dotted_items = await item.query_selector_all(config.SELECTORS['dotted_item'])
        for dotted_item in dotted_items:
            title_attr = await dotted_item.get_attribute('title')
            value_el = await dotted_item.query_selector(config.SELECTORS['dotted_value'])

            if title_attr == 'Бренд' and value_el:
                item_brand = (await value_el.inner_text()).strip()
            elif title_attr == 'Артикул' and value_el:
                item_article = (await value_el.inner_text()).strip()

        return item_brand, item_article

    async def _extract_availability(self, item) -> str:
        """Извлекает информацию о наличии товара."""
        # Ищем "В наличии"
        all_links = await item.query_selector_all(config.SELECTORS['availability_link'])
        for link in all_links:
            b_element = await link.query_selector(config.SELECTORS['availability_bold'])
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

    def _extract_price(self, item) -> tuple[float, bool, str]:
        """
        Извлекает цену из карточки товара.

        Returns:
            Кортеж (цена, есть_цена, текст_цены).
        """
        # Приоритет 1: .price.price_big.price_green
        price_elements = item.query_selector_all(config.SELECTORS['price_green'])
        for el in price_elements:
            text = el.inner_text().strip()
            price_val = self._parse_price_text(text)
            if price_val is not None:
                return price_val, True, text.strip()

        # Приоритет 2: .product-price-new__price_main
        price_elements = item.query_selector_all(config.SELECTORS['price_main'])
        for el in price_elements:
            text = el.inner_text().strip()
            price_val = self._parse_price_text(text)
            if price_val is not None:
                return price_val, True, text.strip()

        return 0.0, False, ""

    def _parse_price_text(self, text: str) -> float | None:
        """
        Парсит текст цены в число.

        Args:
            text: Текст цены.

        Returns:
            Числовое значение цены или None.
        """
        price_str = text.replace(' ', '').replace(',', '.').replace('\u2009', '').replace('\xa0', '').replace('₽', '')
        price_str_list = price_str.split('\n')
        price_str = price_str_list[1] if len(price_str_list) > 1 else price_str_list[0]

        try:
            return float(price_str)
        except ValueError:
            return None

    def _filter_matched_products(self, products: list[Product], brand: str, article: str) -> list[Product]:
        """
        Фильтрует товары по соответствию бренду и артикулу.

        Args:
            products: Список всех товаров.
            brand: Запрошенный бренд.
            article: Запрошенный артикул.

        Returns:
            Список подходящих товаров.
        """
        return [p for p in products if p.is_match(brand, article)]

    def _create_error_result(self, brand: str, article: str, error_message: str) -> SearchResult:
        """
        Создаёт результат с ошибкой.

        Args:
            brand: Бренд.
            article: Артикул.
            error_message: Сообщение об ошибке.

        Returns:
            Результат поиска с ошибкой.
        """
        return SearchResult(
            brand=brand,
            article=article,
            error_message=error_message,
            products=[Product(
                price=0.0,
                has_price=False,
                price_text=error_message,
                product_name=""
            )],
            matched_items=0
        )
