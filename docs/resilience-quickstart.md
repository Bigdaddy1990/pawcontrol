# PawControl Resilience - Quick Start Guide

## 🎯 5-Minute Quick Start

This guide gets you started with PawControl's resilience features in 5 minutes.

---

## What is Resilience?

**Resilience = Your integration stays working even when things fail.**

PawControl uses two main patterns:
1. **Circuit Breaker** - Stops calling broken services
2. **Retry Logic** - Automatically retries failed operations

---

## Quick Check: Is Resilience Working?

### 1. Check Circuit Breaker Status

Open Home Assistant Developer Tools → Template:

```jinja
{{ states.sensor.pawcontrol_statistics.attributes.resilience }}
```

**Healthy Output:**
```json
{
  "dog_data_max": {
    "state": "closed",
    "failures": 0
  },
  "notification_channel_mobile": {
    "state": "closed",
    "failures": 0
  }
}
```

### 2. Check Logs

```bash
grep "Resilience" home-assistant.log | tail -20
```

**Good Signs:**
- "Circuit breaker closed for..."
- "Retry succeeded after X attempts"
- No repeated error messages

**Bad Signs:**
- "Circuit breaker opened for..."
- "Retry exhausted after X attempts"
- Same error repeating

---

## Common Scenarios

### Scenario 1: Mobile Notifications Not Working

**Symptom:** Notifications stop arriving

**Quick Fix:**
```yaml
# Developer Tools → Services
service: pawcontrol.reset_notification_channel
data:
  channel: mobile
```

**Check Status:**
```python
# Template
{{ states.sensor.pawcontrol_notifications.attributes.performance_metrics }}
```

---

### Scenario 2: GPS Updates Failing

**Symptom:** GPS location not updating

**Check:**
1. Is device tracker available?
   ```jinja
   {{ states('device_tracker.max_phone') }}
   ```

2. Check GPS stats:
   ```jinja
   {{ states.sensor.pawcontrol_gps_statistics.attributes }}
   ```

**Quick Fix:**
- Resilience will auto-retry (3 attempts)
- Check device tracker configuration
- Verify GPS permissions on device

---

### Scenario 3: Weather Data Unavailable

**Symptom:** Weather warnings not showing

**Check:**
```jinja
{{ states('weather.home') }}
```

**Quick Fix:**
- Resilience will retry weather entity access
- Verify weather integration is configured
- Check weather entity ID in PawControl options

---

## Configuration Examples

### Conservative (Fewer Retries, Fast Fail)

**Use When:** You want fast responses, have reliable services

```python
# For new components
CircuitBreakerConfig(
    failure_threshold=2,      # Open quickly
    timeout_seconds=15.0,     # Test recovery fast
)

RetryConfig(
    max_attempts=2,           # Only 1 retry
    initial_delay=0.5,        # Fast retry
)
```

---

### Aggressive (More Retries, Tolerant)

**Use When:** You have unreliable networks, want maximum reliability

```python
CircuitBreakerConfig(
    failure_threshold=10,     # Very tolerant
    timeout_seconds=180.0,    # Patient recovery
)

RetryConfig(
    max_attempts=5,           # 4 retries
    initial_delay=2.0,        # Patient retry
    max_delay=30.0,
)
```

---

## Monitoring Dashboard

Create a Lovelace card to monitor resilience:

```yaml
type: entities
title: PawControl Resilience
entities:
  - type: attribute
    entity: sensor.pawcontrol_statistics
    attribute: resilience
    name: Circuit Breakers
  - type: attribute
    entity: sensor.pawcontrol_notifications
    attribute: performance_metrics
    name: Notification Performance
  - entity: sensor.pawcontrol_errors
    name: Error Count
```

---

## Troubleshooting Checklist

### ❌ Something is broken

**Step 1:** Check logs
```bash
tail -f home-assistant.log | grep pawcontrol
```

**Step 2:** Check circuit breaker states
```yaml
service: pawcontrol.get_statistics
```

**Step 3:** Identify the problem
- `state: "open"` → Service is down, wait for recovery
- `failures: X` → Check why operations are failing
- No logs → Integration might not be loaded

**Step 4:** Take action
- Circuit OPEN → Wait or fix underlying service
- Repeated failures → Check configuration
- No response → Restart integration

### ✅ Everything is working

**Regular Checks:**
- Monthly: Review failure rates
- Weekly: Check circuit breaker health
- Daily: Monitor error logs

---

## Performance Tips

### 1. Adjust Timeouts Based on Service Speed

**Fast Services (< 1s response):**
```python
timeout_seconds=30.0
```

**Slow Services (> 5s response):**
```python
timeout_seconds=180.0
```

---

### 2. Use Appropriate Retry Delays

**Fast Network:**
```python
initial_delay=0.5
max_delay=5.0
```

**Slow/Unreliable Network:**
```python
initial_delay=2.0
max_delay=30.0
```

---

### 3. Monitor Cache Hit Rates

High cache hits = good performance:

```jinja
{{ states.sensor.pawcontrol_notifications.attributes.cache_stats.hit_rate }}
```

**Target:** > 70% cache hit rate

---

## Integration with Automations

### Example: Alert on Circuit Breaker Open

```yaml
automation:
  - alias: "PawControl Circuit Breaker Alert"
    trigger:
      - platform: state
        entity_id: sensor.pawcontrol_statistics
    condition:
      - condition: template
        value_template: >
          {% set cb = state_attr('sensor.pawcontrol_statistics', 'resilience') %}
          {{ cb is not none and 
             cb.values() | selectattr('state', 'eq', 'open') | list | length > 0 }}
    action:
      - service: notify.mobile_app
        data:
          title: "PawControl Service Issue"
          message: "A circuit breaker is OPEN - service may be degraded"
```

---

### Example: Reset Circuit Breaker Automatically

```yaml
automation:
  - alias: "Reset PawControl Circuit Breaker"
    trigger:
      - platform: time_pattern
        minutes: "/30"  # Every 30 minutes
    condition:
      - condition: template
        value_template: >
          {% set cb = state_attr('sensor.pawcontrol_statistics', 'resilience') %}
          {{ cb is not none and cb['dog_data_max']['state'] == 'open' and
             (now() - as_datetime(cb['dog_data_max']['opened_at'])).seconds > 1800 }}
    action:
      - service: pawcontrol.reset_circuit_breaker
        data:
          circuit_name: "dog_data_max"
```

---

## Best Practices Summary

### ✅ DO

- Monitor circuit breaker states regularly
- Adjust timeouts based on service characteristics
- Use retry logic for transient failures
- Log failures for debugging
- Test resilience with simulated failures

### ❌ DON'T

- Set failure_threshold too low (causes false opens)
- Use long timeouts for fast services (wastes time)
- Disable resilience for critical operations
- Ignore OPEN circuit breakers (fix root cause)
- Retry authentication failures (won't help)

---

## Getting Help

### Log Issues

**Enable Debug Logging:**
```yaml
logger:
  logs:
    custom_components.pawcontrol.resilience: debug
```

### Check GitHub Issues

Search existing issues: https://github.com/yourusername/pawcontrol/issues

### Community Support

Ask on Home Assistant forums with tag `pawcontrol`

---

## What's Next?

**For More Details:**
- Read [resilience.md](resilience.md) - Complete technical documentation
- Read [architecture.md](architecture.md) - System architecture
- Check [examples/](../examples/) - Code examples

**Need Help?**
- Check [troubleshooting.md](troubleshooting.md)
- Review [FAQ.md](FAQ.md)
- Open a GitHub issue

---

*Quick Start Guide - PawControl v1.0.0*  
*Last Updated: 2025-09-30*
