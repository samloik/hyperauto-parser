"""
Кастомные исключения для парсера Hyperauto.
"""


class ParserError(Exception):
    """Базовое исключение для ошибок парсера."""
    
    def __init__(self, message: str, brand: str = "", article: str = "", **kwargs):
        self.message = message
        self.brand = brand
        self.article = article
        self.context = kwargs
        super().__init__(self.message)
    
    def to_dict(self) -> dict:
        """Преобразует исключение в словарь для логирования."""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "brand": self.brand,
            "article": self.article,
            **self.context
        }


class ParserTimeoutError(ParserError):
    """Превышено время ожидания."""
    pass


class ParserNetworkError(ParserError):
    """Ошибка сети."""
    pass


class ParserValidationError(ParserError):
    """Ошибка валидации данных."""
    pass


class ParserConfigError(ParserError):
    """Ошибка конфигурации."""
    pass


class BrowserLaunchError(ParserError):
    """Ошибка запуска браузера."""
    pass


class CaptchaError(ParserError):
    """Ошибка прохождения капчи."""
    pass


class CookieError(ParserError):
    """Ошибка работы с cookies."""
    pass


class ParseNoResultsError(ParserError):
    """Нет результатов парсинга."""
    pass


class ParseMultipleResultsError(ParserError):
    """Найдено несколько результатов (не критично)."""
    pass
