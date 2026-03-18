"""
Конфигурация парсера Hyperauto.
Настройки загружаются из переменных окружения (.env файла).
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Загрузка переменных окружения из .env файла
load_dotenv()


class Config:
    """Класс конфигурации парсера."""
    
    # Файлы
    INPUT_FILE: str = os.getenv('INPUT_FILE', 'товары.xlsx')
    OUTPUT_FILE_PREFIX: str = os.getenv('OUTPUT_FILE_PREFIX', 'цены_гиперавто')
    COOKIES_FILE: str = os.getenv('COOKIES_FILE', 'cookies.json')
    
    # Папки
    LOGS_DIR: Path = Path('logs')
    ERRORS_DIR: Path = Path('Errors')
    
    # Настройки сайта
    BASE_URL: str = 'https://hyperauto.ru'
    CITY_SLUG: str = os.getenv('CITY_SLUG', 'komsomolsk')
    
    # Таймауты и задержки (в секундах)
    DELAY: float = float(os.getenv('DELAY', '5.0'))
    TIMEOUT: int = int(os.getenv('TIMEOUT', '25000'))  # ms
    PAGE_LOAD_TIMEOUT: int = int(os.getenv('PAGE_LOAD_TIMEOUT', '15000'))  # ms
    RETRY_DELAY: float = float(os.getenv('RETRY_DELAY', '3.0'))
    
    # Попытки
    MAX_RETRIES: int = int(os.getenv('MAX_RETRIES', '3'))
    
    # Браузер
    HEADLESS: bool = os.getenv('DOCKER_ENV', '0') == '1'
    VIEWPORT_WIDTH: int = int(os.getenv('VIEWPORT_WIDTH', '1280'))
    VIEWPORT_HEIGHT: int = int(os.getenv('VIEWPORT_HEIGHT', '900'))
    USER_AGENT: str = os.getenv(
        'USER_AGENT',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    )
    LOCALE: str = os.getenv('LOCALE', 'ru-RU')
    TIMEZONE_ID: str = os.getenv('TIMEZONE_ID', 'Asia/Vladivostok')
    
    # Логирование
    LOG_FORMAT: str = "{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
    LOG_RETENTION_DAYS: int = int(os.getenv('LOG_RETENTION_DAYS', '30'))
    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')
    
    # Excel
    EXCEL_COLUMN_WIDTH_MIN: int = int(os.getenv('EXCEL_COLUMN_WIDTH_MIN', '10'))
    EXCEL_COLUMN_WIDTH_MAX: int = int(os.getenv('EXCEL_COLUMN_WIDTH_MAX', '80'))
    
    @classmethod
    def validate(cls) -> list[str]:
        """
        Валидирует конфигурацию.
        Возвращает список ошибок (пустой, если всё корректно).
        """
        errors = []
        
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


# Глобальный экземпляр конфигурации
config = Config()
