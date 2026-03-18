"""
Health-check для проверки доступности сайта Hyperauto.
"""
import asyncio
from typing import Optional, Tuple

import aiohttp
from loguru import logger

from config import config
from exceptions import ParserNetworkError


# Заголовки для имитации браузера
HEADERS = {
    'User-Agent': config.USER_AGENT,
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}


async def check_site_health(
    url: str = config.BASE_URL,
    timeout: int = 10,
    max_retries: int = 3
) -> Tuple[bool, str]:
    """
    Проверяет доступность сайта.

    Args:
        url: URL для проверки.
        timeout: Таймаут запроса (секунды).
        max_retries: Максимальное количество попыток.

    Returns:
        Кортеж (успех, сообщение).
    """
    last_error: Optional[Exception] = None

    for attempt in range(1, max_retries + 1):
        try:
            async with aiohttp.ClientSession(headers=HEADERS) as session:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                    allow_redirects=True
                ) as response:
                    # 400 может быть из-за отсутствия заголовков — пробуем ещё раз
                    if response.status == 400:
                        logger.warning(f"⚠ Сайт вернул 400, пробуем ещё раз...")
                        await asyncio.sleep(1)
                        continue
                    
                    if response.status == 200:
                        logger.info(f"✓ Сайт {url} доступен (статус: {response.status})")
                        return True, f"OK (статус: {response.status})"
                    else:
                        msg = f"Сайт вернул статус {response.status}"
                        logger.warning(f"⚠ {msg}")
                        return False, msg
                        
        except asyncio.TimeoutError as e:
            last_error = e
            logger.warning(f"Попытка {attempt}/{max_retries}: таймаут подключения к {url}")
            
        except aiohttp.ClientError as e:
            last_error = e
            logger.warning(f"Попытка {attempt}/{max_retries}: ошибка подключения к {url}: {str(e)[:80]}")
            
        except Exception as e:
            last_error = e
            logger.warning(f"Попытка {attempt}/{max_retries}: непредвиденная ошибка: {str(e)[:80]}")
        
        if attempt < max_retries:
            await asyncio.sleep(2)  # Пауза между попытками
    
    # Все попытки исчерпаны
    error_msg = f"Сайт {url} недоступен после {max_retries} попыток"
    logger.error(f"✗ {error_msg}")
    
    if last_error:
        logger.error(f"  Последняя ошибка: {last_error.__class__.__name__}: {str(last_error)[:100]}")
    
    return False, error_msg


async def check_search_availability(
    city_slug: str = config.CITY_SLUG,
    test_query: str = "масло",
    timeout: int = 15
) -> Tuple[bool, str]:
    """
    Проверяет доступность поиска на сайте.

    Args:
        city_slug: Slug города.
        test_query: Тестовый поисковый запрос.
        timeout: Таймаут запроса (секунды).

    Returns:
        Кортеж (успех, сообщение).
    """
    search_url = f"{config.BASE_URL}/{city_slug}/search/{test_query}/"

    try:
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            async with session.get(
                search_url,
                timeout=aiohttp.ClientTimeout(total=timeout),
                allow_redirects=True
            ) as response:
                if response.status == 200:
                    html = await response.text()

                    # Проверяем наличие признаков страницы поиска
                    has_search_results = (
                        'product-list' in html or
                        'product-card' in html or
                        'catalog-item' in html or
                        'Ничего не найдено' in html
                    )

                    if has_search_results:
                        logger.info(f"✓ Поиск доступен (статус: {response.status})")
                        return True, f"OK (статус: {response.status})"
                    else:
                        logger.warning("⚠ Страница поиска не содержит ожидаемых элементов")
                        return False, "Страница поиска не содержит ожидаемых элементов"
                else:
                    msg = f"Поиск вернул статус {response.status}"
                    logger.warning(f"⚠ {msg}")
                    return False, msg
                    
    except asyncio.TimeoutError:
        msg = f"Таймаут проверки поиска: {search_url}"
        logger.error(f"✗ {msg}")
        return False, msg
        
    except aiohttp.ClientError as e:
        msg = f"Ошибка проверки поиска: {str(e)[:100]}"
        logger.error(f"✗ {msg}")
        return False, msg


async def full_health_check() -> bool:
    """
    Полная проверка здоровья перед запуском парсера.

    Returns:
        True если все проверки пройдены, False иначе.
    """
    logger.info("🔍 Проверка доступности сайта...")

    try:
        # Проверка основной страницы
        site_ok, site_msg = await check_site_health()
        if not site_ok:
            logger.error(f"  Основная проверка не пройдена: {site_msg}")
            return False

        # Проверка поиска
        search_ok, search_msg = await check_search_availability()
        if not search_ok:
            logger.error(f"  Проверка поиска не пройдена: {search_msg}")
            return False
        
        logger.info("✓ Все проверки пройдены успешно")
        return True
        
    except Exception as e:
        logger.error(f"  Ошибка проверки: {e}")
        return False
