# Diagnostik

## Setup-Flags-Lokalisierung

Die folgende Tabelle listet die Setup-Flag-Übersetzungen für jede unterstützte
Sprache. Sie wird automatisch durch `scripts/sync_localization_flags` gepflegt.

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

## Benachrichtigungen

Die Diagnostik-Payload enthält unter `notifications.rejection_metrics` eine
zusätzliche Zusammenfassung für Benachrichtigungs-Ablehnungen/Fehler. Die Werte
werden aus dem `delivery_status` des Notification-Managers abgeleitet und
erleichtern die Analyse von fehlerhaften oder abgelehnten Zustellungen pro
Notify-Service.

Felder:

- `schema_version`: Version des Rejection-Schemas (aktuell `1`).
- `total_services`: Anzahl der bekannten Notify-Services im Snapshot.
- `total_failures`: Summe aller Fehlzustellungen über alle Services.
- `services_with_failures`: Liste der Services mit mindestens einer
  Fehlzustellung.
- `service_failures`: Mapping `{service_name: total_failures}` je Service.
- `service_consecutive_failures`: Mapping `{service_name: consecutive_failures}`
  je Service.
- `service_last_error_reasons`: Mapping `{service_name: last_error_reason}` je
  Service (z. B. `missing_notify_service`, `service_not_executed`).
- `service_last_errors`: Mapping `{service_name: last_error}` je Service (inkl.
  Exception-Text, falls vorhanden).
