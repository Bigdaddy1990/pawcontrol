# PawControl Automations & Dashboards (EN)

This guide complements the automation examples by adding dashboard-focused
snippets that surface the diagnostics telemetry in Lovelace. For full automation
workflows, see [`docs/automation_examples.md`](automation_examples.md).

## Diagnostics Dashboards (Lovelace)

### Service guard metrics (`service_execution.guard_metrics`)

```yaml
type: markdown
title: Service guard metrics
content: |-
  {% set service = state_attr('sensor.pawcontrol_statistics', 'service_execution') or {} %}
  {% set guard = service.get('guard_metrics', {}) %}
  ## 🛡️ Guard metrics
  - **Executed:** {{ guard.get('executed', 0) }}
  - **Skipped:** {{ guard.get('skipped', 0) }}
  - **Reasons:** {{ guard.get('reasons', {}) | tojson }}
  - **Last results:** {{ guard.get('last_results', []) | tojson }}
```

### Notification rejection metrics (`notifications.rejection_metrics`)

```yaml
type: markdown
title: Notification rejection metrics
content: |-
  {% set notifications = state_attr('sensor.pawcontrol_diagnostics', 'notifications') or {} %}
  {% set rejection = notifications.get('rejection_metrics', {}) %}
  ## 🔔 Notification failures
  - **Total services:** {{ rejection.get('total_services', 0) }}
  - **Total failures:** {{ rejection.get('total_failures', 0) }}
  - **Services with failures:** {{ rejection.get('services_with_failures', []) | tojson }}
  - **Last error reasons:** {{ rejection.get('service_last_error_reasons', {}) | tojson }}
```

### Guard + notification error metrics (`guard_notification_error_metrics`)

```yaml
type: markdown
title: Guard + notification errors
content: |-
  {% set metrics = state_attr('sensor.pawcontrol_diagnostics', 'guard_notification_error_metrics') or {} %}
  {% set guard = metrics.get('guard', {}) %}
  {% set notifications = metrics.get('notifications', {}) %}
  ## 🚨 Combined error metrics
  - **Available:** {{ metrics.get('available', false) }}
  - **Total errors:** {{ metrics.get('total_errors', 0) }}
  - **Guard skipped:** {{ guard.get('skipped', 0) }}
  - **Guard reasons:** {{ guard.get('reasons', {}) | tojson }}
  - **Notification failures:** {{ notifications.get('total_failures', 0) }}
  - **Classified errors:** {{ metrics.get('classified_errors', {}) | tojson }}
```
