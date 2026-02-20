# 🐕 Paw Control – Home Assistant Companion for Multi-Dog Households

Paw Control is a custom HACS integration that focuses on reliable automation
and monitoring for dogs that are already represented inside Home Assistant. The
integration keeps configuration and runtime logic aligned with Home
Assistant’s architecture guidelines: a config flow provisions helpers and
scripts, a shared `DataUpdateCoordinator` orchestrates module adapters, and all
HTTP calls reuse Home Assistant’s managed aiohttp session.

## Überblick über die Funktionen

### Geführte Einrichtung & Modulwahl
- Der mehrstufige Config Flow legt je Hund Stammdaten an, aktiviert Module wie
  Fütterung, GPS, Garten oder Besuchsmodus und verzweigt bei Bedarf direkt in
  die passenden Detaildialoge (z. B. GPS- oder Fütterungsparameter).
- Automatische Vorschläge aus Zeroconf, DHCP, USB oder HomeKit starten den
  Discovery-Flow, der Profilwahl, Modulzuordnung und externe Entitäten
  zusammenführt, bevor der Config Entry angelegt wird.
- Im Anschluss ordnet die Modulkonfiguration vorhandene Entitäten zu
  (Personen, Geräte-Tracker, Türsensoren, Wetter-Entity) und erlaubt den
  Import externer API-Endpunkte, falls ein Begleitgerät angebunden werden
  soll.
- Helfer wie `input_boolean`, `input_datetime` und Counter werden automatisch
  erzeugt; fehlende Assets lassen sich im Options-Flow nachpflegen.
  Menübasierte Options-Flows bündeln Hunde-Management, Türsensor-Einstellungen,
  Feeding- und GPS-Parameter sowie System-Flags in typisierten Teilflüssen und
  halten Tests für die erweiterten Options-Payloads bereit.

### Laufzeitmodule & Koordinator
- Der `PawControlCoordinator` bündelt alle Hundedaten und startet pro Modul
  passende Adapter (Feeding, Walk, GPS, Garden, Weather). Dadurch greifen alle
  Plattformen konsistent auf dieselbe Datenbasis zu.
- Die Modul-Adapter cachen Ergebnisse, nutzen bei Bedarf den Geräte-API-Client
  und liefern strukturierte Payloads für die Sensorplattformen.
- Das Laufzeit-Cache (`custom_components/pawcontrol/runtime_data.py`) protokolliert jetzt die erzeugende Schema-Version, hebt Altversionen automatisch auf das kompatible Minimum an und entfernt Future-Snapshots sofort aus `hass.data`, damit Reloads lieber sauber neu initialisieren als inkompatible Payloads weiterzureichen.

### Benachrichtigungen & Webhooks
- Der `PawControlNotificationManager` bündelt Push-Nachrichten, Personenerkennung,
  Rückfragen-Logik und Webhook-Handler mit Ratelimits, Caching und optionaler
  Signaturprüfung.
- Eigene Skripte, Buttons und Services (z. B. Testbenachrichtigungen) greifen
  auf dieselbe Infrastruktur zurück, wodurch Rückfragen oder Quittierungen für
  mehrere Benutzer synchron bleiben.

### Besuchsmodus & temporäre Hunde
- Besuchsstatus wird per Service, Switch und Button verwaltet; der
  Datenmanager speichert Metadaten wie Besuchername oder reduzierte Alarme und
  die Binary-Sensor-Plattform stellt den Status dar.
- Schritt-für-Schritt-Abläufe für Gäste-, Türsensor- und Benachrichtigungs-
  Workflows sind in der Produktionsdokumentation zusammengefasst.

### Wetter- und Gesundheitsauswertung
- Der `WeatherHealthManager` analysiert Forecast-Daten einer konfigurierten
  Wetter-Entity, berechnet Health-Scores und schlägt Aktivitätsfenster vor; die
  Ergebnisse fließen über den Weather-Adapter in die Koordinator-Payload ein.
- Ausführliche Automationsbeispiele für wettergesteuerte Benachrichtigungen und
  Schutzmaßnahmen liefert der Weather-Automation-Guide.

### Automations-Bausteine
- Der Dashboard-Generator erstellt und pflegt Lovelace-Layouts asynchron, die
  auf Modulebene differenzieren und optional Wetter-Widgets einblenden.
- Das Script-Management legt Benachrichtigungs-, Reset- und Testskripte pro Hund
  an und hält sie bei Moduländerungen aktuell.
- Zusätzliche Plattformen (Sensoren, Schalter, Buttons, Texte, Selektoren) lesen
  koordinierte Daten aus und spiegeln die Helper-States wider.
- Die System-Einstellungen des Options-Flows übernehmen `manual_check_event`,
  `manual_guard_event` und `manual_breaker_event` direkt als Text-Selectoren und
  synchronisieren sie nach dem Speichern automatisch mit den
  Resilience-Blueprint-Automationen, sodass Diagnostik, Blueprint und Skripte
  konsistent bleiben.
- Wettergesteuerte Automationen sowie Besucher-spezifische Dashboards lassen
  sich anhand der dokumentierten Rezepte direkt übernehmen.

### Asynchronität & Sitzungsverwaltung
- Alle HTTP-Helfer validieren über `ensure_shared_client_session`, dass nur die
  von Home Assistant verwaltete aiohttp-Session verwendet wird; die globalen
  Fixtures stellen mit `session_factory` konsistente aiohttp-Doubles bereit und
  Tests decken die Fehlerszenarien für Validator, Adapter, Notification-Manager
  und HTTP-Helfer ab. Ein Pre-Commit-Guard
  (`scripts/enforce_shared_session_guard.py`) verhindert neue `ClientSession()`-
  Instanzen – inklusive aliasierter `aiohttp.client`-Aufrufe – und entdeckt
  zusätzliche Pakete automatisch.
- Blockierende Arbeiten wie GPX-Generierung, Dashboard-Dateizugriffe und die
  Kalorien-Neuberechnung im Notfallmodus werden mit `asyncio.to_thread`
  beziehungsweise `_offload_blocking` ausgelagert, sodass der Event Loop
  reaktionsfähig bleibt.

### Services & Diagnostik
- Service-Aufrufe für Feeding, Walks, Garden-Sessions, Health-Logging sowie
  Benachrichtigungen sind in `services.yaml` dokumentiert, implementiert in
  `services.py` und durch Service-Telemetrie-Tests abgesichert.
- Diagnostics liefern Setup-Flags, Service-Guard-Metriken, Notification
  Rejection Metrics und eine aggregierte Fehlerübersicht für Guard/Notifications,
  damit Support-Teams Ursachen schneller klassifizieren können.

## Installation & Inbetriebnahme
1. **Repository zu HACS hinzufügen** (Kategorie Integration) und Paw Control
   installieren.
2. **Config Flow starten** (`Einstellungen → Geräte & Dienste → Integration`)
   und je Hund Module sowie Zuordnungen vornehmen.
3. **Optionale Schritte**:
   - Wetter-Entity, Türsensoren, Benachrichtigungsgeräte im Options-Flow
     nachjustieren.
   - Dashboard in Lovelace hinzufügen oder Skripte in Automationen nutzen.
   - Webhook-Ziele samt Secret konfigurieren, wenn externe Systeme angebunden
     werden sollen.

### Einrichtung – klare Schrittfolge
1. **Integration hinzufügen:** `Einstellungen → Geräte & Dienste → Integration`
   öffnen und *Paw Control* auswählen.
2. **Hund(e) anlegen:** Name, ID, Größe, Gewicht und optionale Gesundheitsdaten
   erfassen.
3. **Module wählen:** Feeding, GPS, Garten, Besuchsmodus und Wetter nach Bedarf
   aktivieren.
4. **Externe Entitäten zuordnen:** GPS-Quelle (Person/Gerätetracker),
   optional Türsensoren und Wetter-Entity auswählen.
5. **Optionen prüfen:** Dashboard-Generator, Benachrichtigungen, Performance-
   Modus und Datenaufbewahrung festlegen.
6. **Verifizieren:** Entitäten prüfen und eine Testbenachrichtigung senden.

### Fehlerbehebung – Schnellcheck
1. **Setup schlägt fehl:** Prüfe `Einstellungen → Geräte & Dienste → Logs` auf
   fehlende API-Endpunkte oder ungültige Entitäten.
2. **Keine Entitäten sichtbar:** Stelle sicher, dass mindestens ein Hund
   vollständig konfiguriert ist und das Entity-Profil nicht deaktiviert wurde.
3. **GPS ohne Daten:** GPS-Quelle muss ein aktiver Tracker oder eine Person mit
   Standortupdates sein; Teste die Quelle in Home Assistant.
4. **Benachrichtigungen fehlen:** Prüfe den gewählten Notification-Service und
   sende die Testbenachrichtigung.
5. **Leistungsprobleme:** Aktiviere den Performance-Modus oder reduziere die
   aktivierten Module pro Hund.

## Qualitäts- und Supportstatus
- Docstrings und Typannotationen werden projektweit erzwungen; ein Skript
  überwacht die Ruff-Baseline für fehlende Docstrings.
- Der Volltest-Workflow [`scheduled-pytest.yml`](.github/workflows/scheduled-pytest.yml) reserviert dienstags und freitags um
  03:00 UTC einen dedizierten Slot; manuelle Läufe erfordern `override_ci_window=true` und einen dokumentierten `run_reason`,
  damit abgestimmte Wartungsfenster priorisiert bleiben.
- Der CI-Job „TypedDict audit“ aus [`ci.yml`](.github/workflows/ci.yml) führt bei
  jedem Push sowie in Pull Requests `python -m scripts.check_typed_dicts --path
  custom_components/pawcontrol --path tests --fail-on-findings` aus und blockiert
  Releases sofort, falls neue untypisierte Dictionaries auftauchen.
- Der CI-Workflow prüft zusätzlich per
  `python -m scripts.sync_localization_flags --allowlist scripts/sync_localization_flags.allowlist --check`,
  ob alle Setup-Flag-Übersetzungen konsistent mit `strings.json` bleiben.
- Der Async-Dependency-Audit dokumentiert alle synchronen Bibliotheken, die
  `_offload_blocking`-Messwerte und die gewählten Mitigationsstrategien.
- Koordinator-Statistiken protokollieren jede Laufzeit-Store-Kompatibilitätsprüfung samt Statuszählern, Divergenzmarkern, Zeitstempeln und jetzt auch Laufzeit-Bilanzen pro Schweregrad. Diagnostics und System Health zeigen neben dem aktuellen Snapshot die kumulierten Sekunden je Level sowie die aktuelle Verweildauer an, damit Platinum-Ausrichtungs-Audits die Stabilität ohne Log-Replay nachvollziehen können. Zusätzlich hält eine begrenzte Assessment-Timeline die jüngsten Levelwechsel inklusive Divergenzrate und empfohlenen Aktionen fest und fasst das Fenster, die Event-Dichte, die häufigsten Gründe/Status sowie Spitzen- und Letztwerte der Level-Dauern zusammen, sodass Support-Teams Verlauf und Eskalationen ohne manuelles Historien-Scraping prüfen können.
- Unit-Tests decken die Session-Garantie und Kernadapter ab, benötigen jedoch
  weiterhin ein Home-Assistant-Test-Environment für vollständige Abdeckung.

### Support-Diagnostik
Das Diagnostics-Panel `setup_flags_panel` fasst Analytics-, Backup- und Debug-
Schalter mit lokalisierter Beschriftung zusammen, ergänzt Default-Werte sowie
die ausgehandelte Sprache, damit Support-Teams und Blueprint-Autoren den
Onboarding-Status ohne zusätzliche Parser übernehmen können.
Neben den aktivierten Zählern liefert der Block alle Quellenbezeichnungen aus
`SETUP_FLAG_SOURCE_LABELS` samt Übersetzungs-Keys. `strings.json` führt
dieselben Label- und Quellen-Texte unter `common.setup_flags_panel_*`, sodass
Übersetzungs-Workflows die Panels ohne manuelle Exporte nachpflegen können.

```json
{
  "title": "Setup flags",
  "title_default": "Setup flags",
  "description": "Analytics, backup, and debug logging toggles captured during onboarding and options flows.",
  "description_default": "Analytics, backup, and debug logging toggles captured during onboarding and options flows.",
  "language": "en",
  "flags": [
    {
      "key": "enable_analytics",
      "label": "Analytics telemetry",
      "label_default": "Analytics telemetry",
      "label_translation_key": "component.pawcontrol.common.setup_flags_panel_flag_enable_analytics",
      "enabled": true,
      "source": "system_settings",
      "source_label": "System settings",
      "source_label_default": "System settings",
      "source_label_translation_key": "component.pawcontrol.common.setup_flags_panel_source_system_settings"
    },
    {
      "key": "enable_cloud_backup",
      "label": "Cloud backup",
      "label_default": "Cloud backup",
      "label_translation_key": "component.pawcontrol.common.setup_flags_panel_flag_enable_cloud_backup",
      "enabled": false,
      "source": "default",
      "source_label": "Integration default",
      "source_label_default": "Integration default",
      "source_label_translation_key": "component.pawcontrol.common.setup_flags_panel_source_default"
    },
    {
      "key": "debug_logging",
      "label": "Debug logging",
      "label_default": "Debug logging",
      "label_translation_key": "component.pawcontrol.common.setup_flags_panel_flag_debug_logging",
      "enabled": true,
      "source": "options",
      "source_label": "Options flow",
      "source_label_default": "Options flow",
      "source_label_translation_key": "component.pawcontrol.common.setup_flags_panel_source_options"
    }
  ],
  "enabled_count": 2,
  "disabled_count": 1,
  "source_breakdown": {
    "system_settings": 1,
    "default": 1,
    "options": 1
  },
  "source_labels": {
    "options": "Options flow",
    "system_settings": "System settings",
    "advanced_settings": "Advanced settings",
    "config_entry": "Config entry defaults",
    "default": "Integration default"
  },
  "source_labels_default": {
    "options": "Options flow",
    "system_settings": "System settings",
    "advanced_settings": "Advanced settings",
    "config_entry": "Config entry defaults",
    "default": "Integration default"
  }
}
```

### System-Health-Resilienz & Blueprint-Automation
- Der System-Health-Endpunkt färbt Guard-Skip- und Breaker-Warnungen über
  farbcodierte Indikatoren ein und fasst Guard-, Breaker- und Gesamtstatus
  zusammen, sobald definierte Resilience-Schwellen überschritten werden. Tests
  prüfen Normal-, Warn- und Kritikalarm, deaktivierte Skript-Schwellen sowie
  Options-Fallbacks, damit Bereitschaftsteams im Frontend sofort kritische
  Zustände erkennen.
- Die neuen Options-Flow-Felder `resilience_skip_threshold` und
  `resilience_breaker_threshold` setzen Guard- und Breaker-Schwellen zentral und
  synchronisieren Skript, Diagnostics und System-Health ohne YAML-Anpassungen.
- Die Blueprint-Vorlage `resilience_escalation_followup` ruft das generierte
  Eskalationsskript samt aktiver Schwellenwerte auf, erlaubt optionale Pager-
  Aktionen und bietet getrennte manuelle Guard-/Breaker-Events sowie einen
  Watchdog, damit Runbooks ohne Duplikate auf Abruf reagieren können.
- Diagnostics spiegeln die konfigurierten `manual_*`-Trigger, aggregieren die
  Blueprint-Konfiguration über `config_entries` und migrieren vorhandene
  Skript-Schwellen bei Bestandsinstallationen automatisch in den Optionen-
  Payload. Dadurch bleiben System-Health, Blueprint und Dokumentation
  synchronisiert.
- `service_execution.entity_factory_guard` exportiert die adaptive Laufzeit-
  schutzschwelle der Entity Factory inklusive aktueller Bodenzeit, Delta zum
  Baseline-Floor, gemessenem Peak- und Minimal-Floor, jüngster Bodenzeit-
  Änderung (absolut und relativ), Durchschnitts-/Minimal-/Maximallaufzeit der
  Samples, Stabilitäts- und Volatilitätsquoten sowie Laufzeit-Jitter über
  gesamte Historie und die letzten fünf Kalibrierungen. Die Entity Factory
  protokolliert zusätzlich die letzten Guard-Events, berechnet daraus
  Recency-Samples, Kurzfrist-Stabilität und einen qualitativen Trend, der die
  jüngste Stabilität gegen den Lifetime-Durchschnitt stellt, damit Support sofort
  erkennt, ob sich Scheduler-Jitter erholt oder verschlechtert.
  Jede Rekalibrierung landet im Runtime-Store, Telemetrie normalisiert die Werte
  (einschließlich Streak-Zählern und Event-Historie) und Diagnostics sowie
  System-Health stellen die JSON-Schnappschüsse zusammen mit den Guard- und
  Breaker-Indikatoren bereit.
- Die Config-Entry-Diagnostics enthalten zusätzlich einen Resilience-Block, der
  die zuletzt berechneten Breaker-Snapshots inklusive Recovery-Latenzen,
  Ablehnungsquoten und Identifikatoren aus dem Runtime-Store zieht, sodass
  Support-Teams selbst bei pausiertem Koordinator auf vollständige Resilience-
  Daten zugreifen können.
- Diagnostics und System-Health ergänzen einen `runtime_store`-Block, der für
  jede Config-Entry das gestempelte Schema, den Mindest-Support-Stand, offene
  Migrationen, Divergenzen zwischen Entry-Attribut und Domain-Cache sowie
  zukünftige Schema-Versionen markiert. Damit lassen sich Kompatibilitäts-
  probleme ohne Debug-Konsole erkennen und sofort belegen.
- Die Telemetrie ergänzt eine `runtime_store_assessment`, die Divergenzraten,
  Migrationserfordernisse und Entry-/Store-Status in die Stufen `ok`, `watch`
  oder `action_required` verdichtet. Diagnostics, System-Health und
  Koordinatorstatistiken zeigen dadurch sofort an, wann der
  `runtime_store_compatibility`-Repair oder ein Reload nötig ist. Zusätzlich
  protokollieren wir das vorherige Level, die Level-Streak, den Zeitpunkt der
  letzten Änderung sowie Eskalations- und Deeskalationszähler, damit Audits
  erkennen, ob sich die Cache-Gesundheit stabilisiert oder erneut verschlechtert
  und Rotationen bei Bedarf sofort eingreifen können.
- Zusätzlich fasst eine `runtime_store_timeline_summary` die wichtigsten
  Kennzahlen der Kompatibilitäts-Timeline zusammen: Gesamtanzahl und Anteil der
  Level-Wechsel, Level-/Status-Histogramme, eindeutige Gründe sowie das zuletzt
  beobachtete Level mitsamt Divergenzindikatoren. Telemetrie normalisiert diese
  Zusammenfassung, Diagnostics und System-Health liefern sie neben der
  vollständigen Ereignisliste und die Tests sichern das Rollup ab, sodass
  Platin-Audits die Cache-Stabilität ohne manuelles Parsen der Timeline bewerten
  können.
- Die Reparaturprüfungen spiegeln den gleichen Snapshot wider, erzeugen das Issue
  `runtime_store_compatibility` mit abgestuften Schweregraden bei Divergenzen,
  Migrationsbedarf oder zukünftigen Schemata und räumen den Eintrag, sobald die
  Metadaten wieder `current` melden. Damit bleibt das Reparatur-Dashboard eng an
  den Diagnostics-Nachweisen gekoppelt.

Paw Control konzentriert sich auf eine verlässliche Home-Assistant-Integration
statt auf proprietäre Cloud-Dienste. Funktionen, die noch in Arbeit sind (z. B.
Hardware-spezifische APIs), werden erst in der Dokumentation beworben, wenn sie
inklusive Tests ausgeliefert sind.
