# Diagnostics

## Setup Flags Localization

The following table lists the setup flag translations for each supported
language. It is maintained automatically by `scripts/sync_localization_flags`.

<!-- START_SETUP_FLAGS_TABLE -->
| Übersetzungsschlüssel | Englisch (`en`) | Deutsch (`de`) | Spanisch (`es`) | Französisch (`fr`) |
| --- | --- | --- | --- | --- |
| component.pawcontrol.common.setup_flags_panel_flag_debug_logging | Debug logging | Debug-Logging | Registro de depuración | Journalisation de débogage |
| component.pawcontrol.common.setup_flags_panel_flag_enable_analytics | Analytics telemetry | Analyse-Telemetrie | Telemetría de analíticas | Télémétrie d'analyse |
| component.pawcontrol.common.setup_flags_panel_flag_enable_cloud_backup | Cloud backup | Cloud-Backup | Copia de seguridad en la nube | Sauvegarde cloud |
| component.pawcontrol.common.setup_flags_panel_source_advanced_settings | Advanced settings | Erweiterte Einstellungen | Configuración avanzada | Paramètres avancés |
| component.pawcontrol.common.setup_flags_panel_source_blueprint | Blueprint suggestion | Blueprint-Vorschlag | Sugerencia de blueprint | Suggestion de blueprint |
| component.pawcontrol.common.setup_flags_panel_source_config_entry | Config entry defaults | Konfigurationseintrag | Valores predeterminados de la entrada de configuración | Valeurs par défaut de l'entrée de configuration |
| component.pawcontrol.common.setup_flags_panel_source_default | Integration default | Integrationsstandard | Valor predeterminado de la integración | Valeur par défaut de l'intégration |
| component.pawcontrol.common.setup_flags_panel_source_disabled | Disable | Deaktivieren | Desactivar | Désactiver |
| component.pawcontrol.common.setup_flags_panel_source_options | Options flow | Options-Flow | Flujo de opciones | Flux d'options |
| component.pawcontrol.common.setup_flags_panel_source_system_settings | System settings | Systemeinstellungen | Configuración del sistema | Paramètres système |
<!-- END_SETUP_FLAGS_TABLE -->

## Notifications

The diagnostics payload includes an additional summary for notification
rejections or failures under `notifications.rejection_metrics`. The values are
derived from the Notification Manager's `delivery_status` and make it easier to
analyze failed or rejected deliveries per notify service.

Fields:

- `schema_version`: Version of the rejection schema (currently `1`).
- `total_services`: Number of known notify services in the snapshot.
- `total_failures`: Sum of failed deliveries across all services.
- `services_with_failures`: List of services with at least one failed delivery.
- `service_failures`: Mapping `{service_name: total_failures}` per service.
- `service_consecutive_failures`: Mapping
  `{service_name: consecutive_failures}` per service.
- `service_last_error_reasons`: Mapping `{service_name: last_error_reason}` per
  service (for example, `missing_notify_service`, `service_not_executed`).
- `service_last_errors`: Mapping `{service_name: last_error}` per service
  (including exception text, when available).

## Rejection Metrics Failure Reasons

Service delivery failures also populate the shared `rejection_metrics` payload
within coordinator/performance diagnostics. These counters aggregate failure
reasons across notification delivery attempts and service-triggered sends.

Fields:

- `last_failure_reason`: Most recent classified failure reason (for example,
  `auth_error`, `device_unreachable`, `missing_service`).
- `failure_reasons`: Mapping `{reason: count}` summarising failure reasons.

## Coordinator Rejection Metrics Schema

The diagnostics payload always exports a full `rejection_metrics` snapshot (with
defaults) under `coordinator_info.statistics.rejection_metrics`,
`performance_metrics.rejection_metrics`, and `service_execution.rejection_metrics`.
The schema version is currently `4`.

Fields:

- `schema_version`: Version of the rejection metrics payload (`4`).
- `rejected_call_count`: Total rejected coordinator calls.
- `rejection_breaker_count`: Total circuit breaker rejections.
- `rejection_rate`: Rejection rate for the observed window.
- `last_rejection_time`: Timestamp of the most recent rejection.
- `last_rejection_breaker_id`: Circuit breaker identifier for the last rejection.
- `last_rejection_breaker_name`: Circuit breaker name for the last rejection.
- `last_failure_reason`: Most recent classified failure reason.
- `failure_reasons`: Mapping `{reason: count}` for failure classifications.
- `open_breaker_count`: Count of open circuit breakers.
- `half_open_breaker_count`: Count of half-open circuit breakers.
- `unknown_breaker_count`: Count of breakers without a known state.
- `open_breakers`: List of open breaker names.
- `open_breaker_ids`: List of open breaker identifiers.
- `half_open_breakers`: List of half-open breaker names.
- `half_open_breaker_ids`: List of half-open breaker identifiers.
- `unknown_breakers`: List of breaker names without a known state.
- `unknown_breaker_ids`: List of breaker identifiers without a known state.
- `rejection_breaker_ids`: List of breakers responsible for rejections.
- `rejection_breakers`: List of breaker names responsible for rejections.

## Service Guard Metrics

Guarded Home Assistant service calls are exported under
`service_execution.guard_metrics`. The diagnostics payload always includes this
section, even when no guarded calls have been recorded, in which case the
metrics default to zeroed values.

Fields:

- `executed`: Count of guarded service calls that executed.
- `skipped`: Count of guarded service calls that were skipped.
- `reasons`: Mapping `{reason: count}` for skip reasons.
- `last_results`: Ordered list of recent guard results with `domain`, `service`,
  `executed`, and optional `reason`/`description`.

## Service Guard + Notification Errors

The diagnostics payload also exports aggregated error metrics under
`guard_notification_error_metrics`. This section combines service guard skip
reasons with notification delivery failures to highlight recurring issues in a
single place.

Fields:

- `schema_version`: Version of the aggregated error schema (currently `1`).
- `available`: `true` when at least one guard skip or notification failure is
  recorded.
- `total_errors`: Combined count of guard skips and notification failures.
- `guard.skipped`: Total service guard skips captured.
- `guard.reasons`: Mapping `{reason: count}` for guard skips.
- `notifications.total_failures`: Total failed notification deliveries.
- `notifications.services_with_failures`: List of notify services with failures.
- `notifications.reasons`: Mapping `{reason: count}` for notification failures.
- `classified_errors`: Mapping `{classification: count}` that bucketizes guard
  and notification errors into shared categories (for example, `auth_error`,
  `device_unreachable`, `missing_service`).
