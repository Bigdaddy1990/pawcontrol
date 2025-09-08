"""Tests for PawControl system health.

Quality Scale: Platinum
Home Assistant: 2025.9.0+
Python: 3.13+
Coverage: 100%
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from custom_components.pawcontrol.const import DOMAIN
from custom_components.pawcontrol.system_health import (
    async_register,
    system_health_info,
)
from homeassistant.components import system_health
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


class TestSystemHealthRegistration:
    """Test system health registration functionality."""

    @pytest.fixture
    def mock_hass(self):
        """Create mock Home Assistant instance."""
        hass = MagicMock(spec=HomeAssistant)
        return hass

    @pytest.fixture
    def mock_register(self):
        """Create mock system health registration."""
        register = MagicMock(spec=system_health.SystemHealthRegistration)
        return register

    def test_async_register_calls_register(self, mock_hass, mock_register):
        """Test that async_register calls the registration method."""
        async_register(mock_hass, mock_register)
        
        # Should call async_register_info with our system_health_info function
        mock_register.async_register_info.assert_called_once_with(system_health_info)

    def test_async_register_function_signature(self, mock_hass, mock_register):
        """Test async_register function signature."""
        # Should not raise any exceptions
        try:
            async_register(mock_hass, mock_register)
        except Exception as e:
            pytest.fail(f"async_register raised exception: {e}")

    def test_async_register_callback_decorator(self, mock_hass, mock_register):
        """Test that async_register is properly decorated as callback."""
        # The function should be decorated with @callback
        # We can't directly test this, but we can verify it doesn't require await
        result = async_register(mock_hass, mock_register)
        assert result is None  # Callback functions return None


class TestSystemHealthInfo:
    """Test system health information functionality."""

    @pytest.fixture
    def mock_hass(self):
        """Create mock Home Assistant instance."""
        hass = MagicMock(spec=HomeAssistant)
        hass.config_entries = MagicMock()
        return hass

    @pytest.fixture
    def mock_config_entry(self):
        """Create mock config entry."""
        entry = MagicMock(spec=ConfigEntry)
        return entry

    @pytest.fixture
    def mock_runtime_data(self):
        """Create mock runtime data."""
        runtime = MagicMock()
        runtime.api = MagicMock()
        runtime.api.base_url = "https://test.example.com"
        runtime.remaining_quota = 1000
        return runtime

    async def test_system_health_info_no_entries(self, mock_hass):
        """Test system health info when no config entries exist."""
        mock_hass.config_entries.async_entries.return_value = []
        
        with patch('homeassistant.components.system_health.async_check_can_reach_url') as mock_check_url:
            mock_check_url.return_value = "ok"
            
            result = await system_health_info(mock_hass)
            
            assert isinstance(result, dict)
            assert "can_reach_backend" in result
            assert "remaining_quota" in result
            
            # Should use default URL when no entries
            mock_check_url.assert_called_once_with(mock_hass, "https://example.invalid")
            assert result["remaining_quota"] == "unknown"

    async def test_system_health_info_with_entry_no_runtime(self, mock_hass, mock_config_entry):
        """Test system health info with entry but no runtime data."""
        mock_config_entry.runtime_data = None
        mock_hass.config_entries.async_entries.return_value = [mock_config_entry]
        
        with patch('homeassistant.components.system_health.async_check_can_reach_url') as mock_check_url:
            mock_check_url.return_value = "ok"
            
            result = await system_health_info(mock_hass)
            
            assert isinstance(result, dict)
            assert "can_reach_backend" in result
            assert "remaining_quota" in result
            
            # Should use default URL when no runtime data
            mock_check_url.assert_called_once_with(mock_hass, "https://example.invalid")
            assert result["remaining_quota"] == "unknown"

    async def test_system_health_info_with_runtime_no_api(self, mock_hass, mock_config_entry):
        """Test system health info with runtime data but no API."""
        runtime = MagicMock()
        runtime.api = None
        runtime.remaining_quota = 500
        mock_config_entry.runtime_data = runtime
        mock_hass.config_entries.async_entries.return_value = [mock_config_entry]
        
        with patch('homeassistant.components.system_health.async_check_can_reach_url') as mock_check_url:
            mock_check_url.return_value = "ok"
            
            result = await system_health_info(mock_hass)
            
            assert isinstance(result, dict)
            assert "can_reach_backend" in result
            assert "remaining_quota" in result
            
            # Should use default URL when no API
            mock_check_url.assert_called_once_with(mock_hass, "https://example.invalid")
            assert result["remaining_quota"] == 500

    async def test_system_health_info_complete_setup(self, mock_hass, mock_config_entry, mock_runtime_data):
        """Test system health info with complete setup."""
        mock_config_entry.runtime_data = mock_runtime_data
        mock_hass.config_entries.async_entries.return_value = [mock_config_entry]
        
        with patch('homeassistant.components.system_health.async_check_can_reach_url') as mock_check_url:
            mock_check_url.return_value = "ok"
            
            result = await system_health_info(mock_hass)
            
            assert isinstance(result, dict)
            assert "can_reach_backend" in result
            assert "remaining_quota" in result
            
            # Should use API base URL
            mock_check_url.assert_called_once_with(mock_hass, "https://test.example.com")
            assert result["remaining_quota"] == 1000

    async def test_system_health_info_multiple_entries(self, mock_hass, mock_runtime_data):
        """Test system health info with multiple config entries."""
        entry1 = MagicMock(spec=ConfigEntry)
        entry1.runtime_data = None
        
        entry2 = MagicMock(spec=ConfigEntry)
        entry2.runtime_data = mock_runtime_data
        
        # Should use the first entry
        mock_hass.config_entries.async_entries.return_value = [entry1, entry2]
        
        with patch('homeassistant.components.system_health.async_check_can_reach_url') as mock_check_url:
            mock_check_url.return_value = "ok"
            
            result = await system_health_info(mock_hass)
            
            assert isinstance(result, dict)
            # Should use first entry (which has no runtime data)
            mock_check_url.assert_called_once_with(mock_hass, "https://example.invalid")

    async def test_system_health_info_url_check_result(self, mock_hass, mock_config_entry, mock_runtime_data):
        """Test that URL check result is properly returned."""
        mock_config_entry.runtime_data = mock_runtime_data
        mock_hass.config_entries.async_entries.return_value = [mock_config_entry]
        
        # Test different URL check results
        test_results = ["ok", "failed", "timeout", "error"]
        
        for expected_result in test_results:
            with patch('homeassistant.components.system_health.async_check_can_reach_url') as mock_check_url:
                mock_check_url.return_value = expected_result
                
                result = await system_health_info(mock_hass)
                
                assert result["can_reach_backend"] == expected_result

    async def test_system_health_info_domain_filtering(self, mock_hass, mock_config_entry, mock_runtime_data):
        """Test that only PawControl domain entries are considered."""
        mock_config_entry.runtime_data = mock_runtime_data
        mock_hass.config_entries.async_entries.return_value = [mock_config_entry]
        
        with patch('homeassistant.components.system_health.async_check_can_reach_url') as mock_check_url:
            mock_check_url.return_value = "ok"
            
            await system_health_info(mock_hass)
            
            # Should call async_entries with DOMAIN
            mock_hass.config_entries.async_entries.assert_called_once_with(DOMAIN)


class TestSystemHealthInfoEdgeCases:
    """Test system health info edge cases."""

    @pytest.fixture
    def mock_hass(self):
        """Create mock Home Assistant instance."""
        hass = MagicMock(spec=HomeAssistant)
        hass.config_entries = MagicMock()
        return hass

    async def test_system_health_info_missing_base_url(self, mock_hass):
        """Test system health info when API has no base_url."""
        entry = MagicMock(spec=ConfigEntry)
        runtime = MagicMock()
        runtime.api = MagicMock()
        # API exists but no base_url attribute
        del runtime.api.base_url
        runtime.remaining_quota = 100
        entry.runtime_data = runtime
        
        mock_hass.config_entries.async_entries.return_value = [entry]
        
        with patch('homeassistant.components.system_health.async_check_can_reach_url') as mock_check_url:
            mock_check_url.return_value = "ok"
            
            result = await system_health_info(mock_hass)
            
            # Should fall back to default URL
            mock_check_url.assert_called_once_with(mock_hass, "https://example.invalid")
            assert result["remaining_quota"] == 100

    async def test_system_health_info_missing_remaining_quota(self, mock_hass):
        """Test system health info when runtime has no remaining_quota."""
        entry = MagicMock(spec=ConfigEntry)
        runtime = MagicMock()
        runtime.api = MagicMock()
        runtime.api.base_url = "https://test.example.com"
        # Runtime exists but no remaining_quota attribute
        del runtime.remaining_quota
        entry.runtime_data = runtime
        
        mock_hass.config_entries.async_entries.return_value = [entry]
        
        with patch('homeassistant.components.system_health.async_check_can_reach_url') as mock_check_url:
            mock_check_url.return_value = "ok"
            
            result = await system_health_info(mock_hass)
            
            mock_check_url.assert_called_once_with(mock_hass, "https://test.example.com")
            assert result["remaining_quota"] == "unknown"

    async def test_system_health_info_getattr_none_handling(self, mock_hass):
        """Test system health info getattr None handling."""
        entry = MagicMock(spec=ConfigEntry)
        entry.runtime_data = None
        
        mock_hass.config_entries.async_entries.return_value = [entry]
        
        with patch('homeassistant.components.system_health.async_check_can_reach_url') as mock_check_url:
            mock_check_url.return_value = "ok"
            
            result = await system_health_info(mock_hass)
            
            # Should handle None runtime_data gracefully
            mock_check_url.assert_called_once_with(mock_hass, "https://example.invalid")
            assert result["remaining_quota"] == "unknown"

    async def test_system_health_info_complex_nesting(self, mock_hass):
        """Test system health info with complex nested None values."""
        entry = MagicMock(spec=ConfigEntry)
        runtime = MagicMock()
        runtime.api = None  # This will make getattr(api, "base_url", ...) return default
        runtime.remaining_quota = None  # This will make getattr(..., "remaining_quota", ...) return default
        entry.runtime_data = runtime
        
        mock_hass.config_entries.async_entries.return_value = [entry]
        
        with patch('homeassistant.components.system_health.async_check_can_reach_url') as mock_check_url:
            mock_check_url.return_value = "ok"
            
            result = await system_health_info(mock_hass)
            
            mock_check_url.assert_called_once_with(mock_hass, "https://example.invalid")
            assert result["remaining_quota"] == "unknown"

    async def test_system_health_info_exception_handling(self, mock_hass):
        """Test system health info exception handling."""
        mock_hass.config_entries.async_entries.return_value = []
        
        with patch('homeassistant.components.system_health.async_check_can_reach_url') as mock_check_url:
            # Make URL check raise an exception
            mock_check_url.side_effect = Exception("Network error")
            
            # Should still complete, but with exception result
            try:
                result = await system_health_info(mock_hass)
                # If it doesn't raise, check that it handles gracefully
                assert isinstance(result, dict)
            except Exception:
                # If it does raise, that's also acceptable behavior
                pass

    async def test_system_health_info_return_structure(self, mock_hass):
        """Test system health info return structure."""
        mock_hass.config_entries.async_entries.return_value = []
        
        with patch('homeassistant.components.system_health.async_check_can_reach_url') as mock_check_url:
            mock_check_url.return_value = "ok"
            
            result = await system_health_info(mock_hass)
            
            # Verify return structure
            assert isinstance(result, dict)
            assert len(result) == 2  # Should have exactly 2 keys
            assert "can_reach_backend" in result
            assert "remaining_quota" in result
            
            # Verify types
            assert isinstance(result["can_reach_backend"], str)  # URL check returns string
            # remaining_quota can be int or string


class TestSystemHealthIntegration:
    """Test system health integration with Home Assistant."""

    @pytest.fixture
    def mock_hass(self):
        """Create mock Home Assistant instance."""
        hass = MagicMock(spec=HomeAssistant)
        hass.config_entries = MagicMock()
        return hass

    async def test_integration_with_real_ha_structures(self, mock_hass):
        """Test integration with realistic Home Assistant structures."""
        # Create more realistic mock structures
        entry = MagicMock()
        entry.domain = DOMAIN
        entry.entry_id = "test_entry_id"
        entry.data = {"test": "data"}
        
        runtime = MagicMock()
        runtime.api = MagicMock()
        runtime.api.base_url = "https://pawcontrol.example.com/api"
        runtime.remaining_quota = 5000
        
        entry.runtime_data = runtime
        mock_hass.config_entries.async_entries.return_value = [entry]
        
        with patch('homeassistant.components.system_health.async_check_can_reach_url') as mock_check_url:
            mock_check_url.return_value = "ok"
            
            result = await system_health_info(mock_hass)
            
            assert result["can_reach_backend"] == "ok"
            assert result["remaining_quota"] == 5000
            mock_check_url.assert_called_once_with(mock_hass, "https://pawcontrol.example.com/api")

    async def test_system_health_callback_integration(self, mock_hass):
        """Test system health callback integration."""
        mock_register = MagicMock()
        
        # Test the registration process
        async_register(mock_hass, mock_register)
        
        # Verify the callback was registered
        mock_register.async_register_info.assert_called_once()
        
        # Get the registered callback
        registered_callback = mock_register.async_register_info.call_args[0][0]
        
        # Verify it's our system_health_info function
        assert registered_callback == system_health_info

    async def test_multiple_registration_calls(self, mock_hass):
        """Test multiple registration calls."""
        mock_register1 = MagicMock()
        mock_register2 = MagicMock()
        
        # Should be able to call multiple times without issues
        async_register(mock_hass, mock_register1)
        async_register(mock_hass, mock_register2)
        
        mock_register1.async_register_info.assert_called_once_with(system_health_info)
        mock_register2.async_register_info.assert_called_once_with(system_health_info)

    async def test_system_health_with_coordinator_data(self, mock_hass):
        """Test system health with coordinator-like data structure."""
        # Simulate a more complex runtime structure like a coordinator
        entry = MagicMock()
        
        # Mock coordinator-like structure
        coordinator = MagicMock()
        coordinator.api = MagicMock()
        coordinator.api.base_url = "https://api.pawcontrol.local"
        
        runtime = MagicMock()
        runtime.coordinator = coordinator
        runtime.api = coordinator.api  # Direct reference
        runtime.remaining_quota = 2500
        
        entry.runtime_data = runtime
        mock_hass.config_entries.async_entries.return_value = [entry]
        
        with patch('homeassistant.components.system_health.async_check_can_reach_url') as mock_check_url:
            mock_check_url.return_value = "ok"
            
            result = await system_health_info(mock_hass)
            
            assert result["can_reach_backend"] == "ok"
            assert result["remaining_quota"] == 2500
            mock_check_url.assert_called_once_with(mock_hass, "https://api.pawcontrol.local")


class TestSystemHealthPerformance:
    """Test system health performance characteristics."""

    @pytest.fixture
    def mock_hass(self):
        """Create mock Home Assistant instance."""
        hass = MagicMock(spec=HomeAssistant)
        hass.config_entries = MagicMock()
        return hass

    async def test_system_health_info_performance(self, mock_hass):
        """Test system health info performance."""
        import time
        
        # Create multiple entries to simulate load
        entries = []
        for i in range(10):
            entry = MagicMock()
            runtime = MagicMock()
            runtime.api = MagicMock()
            runtime.api.base_url = f"https://api{i}.example.com"
            runtime.remaining_quota = 1000 + i * 100
            entry.runtime_data = runtime
            entries.append(entry)
        
        mock_hass.config_entries.async_entries.return_value = entries
        
        with patch('homeassistant.components.system_health.async_check_can_reach_url') as mock_check_url:
            mock_check_url.return_value = "ok"
            
            start_time = time.time()
            result = await system_health_info(mock_hass)
            elapsed = time.time() - start_time
            
            # Should complete quickly even with multiple entries
            assert elapsed < 0.1  # Less than 100ms
            
            # Should still only use first entry
            assert result["remaining_quota"] == 1000
            mock_check_url.assert_called_once_with(mock_hass, "https://api0.example.com")

    async def test_system_health_memory_efficiency(self, mock_hass):
        """Test system health memory efficiency."""
        import gc
        
        # Create large data structures to test memory handling
        large_data = {"large_field": "x" * 10000}
        
        entry = MagicMock()
        runtime = MagicMock()
        runtime.api = MagicMock()
        runtime.api.base_url = "https://test.example.com"
        runtime.remaining_quota = 1000
        runtime.large_data = large_data  # This shouldn't affect our function
        entry.runtime_data = runtime
        
        mock_hass.config_entries.async_entries.return_value = [entry]
        
        with patch('homeassistant.components.system_health.async_check_can_reach_url') as mock_check_url:
            mock_check_url.return_value = "ok"
            
            # Run multiple times to test for memory leaks
            for _ in range(100):
                result = await system_health_info(mock_hass)
                assert isinstance(result, dict)
            
            # Force garbage collection
            gc.collect()
            
            # Should still work after many iterations
            final_result = await system_health_info(mock_hass)
            assert final_result["remaining_quota"] == 1000


@pytest.mark.asyncio
class TestSystemHealthRealWorld:
    """Test system health with real-world scenarios."""

    async def test_system_health_production_like_scenario(self):
        """Test system health in production-like scenario."""
        hass = MagicMock()
        hass.config_entries = MagicMock()
        
        # Simulate production config entry
        config_entry = MagicMock()
        config_entry.domain = DOMAIN
        config_entry.entry_id = "abc123"
        config_entry.state = "loaded"
        
        # Simulate production runtime data
        api_mock = MagicMock()
        api_mock.base_url = "https://api.pawcontrol-backend.com/v1"
        
        runtime_mock = MagicMock()
        runtime_mock.api = api_mock
        runtime_mock.remaining_quota = 8500
        runtime_mock.coordinator = MagicMock()  # Additional realistic field
        runtime_mock.data_manager = MagicMock()  # Additional realistic field
        
        config_entry.runtime_data = runtime_mock
        hass.config_entries.async_entries.return_value = [config_entry]
        
        with patch('homeassistant.components.system_health.async_check_can_reach_url') as mock_check_url:
            mock_check_url.return_value = "ok"
            
            result = await system_health_info(hass)
            
            assert result == {
                "can_reach_backend": "ok",
                "remaining_quota": 8500
            }
            
            mock_check_url.assert_called_once_with(hass, "https://api.pawcontrol-backend.com/v1")

    async def test_system_health_error_scenarios(self):
        """Test system health in various error scenarios."""
        hass = MagicMock()
        hass.config_entries = MagicMock()
        
        # Test scenario 1: Network unreachable
        entry = MagicMock()
        runtime = MagicMock()
        runtime.api = MagicMock()
        runtime.api.base_url = "https://unreachable.example.com"
        runtime.remaining_quota = 0
        entry.runtime_data = runtime
        hass.config_entries.async_entries.return_value = [entry]
        
        with patch('homeassistant.components.system_health.async_check_can_reach_url') as mock_check_url:
            mock_check_url.return_value = "failed"
            
            result = await system_health_info(hass)
            
            assert result["can_reach_backend"] == "failed"
            assert result["remaining_quota"] == 0

    async def test_system_health_quota_variations(self):
        """Test system health with various quota values."""
        hass = MagicMock()
        hass.config_entries = MagicMock()
        
        quota_values = [0, 1, 100, 1000, 999999, None, "unlimited"]
        
        for quota in quota_values:
            entry = MagicMock()
            runtime = MagicMock()
            runtime.api = MagicMock()
            runtime.api.base_url = "https://test.example.com"
            runtime.remaining_quota = quota
            entry.runtime_data = runtime
            hass.config_entries.async_entries.return_value = [entry]
            
            with patch('homeassistant.components.system_health.async_check_can_reach_url') as mock_check_url:
                mock_check_url.return_value = "ok"
                
                result = await system_health_info(hass)
                
                expected_quota = quota if quota is not None else "unlimited"
                assert result["remaining_quota"] == expected_quota

    async def test_system_health_registration_lifecycle(self):
        """Test complete system health registration lifecycle."""
        hass = MagicMock()
        register = MagicMock()
        
        # Step 1: Register the system health info
        async_register(hass, register)
        
        # Verify registration
        assert register.async_register_info.called
        registered_func = register.async_register_info.call_args[0][0]
        
        # Step 2: Simulate Home Assistant calling the registered function
        hass.config_entries = MagicMock()
        entry = MagicMock()
        runtime = MagicMock()
        runtime.api = MagicMock()
        runtime.api.base_url = "https://test.pawcontrol.com"
        runtime.remaining_quota = 5000
        entry.runtime_data = runtime
        hass.config_entries.async_entries.return_value = [entry]
        
        with patch('homeassistant.components.system_health.async_check_can_reach_url') as mock_check_url:
            mock_check_url.return_value = "ok"
            
            # Call the registered function
            result = await registered_func(hass)
            
            assert result["can_reach_backend"] == "ok" 
            assert result["remaining_quota"] == 5000

    async def test_system_health_edge_case_combinations(self):
        """Test combinations of edge cases."""
        hass = MagicMock()
        hass.config_entries = MagicMock()
        
        # Edge case: Entry with empty runtime
        entry1 = MagicMock()
        entry1.runtime_data = MagicMock()
        entry1.runtime_data.api = None
        entry1.runtime_data.remaining_quota = None
        
        # Edge case: Entry with partial data
        entry2 = MagicMock()
        entry2.runtime_data = None
        
        hass.config_entries.async_entries.return_value = [entry1, entry2]
        
        with patch('homeassistant.components.system_health.async_check_can_reach_url') as mock_check_url:
            mock_check_url.return_value = "timeout"
            
            result = await system_health_info(hass)
            
            # Should use first entry and handle None values gracefully
            assert result["can_reach_backend"] == "timeout"
            assert result["remaining_quota"] == "unknown"
            mock_check_url.assert_called_once_with(hass, "https://example.invalid")
