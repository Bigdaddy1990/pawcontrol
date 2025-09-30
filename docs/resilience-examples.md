# PawControl Resilience - Code Examples

## Overview

Practical code examples for implementing resilience patterns in PawControl components.

---

## Example 1: Basic Circuit Breaker

### Protecting an API Call

```python
from homeassistant.core import HomeAssistant
from .resilience import CircuitBreakerConfig, ResilienceManager

class MyAPIClient:
    def __init__(self, hass: HomeAssistant):
        self.hass = hass
        self.resilience_manager = ResilienceManager(hass)
        
        # Configure circuit breaker
        self._circuit_config = CircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=2,
            timeout_seconds=30.0,
            half_open_max_calls=2,
        )
    
    async def fetch_data(self, dog_id: str) -> dict:
        """Fetch data with circuit breaker protection."""
        
        async def _internal_fetch() -> dict:
            # Your actual API call
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://api.example.com/dogs/{dog_id}") as response:
                    response.raise_for_status()
                    return await response.json()
        
        # Execute with circuit breaker
        return await self.resilience_manager.execute_with_resilience(
            _internal_fetch,
            circuit_breaker_name=f"api_fetch_{dog_id}",
        )
```

**Key Points:**
- ✅ Separate internal fetch function
- ✅ Unique circuit breaker name per dog
- ✅ Automatic failure tracking
- ✅ Fast-fail when circuit is OPEN

---

## Example 2: Retry Logic

### Retrying Transient Failures

```python
from .resilience import RetryConfig

class WeatherService:
    def __init__(self, hass: HomeAssistant):
        self.hass = hass
        self.resilience_manager = ResilienceManager(hass)
        
        # Configure retry behavior
        self._retry_config = RetryConfig(
            max_attempts=3,           # 2 retries
            initial_delay=1.0,        # 1s first retry
            max_delay=5.0,           # Max 5s delay
            exponential_base=2.0,     # Double each time
            jitter=True,              # Add randomness
        )
    
    async def get_weather(self, location: str) -> dict:
        """Get weather with automatic retry."""
        
        async def _fetch_weather() -> dict:
            # Fetch from Home Assistant weather entity
            weather_entity = self.hass.states.get(f"weather.{location}")
            
            if not weather_entity or weather_entity.state == "unavailable":
                raise ValueError(f"Weather entity unavailable: {location}")
            
            return {
                "temperature": weather_entity.attributes.get("temperature"),
                "humidity": weather_entity.attributes.get("humidity"),
                "condition": weather_entity.state,
            }
        
        # Execute with retry
        return await self.resilience_manager.execute_with_resilience(
            _fetch_weather,
            retry_config=self._retry_config,
        )
```

**Retry Behavior:**
```
Attempt 1: Immediate (0s)
Attempt 2: Wait 1.0s * (2^1) ± jitter = ~2s
Attempt 3: Wait 1.0s * (2^2) ± jitter = ~4s
Max delay: 5.0s (capped)
```

---

## Example 3: Combined Circuit Breaker + Retry

### Maximum Protection

```python
class RobustDataFetcher:
    def __init__(self, hass: HomeAssistant):
        self.hass = hass
        self.resilience_manager = ResilienceManager(hass)
        
        self._circuit_config = CircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=2,
            timeout_seconds=30.0,
        )
        
        self._retry_config = RetryConfig(
            max_attempts=2,
            initial_delay=1.0,
            max_delay=5.0,
            jitter=True,
        )
    
    async def fetch_with_full_protection(self, dog_id: str) -> dict:
        """Fetch with both circuit breaker and retry."""
        
        async def _protected_fetch() -> dict:
            # Your fetch logic here
            return await self._do_api_call(dog_id)
        
        # Both patterns applied automatically
        return await self.resilience_manager.execute_with_resilience(
            _protected_fetch,
            circuit_breaker_name=f"dog_data_{dog_id}",
            retry_config=self._retry_config,
        )
```

**Flow:**
```
Request → Circuit Breaker Check
          ↓ (CLOSED)
          Retry Logic (attempt 1)
          ↓ (failure)
          Retry Logic (attempt 2) 
          ↓ (failure)
          Circuit Breaker (track failure)
          ↓
          Raise Exception
```

---

## Example 4: Per-Channel Notification Protection

### Independent Channel Circuits

```python
class NotificationService:
    def __init__(self, hass: HomeAssistant):
        self.hass = hass
        self.resilience_manager = ResilienceManager(hass)
        
        # Different configs per channel type
        self._critical_config = CircuitBreakerConfig(
            failure_threshold=3,      # Less tolerant
            timeout_seconds=30.0,     # Fast recovery
        )
        
        self._non_critical_config = CircuitBreakerConfig(
            failure_threshold=10,     # More tolerant
            timeout_seconds=120.0,    # Patient recovery
        )
    
    async def send_notification(
        self, 
        channel: str, 
        message: str,
        is_critical: bool = False
    ) -> bool:
        """Send notification with per-channel protection."""
        
        async def _send_to_channel() -> bool:
            # Channel-specific sending logic
            if channel == "mobile":
                await self._send_mobile(message)
            elif channel == "email":
                await self._send_email(message)
            elif channel == "sms":
                await self._send_sms(message)
            return True
        
        try:
            config = self._critical_config if is_critical else self._non_critical_config
            circuit_name = f"notification_{channel}"
            
            await self.resilience_manager.execute_with_resilience(
                _send_to_channel,
                circuit_breaker_name=circuit_name,
            )
            return True
            
        except Exception as err:
            _LOGGER.error(f"Failed to send {channel} notification: {err}")
            return False
```

**Benefits:**
- Mobile failure ≠ Email failure
- Critical notifications less tolerant
- Independent recovery per channel

---

## Example 5: Graceful Degradation

### Using Cached Data on Failure

```python
class DataManager:
    def __init__(self, hass: HomeAssistant):
        self.hass = hass
        self.resilience_manager = ResilienceManager(hass)
        self._cache: dict[str, dict] = {}
        
        self._retry_config = RetryConfig(
            max_attempts=2,
            initial_delay=1.0,
        )
    
    async def get_dog_data(self, dog_id: str) -> dict:
        """Get data with graceful degradation to cache."""
        
        async def _fetch_fresh_data() -> dict:
            # Fetch from API
            data = await self._api_call(dog_id)
            
            # Cache successful fetch
            self._cache[dog_id] = {
                **data,
                "cached_at": dt_util.utcnow(),
            }
            
            return data
        
        try:
            # Try to get fresh data
            return await self.resilience_manager.execute_with_resilience(
                _fetch_fresh_data,
                circuit_breaker_name=f"dog_data_{dog_id}",
                retry_config=self._retry_config,
            )
            
        except Exception as err:
            _LOGGER.warning(f"Failed to fetch fresh data for {dog_id}, using cache: {err}")
            
            # Fallback to cached data
            cached = self._cache.get(dog_id)
            if cached:
                return cached
            
            # No cache available - return empty
            return {"status": "unavailable"}
```

**Degradation Levels:**
1. ✅ Fresh data from API (ideal)
2. ⚠️ Cached data (degraded)
3. ❌ Empty data (unavailable)

---

## Example 6: Monitoring & Alerts

### Health Check System

```python
class ResilienceHealthMonitor:
    def __init__(self, hass: HomeAssistant, coordinator):
        self.hass = hass
        self.coordinator = coordinator
    
    async def check_health(self) -> dict[str, any]:
        """Comprehensive resilience health check."""
        
        # Get statistics
        stats = self.coordinator.get_statistics()
        resilience_stats = stats.get("resilience", {})
        
        # Analyze circuit breaker states
        open_circuits = []
        degraded_circuits = []
        
        for name, cb_stats in resilience_stats.items():
            state = cb_stats.get("state")
            failures = cb_stats.get("failures", 0)
            
            if state == "open":
                open_circuits.append(name)
            elif state == "closed" and failures > 0:
                degraded_circuits.append(name)
        
        # Determine overall health
        is_healthy = len(open_circuits) == 0
        is_degraded = len(degraded_circuits) > 0
        
        health = {
            "status": "healthy" if is_healthy else "degraded" if not open_circuits else "critical",
            "open_circuits": open_circuits,
            "degraded_circuits": degraded_circuits,
            "circuit_count": len(resilience_stats),
            "timestamp": dt_util.utcnow().isoformat(),
        }
        
        # Send alert if unhealthy
        if not is_healthy:
            await self._send_health_alert(health)
        
        return health
    
    async def _send_health_alert(self, health: dict) -> None:
        """Send alert when resilience is compromised."""
        
        if health["status"] == "critical":
            message = f"⚠️ PawControl resilience critical: {len(health['open_circuits'])} circuits OPEN"
        else:
            message = f"⚠️ PawControl resilience degraded: {len(health['degraded_circuits'])} circuits failing"
        
        # Send to notification manager
        await self.hass.services.async_call(
            "notify",
            "persistent_notification",
            {
                "title": "PawControl Health Alert",
                "message": message,
            }
        )
```

---

## Example 7: Error Type Handling

### Different Strategies for Different Errors

```python
from homeassistant.exceptions import ConfigEntryAuthFailed
from .resilience import CircuitBreakerOpenError, RetryExhaustedError

class SmartErrorHandler:
    async def fetch_data(self, dog_id: str) -> dict:
        """Fetch data with smart error handling."""
        
        try:
            return await self.resilience_manager.execute_with_resilience(
                self._fetch_dog_data,
                dog_id,
                circuit_breaker_name=f"dog_{dog_id}",
                retry_config=self._retry_config,
            )
            
        except ConfigEntryAuthFailed:
            # Authentication failure - don't retry, trigger reauth
            _LOGGER.error(f"Authentication failed for {dog_id}")
            self.hass.async_create_task(
                self.hass.config_entries.flow.async_init(
                    DOMAIN,
                    context={"source": "reauth"},
                    data={"dog_id": dog_id},
                )
            )
            raise
            
        except CircuitBreakerOpenError:
            # Circuit is OPEN - fail fast, use cache
            _LOGGER.warning(f"Circuit OPEN for {dog_id}, using cached data")
            return self._get_cached_data(dog_id)
            
        except RetryExhaustedError:
            # All retries failed - log and degrade
            _LOGGER.error(f"All retries exhausted for {dog_id}")
            return self._get_degraded_data(dog_id)
            
        except TimeoutError:
            # Timeout - log but don't fail integration
            _LOGGER.warning(f"Timeout fetching data for {dog_id}")
            return self._get_cached_data(dog_id)
            
        except Exception as err:
            # Unexpected error - log details
            _LOGGER.exception(f"Unexpected error for {dog_id}: {err}")
            return {"status": "error", "message": str(err)}
```

**Error Handling Strategy:**

| Error Type | Retry? | Circuit Breaker? | Action |
|------------|--------|------------------|--------|
| Auth Failed | ❌ No | ❌ No | Trigger reauth flow |
| Network Error | ✅ Yes | ✅ Yes | Retry then open circuit |
| Timeout | ✅ Yes | ✅ Yes | Retry with longer delay |
| Not Found | ❌ No | ❌ No | Return empty data |
| Rate Limited | ✅ Yes | ❌ No | Retry with backoff |

---

## Example 8: Testing Resilience

### Unit Tests for Circuit Breaker

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from custom_components.pawcontrol.resilience import (
    ResilienceManager,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
)

@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_failures():
    """Test circuit breaker opens after threshold failures."""
    
    # Setup
    hass = MagicMock()
    manager = ResilienceManager(hass)
    
    # Mock failing operation
    failing_operation = AsyncMock(side_effect=Exception("API Error"))
    
    # Execute operations until circuit opens
    config = CircuitBreakerConfig(
        failure_threshold=3,
        timeout_seconds=30.0,
    )
    
    # First 3 failures should pass through
    for i in range(3):
        with pytest.raises(Exception):
            await manager.execute_with_resilience(
                failing_operation,
                circuit_breaker_name="test_circuit",
            )
    
    # 4th attempt should raise CircuitBreakerOpenError
    with pytest.raises(CircuitBreakerOpenError):
        await manager.execute_with_resilience(
            failing_operation,
            circuit_breaker_name="test_circuit",
        )

@pytest.mark.asyncio
async def test_circuit_breaker_recovers():
    """Test circuit breaker recovers after timeout."""
    
    hass = MagicMock()
    manager = ResilienceManager(hass)
    
    # Open the circuit
    failing_op = AsyncMock(side_effect=Exception("Error"))
    for _ in range(3):
        with pytest.raises(Exception):
            await manager.execute_with_resilience(
                failing_op,
                circuit_breaker_name="test",
            )
    
    # Wait for timeout (in real code, use asyncio.sleep)
    # In test, manually transition to HALF_OPEN
    cb = manager._circuit_breakers["test"]
    cb._state = CircuitBreakerState.HALF_OPEN
    
    # Success should close circuit
    success_op = AsyncMock(return_value="success")
    result = await manager.execute_with_resilience(
        success_op,
        circuit_breaker_name="test",
    )
    
    assert result == "success"
    assert cb._state == CircuitBreakerState.CLOSED
```

---

## Example 9: Advanced Monitoring

### Prometheus-Style Metrics

```python
from dataclasses import dataclass
from typing import Dict, List

@dataclass
class ResilienceMetrics:
    """Prometheus-compatible metrics for resilience."""
    
    circuit_breaker_state: Dict[str, str]  # name → state
    circuit_breaker_failures: Dict[str, int]  # name → count
    circuit_breaker_successes: Dict[str, int]  # name → count
    retry_attempts_total: int
    retry_successes: int
    retry_failures: int

class MetricsCollector:
    def __init__(self, resilience_manager: ResilienceManager):
        self.manager = resilience_manager
    
    def collect_metrics(self) -> ResilienceMetrics:
        """Collect Prometheus-compatible metrics."""
        
        circuit_states = {}
        circuit_failures = {}
        circuit_successes = {}
        
        for name, cb in self.manager._circuit_breakers.items():
            circuit_states[name] = cb._state.value
            circuit_failures[name] = cb._failures
            circuit_successes[name] = cb._successes
        
        return ResilienceMetrics(
            circuit_breaker_state=circuit_states,
            circuit_breaker_failures=circuit_failures,
            circuit_breaker_successes=circuit_successes,
            retry_attempts_total=self.manager._retry_stats.get("total", 0),
            retry_successes=self.manager._retry_stats.get("successes", 0),
            retry_failures=self.manager._retry_stats.get("failures", 0),
        )
    
    def export_prometheus_format(self) -> str:
        """Export metrics in Prometheus text format."""
        
        metrics = self.collect_metrics()
        lines = []
        
        # Circuit breaker states (0=closed, 1=open, 2=half_open)
        for name, state in metrics.circuit_breaker_state.items():
            state_value = {
                "closed": 0,
                "open": 1,
                "half_open": 2,
            }[state]
            lines.append(
                f'pawcontrol_circuit_breaker_state{{name="{name}"}} {state_value}'
            )
        
        # Circuit breaker failures
        for name, failures in metrics.circuit_breaker_failures.items():
            lines.append(
                f'pawcontrol_circuit_breaker_failures_total{{name="{name}"}} {failures}'
            )
        
        # Retry statistics
        lines.append(f"pawcontrol_retry_attempts_total {metrics.retry_attempts_total}")
        lines.append(f"pawcontrol_retry_successes_total {metrics.retry_successes}")
        lines.append(f"pawcontrol_retry_failures_total {metrics.retry_failures}")
        
        return "\n".join(lines)
```

---

## Example 10: Custom Resilience Patterns

### Rate Limiting + Circuit Breaker

```python
from datetime import timedelta
from collections import deque

class RateLimitedService:
    """Service with rate limiting and circuit breaker."""
    
    def __init__(self, hass: HomeAssistant):
        self.hass = hass
        self.resilience_manager = ResilienceManager(hass)
        
        # Rate limiting
        self._request_times: deque[datetime] = deque(maxlen=10)
        self._rate_limit_window = timedelta(minutes=1)
        self._max_requests_per_window = 10
    
    async def call_api(self, endpoint: str) -> dict:
        """Call API with rate limiting and circuit breaker."""
        
        # Check rate limit
        now = dt_util.utcnow()
        
        # Remove old requests outside window
        while self._request_times and (now - self._request_times[0]) > self._rate_limit_window:
            self._request_times.popleft()
        
        # Check if rate limit exceeded
        if len(self._request_times) >= self._max_requests_per_window:
            raise Exception(f"Rate limit exceeded: {self._max_requests_per_window} requests per minute")
        
        # Record this request
        self._request_times.append(now)
        
        # Execute with resilience
        async def _api_call():
            async with aiohttp.ClientSession() as session:
                async with session.get(endpoint) as response:
                    response.raise_for_status()
                    return await response.json()
        
        return await self.resilience_manager.execute_with_resilience(
            _api_call,
            circuit_breaker_name="rate_limited_api",
            retry_config=RetryConfig(max_attempts=2),
        )
```

---

## Best Practices Summary

### ✅ DO

1. **Use unique circuit breaker names** per service/resource
2. **Configure timeouts appropriately** for service characteristics  
3. **Handle different error types** differently
4. **Log resilience events** for debugging
5. **Monitor circuit breaker states** regularly
6. **Test failure scenarios** with unit tests
7. **Use graceful degradation** with cached data
8. **Share ResilienceManager** across components

### ❌ DON'T

1. **Don't retry authentication errors** (won't help)
2. **Don't use same circuit breaker** for different services
3. **Don't ignore OPEN circuits** (fix root cause)
4. **Don't set thresholds too low** (false positives)
5. **Don't retry indefinitely** (set max attempts)
6. **Don't block on retries** (use async/await)
7. **Don't log at ERROR level** for expected retries
8. **Don't create new ResilienceManager** per operation

---

## Further Reading

- [resilience.md](resilience.md) - Complete technical documentation
- [resilience-quickstart.md](resilience-quickstart.md) - Quick start guide
- [architecture.md](architecture.md) - System architecture

---

*Code Examples - PawControl v1.0.0*  
*Last Updated: 2025-09-30*
