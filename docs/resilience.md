# PawControl Resilience Architecture

## Overview

PawControl implements comprehensive fault tolerance patterns to ensure reliable operation even when external services fail. The resilience architecture protects against:

- Transient network failures
- API service degradation
- Notification channel outages
- GPS/Weather data unavailability
- Resource exhaustion

---

## Architecture

### Core Components

```
┌─────────────────────────────────────────────────────────────┐
│                    ResilienceManager                         │
│  - Circuit Breaker Management                                │
│  - Retry Logic Execution                                     │
│  - Statistics & Monitoring                                   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ├─────────────────────┐
                              ▼                     ▼
                    ┌──────────────────┐  ┌──────────────────┐
                    │  Circuit Breaker │  │   Retry Logic    │
                    │   - Per Service  │  │  - Exponential   │
                    │   - State: OPEN  │  │  - Jitter        │
                    │     CLOSED       │  │  - Max Attempts  │
                    │     HALF_OPEN    │  │                  │
                    └──────────────────┘  └──────────────────┘
                              │                     │
        ┌─────────────────────┼─────────────────────┴────────────┐
        ▼                     ▼                     ▼             ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ Coordinator  │  │ Notifications│  │  GPS Manager │  │Weather Manager│
│ - API Calls  │  │ - Channels   │  │ - Tracking   │  │ - Updates    │
└──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘
```

---

## Resilience Patterns

### 1. Circuit Breaker Pattern

The Circuit Breaker prevents cascading failures by stopping calls to failing services.

#### States

**CLOSED (Normal Operation)**
- All requests pass through
- Failures are tracked
- Transitions to OPEN after threshold

**OPEN (Failure State)**
- All requests fail fast
- No calls to failing service
- Waits for timeout period
- Transitions to HALF_OPEN after timeout

**HALF_OPEN (Testing State)**
- Limited test calls allowed
- Success → transitions to CLOSED
- Failure → transitions to OPEN

#### State Diagram

```
     [CLOSED]
        │
        │ failures ≥ threshold
        ▼
     [OPEN]
        │
        │ timeout expired
        ▼
   [HALF_OPEN]
        │
        ├─ success ≥ threshold → [CLOSED]
        └─ any failure → [OPEN]
```

#### Configuration

```python
CircuitBreakerConfig(
    failure_threshold=3,      # Open after 3 consecutive failures
    success_threshold=2,      # Close after 2 successes in HALF_OPEN
    timeout_seconds=30.0,     # Wait 30s before testing again
    half_open_max_calls=2,    # Max 2 concurrent test calls
)
```

**Coordinator API Circuit Breaker:**
```python
# In coordinator.py
self._circuit_breaker_config = CircuitBreakerConfig(
    failure_threshold=3,
    success_threshold=2,
    timeout_seconds=30.0,
    half_open_max_calls=2,
)
```

**Notification Channel Circuit Breakers:**
```python
# In notifications.py - per channel
self._channel_circuit_config = CircuitBreakerConfig(
    failure_threshold=5,      # More tolerant for notifications
    success_threshold=3,
    timeout_seconds=120.0,    # Longer timeout
    half_open_max_calls=1,
)
```

---

### 2. Retry Pattern

Automatic retry with exponential backoff for transient failures.

#### Algorithm

```
Attempt 1: Immediate
Attempt 2: Wait initial_delay * (base ^ 1) + jitter
Attempt 3: Wait initial_delay * (base ^ 2) + jitter
...
Attempt N: Wait min(max_delay, calculated_delay) + jitter
```

#### Configuration

```python
RetryConfig(
    max_attempts=3,           # 2 retries (3 total attempts)
    initial_delay=1.0,        # 1 second initial delay
    max_delay=5.0,            # Max 5 seconds delay
    exponential_base=2.0,     # Double delay each time
    jitter=True,              # Add random jitter (±25%)
)
```

**Coordinator Retries:**
```python
# In coordinator.py - for API data fetching
self._retry_config = RetryConfig(
    max_attempts=2,           # Only 1 retry for data fetching
    initial_delay=1.0,
    max_delay=5.0,
    exponential_base=2.0,
    jitter=True,
)
```

**GPS Manager Retries:**
```python
# In gps_manager.py - for GPS updates
self._gps_retry_config = RetryConfig(
    max_attempts=3,           # 2 retries for GPS
    initial_delay=0.5,        # Faster initial retry
    max_delay=2.0,
    exponential_base=2.0,
    jitter=True,
)
```

**Weather Manager Retries:**
```python
# In weather_manager.py - for weather updates
self._retry_config = RetryConfig(
    max_attempts=2,           # Limited for weather
    initial_delay=2.0,
    max_delay=5.0,
    exponential_base=1.5,     # Slower growth
    jitter=True,
)
```

---

## Implementation Details

### Coordinator Integration

The coordinator uses both Circuit Breaker and Retry patterns for API calls:

```python
# coordinator.py
async def _async_update_data(self) -> dict[str, Any]:
    async def fetch_and_store(dog_id: str) -> None:
        try:
            # Circuit Breaker + Retry protection
            result = await self.resilience_manager.execute_with_resilience(
                self._fetch_dog_data_protected,
                dog_id,
                circuit_breaker_name=f"dog_data_{dog_id}",
                retry_config=self._retry_config,
            )
            all_data[dog_id] = result
        except ConfigEntryAuthFailed:
            # Authentication errors - don't retry
            raise
        except Exception as err:
            # All other errors - use cached data
            all_data[dog_id] = self._data.get(dog_id, {})
```

**Key Features:**
- Per-dog circuit breakers (`dog_data_{dog_id}`)
- Authentication errors bypass resilience (re-raised immediately)
- Failed fetches use cached data
- Parallel fetching with TaskGroup

---

### Notification Integration

Each notification channel has independent circuit breaker protection:

```python
# notifications.py
async def _send_to_channel_safe(
    self,
    notification: NotificationEvent,
    channel: NotificationChannel,
    handler: Callable,
) -> None:
    # Circuit breaker per channel
    circuit_name = f"notification_channel_{channel.value}"
    await self.resilience_manager.execute_with_resilience(
        handler,
        notification,
        circuit_breaker_name=circuit_name,
    )
```

**Benefits:**
- Mobile notification failure doesn't affect email
- Persistent notifications independent from SMS
- Per-channel failure tracking
- Automatic recovery

---

### GPS Manager Integration

GPS location updates use retry logic for device tracker access:

```python
# gps_manager.py
async def _update_location_from_device_tracker(self, dog_id: str) -> None:
    async def _fetch_device_tracker_location() -> None:
        # Device tracker entity lookup and GPS extraction
        ...
    
    # Retry for transient failures
    await self.resilience_manager.execute_with_resilience(
        _fetch_device_tracker_location,
        retry_config=self._gps_retry_config,
    )
```

**Why Retry Only:**
- GPS updates are periodic, not critical
- No need for circuit breaker (non-API calls)
- Transient device tracker issues common
- Graceful degradation via logging

---

### Weather Manager Integration

Weather data fetching uses retry logic for Home Assistant entity access:

```python
# weather_manager.py
async def async_update_weather_data(
    self, weather_entity_id: str | None = None
) -> WeatherConditions | None:
    async def _fetch_weather_data() -> WeatherConditions | None:
        # Weather entity state fetch and parsing
        ...
    
    # Retry for transient failures
    return await self.resilience_manager.execute_with_resilience(
        _fetch_weather_data,
        retry_config=self._retry_config,
    )
```

**Features:**
- Retry on entity unavailability
- Fallback when no resilience manager
- Both current and forecast protected
- Non-critical failures logged

---

## Monitoring & Statistics

### Circuit Breaker Statistics

Get real-time circuit breaker states:

```python
# Via coordinator
stats = coordinator.get_statistics()
resilience_stats = stats["resilience"]

# Example output:
{
    "dog_data_max": {
        "state": "closed",
        "failures": 0,
        "successes": 47,
        "last_failure": None,
        "opened_at": None
    },
    "notification_channel_mobile": {
        "state": "open",
        "failures": 5,
        "successes": 0,
        "last_failure": "2025-09-30T10:15:23Z",
        "opened_at": "2025-09-30T10:15:23Z"
    }
}
```

### Notification Performance Metrics

```python
# Via notification manager
perf_stats = await notification_manager.async_get_performance_statistics()

# Example output:
{
    "performance_metrics": {
        "notifications_sent": 156,
        "notifications_failed": 3,
        "average_delivery_time_ms": 247.5,
        "person_targeted_notifications": 89,
        "static_fallback_notifications": 4
    },
    "cache_stats": {
        "config_entries": 12,
        "quiet_time_entries": 4,
        "rate_limit_entries": 8,
        "cache_utilization": 12.0  # percent
    }
}
```

### Accessing Statistics

#### Via Home Assistant Services

```yaml
# Get coordinator statistics
service: pawcontrol.get_statistics
data:
  entry_id: "your_entry_id"
```

#### Via Python

```python
# In custom component or script
from homeassistant.helpers import config_entry

entry = config_entry.async_entries(hass, "pawcontrol")[0]
runtime_data = entry.runtime_data

# Coordinator stats
coord_stats = runtime_data.coordinator.get_statistics()

# Notification stats
notification_stats = await runtime_data.notification_manager.async_get_performance_statistics()

# GPS stats
gps_stats = await runtime_data.gps_geofence_manager.async_get_statistics()
```

---

## Troubleshooting

### Circuit Breaker Stuck OPEN

**Symptoms:**
- Circuit breaker remains in OPEN state
- No requests passing through
- API calls failing immediately

**Diagnosis:**
```python
stats = coordinator.get_statistics()
cb_stats = stats["resilience"]["dog_data_max"]

print(f"State: {cb_stats['state']}")
print(f"Failures: {cb_stats['failures']}")
print(f"Opened at: {cb_stats['opened_at']}")
```

**Solutions:**

1. **Check API Availability:**
   - Verify external API is accessible
   - Check network connectivity
   - Review API credentials

2. **Review Timeout:**
   - Default timeout is 30 seconds
   - Wait for automatic HALF_OPEN transition
   - Circuit will self-heal if API recovers

3. **Manual Reset (if needed):**
   ```python
   # Reset circuit breaker state
   cb = coordinator.resilience_manager._circuit_breakers["dog_data_max"]
   cb._state = CircuitBreakerState.CLOSED
   cb._failures = 0
   ```

---

### Excessive Retries

**Symptoms:**
- High CPU usage
- Slow response times
- Many retry log messages

**Diagnosis:**
```bash
# Check Home Assistant logs
grep "Retrying operation" home-assistant.log | wc -l
grep "Retry attempt" home-assistant.log | tail -20
```

**Solutions:**

1. **Identify Failing Component:**
   - Check which operations retry most
   - Review error messages

2. **Adjust Retry Configuration:**
   ```python
   # Reduce max attempts
   RetryConfig(
       max_attempts=2,  # Was 3
       initial_delay=2.0,  # Was 1.0
       max_delay=10.0,  # Was 5.0
   )
   ```

3. **Fix Root Cause:**
   - Resolve API authentication issues
   - Fix network configuration
   - Update entity IDs

---

### Notification Delivery Issues

**Symptoms:**
- Notifications not received
- Partial notification delivery
- Notification delays

**Diagnosis:**
```python
perf_stats = await notification_manager.async_get_performance_statistics()

# Check failure rate
total = perf_stats["performance_metrics"]["notifications_sent"]
failed = perf_stats["performance_metrics"]["notifications_failed"]
failure_rate = (failed / total * 100) if total > 0 else 0

print(f"Failure Rate: {failure_rate:.1f}%")

# Check circuit breaker states
for channel in ["mobile", "persistent", "tts"]:
    cb_name = f"notification_channel_{channel}"
    if cb_name in stats["resilience"]:
        cb_state = stats["resilience"][cb_name]["state"]
        print(f"{channel}: {cb_state}")
```

**Solutions:**

1. **Check Channel-Specific Issues:**
   - Verify mobile app configured
   - Check notification service availability
   - Test individual channels

2. **Review Circuit Breaker States:**
   - Wait for OPEN circuits to heal
   - Check underlying service health

3. **Adjust Thresholds:**
   ```python
   # More tolerant for intermittent issues
   CircuitBreakerConfig(
       failure_threshold=10,  # Was 5
       timeout_seconds=300.0,  # Was 120
   )
   ```

---

## Best Practices

### 1. Circuit Breaker Configuration

**Choose Appropriate Thresholds:**

| Service Type | Failure Threshold | Timeout | Reason |
|--------------|-------------------|---------|--------|
| Critical API | 3 | 30s | Fast fail for user-facing operations |
| Notifications | 5-10 | 120s | More tolerant, non-blocking |
| Background Jobs | 5 | 60s | Balance between reliability and responsiveness |

**Example:**
```python
# Critical user-facing API
CircuitBreakerConfig(
    failure_threshold=3,
    success_threshold=2,
    timeout_seconds=30.0,
)

# Non-critical notifications
CircuitBreakerConfig(
    failure_threshold=10,
    success_threshold=3,
    timeout_seconds=120.0,
)
```

---

### 2. Retry Configuration

**Match Retry Strategy to Service:**

| Service Type | Max Attempts | Initial Delay | Reason |
|--------------|--------------|---------------|--------|
| Fast APIs | 2 | 0.5s | Quick operations, fast retry |
| Slow APIs | 3 | 2.0s | Longer operations, patient retry |
| Entity Access | 2 | 1.0s | Local access, fast recovery |

**Always Use Jitter:**
```python
RetryConfig(
    max_attempts=3,
    initial_delay=1.0,
    jitter=True,  # IMPORTANT: Prevents thundering herd
)
```

---

### 3. Error Handling

**Differentiate Error Types:**

```python
try:
    result = await resilience_manager.execute_with_resilience(
        some_operation,
        retry_config=retry_config,
    )
except ConfigEntryAuthFailed:
    # Authentication - don't retry, re-raise
    raise
except RetryExhaustedError:
    # All retries failed - use fallback
    result = get_cached_data()
except CircuitBreakerOpenError:
    # Circuit open - fail fast
    return None
except Exception as err:
    # Unexpected - log and handle
    _LOGGER.error("Unexpected error: %s", err)
    return None
```

---

### 4. Monitoring

**Regular Health Checks:**

```python
async def check_resilience_health() -> dict[str, Any]:
    """Periodic health check for resilience systems."""
    
    # Get all circuit breaker states
    stats = coordinator.get_statistics()
    resilience_stats = stats["resilience"]
    
    open_circuits = [
        name for name, cb in resilience_stats.items()
        if cb["state"] == "open"
    ]
    
    # Check notification performance
    notif_stats = await notification_manager.async_get_performance_statistics()
    failure_rate = (
        notif_stats["performance_metrics"]["notifications_failed"] /
        max(notif_stats["performance_metrics"]["notifications_sent"], 1)
    )
    
    return {
        "healthy": len(open_circuits) == 0 and failure_rate < 0.05,
        "open_circuits": open_circuits,
        "notification_failure_rate": failure_rate,
    }
```

---

### 5. Testing

**Simulate Failures:**

```python
# Test circuit breaker behavior
async def test_circuit_breaker():
    # Force failures to trigger circuit breaker
    for i in range(5):
        try:
            await coordinator._fetch_dog_data_protected("test_dog")
        except Exception:
            pass
    
    # Check circuit is OPEN
    stats = coordinator.get_statistics()
    assert stats["resilience"]["dog_data_test_dog"]["state"] == "open"
    
    # Wait for timeout
    await asyncio.sleep(35)
    
    # Circuit should transition to HALF_OPEN
    stats = coordinator.get_statistics()
    assert stats["resilience"]["dog_data_test_dog"]["state"] == "half_open"
```

---

## Performance Impact

### Overhead Analysis

**Circuit Breaker:**
- State check: < 1ms
- State update: < 1ms
- **Total overhead: ~1-2ms per operation**

**Retry Logic:**
- Retry calculation: < 1ms
- Delay overhead: (configurable)
- **Total overhead: delay duration only**

**Combined:**
- Normal operation: < 2ms overhead
- During failures: delay + 2ms per retry

### Recommendations

1. **Use Circuit Breakers for:**
   - External API calls
   - Network operations
   - High-latency services

2. **Use Retries for:**
   - Transient failures
   - Network hiccups
   - Eventual consistency needs

3. **Avoid for:**
   - Pure computation
   - Local data access
   - Synchronous operations

---

## Migration Guide

### Adding Resilience to New Components

1. **Initialize ResilienceManager:**
   ```python
   class MyManager:
       def __init__(self, hass: HomeAssistant):
           self.resilience_manager = ResilienceManager(hass)
           self._retry_config = RetryConfig(
               max_attempts=3,
               initial_delay=1.0,
           )
   ```

2. **Wrap Critical Operations:**
   ```python
   async def fetch_data(self):
       async def _internal_fetch():
           # Your fetch logic
           return data
       
       return await self.resilience_manager.execute_with_resilience(
           _internal_fetch,
           circuit_breaker_name="my_service",
           retry_config=self._retry_config,
       )
   ```

3. **Share Resilience Manager:**
   ```python
   # In __init__.py
   if gps_manager:
       gps_manager.resilience_manager = coordinator.resilience_manager
   ```

---

## Appendix

### Configuration Reference

#### CircuitBreakerConfig

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `failure_threshold` | int | 5 | Failures before opening |
| `success_threshold` | int | 2 | Successes before closing |
| `timeout_seconds` | float | 60.0 | Time in OPEN before HALF_OPEN |
| `half_open_max_calls` | int | 1 | Max concurrent test calls |

#### RetryConfig

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_attempts` | int | 3 | Total attempts (including first) |
| `initial_delay` | float | 1.0 | First retry delay (seconds) |
| `max_delay` | float | 60.0 | Maximum retry delay |
| `exponential_base` | float | 2.0 | Backoff multiplier |
| `jitter` | bool | True | Add random jitter |

---

### Circuit Breaker State Machine

```python
class CircuitBreakerState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Blocking all calls
    HALF_OPEN = "half_open"  # Testing recovery

# State transitions
CLOSED → OPEN: failures >= failure_threshold
OPEN → HALF_OPEN: timeout expired
HALF_OPEN → CLOSED: successes >= success_threshold
HALF_OPEN → OPEN: any failure
```

---

### Error Hierarchy

```
Exception
├── ResilienceError (Base)
│   ├── CircuitBreakerOpenError
│   │   └── Raised when circuit is OPEN
│   └── RetryExhaustedError
│       └── Raised after all retries fail
└── Other Exceptions
    └── Passed through resilience layer
```

---

## Support

### Logging

Enable debug logging for resilience:

```yaml
# configuration.yaml
logger:
  default: info
  logs:
    custom_components.pawcontrol.resilience: debug
    custom_components.pawcontrol.coordinator: debug
    custom_components.pawcontrol.notifications: debug
```

### Diagnostics

Download diagnostics via:
1. Settings → Devices & Services → PawControl
2. Click "..." → Download diagnostics

Includes:
- Circuit breaker states
- Retry statistics
- Performance metrics
- Error history

---

## Changelog

### Version 1.0.0 (2025-09-30)

**Initial Release:**
- Circuit Breaker pattern for API calls
- Retry logic with exponential backoff
- Per-channel notification protection
- GPS/Weather resilience integration
- Comprehensive monitoring

**Components:**
- ✅ coordinator.py: Full integration
- ✅ notifications.py: Per-channel protection
- ✅ gps_manager.py: Retry logic
- ✅ weather_manager.py: Retry logic
- ✅ __init__.py: Manager distribution

---

*Last Updated: 2025-09-30*  
*PawControl Version: 1.0.0*  
*Home Assistant: 2025.9.3+*
