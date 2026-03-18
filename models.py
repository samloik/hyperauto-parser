"""
Модели данных для парсера Hyperauto.
"""
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class Product:
    """
    Модель карточки товара, найденной на странице.
    """
    price: float = 0.0
    has_price: bool = False
    price_text: str = ""
    product_name: str = ""
    availability: str = ""
    item_brand: str = ""
    item_article: str = ""
    html_content: str = ""

    @property
    def formatted_price(self) -> str:
        """Возвращает отформатированную цену."""
        if self.has_price:
            return f"{self.price:,.2f}"
        return ""

    def is_match(self, brand: str, article: str) -> bool:
        """
        Проверяет, соответствует ли товар запрошенным бренду и артикулу.
        """
        return _check_brand_article_in_name(self.product_name, brand, article) or \
               _check_brand_article_in_fields(self.item_brand, self.item_article, brand, article)


@dataclass
class SearchResult:
    """
    Результат поиска для одной пары бренд/артикул.
    """
    brand: str
    article: str
    products: list[Product] = field(default_factory=list)
    error_message: str = ""
    total_items_on_page: int = 0
    matched_items: int = 0
    elapsed_seconds: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def has_error(self) -> bool:
        """Есть ли ошибка в результате."""
        return bool(self.error_message) or (self.matched_items == 0 and not self.products)

    @property
    def success(self) -> bool:
        """Успешен ли поиск."""
        return not self.has_error and len(self.products) > 0


@dataclass
class ParserResult:
    """
    Результат парсинга для экспорта в Excel.
    """
    row_number: str
    brand: str
    article: str
    brand_from_card: str
    article_from_card: str
    price: Optional[float]
    datetime: str
    execution_time: str
    availability: str
    product_name: str
    link: str

    def to_dict(self) -> dict:
        """Преобразует в словарь для DataFrame."""
        return {
            '№': self.row_number,
            'Бренд': self.brand,
            'Артикул': self.article,
            'Бренд_карточка': self.brand_from_card,
            'Артикул_карточка': self.article_from_card,
            'Цена_Гиперавто_КнА': self.price,
            'Дата и время': self.datetime,
            'Выполнение запроса': self.execution_time,
            'Наличие': self.availability,
            'Наименование': self.product_name,
            'Ссылка': self.link
        }


def _check_brand_article_in_name(product_name: str, brand: str, article: str) -> bool:
    """
    Проверяет наличие бренда и артикула в наименовании товара.
    """
    if not product_name:
        return False

    name_upper = product_name.upper().replace('-', '')
    brand_upper = brand.upper()
    article_upper = ' ' + article.upper()

    has_brand = brand_upper in name_upper
    has_article = article_upper in name_upper

    if has_article:
        article_pos = name_upper.find(article_upper)
        if article_pos >= 0:
            after_article_pos = article_pos + len(article_upper)
            if after_article_pos < len(name_upper):
                next_char = name_upper[after_article_pos]
                if next_char.isalnum():
                    has_article = False

    return has_brand and has_article


def _check_brand_article_in_fields(
    item_brand: str,
    item_article: str,
    brand: str,
    article: str
) -> bool:
    """
    Проверяет соответствие бренда и артикула по полям карточки.
    """
    if not item_brand or not item_article:
        return False

    if item_brand.upper() != brand.upper():
        return False

    item_article_upper = item_article.upper().replace('-', '')
    article_upper = article.upper()

    if article_upper not in item_article_upper:
        return False

    article_pos = item_article_upper.find(article_upper)
    if article_pos < 0:
        return False

    after_article_pos = article_pos + len(article_upper)
    if after_article_pos >= len(item_article_upper):
        return True

    next_char = item_article_upper[after_article_pos]
    return not next_char.isalnum()
