"""
Модуль парсинга карточек товаров с сайта Hyperauto.
Выделен из parser.py для соблюдения Single Responsibility Principle.
"""
import re
from typing import Optional

from playwright.async_api import Locator, Page

from models import Product


class ProductCardParser:
    """
    Класс для парсинга отдельных карточек товаров.

    Отвечает только за извлечение данных из карточек:
    - наименование
    - бренд и артикул
    - наличие
    - цена

    Attributes:
        page: Объект страницы Playwright.
    """

    def __init__(self, page: Page):
        self.page = page

    async def parse_cards(
        self,
        brand: str,
        article: str,
        total_items_ref: dict
    ) -> list[Product]:
        """
        Находит и парсит карточки товаров на странице.

        Args:
            brand: Запрошенный бренд.
            article: Запрошенный артикул.
            total_items_ref: Словарь для передачи total_items (по ссылке).

        Returns:
            Список найденных товаров, отфильтрованных по бренду и артикулу.
        """
        items = await self._find_product_items()
        total_items_ref['value'] = len(items)

        # Парсим все карточки
        all_products = []
        for item in items:
            product = await self._parse_single_card(item)
            if product:
                all_products.append(product)

        # Фильтруем по бренду и артикулу
        return self._filter_matched_products(all_products, brand, article)

    async def _find_product_items(self) -> list[Locator]:
        """
        Находит элементы карточек товаров на странице.

        Returns:
            Список локаторов карточек.
        """
        # Находим контейнер со списком товаров
        product_list_locator = self.page.locator(
            '.product-list.product-list_row'
        )
        product_list_count = await product_list_locator.count()

        if product_list_count > 0:
            # Используем первый элемент
            product_list = product_list_locator.first
            items: list[Locator] = []
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
                    items.append(item)
        else:
            # Fallback: ищем напрямую на странице
            fallback_locator = self.page.locator(
                '.product-list__item, article, div[class*="card"], '
                'div[class*="item"], .product-card, .catalog-item, div.product'
            )
            items = []
            item_count = await fallback_locator.count()
            for i in range(item_count):
                items.append(fallback_locator.nth(i))

        return items

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

    def _filter_matched_products(
        self,
        products: list[Product],
        brand: str,
        article: str
    ) -> list[Product]:
        """
        Фильтрует товары по бренду и артикулу.

        Args:
            products: Список всех товаров.
            brand: Запрошенный бренд.
            article: Запрошенный артикул.

        Returns:
            Список совпавших товаров.
        """
        matched = []
        for product in products:
            if self._check_brand_article_in_name(
                product.product_name, brand, article
            ):
                matched.append(product)
            elif product.item_brand and product.item_article:
                if self._validate_brand_article(
                    product.item_brand, product.item_article, brand, article
                ):
                    matched.append(product)
        return matched

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

        name_upper = product_name.upper()
        brand_upper = brand.upper()

        # Проверяем бренд
        has_brand = brand_upper in name_upper
        if not has_brand:
            return False

        # Проверяем артикул с учётом границ слова
        article_upper = article.upper().replace('-', '')
        article_escaped = re.escape(article_upper)

        # Паттерн: артикул, за которым следует граница (не буква/цифра или конец строки)
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
        article_escaped = re.escape(article_upper)

        # Паттерн: артикул, за которым следует граница
        pattern = rf'(?<![A-Z0-9]){article_escaped}(?![A-Z0-9])'

        return bool(re.search(pattern, item_article_upper))
