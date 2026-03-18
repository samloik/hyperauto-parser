"""
Конфигурация парсера Hyperauto.
Настройки загружаются из переменных окружения (.env файла).

Использует dataclass для хранения состояния (вместо ClassVar антипаттерна).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from dotenv import load_dotenv

# Загрузка переменных окружения из .env файла
load_dotenv()


@dataclass
class Config:
    """
    Класс конфигурации парсера на основе dataclass.

    Все поля инициализируются из переменных окружения или значений по умолчанию.
    """

    # Файлы
    INPUT_FILE: Path = field(default_factory=lambda: Path(os.getenv('INPUT_FILE', 'товары.xlsx')))
    OUTPUT_FILE_PREFIX: str = field(default_factory=lambda: os.getenv('OUTPUT_FILE_PREFIX', 'цены_гиперавто'))
    COOKIES_FILE: Path = field(default_factory=lambda: Path(os.getenv('COOKIES_FILE', 'cookies.json')))

    # Папки
    LOGS_DIR: Path = field(default_factory=lambda: Path('logs'))
    ERRORS_DIR: Path = field(default_factory=lambda: Path('Errors'))

    # Настройки сайта
    BASE_URL: str = 'https://hyperauto.ru'
    CITY_SLUG: str = field(default_factory=lambda: os.getenv('CITY_SLUG', 'komsomolsk'))

    # Таймауты и задержки (в секундах)
    DELAY: float = field(default_factory=lambda: float(os.getenv('DELAY', '5.0')))
    TIMEOUT: int = field(default_factory=lambda: int(os.getenv('TIMEOUT', '25000')))
    PAGE_LOAD_TIMEOUT: int = field(default_factory=lambda: int(os.getenv('PAGE_LOAD_TIMEOUT', '15000')))
    RETRY_DELAY: float = field(default_factory=lambda: float(os.getenv('RETRY_DELAY', '3.0')))

    # Попытки
    MAX_RETRIES: int = field(default_factory=lambda: int(os.getenv('MAX_RETRIES', '3')))

    # Параллелизм
    MAX_CONCURRENT_REQUESTS: int = field(default_factory=lambda: int(os.getenv('MAX_CONCURRENT_REQUESTS', '1')))

    # Браузер
    HEADLESS: bool = field(default_factory=lambda: os.getenv('DOCKER_ENV', '0') == '1')
    VIEWPORT_WIDTH: int = field(default_factory=lambda: int(os.getenv('VIEWPORT_WIDTH', '1280')))
    VIEWPORT_HEIGHT: int = field(default_factory=lambda: int(os.getenv('VIEWPORT_HEIGHT', '900')))
    USER_AGENT: str = field(
        default_factory=lambda: os.getenv(
            'USER_AGENT',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
        )
    )
    LOCALE: str = field(default_factory=lambda: os.getenv('LOCALE', 'ru-RU'))
    TIMEZONE_ID: str = field(default_factory=lambda: os.getenv('TIMEZONE_ID', 'Asia/Vladivostok'))

    # Логирование
    LOG_FORMAT: str = "{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
    LOG_FORMAT_JSON: str = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {extra} | {message}"
    LOG_RETENTION_DAYS: int = field(default_factory=lambda: int(os.getenv('LOG_RETENTION_DAYS', '30')))
    LOG_LEVEL: str = field(default_factory=lambda: os.getenv('LOG_LEVEL', 'INFO'))
    LOG_JSON_ENABLED: bool = field(default_factory=lambda: os.getenv('LOG_JSON_ENABLED', '0') == '1')

    # Метрики и алерты
    ERROR_THRESHOLD: float = field(default_factory=lambda: float(os.getenv('ERROR_THRESHOLD', '50.0')))

    # Excel
    EXCEL_COLUMN_WIDTH_MIN: int = field(default_factory=lambda: int(os.getenv('EXCEL_COLUMN_WIDTH_MIN', '10')))
    EXCEL_COLUMN_WIDTH_MAX: int = field(default_factory=lambda: int(os.getenv('EXCEL_COLUMN_WIDTH_MAX', '80')))

    def validate(self) -> List[str]:
        """
        Валидирует конфигурацию.

        Returns:
            Список ошибок (пустой, если всё корректно).
        """
        errors: List[str] = []

        if not self.INPUT_FILE:
            errors.append("INPUT_FILE не указан")

        if self.DELAY <= 0:
            errors.append("DELAY должен быть больше 0")

        if self.TIMEOUT <= 0:
            errors.append("TIMEOUT должен быть больше 0")

        if self.MAX_RETRIES < 1:
            errors.append("MAX_RETRIES должен быть >= 1")

        return errors

    def init_dirs(self) -> None:
        """Создаёт необходимые директории."""
        self.LOGS_DIR.mkdir(exist_ok=True)
        self.ERRORS_DIR.mkdir(exist_ok=True)


# Глобальный экземпляр конфигурации (для обратной совместимости)
config: Config = Config()
