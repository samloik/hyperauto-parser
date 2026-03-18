"""
Конфигурация парсера Hyperauto.
Настройки загружаются из переменных окружения (.env файла).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import ClassVar, List

from dotenv import load_dotenv

# Загрузка переменных окружения из .env файла
load_dotenv()


class Config:
    """Класс конфигурации парсера."""

    # Файлы (как Path для удобства работы)
    INPUT_FILE: ClassVar[Path]
    OUTPUT_FILE_PREFIX: ClassVar[str]
    COOKIES_FILE: ClassVar[Path]

    # Папки
    LOGS_DIR: ClassVar[Path]
    ERRORS_DIR: ClassVar[Path]

    # Настройки сайта
    BASE_URL: ClassVar[str]
    CITY_SLUG: ClassVar[str]

    # Таймауты и задержки (в секундах)
    DELAY: ClassVar[float]
    TIMEOUT: ClassVar[int]
    PAGE_LOAD_TIMEOUT: ClassVar[int]
    RETRY_DELAY: ClassVar[float]

    # Попытки
    MAX_RETRIES: ClassVar[int]

    # Браузер
    HEADLESS: ClassVar[bool]
    VIEWPORT_WIDTH: ClassVar[int]
    VIEWPORT_HEIGHT: ClassVar[int]
    USER_AGENT: ClassVar[str]
    LOCALE: ClassVar[str]
    TIMEZONE_ID: ClassVar[str]

    # Логирование
    LOG_FORMAT: ClassVar[str]
    LOG_FORMAT_JSON: ClassVar[str]
    LOG_RETENTION_DAYS: ClassVar[int]
    LOG_LEVEL: ClassVar[str]
    LOG_JSON_ENABLED: ClassVar[bool]

    # Метрики и алерты
    ERROR_THRESHOLD: ClassVar[float]

    # Excel
    EXCEL_COLUMN_WIDTH_MIN: ClassVar[int]
    EXCEL_COLUMN_WIDTH_MAX: ClassVar[int]

    @classmethod
    def _init_values(cls) -> None:
        """Инициализирует значения конфигурации."""
        cls.INPUT_FILE = Path(os.getenv('INPUT_FILE', 'товары.xlsx'))
        cls.OUTPUT_FILE_PREFIX = os.getenv(
            'OUTPUT_FILE_PREFIX', 'цены_гиперавто')
        cls.COOKIES_FILE = Path(os.getenv('COOKIES_FILE', 'cookies.json'))
        cls.LOGS_DIR = Path('logs')
        cls.ERRORS_DIR = Path('Errors')
        cls.BASE_URL = 'https://hyperauto.ru'
        cls.CITY_SLUG = os.getenv('CITY_SLUG', 'komsomolsk')
        cls.DELAY = float(os.getenv('DELAY', '5.0'))
        cls.TIMEOUT = int(os.getenv('TIMEOUT', '25000'))
        cls.PAGE_LOAD_TIMEOUT = int(os.getenv('PAGE_LOAD_TIMEOUT', '15000'))
        cls.RETRY_DELAY = float(os.getenv('RETRY_DELAY', '3.0'))
        cls.MAX_RETRIES = int(os.getenv('MAX_RETRIES', '3'))
        cls.HEADLESS = os.getenv('DOCKER_ENV', '0') == '1'
        cls.VIEWPORT_WIDTH = int(os.getenv('VIEWPORT_WIDTH', '1280'))
        cls.VIEWPORT_HEIGHT = int(os.getenv('VIEWPORT_HEIGHT', '900'))
        cls.USER_AGENT = os.getenv(
            'USER_AGENT',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
        )
        cls.LOCALE = os.getenv('LOCALE', 'ru-RU')
        cls.TIMEZONE_ID = os.getenv('TIMEZONE_ID', 'Asia/Vladivostok')
        cls.LOG_FORMAT = "{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
        cls.LOG_FORMAT_JSON = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {extra} | {message}"
        cls.LOG_RETENTION_DAYS = int(os.getenv('LOG_RETENTION_DAYS', '30'))
        cls.LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
        cls.LOG_JSON_ENABLED = os.getenv('LOG_JSON_ENABLED', '0') == '1'
        cls.ERROR_THRESHOLD = float(os.getenv('ERROR_THRESHOLD', '50.0'))
        cls.EXCEL_COLUMN_WIDTH_MIN = int(
            os.getenv('EXCEL_COLUMN_WIDTH_MIN', '10'))
        cls.EXCEL_COLUMN_WIDTH_MAX = int(
            os.getenv('EXCEL_COLUMN_WIDTH_MAX', '80'))

    @classmethod
    def validate(cls) -> List[str]:
        """
        Валидирует конфигурацию.

        Returns:
            Список ошибок (пустой, если всё корректно).
        """
        errors: List[str] = []

        if not cls.INPUT_FILE:
            errors.append("INPUT_FILE не указан")

        if cls.DELAY <= 0:
            errors.append("DELAY должен быть больше 0")

        if cls.TIMEOUT <= 0:
            errors.append("TIMEOUT должен быть больше 0")

        if cls.MAX_RETRIES < 1:
            errors.append("MAX_RETRIES должен быть >= 1")

        return errors

    @classmethod
    def init_dirs(cls) -> None:
        """Создаёт необходимые директории."""
        cls.LOGS_DIR.mkdir(exist_ok=True)
        cls.ERRORS_DIR.mkdir(exist_ok=True)


# Инициализация значений
Config._init_values()

# Глобальный экземпляр конфигурации
config: Config = Config()
