# Abgleich Home Assistant Developer-Vorgaben – PawControl

Diese Übersicht gleicht die Home Assistant Developer-Dokumentation mit der
aktuellen Implementierung der PawControl-Integration ab. Für jede
Integrationsebene wird der Stand der Umsetzung dokumentiert und potenzielle
Lücken werden benannt, damit die Platinum-Anforderungen nachvollziehbar
bleiben.

## 1) Config Flow

**Status:** Teilweise erfüllt

**Beobachtungen (Evidenz):**
- In UI-Config-Flow ist vorhanden (`ConfigFlow`, `async_step_user`,
  `async_step_dogs`, `async_step_finish`).
- Single-Instance-Schutz erfolgt über `_async_current_entries()`.
- Config-Eintrag wird ohne YAML-Config erstellt.

**Potenzielle Lücken gegenüber HA-Guidelines:**
- Kein `unique_id`/`async_set_unique_id` sichtbar; dadurch keine explizite
  Konfliktprüfung über IDs.
- Kein Reauth/Reconfigure-Flow erkennbar.

## 2) Options Flow

**Status:** Teilweise erfüllt

**Beobachtungen (Evidenz):**
- Options-Flow existiert (`PawControlOptionsFlow`), mit Menüführung und
  separatem Schritt für globale Einstellungen.
- Optionen werden direkt in `ConfigEntry.options` gespeichert.

**Potenzielle Lücken gegenüber HA-Guidelines:**
- Validierungs-/Normalisierungslogik (z. B. `GPSOptionsNormalizerMixin`) wird
  im Options-Flow derzeit nicht genutzt.
- Nur globale Settings sind editierbar; keine per-Dog-Optionen.

## 3) Coordinator

**Status:** Erfüllt

**Beobachtungen (Evidenz):**
- Nutzung von `DataUpdateCoordinator` mit `config_entry` und
  `update_interval`.
- Fehlerbehandlung via `UpdateFailed`.
- Zentralisierung des Datenabrufs pro Hund und Module.

## 4) Plattformen (Entities)

**Status:** Erfüllt

**Beobachtungen (Evidenz):**
- Entitäten nutzen `_attr_has_entity_name = True` und `unique_id`-Schemas.
- Geräteinformationen werden über `create_device_info` konsistent erzeugt.
- Plattformen sind über `PLATFORMS` in `__init__.py` registriert.

## 5) Services

**Status:** Erfüllt

**Beobachtungen (Evidenz):**
- Service-Handler befinden sich in `services.py`.
- Service-Schemas/Dokumentation in `services.yaml` gepflegt.

## 6) Diagnostics

**Status:** Teilweise erfüllt

**Beobachtungen (Evidenz):**
- Diagnostics-Export implementiert (`async_get_config_entry_diagnostics`).
- Redaction sensibler Daten über `async_redact_data`.

**Potenzielle Lücken gegenüber HA-Guidelines und eigenen Platinum-Hinweisen:**
- Aktueller Export enthält nur Entry/Coordinator/Dog-Überblick; die in
  `docs/diagnostics.md` beschriebenen Abschnitte (z. B.
  `notifications.rejection_metrics`, `service_execution.guard_metrics`) werden
  nicht ausgegeben.

## 7) Quality Scale / Platinum-Nachweise

**Status:** Erfüllt (Declaration + interne Nachweise vorhanden)

**Beobachtungen (Evidenz):**
- Manifest deklariert `quality_scale: "platinum"`.
- `quality_scale.yaml` und `docs/compliance_gap_analysis.md` dokumentieren
  die Platinum-Regeln und verweisen auf Tests/Dokumentation.

## Nächste empfohlene Schritte

1. **Config Flow**: Prüfen, ob in stabiler `unique_id` gesetzt werden kann und
   ob Reauth/Reconfigure-Fälle relevant sind.
2. **Options Flow**: Validierungs-/Normalisierungslogik konsolidieren und ggf.
   per-Dog-Optionen anbieten.
3. **Diagnostics**: Diagnostics-Ausgabe an die Dokumentation anpassen oder die
   Dokumentation aktualisieren, damit Platinum-Nachweise konsistent bleiben.
