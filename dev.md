# Development plan

## Aktueller Baustellenüberblick

- Die notwendigen Shims für `pytest_asyncio`, `pytest_cov.plugin` und
  `pytest_homeassistant_custom_component` liegen jetzt lokal vor, damit Pytest
  ohne externe Abhängigkeiten startet.
- Regressionstests stellen sicher, dass diese Pytest-Shims auch künftig ohne
  externe Abhängigkeiten importierbar bleiben.
- Ein lokales `hassfest`-Skript validiert Manifest- und Übersetzungsfelder
  offline; ein Regressionstest deckt Erfolgs- und Fehlerpfade ab, damit der
  Guard-Lauf ohne Home-Assistant-Abhängigkeiten stabil bleibt.
- Die Home-Assistant-Stubs decken zusätzlich `homeassistant.components.repairs`
  und `data_entry_flow` ab; diese Bereiche müssen mit kommenden HA-Releases
  aktiv gegengeprüft werden.
- Die Flow-Stubs spiegeln jetzt die Home-Assistant-Menü- und Progress-
  Ergebnisse (Menu, Progress, Progress Done, External Done) nach, damit neue
  Release-Änderungen bei Repairs- und Options-Flows frühzeitig erkannt werden.
- Das Event-Loop-Plugin importiert jetzt `asyncio` korrekt und stellt somit den
  Haupt-Thread-Loop wieder zuverlässig bereit.
- Ein Regressionstest prüft jetzt explizit den Import des Asyncio-Test-Plugins
  und dass das Patchen/Zurücksetzen von `get_event_loop` nach HA-Vorbild
  funktioniert, sodass Python-3.13-Event-Loop-Anpassungen früh auffallen.
- Der Entwicklungsplan bleibt die zentrale Stelle, um Shim-Drift und neue HA-
  Anforderungen zeitnah festzuhalten und gegen die Platinum-Checks
  gegenzuprüfen.
- Die Registry-Stubs speichern jetzt Config-Entry-Zuordnungen und Basis-
  Metadaten (Name, Hersteller, Modell, Konfigurations-URL) je Gerät und
  synchronisieren Entity-Metadaten, sodass Registry-Tests eng an den HA-
  Release-Notes bleiben.
- Die Registry-Stubs erfassen jetzt Config-Entry-Mengen sowie zusätzliche
  Geräte- und Entity-Metadaten (Identifiers, Connections, Name-by-User,
  Translation Keys, Aliases), damit die Factory-Tests HA-Änderungen an den
  Registry-Signaturen frühzeitig melden.
- Die Registry-Stubs spiegeln zusätzliche HA-Felder (z. B. Area-ID,
  Suggested-Area, Disabled-Status, Primary-Config-Entry, Entity-Category,
  Icon, Original-Icon, Unit-of-Measurement) und prüfen diese in den
  Regressionstests, damit spätere API-Erweiterungen sofort auffallen.
- Die Registry-Stubs spiegeln jetzt auch `original_unit_of_measurement` in den
  Entity-Metadaten wider und testen die Fortschreibung, damit neue
  Einheitserweiterungen aus HA-Release-Notes sofort sichtbar werden.
- Die Registry-Stubs erweitern Geräte- und Entity-Metadaten um Preferred-Area-
  IDs sowie Hidden-Flags, damit neue HA-Felder zu Bereichszuweisungen und
  Sichtbarkeit unmittelbar in den Regressionstests reflektiert werden.
- Die Registry-Stubs speichern jetzt auch `model_id`-Metadaten und prüfen deren
  Fortschreibung bei Create-/Update-Aufrufen, damit HA-Änderungen an der
  Geräte-Registry frühzeitig sichtbar werden.
- Die Registry-Stubs halten jetzt die Home-Assistant-Zeitstempel
  (`created_at`/`modified_at`) fest und prüfen deren Fortschreibung in den
  Regressionstests, damit künftige Registry-Metadaten-Erweiterungen lückenlos
  erkannt werden.
- Der gemeinsame UTC-Helfer wird jetzt zentral genutzt, sodass Registry-
  Zeitstempel konsistent bleiben und keine doppelten Definitionen mehr durch
  die Flow- und Registry-Stubs laufen.
- Reparatur- und OptionsFlow-Regressionstests decken nun auch Standard-
  Platzhalter sowie External-/Progress-Schritte ab, damit optionale Felder aus
  neuen HA-Releases sofort auffallen.
- Die Registry-Stubs liefern jetzt pro Testlauf konsistente Singletons für
  Geräte- und Entity-Registries; Regressionstests prüfen den gemeinsamen
  Zustand über die Modul-Helper hinweg.
- Die Registry-Stubs bieten jetzt HA-ähnliche Lookup-Helper
  (`async_get_device`, `async_entries_for_device`) und Regressionstests decken
  die Identifier/Connection-Filtern sowie Geräte-basierte Entity-Filter ab,
  damit Registry-Aufrufe aus HA-Release-Notes frühzeitig validiert werden.
- Die Registry-Stubs unterstützen jetzt das Entfernen von Geräten und Entities
  (`async_remove_device`, `async_remove`) samt Modul-Helpern; Regressionstests
  prüfen die Entfernung sowie das leere Ergebnis der Filter-Helper nach dem
  Entfernen.
- Die Registry-Stubs mergen jetzt Geräte anhand von Identifiers/Connections
  sowie Entities anhand von Unique-IDs/Plattformen, sodass
  `async_get_or_create` bestehende Einträge wie in HA wiederverwendet;
  Regressionstests prüfen die Zusammenführung und die angereicherten
  Config-Entry-Zuordnungen.
- Die Issue-Registry-Stubs spiegeln jetzt HA-ähnliche
  `async_get`/`async_create_issue`/`async_delete_issue`-Helper wider und ein
  Regressionstest prüft das Anlegen, Aktualisieren und Entfernen von Issues,
  damit kommende HA-Release-Änderungen an der Issue-Registry früh sichtbar
  werden.
- Die Issue-Registry-Stubs bieten jetzt zusätzlich einen
  `async_get_issue`-Helper, der gespeicherte Issues wie in Home Assistant
  zurückliefert; die Regressionstests prüfen Get/Update/Delete gemeinsam, um
  API-Drift sofort zu erkennen.
- Die Issue-Registry-Stubs erfassen jetzt `translation_domain` (Default: Domain)
  und prüfen Overrides in den Regressionstests, damit Übersetzungsänderungen aus
  Home Assistant zeitnah auffallen.
- Die Issue-Registry-Stubs spiegeln jetzt Persistenz- und Issue-Domain-Flags,
  Created/Dismissed-Zeitstempel sowie Ignore-Helper wider; die Regressionstests
  prüfen Persistenz-Defaults, Timestamp-Fortschreibung und Ignore-Flows, damit
  HA-Änderungen an der Issue-Registry frühzeitig sichtbar werden.
- Die Issue-Registry-Stubs bewahren ab sofort `dismissed`-Zeitstempel bei Re-
  Registrierungen und aktualisieren diese nur bei neuen Dismissals; die
  Regressionstests prüfen die Timestamp-Erhaltung sowie Ignore/Unignore-Flows
  und die Severity-/Metadata-Felder gemeinsam.
- Die Issue-Registry-Stubs behalten Übersetzungsdomänen, Breaks-in-Version- und
  Learn-More-Metadaten bei Update-Aufrufen bei, damit Re-Registrierungen keine
  vorhandenen Felder verlieren; Regressionstests prüfen die Fallbacks auf
  bestehende Metadaten.
- Die Issue-Registry-Stubs nehmen jetzt `dismissed_version` entgegen, behalten
  bestehende Werte bei Re-Registrierungen bei und lassen sich gezielt
  überschreiben; Regressionstests prüfen Defaults, Overrides und den Erhalt
  bestehender Metadaten.
- Die Issue-Registry-Stubs exportieren jetzt eine HA-ähnliche `IssueSeverity`
  (Enum) und normalisieren Severity-Werte bei Create-/Update-Aufrufen; die
  Regressionstests prüfen Enum-Defaults und String-Fallbacks, damit neue HA-
  Severity-Felder oder -Standards sofort sichtbar werden.
- Die Issue-Registry-Stubs halten jetzt den Ignored-Status und setzen `active`
  entsprechend bei Ignore/Unignore-Aufrufen; Regressionstests prüfen das
  Verhalten gemeinsam mit den bestehenden Timestamp- und Metadata-Checks, um
  HA-API-Drift bei Ignore-Mechanismen früh zu erkennen.
- Ignore-Helper setzen `dismissed_version` jetzt auf die Home-Assistant-
  Versionskonstante, bevor sie die Ignore-Flags toggeln; Regressionstests
  vergleichen die Version gegen `homeassistant.const.__version__`, damit
  Upstream-Anpassungen am Ignore-Pfad sofort sichtbar werden.
- Die Issue-Registry-Stubs lassen optionale Felder wie `data` und
  `translation_placeholders` jetzt auf `None`, wenn sie nicht gesetzt wurden,
  und Regressionstests prüfen, dass spätere Updates bestehende Metadaten nicht
  überschreiben.
- Die Issue-Registry-Stubs setzen `translation_key` jetzt standardmäßig auf die
  Issue-ID und `issue_domain` auf die Domain des Issues, damit die Pflichtfelder
  aus dem Upstream-Pfad auch ohne explizite Parameter gefüllt werden; die
  Regressionstests prüfen die neuen Default-Fallbacks.
- Die Issue-Registry-Stubs setzen `is_fixable` jetzt standardmäßig auf `False`
  nach HA-Vorbild und behalten vorhandene Werte bei Re-Registrierungen bei;
  Regressionstests prüfen den Default sowie die Fortschreibung.
- Die Device-Registry-Stubs mergen jetzt nachgelieferte Identifiers und
  Connections in bestehende Einträge, sodass Merge-Aufrufe keine Metadaten mehr
  verlieren, wenn sie nur neue Hints liefern.
- Die Device-Registry-Stubs vergeben jetzt eindeutige IDs, wenn weder
  Identifiers/Connections noch eine explizite ID übergeben werden, damit
  Registry-Tests keine Gerätekollisionen verdecken und HA-ähnliche IDs prüfen
  können.
- Die Device-Registry-Stubs berücksichtigen jetzt manuell gesetzte
  `device-*`-IDs für ihre Zähler, damit automatisch erzeugte IDs nicht mit
  benutzerdefinierten Präfix-IDs kollidieren; Regressionstests prüfen die
  fortlaufende Sequenzierung.
- Die Device-Registry-Stubs lösen Geräte jetzt direkt über Device-IDs auf und
  Regressionstests prüfen die ID-basierten Lookups über Registry- und Modul-
  Helper, damit HA-Änderungen an den Lookup-Pfaden frühzeitig auffallen.
- Die ConfigEntryState-Stubs spiegeln jetzt alle HA-Zustände inklusive
  Recoverability-Flags wider (z. B. Setup/Unload-In-Progress) und werden durch
  Regressionstests für die Home-Assistant- und Kompatibilitäts-Stubs geprüft,
  damit API-Erweiterungen frühzeitig auffallen.
- Die ConfigEntry-Stubs spiegeln jetzt zusätzliche HA-Metadaten wie
  Supports-Unload/Remove-Device/Options/Reconfigure, Subentry-Typen,
  Discovery-Keys und Übersetzungsgründe wider; Regressionstests prüfen die
  Default- und Override-Werte sowie die Zeitstempel.
- Die ConfigEntry-Stubs liefern jetzt die HA-Defaultlogik für
  Options-/Reconfigure-Unterstützung und Subentry-Typen; Regressionstests
  prüfen die Fallbacks (Options-abhängig) und Overrides explizit.
- Die Kompatibilitäts-ConfigEntry-Stubs spiegeln dieselben HA-Metadaten
  (Discovery-Keys, Support-Flags, Subentry-Typen, Übersetzungsgründe,
  Zeitstempel) wider; Regressionstests prüfen Default- und Override-Werte,
  damit Drift zwischen HA- und Compat-Stubs früh auffällt.
- Die ConfigEntry-Stubs ziehen die Options-/Reconfigure-Unterstützung jetzt
  über die Handler-Hooks (`HANDLERS`) nach HA-Vorbild heran statt über Options-
  Payloads; Regressionstests decken die Handler-Fallbacks für HA- und Compat-
  Stubs ab.
- Die ConfigEntry-Stubs spiegeln jetzt Subentries wider und leiten
  `supported_subentry_types` über Handler-Hooks ab; Regressionstests prüfen die
  Subentry-Payloads und Handler-Fallbacks auf Drift.
- Die ConfigEntry-Stubs leiten Supports-Unload/Remove-Device jetzt über die
  Handler-Hooks ab; Regressionstests prüfen die Fallbacks, damit HA-
  Änderungen an den Support-Flags frühzeitig erkannt werden.
- Die ConfigEntry-Stubs stellen jetzt handler-basierte Helper
  (`support_entry_unload`, `support_remove_from_device`) bereit; Regressionstests
  prüfen die Rückgabewerte, damit fehlende Loader-Hooks sofort auffallen.
- Die ConfigEntry-Stubs setzen `unique_id` jetzt standardmäßig auf `None` nach
  HA-Vorbild, damit Tests keine stillschweigende ID-Annahme treffen; die
  Regressionstests prüfen die Default-Unique-ID für HA- und Compat-Stubs.
- Die ConfigEntry-Stubs spiegeln jetzt auch das HA-Feld
  `pref_disable_discovery` wider und testen Default-/Override-Werte, damit neue
  Präferenzfelder aus den Release-Notes frühzeitig sichtbar werden.
- Die ConfigEntry-Stubs prüfen jetzt zusätzlich die Preferences
  `pref_disable_new_entities` und `pref_disable_polling` für HA- und Compat-
  Stubs, damit beide Varianten die HA-Präferenzfelder und Overrides
  widerspruchsfrei abdecken.
- Die Benachrichtigungs-Quiet-Hours validieren Options-Payloads jetzt defensiv
  (Mapping-Guards, Timestamp-Normalisierung via `_deserialize_datetime` und
  String-Fallbacks), damit ungültige Optionen keine Laufzeitfehler mehr
  auslösen.
- Zuletzt ausgeführte Checks (nach dem hassfest-Shim-Update): `ruff check`,
  `PYTHONPATH=$(pwd) pytest -q`, `python -m script.enforce_test_requirements`,
  `python -m scripts.enforce_shared_session_guard`,
  `python -m script.hassfest --integration-path custom_components/pawcontrol`
  (alle grün). `mypy custom_components/pawcontrol` schlägt weiterhin mit
  zahlreichen Typfehlern fehl und muss bereinigt werden, bevor eine Platinum-
  Freigabe möglich ist.

## Offene Fehler und Verbesserungen

- Die Reparatur- und Flow-Stubs sollten mit jedem HA-Release auf neue
  Signaturen geprüft werden (z. B. zusätzliche Attribute in RepairsFlow-
  Ergebnissen), damit Konfigurations- und Reparaturtests nicht erneut brechen;
  die neuen Regressionstests für die RepairsFlow-Ergebnisse, die FlowResult-
  Aliase in `config_entries`/`data_entry_flow` und die OptionsFlow-Helfer
  dienen als Frühwarnung und müssen bei API-Änderungen mitgezogen werden.
- Das lokale `hassfest`-Shim muss mit neuen Upstream-Regeln (z. B. zusätzliche
  Manifest- oder Übersetzungsfelder) abgeglichen und die Regressionstests
  entsprechend erweitert werden, damit der Guard-Lauf valide bleibt.
- Tests für die Quiet-Hours-Parser sollten fehlerhafte Optionen (Nicht-
  Mappings, Datetime-/String-Mischformen) abdecken, damit Regressionen in der
  Benachrichtigungslogik frühzeitig auffallen.
- `mypy custom_components/pawcontrol` meldet weiterhin zahlreiche Typfehler
  (u. a. in `notifications.py`, `data_manager.py`, `options_flow.py`,
  `sensor.py`, `text.py`, `config_flow_external.py` und
  `config_flow_profile.py`). Die JSONValue-Coercions, TypedDict-Literale und
  Collection-Guards müssen vereinheitlicht werden, damit der MyPy-Guard wieder
  grün wird und die Home-Assistant-Platinum-Anforderungen erfüllt.
- Menü-, Progress- und External-Done-Ergebnisse der Flow-Stubs müssen bei
  Änderungen in den HA-Release-Notes (z. B. neue Felder in `FlowResult`)
  abgeglichen und in den Regressionstests ergänzt werden.
- ConfigEntryState-Erweiterungen (z. B. neue Recoverability-Flags oder weitere
  Zustände) mit den HA-Release-Notes abgleichen und bei Bedarf in den Stubs und
  Regressionstests nachziehen.
- Neue ConfigEntry-Support-Flags (z. B. Supports-Unload/Remove-Device,
  Options/Reconfigure oder Subentry-Typen) und Übersetzungsfelder aus den HA-
  Release-Notes ableiten, in den Stubs ergänzen und die Regressionstests
  entsprechend erweitern; Compat-Stubs parallel pflegen, damit Offline-Tests
  keinen Drift zu den HA-Stubs aufbauen.
- Die Defaultlogik für Options-/Reconfigure-Unterstützung und Subentry-Typen
  aus den HA-Release-Notes ableiten, damit die Stubs Fallbacks (z. B.
  Options-abhängige Aktivierung) korrekt nachbilden.
- Registry-Helfer müssen die Config-Entry-Filter und Metadaten-Updates aus HA
  spiegeln, damit die Factory-Tests echte API-Änderungen anzeigen und nicht
  durch zu großzügige Filterung verdeckt werden.
- Merge-Heuristiken der Registry-Stubs (Identifiers/Connections bzw. Unique-ID
  + Plattform) regelmäßig gegen HA-Release-Notes prüfen und Regressionstests
  erweitern, falls Upstream neue Abgleichsregeln einführt.
- Service-Guard-Metriken normalisieren jetzt Zähler und Historie über einen
  gemeinsamen Integer-Coercer, sodass Guard-Zusammenfassungen keine
  Nicht-Zahlen mehr akkumulieren.
- Runtime-Store-Dauer-Percentiles werden jetzt explizit pro Schlüssel
  (`p75`/`p90`/`p95`) berechnet, damit die TypedDict-Anforderungen von
  Home Assistant eingehalten und strengere MyPy-Checks bestanden werden.
- Registry-Stubs sollen mehrere Config-Entries und zusätzliche Metadaten pro
  Entity/Device speichern (z. B. Identifiers, Connections, Translation Keys,
  Aliases) und erweitern dies um Area/Disabled/Primary/Icons/Units, damit
  Filter und Factory-Tests HA-Änderungen erkennen.
- Preferred-Area-IDs und Hidden-Flags der Registry-Stubs an die HA-Release-
  Notes koppeln und bei neuen Feldern sofort in Regressionstests ergänzen.
- `original_unit_of_measurement` im Entity-Registry-Stub gegen HA-Release-Notes
  abgleichen und Regressionstests bei neuen Einheitspfaden erweitern, damit
  Unit-bezogene API-Änderungen frühzeitig auffallen.
- Die neuen HA-Zeitstempel-Felder `created_at`/`modified_at` im Device- und
  Entity-Registry-Stub müssen weiter mit Release-Notes abgeglichen werden, um
  zusätzliche Zeitstempel-Attribute oder Zeitzonenanpassungen früh zu erkennen.
- Handler-basierte Options-/Reconfigure-Erkennung in den ConfigEntry-Stubs
  regelmäßig gegen HA-Release-Notes prüfen; Handler-APIs in den Regressionstests
  nachziehen, wenn sich die Unterstützungslogik ändert.
- Subentry-APIs aus den HA-Release-Notes (z. B. neue Felder oder
  `supported_subentry_types`-Erweiterungen) prüfen und in den Stubs sowie den
  Regressionstests ergänzen, damit neue Subentry-Typen früh auffallen.
- `dismissed_version`-Updates in der Issue-Registry gegen HA-Release-Notes
  spiegeln und Regressionstests erweitern, falls HA neue Felder oder
  Standardwerte ergänzt.
- Ignore-/Unignore-Mechanismen der Issue-Registry bei HA-Release-Notes
  gegenprüfen und Regressionstests erweitern, wenn weitere Felder (z. B.
  zusätzliche Flags zu Active/Ignore) ergänzt werden.
- Nach jedem Stub-Update müssen `ruff check`, `pytest -q` und die Guard-
  Skripte (`script.enforce_test_requirements`,
  `scripts.enforce_shared_session_guard.py`) konsequent ausgeführt und die
  Ergebnisse dokumentiert werden. Zusätzlich sind `mypy
  custom_components/pawcontrol` (derzeit mit zahlreichen Typfehlern) und
  `python -m script.hassfest --integration-path custom_components/pawcontrol`
  (derzeit ohne Modulauflösung) offen und müssen bereinigt werden, bevor eine
  Platinum-konforme Freigabe erfolgt.
- Für Python 3.13+ sollte weiterhin geprüft werden, ob neue
  Event-Loop-Anpassungen im Upstream-Home-Assistant zusätzliche
  Kompatibilitätsschichten erfordern.

### Priorisierte Maßnahmen

1. Die neuen Regressionstests für die Pytest-Shims fortlaufend pflegen und bei
   Änderungen an den Upstream-Plugins sofort anpassen, damit Import-Pfade
   langfristig stabil bleiben.
2. Reparatur-, Optionsflow- und Entity-Factory-Stubs eng mit HA-Release-Notes
   abgleichen und bei Bedarf erweitern; die Regressionstests für RepairsFlow,
   OptionsFlow und die Registry-Factories sind die Frühwarnsysteme für API-
   Drift. Die Registry-Stubs müssen Config-Entry-Zuordnungen und Metadaten
   speichern, damit `async_entries_for_config_entry` wie in HA filtert und
   Factory-Tests echten API-Änderungen folgen.
3. Nach jedem Stub-Update `ruff check`, `pytest -q` sowie die Guard-Skripte
   laufen lassen und im Plan dokumentieren, um die Platinum-Kriterien
   nachweisbar einzuhalten. Optionen- und Repairs-Flow-Menüs/Progress-
   Ergebnisse in Regressionstests abdecken, damit neue Attribute aus den HA-
   Release-Notes sofort auffallen.

#### Funktionale Abdeckung

- Reparatur-, Optionsflow- und Entity-Factory-Tests priorisieren, weil sie
  frühzeitig melden, wenn sich Home-Assistant-APIs ändern und die Stubs nicht
  mehr passen.
