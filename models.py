"""
Модели данных для парсера Hyperauto.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Product:
    """
    Модель карточки товара.
    
    Attributes:
        price: Цена товара (число).
        is_price: Флаг наличия цены (True если цена найдена).
        price_text: Исходный текст цены (например, "1 234 ₽").
        product_name: Наименование товара.
        availability: Информация о наличии ("В наличии" или "Доставка: ...").
        item_brand: Бренд из карточки товара.
        item_article: Артикул из карточки товара.
        html_content: HTML-содержимое страницы (для ошибок).
    """
    price: float = 0.0
    is_price: bool = False
    price_text: str = ""
    product_name: str = ""
    availability: str = ""
    item_brand: str = ""
    item_article: str = ""
    html_content: str = ""
    
    @property
    def has_error(self) -> bool:
        """Проверяет, является ли результат ошибкой."""
        return not self.is_price and not self.product_name
    
    def to_dict(self) -> dict:
        """Преобразует в словарь для DataFrame."""
        return {
            'price': self.price if self.is_price else None,
            'price_text': self.price_text,
            'product_name': self.product_name,
            'availability': self.availability,
            'item_brand': self.item_brand,
            'item_article': self.item_article,
        }


@dataclass
class ParseResult:
    """
    Результат парсинга одной позиции (бренд + артикул).
    
    Attributes:
        brand: Запрошенный бренд.
        article: Запрошенный артикул.
        products: Список найденных товаров (может быть несколько совпадений).
        error_message: Сообщение об ошибке (если есть).
        total_items: Общее количество товаров на странице.
        matched_items: Количество совпавших товаров.
        elapsed_time: Время выполнения запроса (секунды).
        timestamp: Время выполнения запроса.
        url: URL страницы поиска.
    """
    brand: str
    article: str
    products: list[Product] = field(default_factory=list)
    error_message: str = ""
    total_items: int = 0
    matched_items: int = 0
    elapsed_time: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    url: str = ""
    
    @property
    def has_errors(self) -> bool:
        """Проверяет, есть ли ошибки в результатах."""
        return self.error_message or any(p.has_error for p in self.products)
    
    def to_excel_rows(self, row_number: int, total_len: int) -> list[dict]:
        """
        Преобразует результат в строки для Excel.
        
        Args:
            row_number: Номер строки в исходном файле (0-based).
            total_len: Общее количество строк (для форматирования номера).
            
        Returns:
            Список словарей для DataFrame.
        """
        rows = []
        total_width = len(str(total_len))
        
        for idx, product in enumerate(self.products):
            # Формируем номер позиции
            if len(self.products) > 1:
                prefix = f"[{row_number + 1:0{total_width}d}/{total_len}][{idx + 1}]"
            else:
                prefix = f"[{row_number + 1:0{total_width}d}/{total_len}] "
            
            row = {
                '№': prefix,
                'Бренд': self.brand,
                'Артикул': self.article,
                'Бренд_карточка': product.item_brand,
                'Артикул_карточка': product.item_article,
                'Цена_Гиперавто_КнА': product.price if product.is_price else None,
                'Дата и время': self.timestamp.strftime('%Y-%m-%d %H:%M'),
                'Выполнение запроса': f"{self.elapsed_time:.1f} сек",
                'Наличие': product.availability if product.availability else "",
                'Наименование': product.product_name if product.product_name else (
                    product.price_text if not product.is_price else ""
                ),
                'Ссылка': self.url,
            }
            rows.append(row)
        
        return rows


@dataclass
class ParseStats:
    """
    Статистика выполнения парсинга.
    
    Attributes:
        total_items: Общее количество обработанных позиций.
        success_items: Количество успешных позиций.
        error_items: Количество позиций с ошибками.
        total_time: Общее время выполнения (секунды).
        times: Список времён выполнения каждого запроса.
        error_threshold: Порог срабатывания алерта (процент ошибок).
    """
    total_items: int = 0
    success_items: int = 0
    error_items: int = 0
    total_time: float = 0.0
    times: list[float] = field(default_factory=list)
    error_threshold: float = 50.0
    _alert_triggered: bool = False
    
    @property
    def avg_time(self) -> float:
        """Среднее время выполнения запроса."""
        return sum(self.times) / len(self.times) if self.times else 0.0
    
    @property
    def success_rate(self) -> float:
        """Процент успешных запросов."""
        if self.total_items == 0:
            return 0.0
        return (self.success_items / self.total_items) * 100
    
    @property
    def error_rate(self) -> float:
        """Процент ошибок."""
        if self.total_items == 0:
            return 0.0
        return (self.error_items / self.total_items) * 100
    
    def add_result(self, result: ParseResult) -> None:
        """Добавляет результат парсинга в статистику."""
        self.total_items += 1
        self.times.append(result.elapsed_time)
        if result.has_errors:
            self.error_items += 1
            self._check_alert()
        else:
            self.success_items += 1
    
    def _check_alert(self) -> None:
        """Проверяет порог ошибок и triggering алерт."""
        if self._alert_triggered:
            return
        
        # Не срабатываем раньше чем после 5 запросов
        min_requests_for_alert = 5
        if self.total_items < min_requests_for_alert:
            return

        if self.error_rate >= self.error_threshold:
            self._alert_triggered = True
            self._send_alert()
    
    def _send_alert(self) -> None:
        """Отправляет алерт о высоком проценте ошибок."""
        from loguru import logger
        logger.error(
            f"🚨 ALERT: Высокий процент ошибок! "
            f"{self.error_rate:.1f}% ({self.error_items}/{self.total_items})"
        )
    
    def should_alert(self) -> bool:
        """Проверяет, был ли отправлен алерт."""
        return self._alert_triggered
    
    def get_summary(self) -> dict:
        """Возвращает сводку по статистике."""
        return {
            "total_items": self.total_items,
            "success_items": self.success_items,
            "error_items": self.error_items,
            "success_rate": self.success_rate,
            "error_rate": self.error_rate,
            "avg_time": self.avg_time,
            "total_time": self.total_time,
            "alert_triggered": self._alert_triggered,
        }
