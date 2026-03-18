"""
Юнит-тесты для health-check (health_check.py).
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from health_check import (
    check_site_health,
    check_search_availability,
    full_health_check,
    HEADERS
)


class TestHeaders:
    """Тесты для заголовков."""
    
    def test_headers_exist(self):
        """Проверка наличия заголовков."""
        assert isinstance(HEADERS, dict)
        assert 'User-Agent' in HEADERS
        assert 'Accept' in HEADERS
        assert 'Accept-Language' in HEADERS


class TestCheckSiteHealth:
    """Тесты для check_site_health."""
    
    @pytest.mark.asyncio
    async def test_check_site_health_success(self, mock_aiohttp_session):
        """Проверка успешной проверки сайта."""
        with patch('health_check.aiohttp.ClientSession') as mock_session_class:
            mock_session_class.return_value.__aenter__.return_value = mock_aiohttp_session
            
            success, message = await check_site_health(max_retries=1)
            
            assert success is True
            assert "OK" in message
    
    @pytest.mark.asyncio
    async def test_check_site_health_400_retry(self, mock_aiohttp_session):
        """Проверка повторной попытки при 400 статусе."""
        # Первый вызов возвращает 400, второй 200
        response_400 = AsyncMock()
        response_400.status = 400
        response_400.__aenter__ = AsyncMock(return_value=response_400)
        response_400.__aexit__ = AsyncMock(return_value=None)
        
        response_200 = AsyncMock()
        response_200.status = 200
        response_200.text = AsyncMock(return_value="<html>ok</html>")
        response_200.__aenter__ = AsyncMock(return_value=response_200)
        response_200.__aexit__ = AsyncMock(return_value=None)
        
        mock_aiohttp_session.get.side_effect = [response_400, response_200]
        
        with patch('health_check.aiohttp.ClientSession') as mock_session_class:
            mock_session_class.return_value.__aenter__.return_value = mock_aiohttp_session
            
            success, message = await check_site_health(max_retries=2)
            
            assert success is True
    
    @pytest.mark.asyncio
    async def test_check_site_health_timeout(self):
        """Проверка таймаута подключения."""
        import asyncio
        
        with patch('health_check.aiohttp.ClientSession') as mock_session_class:
            mock_session_class.return_value.__aenter__.side_effect = asyncio.TimeoutError()
            
            success, message = await check_site_health(max_retries=1, timeout=1)
            
            assert success is False
            assert "таймаут" in message.lower() or "недоступен" in message.lower()
    
    @pytest.mark.asyncio
    async def test_check_site_health_all_retries_fail(self):
        """Проверка исчерпания всех попыток."""
        import asyncio
        
        with patch('health_check.aiohttp.ClientSession') as mock_session_class:
            mock_session_class.return_value.__aenter__.side_effect = asyncio.TimeoutError()
            
            success, message = await check_site_health(max_retries=2, timeout=1)
            
            assert success is False


class TestCheckSearchAvailability:
    """Тесты для check_search_availability."""
    
    @pytest.mark.asyncio
    async def test_check_search_success(self, mock_aiohttp_session):
        """Проверка успешной проверки поиска."""
        # Ответ с признаками страницы поиска
        mock_aiohttp_session.get.return_value.__aenter__.return_value.text = AsyncMock(
            return_value="<html><body><div class='product-list'>...</div></body></html>"
        )
        
        with patch('health_check.aiohttp.ClientSession') as mock_session_class:
            mock_session_class.return_value.__aenter__.return_value = mock_aiohttp_session
            
            success, message = await check_search_availability()
            
            assert success is True
    
    @pytest.mark.asyncio
    async def test_check_search_no_results(self, mock_aiohttp_session):
        """Проверка страницы 'Ничего не найдено'."""
        mock_aiohttp_session.get.return_value.__aenter__.return_value.text = AsyncMock(
            return_value="<html><body>Ничего не найдено</body></html>"
        )
        
        with patch('health_check.aiohttp.ClientSession') as mock_session_class:
            mock_session_class.return_value.__aenter__.return_value = mock_aiohttp_session
            
            success, message = await check_search_availability()
            
            assert success is True  # Это не ошибка, просто нет товаров
    
    @pytest.mark.asyncio
    async def test_check_search_empty_response(self, mock_aiohttp_session):
        """Проверка пустого ответа."""
        mock_aiohttp_session.get.return_value.__aenter__.return_value.text = AsyncMock(
            return_value="<html><body></body></html>"
        )
        
        with patch('health_check.aiohttp.ClientSession') as mock_session_class:
            mock_session_class.return_value.__aenter__.return_value = mock_aiohttp_session
            
            success, message = await check_search_availability()
            
            assert success is False


class TestFullHealthCheck:
    """Тесты для full_health_check."""
    
    @pytest.mark.asyncio
    async def test_full_health_check_success(self):
        """Проверка успешной полной проверки."""
        with patch('health_check.check_site_health', new_callable=AsyncMock) as mock_site:
            mock_site.return_value = (True, "OK")
            
            with patch('health_check.check_search_availability', new_callable=AsyncMock) as mock_search:
                mock_search.return_value = (True, "OK")
                
                result = await full_health_check()
                
                assert result is True
                mock_site.assert_called_once()
                mock_search.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_full_health_check_site_down(self):
        """Проверка недоступности сайта."""
        with patch('health_check.check_site_health', new_callable=AsyncMock) as mock_site:
            mock_site.return_value = (False, "Site down")
            
            with patch('health_check.check_search_availability', new_callable=AsyncMock) as mock_search:
                result = await full_health_check()
                
                assert result is False
                mock_site.assert_called_once()
                mock_search.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_full_health_check_search_down(self):
        """Проверка недоступности поиска."""
        with patch('health_check.check_site_health', new_callable=AsyncMock) as mock_site:
            mock_site.return_value = (True, "OK")
            
            with patch('health_check.check_search_availability', new_callable=AsyncMock) as mock_search:
                mock_search.return_value = (False, "Search down")
                
                result = await full_health_check()
                
                assert result is False
                mock_site.assert_called_once()
                mock_search.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_full_health_check_exception(self):
        """Проверка обработки исключения."""
        with patch('health_check.check_site_health', new_callable=AsyncMock) as mock_site:
            mock_site.side_effect = Exception("Unexpected error")
            
            # Исключение должно быть поймано внутри full_health_check
            # и функция должна вернуть False
            result = await full_health_check()
            
            assert result is False
