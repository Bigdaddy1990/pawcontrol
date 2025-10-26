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

Die automatisch generierte Statistik-Ansicht der PawControl-Dashboards ergänzt
dieses Monitoring um eine **Resilience metrics**-Markdown-Karte. Sie kombiniert
die Koordinator-Snapshot-Werte mit den `service_execution.rejection_metrics`
und `service_execution.guard_metrics` aus den Performance-Statistiken, zeigt
Ablehnungszähler, Breaker-Anzahl, Guard-Ausführungs- und Skip-Zähler samt
Gründen sowie den letzten Breaker synchronisiert an und erspart Platinum-
Dashboards eigene Templates.【F:custom_components/pawcontrol/dashboard_templates.py†L1723-L1966】【F:tests/components/pawcontrol/test_dashboard_renderer.py†L92-L176】
Automationen können dieselben Guard-Zähler direkt über
`sensor.pawcontrol_statistics.attributes.service_execution.guard_metrics`
verarbeiten; der Laufzeitsnapshot liefert ausgeführte/übersprungene Aufrufe,
zusammengefasste Gründe und die jüngsten Guard-Ergebnisse parallel zu den
Rejection-Kennzahlen und ermöglicht Eskalationen ohne Dashboard-Scraping.【F:custom_components/pawcontrol/coordinator_tasks.py†L902-L990】【F:tests/unit/test_coordinator_tasks.py†L1004-L1074】
API-Clients, die auf die Rohdaten angewiesen sind, bekommen identische
`service_execution`-Blöcke über `PawControlCoordinator.get_performance_snapshot()`
und sparen sich eigene Normalisierung, weil der Koordinator die Guard-Zähler
aus den Runtime-Statistiken übernimmt und dieselben Rejection-Metriken
anhängt.【F:custom_components/pawcontrol/coordinator.py†L474-L525】【F:tests/unit/test_coordinator.py†L117-L165】
Der Script-Manager legt zusätzlich ein **Resilience-Eskalationsskript** an, das
Guard-Skip-Schwellen und Breaker-Zähler überwacht, persistente Benachrichtigungen
auslöst und bei Bedarf ein Follow-up-Skript startet, sodass Bereitschaftsteams
automatisch reagieren können.【F:custom_components/pawcontrol/script_manager.py†L360-L760】【F:tests/unit/test_data_manager.py†L470-L580】

### Resilience-Eskalationspanel interpretieren
Diagnostics exportieren das Panel `resilience_escalation`, damit Runbooks die
automatisch erzeugte Eskalationslogik prüfen können. Der Snapshot umfasst die
bereitgestellte Script-Entity, aktive Guard- und Breaker-Schwellen, das
Follow-up-Skript sowie die zuletzt generierte und ausgelöste Zeitmarke.【F:custom_components/pawcontrol/script_manager.py†L744-L940】【F:custom_components/pawcontrol/diagnostics.py†L180-L214】【F:tests/components/pawcontrol/test_diagnostics.py†L214-L247】

```json
{
  "entity_id": "script.pawcontrol_pack_resilience_escalation",
  "available": true,
  "thresholds": {
    "skip_threshold": {"default": 3, "active": 5},
    "breaker_threshold": {"default": 1, "active": 2}
  },
  "followup_script": {
    "default": "",
    "active": "script.ops_oncall_followup",
    "configured": true
  },
  "statistics_entity_id": {
    "default": "sensor.pawcontrol_statistics",
    "active": "sensor.pawcontrol_statistics"
  },
  "escalation_service": {
    "default": "persistent_notification.create",
    "active": "persistent_notification.create"
  },
  "last_generated": "2024-02-20T09:15:00+00:00",
  "last_triggered": "2024-02-21T06:42:10+00:00"
}
```

Die Guard- und Breaker-Schwellen lassen sich direkt über den Options-Flow im
Schritt **Systemeinstellungen** pflegen. Die neuen Eingaben
`resilience_skip_threshold` und `resilience_breaker_threshold` übernehmen die
ausgewählten Werte, setzen das Resilience-Skript mit denselben Defaults neu auf
und stehen dem System-Health-Endpunkt ohne zusätzliche Blueprint-Anpassungen zur
Verfügung.【F:custom_components/pawcontrol/options_flow.py†L1088-L1143】【F:tests/unit/test_options_flow.py†L804-L852】【F:custom_components/pawcontrol/script_manager.py†L431-L820】

**Interpretation:**

- `skip_threshold.active` = 5 → Guard-Skips lösen erst bei fünf Übersprüngen
  eine Eskalation aus. Runbooks können niedrigere Schwellen wählen, wenn
  kritische Automationen schon nach wenigen Skips untersucht werden sollen.
- `breaker_threshold.active` = 2 → Bereits zwei gleichzeitige offene oder halb
  offene Breaker erzeugen eine Benachrichtigung. Höhere Werte eignen sich für
  weniger empfindliche Umgebungen.
- `followup_script.active` = `script.ops_oncall_followup` → Nach jeder
  Eskalation wird dieses Skript mit Kontextvariablen (Skip- und Breaker-Zähler)
  gestartet, um Tickets oder Pager auszulösen.【F:custom_components/pawcontrol/script_manager.py†L642-L720】
- `last_triggered` dokumentiert den jüngsten Alarmzeitpunkt in UTC und erlaubt
  Bereitschaften, ausgelöste Eskalationen mit Incident-Logs abzugleichen.

### System-Health-Abgleich

Der System-Health-Endpunkt übernimmt die aktiven `skip_threshold`- und
`breaker_threshold`-Werte aus dem Resilience-Skript. Skip-Warnungen wechseln von
Verhältnis-Schwellen auf die konfigurierten Counts, behalten aber einen
Fallback für das systemweite Verhältnis bei, sobald weniger als eine Konfiguration
vorliegt. Breaker-Indikatoren werden kritisch, sobald die aktive Schwelle
erreicht wird, und warnen weiterhin bei Rejection-Breakern oder Countdown-Werten
unterhalb der Eskalationsgrenze.【F:custom_components/pawcontrol/system_health.py†L150-L356】【F:tests/components/pawcontrol/test_system_health.py†L1-L210】
Damit sehen Bereitschaftsteams dieselben Grenzwerte wie das Skript; die
Diagnose-Telemetrie `service_execution.guard_summary.thresholds` und
`service_execution.breaker_overview.thresholds` dokumentieren Quelle, aktive
Counts sowie die optionalen Default-Verhältnisse für Dashboards und Runbooks.

### Blueprint: Resilience-Eskalations-Follow-up

Die mitgelieferte Blueprint-Automation
`pawcontrol/resilience_escalation_followup` prüft dieselben
`service_execution`-Kennzahlen wie das Panel, liest die aktiven Guard- und
Breaker-Schwellen direkt aus dem generierten Script-Entity und ruft das Skript
inklusive optionaler Pager-/Follow-up-Aktionen auf, sobald eine Schwelle
übertreten wird. Damit entfallen doppelte YAML-Schwellen; zusätzliche Aktionen
lassen sich über die Blueprint-Eingaben konfigurieren, ohne dass die Guard-
oder Breaker-Checks kopiert werden müssen.【F:blueprints/automation/pawcontrol/resilience_escalation_followup.yaml†L1-L160】

Neu hinzugekommen sind ein zeitbasierter Watchdog (`watchdog_interval_minutes`)
und ein manuell auslösbares Ereignis (`manual_check_event`), sodass
Resilience-Checks auch bei stagnierenden Sensordaten oder auf Abruf ausgelöst
werden können, ohne dass separate Automationen erstellt werden müssen.【F:blueprints/automation/pawcontrol/resilience_escalation_followup.yaml†L25-L65】
Zusätzliche Ereignisse (`manual_guard_event`, `manual_breaker_event`) erlauben
separate Pager-Pfade für Guard- und Breaker-Rechecks. Beide Trigger rufen das
Eskalationsskript sowie die jeweiligen Follow-up-Aktionen auch ohne Überschreiten
der Schwellen auf, sodass Runbooks ohne YAML-Duplikate manuelle Prüfungen
auslösen können.【F:blueprints/automation/pawcontrol/resilience_escalation_followup.yaml†L36-L125】

Diagnostics exportieren die konfigurierten `manual_*`-Events zusammen mit den
resolvierten Guard-/Breaker-Schwellen direkt aus dem generierten Skript. Damit
sehen Support-Handbücher sofort, welche Trigger aktiv sind und ob ältere
Installationen ihre Script-Defaults bereits in die Optionen übernommen haben.
Die Snapshot-Logik aggregiert Blueprint-Konfigurationen über die
`config_entries`-API, während die Tests sicherstellen, dass die Events in den
Ausgaben auftauchen.【F:custom_components/pawcontrol/script_manager.py†L238-L412】【F:tests/components/pawcontrol/test_diagnostics.py†L120-L208】

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
