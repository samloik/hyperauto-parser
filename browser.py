"""
Модуль работы с браузером Playwright.
"""
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from loguru import logger

import config
import utils


class BrowserManager:
    """
    Менеджер браузера для работы с Playwright.
    """

    def __init__(self):
        self.playwright = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    async def initialize(self) -> Page:
        """
        Инициализирует Playwright и запускает браузер.

        Returns:
            Страница браузера.
        """
        logger.info("Попытка запуска браузера Playwright...")
        self.playwright = await async_playwright().start()
        logger.info("Playwright инициализирован")

        headless = utils.is_docker_env()
        self.browser = await self.playwright.chromium.launch(
            headless=headless,
            slow_mo=config.SLOW_MO if not headless else 0
        )
        logger.info("Браузер запущен")

        return await self.create_context()

    async def create_context(self, storage_state: dict | None = None) -> Page:
        """
        Создаёт контекст браузера и новую страницу.

        Args:
            storage_state: Состояние хранилища (cookies).

        Returns:
            Страница браузера.
        """
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

        self.page = await self.context.new_page()

        # Обход детектов ботов
        await self.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)

        return self.page

    async def setup_session(self) -> None:
        """
        Настраивает сессию: загружает cookies или даёт пройти капчу.
        """
        storage_state = utils.load_cookies()

        if storage_state is None:
            await self._handle_captcha()
        else:
            await self.create_context(storage_state)

    async def _handle_captcha(self) -> None:
        """
        Обрабатывает прохождение капчи пользователем.
        """
        logger.info("\n>>> Открой https://hyperauto.ru в этой вкладке и пройди капчу!")
        logger.info(">>> После этого нажми Enter в консоли...")

        # Создаём контекст без сессии для прохождения капчи
        await self.create_context(None)

        input()  # Ждём нажатия Enter

        await self.page.goto("https://hyperauto.ru/", wait_until="domcontentloaded")
        await self.page.wait_for_timeout(3000)

        await self.context.storage_state(path=config.COOKIES_FILE)
        logger.info(f"✓ Сессия сохранена в {config.COOKIES_FILE}")
        logger.info("  Следующие запуски пройдут без капчи!\n")

    async def goto(self, url: str, wait_until: str = "domcontentloaded", timeout: int | None = None) -> None:
        """
        Переходит на указанную страницу.

        Args:
            url: URL для перехода.
            wait_until: Когда считать загрузку завершённой.
            timeout: Таймаут в мс.
        """
        await self.page.goto(url, wait_until=wait_until, timeout=timeout or config.TIMEOUT)

    async def wait(self, timeout: int | None = None) -> None:
        """
        Ждёт указанное время.

        Args:
            timeout: Время ожидания в мс.
        """
        await self.page.wait_for_timeout(timeout or utils.get_random_delay())

    async def close(self) -> None:
        """
        Закрывает браузер и освобождает ресурсы.
        """
        if self.browser:
            await self.browser.close()

        if self.playwright:
            await self.playwright.stop()

    @property
    def is_ready(self) -> bool:
        """
        Проверяет, готов ли браузер к работе.

        Returns:
            True если браузер готов.
        """
        return self.page is not None
