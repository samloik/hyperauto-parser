"""
Модуль для управления браузером Playwright.
"""
from typing import Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from config import config
from utils import logger, load_cookies, save_cookies


class BrowserSession:
    """
    Класс для управления сессией браузера Playwright.

    Инкапсулирует создание, настройку и закрытие браузера,
    а также управление cookies/сессией.

    Attributes:
        playwright: Экземпляр Playwright.
        browser: Экземпляр браузера.
        context: Контекст браузера (вкладки, cookies).
        page: Объект страницы.
    """

    def __init__(self):
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self._has_session: bool = False
        self._playwright_context = None

    async def start(self) -> None:
        """
        Запускает браузер и создаёт страницу.

        Если есть файл cookies, загружает сессию.
        Если нет — даёт пользователю пройти капчу и сохраняет сессию.
        """
        logger.info("Попытка запуска браузера Playwright...")

        self._playwright_context = async_playwright()
        self.playwright = await self._playwright_context.__aenter__()

        logger.info("Playwright инициализирован")

        # Загружаем cookies если есть
        storage_state = load_cookies()
        self._has_session = storage_state is not None

        # Запускаем браузер
        self.browser = await self.playwright.chromium.launch(
            headless=config.HEADLESS,
            slow_mo=500
        )
        logger.info("Браузер запущен")

        # Создаём контекст
        self.context = await self.browser.new_context(
            storage_state=storage_state,
            viewport={
                'width': config.VIEWPORT_WIDTH,
                'height': config.VIEWPORT_HEIGHT
            },
            user_agent=config.USER_AGENT,
            locale=config.LOCALE,
            timezone_id=config.TIMEZONE_ID,
        )

        # Создаём страницу
        self.page = await self.context.new_page()

        # Обход детектов ботов
        await self.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        # Если сессии не было — даём время пройти капчу
        if not self._has_session:
            await self._handle_captcha()

    async def _handle_captcha(self) -> None:
        """Обрабатывает первое прохождение капчи."""
        logger.info(
            "\n>>> Открой https://hyperauto.ru в этой вкладке и пройди капчу!")
        logger.info(">>> После этого нажми Enter в консоли...")
        input()

        await self.page.goto(
            config.BASE_URL,
            wait_until="domcontentloaded"
        )
        await self.page.wait_for_timeout(3000)

        # Сохраняем сессию
        storage_state = await self.context.storage_state()
        save_cookies(storage_state)
        logger.info("  Следующие запуски пройдут без капчи!\n")

    async def close(self) -> None:
        """Закрывает браузер и очищает ресурсы."""
        if self.browser:
            await self.browser.close()

        if self.playwright:
            await self.playwright.stop()

        if self._playwright_context:
            await self._playwright_context.__aexit__(None, None, None)

    async def __aenter__(self) -> 'BrowserSession':
        """Асинхронный контекстный менеджер (вход)."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Асинхронный контекстный менеджер (выход)."""
        await self.close()

    @property
    def has_session(self) -> bool:
        """Проверяет, была ли загружена существующая сессия."""
        return self._has_session
