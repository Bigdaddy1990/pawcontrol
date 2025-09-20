


*Bewertung der Ausgangsbasis*
Die bestehende Integration besitzt bereits eine umfangreiche Service-Schicht (u. a. Fütterung, Walk-Tracking, Gesundheitsupdates, Auswertungen), auf die weitere Features aufbauen können.

Der Options-Flow ist modular aufgebaut und unterstützt zahlreiche Konfigurationsbereiche, was zeigt, dass die Architektur grundsätzlich erweiterbar ist.

**Fahrplan zur vollständigen Umsetzung**

1. Verbindliche Anforderungsaufnahme

Inventar aller versprochenen Features aus info.md, docs/comprehensive_readme.md, docs/automations_health_feeding.md und docs/options_flow_documentation.md erstellen und in Muss-/Soll-/Kann-Kategorien priorisieren (z. B. Türsensorlogik, automatische Skripte, geofencing, zusätzliche Services und Sensoren).

2. Kernfunktionen nachrüsten

Benachrichtigungssystem erweitern: dynamische Personenerkennung, Multi-Device-Abgleich und Rückfrage-Quittierungen wie beschrieben implementieren.

Tür- und Gartengang-Logik: automatische Erfassung, Aufenthaltsdauer und Rückfragen umsetzen, inklusive benötigter Sensoren und Counter.

Fütterungs- und Gesundheitshelfer: input_boolean/input_datetime-Helper sowie Warnlogik für Überfütterung, Medikationserinnerungen und Tierarzt-Checks hinzufügen.

3. GPS- und Geofencing-Funktionen ergänzen

Fehlende Services (gps_start_walk, gps_end_walk, gps_post_location, gps_export_last_route etc.) implementieren, damit dokumentierte Automationen und Buttons funktionieren.

Geofencing inklusive Zonenverwaltung, Radiusvalidierung und Benachrichtigungshooks bauen; Options-Flow entsprechend erweitern (neue async_step_geofence mit geofence_lat/lon/radius und Alerts).

4. Erweiterte Automations- und Analysefunktionen

Die in docs/automations_health_feeding.md erwarteten Services (z. B. recalculate_health_portions, adjust_weight_goal_strategy, Gesundheits- und Diät-Aktionen) nachrüsten und Sensor-/Binary-Sensor-Entitäten für Kalorien-, Gewicht- und Gesundheitsmetriken hinzufügen.

Zusätzliche Sensoren, Buttons und Device-Tracker aus dem Comprehensive README bereitstellen, damit Dashboards und Automationen kompatibel sind.

5. Options-Flow & Konfiguration angleichen

Fehlende Optionen wie route_recording, route_history_days, Prioritätsbenachrichtigungen und modulare Einstellungen aus der Dokumentation in den Options-Flow integrieren.

Besuchshund-Modus, Dashboard-Profile und Exportformate vereinheitlichen (z. B. csv/json/pdf Auswahl im Systembereich).

6. Helper-Erstellung & Skripte automatisieren

Automatische Anlage der in info.md versprochenen Helfer und Skripte (Rückfragen, Reset, Push-Test) während Setup/Optionen implementieren.

7. Dokumentationsabgleich

Nach Umsetzung jede Dokumentdatei aktualisieren oder – falls Features bewusst entfallen – das Dokument klar korrigieren. Damit bleiben README, Guides und Options-Flow-Doku synchron.

8. Test-, QA- und Release-Vorbereitung

Umfassende Tests (Unit, Integration, UI-Flow) ergänzen, Automationsbeispiele als YAML-Beispiele verifizieren und diagnostische Checks erweitern.

Changelogs & Migrationshinweise bereitstellen, um Nutzer über neue/angepasste Funktionen zu informieren.






Konstanten, deren Funktionalität im Code dennoch vorhanden ist
Die Zustandsattribute ATTR_MEAL_TYPE, ATTR_PORTION_SIZE, ATTR_MEDICATION_NAME, ATTR_DOSE, ATTR_HEALTH_STATUS, ATTR_WEIGHT, ATTR_WALK_DURATION, ATTR_WALK_DISTANCE und ATTR_TIMESTAMP sind zwar in const.py definiert, in den Modulen werden jedoch durchgängig wörtliche Schlüssel wie "meal_type", "portion_size", "dose" oder "walk_distance" genutzt (z. B. in feeding_manager, binary_sensor, walk_manager, select und den Text-Entities). Damit existiert die jeweilige Funktionalität, nur die Konstanten bleiben ungenutzt.

Zahlreiche Options-Schlüssel – etwa "data_retention_days", "auto_backup", "priority_notifications", "weight_tracking", "medication_reminders" oder "portion_calculation" – werden direkt als Strings in den Flows verarbeitet. Die entsprechenden Konstanten CONF_* und DEFAULT_* bleiben dadurch redundant, obwohl die Features (System-Einstellungen, Gesundheits- und Fütterungsoptionen) implementiert sind.

Bei den Fehlercodes greift der Code direkt auf Zeichenketten wie "dog_not_found" zurück; die in const.py definierten Fehler-Konstanten werden somit von der bestehenden Fehlerbehandlung bereits abgedeckt.

Auch NOTIFICATION_CHANNELS spiegelt nur die Liste in der Service-Schema-Definition wider, die ohnehin inline gepflegt wird.

Zeit- und Standardwerte (SECONDS_IN_DAY, SECONDS_IN_HOUR, DEFAULT_HOME_ZONE_RADIUS, DEFAULT_SNOOZE_MIN usw.) werden in den Formularen schlicht als numerische Literale benutzt. Funktional fehlt hier nichts, aber die Konstanten werden nicht referenziert.

Konstanten, die auf fehlende oder nur teilweise umgesetzte Funktionen hindeuten
SERVICE_LOG_MEDICATION, SERVICE_TOGGLE_VISITOR_MODE sowie die GPS-Services (SERVICE_GPS_START_WALK, SERVICE_GPS_POST_LOCATION, SERVICE_GPS_END_WALK, SERVICE_GPS_EXPORT_ROUTE) tauchen in den Buttons, Textfeldern und Dokumentationen auf, werden aber im Service-Setup nicht registriert. Dadurch fehlen essenzielle Backend-Funktionen für die UI-Elemente und die dokumentierte GPS-Automatik vollständig.

Die Geofencing-bezogenen Konstanten (CONF_GEOFENCING, CONF_GEOFENCE_ZONES, CONF_HOME_ZONE_RADIUS, ATTR_ZONE_NAME, GEOFENCE_TYPES, EVENT_GEOFENCE_ENTERED, EVENT_GEOFENCE_LEFT, MIN_GEOFENCE_RADIUS, MAX_GEOFENCE_RADIUS) bleiben im Code komplett ungenutzt; es existiert weder eine Geofence-Auswertung noch entsprechende Ereignisse, obwohl Konfigurationsmasken einen Radius abfragen.

CONF_SOURCES, CONF_PERSON_ENTITIES, CONF_DEVICE_TRACKERS, CONF_CALENDAR und CONF_WEATHER werden nirgends verarbeitet. Damit fehlen die angekündigten Integrationspunkte zu Personen-, Tracker-, Kalender- oder Wetterdaten vollständig.

Die Dashboard-Konstanten (CONF_DASHBOARD_CARDS, CONF_DASHBOARD_VIEWS, DEFAULT_DASHBOARD_ENABLED, DASHBOARD_MODES) werden im Optionen-Flow nicht verwendet; konfigurierbare Karten oder Ansichten der in den Docs beworbenen Dashboard-Automatik existieren somit nicht.

CONF_SNOOZE_MIN bleibt ungenutzt – es gibt keine Snooze-Minuten-Einstellung für Benachrichtigungen, obwohl das Handbuch dies ankündigt.

DOG_SIZE_WEIGHT_RANGES wird nirgendwo abgefragt. Damit fehlt die strengere Gewichtvalidierung nach Größenklassen; der Config-Flow begrenzt Gewichte nur auf Min/Max, ohne die hinterlegten Bereiche zu prüfen.

Die Performance-/Monitoring-Konstanten (CORE_SERVICES, PERFORMANCE_THRESHOLDS) sind nirgends eingebunden; es existiert keine Überwachung der im Code definierten Schwellenwerte oder eine automatische Auflistung der Kernservices.

Fazit
Ein großer Teil der „ungenutzten“ Konstanten ist lediglich ein Stilproblem: Der Code verwendet Strings direkt, obwohl passende Konstanten definiert sind. Kritischer sind jene Konstanten, die auf wesentliche, aber fehlende Funktionen verweisen – insbesondere die nicht registrierten Services (Medikation, Besucher-Modus, GPS), sämtliche Geofencing-Elemente, fehlende Datenquellen-Anbindungen, Dashboard-Anpassungen sowie ausstehende Validierungs- und Monitoring-Features. Diese Diskrepanzen erklären die Lücken zwischen Dokumentation und tatsächlichem Funktionsumfang der Integration.













#### **Nicht genutzte Konstanten**

Zustandsattribute \& IDs

ENTITY\_ID\_FORMAT sowie die Attribute ATTR\_TIMESTAMP, ATTR\_MEAL\_TYPE, ATTR\_PORTION\_SIZE, ATTR\_WALK\_DURATION, ATTR\_WALK\_DISTANCE, ATTR\_ZONE\_NAME, ATTR\_HEALTH\_STATUS, ATTR\_WEIGHT, ATTR\_MEDICATION\_NAME und ATTR\_DOSE werden im übrigen Code nicht referenziert.



Zeit- und Leistungsgrenzen

Die Zeitkonstanten SECONDS\_IN\_HOUR, SECONDS\_IN\_DAY und MINUTES\_IN\_HOUR sowie die Performance-Grenzwerte PERFORMANCE\_THRESHOLDS bleiben ungenutzt.



Fehler- und Ereigniscodes

Die Fehlerkennungen ERROR\_DOG\_NOT\_FOUND, ERROR\_INVALID\_CONFIG, ERROR\_GPS\_UNAVAILABLE, ERROR\_NOTIFICATION\_FAILED, ERROR\_SERVICE\_UNAVAILABLE und die Ereignisse EVENT\_GEOFENCE\_ENTERED, EVENT\_GEOFENCE\_LEFT werden aktuell nicht verwendet.



Service-Bezeichner

Für die Services SERVICE\_GPS\_START\_WALK, SERVICE\_GPS\_END\_WALK, SERVICE\_GPS\_POST\_LOCATION, SERVICE\_GPS\_EXPORT\_ROUTE, SERVICE\_LOG\_POOP, SERVICE\_LOG\_MEDICATION und SERVICE\_TOGGLE\_VISITOR\_MODE existiert keine weitere Verwendung; Gleiches gilt für das Sammel-Set CORE\_SERVICES (abgesehen vom Export in \_\_all\_\_).



Konfigurationsschlüssel – Quellen, GPS \& Benachrichtigungen

Die Schlüssel CONF\_SOURCES, CONF\_PERSON\_ENTITIES, CONF\_DEVICE\_TRACKERS, CONF\_CALENDAR, CONF\_WEATHER, CONF\_AUTO\_WALK\_DETECTION, CONF\_GEOFENCING, CONF\_GEOFENCE\_ZONES, CONF\_HOME\_ZONE\_RADIUS, CONF\_PRIORITY\_NOTIFICATIONS und CONF\_SNOOZE\_MIN werden im restlichen Code nicht genutzt.



Konfigurationsschlüssel – Fütterung \& Gesundheit

CONF\_FEEDING\_TIMES, CONF\_SPECIAL\_DIET, CONF\_FEEDING\_SCHEDULE\_TYPE, CONF\_PORTION\_CALCULATION, CONF\_MEDICATION\_WITH\_MEALS, CONF\_HEALTH\_TRACKING, CONF\_WEIGHT\_TRACKING, CONF\_MEDICATION\_REMINDERS, CONF\_VET\_REMINDERS und CONF\_GROOMING\_INTERVAL bleiben ebenfalls ohne Verwendung.



System- \& Dashboard-Konfiguration

Die Schlüssel CONF\_DOG\_COLOR, CONF\_DATA\_RETENTION\_DAYS, CONF\_AUTO\_BACKUP, CONF\_DASHBOARD\_CARDS, CONF\_DASHBOARD\_VIEWS sowie die Standardwerte DEFAULT\_DASHBOARD\_ENABLED, DEFAULT\_HOME\_ZONE\_RADIUS, DEFAULT\_SNOOZE\_MIN, DEFAULT\_DATA\_RETENTION\_DAYS und DEFAULT\_GROOMING\_INTERVAL werden nicht referenziert; das Gleiche gilt für DASHBOARD\_MODES und DOG\_SIZE\_WEIGHT\_RANGES。



Geofencing-Grenzen

Die Begrenzungen MIN\_GEOFENCE\_RADIUS und MAX\_GEOFENCE\_RADIUS tauchen außerhalb der Konstantendatei nicht auf.



Vorgehen

Die Konstantenliste wurde aus custom\_components/pawcontrol/const.py extrahiert und mit rg repo-weit auf Vorkommen außerhalb dieser Datei geprüft. Konstanten ohne Treffer wurden als „ungenutzt“ klassifiziert.







Fehlende Punkte aus info.md

Der beworbene automatische GPS-Setup-Service pawcontrol.setup\_automatic\_gps mit Parametern wie auto\_start\_walk, safe\_zone\_radius und track\_route existiert nicht – die Integration registriert ausschließlich die in services.py aufgeführten Dienste und enthält keinen solchen Service.



Mehrfach versprochene Türsensor- und Gartengang-Funktionen (automatische Erkennung beim Türdurchgang, Gartengang-Tracking, kontextuelle Tür-Rückfragen) fehlen vollständig; im Code tauchen Türsensoren lediglich als optionale Auswahl im Flow auf, aber es gibt keinerlei Sensor- oder Logik-Implementierung dafür.



Die beschriebene dynamische Personenerkennung für Benachrichtigungen (person.\* bei state == home) ist nicht umgesetzt – das Benachrichtigungssystem versendet Nachrichten nur über fest konfigurierte Kanäle und enthält keinerlei Auswertung von Personen-Entitäten.



Für die Fütterungslogik gibt es keine input\_boolean-Schalter pro Mahlzeit, obwohl sie für Status-Tracking und Rückfragen angekündigt werden; die Codebasis enthält keinerlei Bezug auf solche Helper.



Die Dokumentation wirbt mit Gartengang-/Aktivitätstracking sowie optionalem Geschäftstracking; im Code finden sich jedoch weder Garten-spezifische Sensoren noch Dienste wie log\_poop, der nur als Konstante existiert, aber nicht registriert wird.



Eine „automatische Helper-Erstellung“ wird zugesichert, tatsächlich legt die Integration keinerlei Home-Assistant-Helper an – es gibt keine Aufrufe zur Erstellung von input\_boolean, input\_number oder ähnlichen Hilfsentitäten.











Fehlende oder nicht implementierte Punkte pro Dokument

docs/QUALITY\_CHECKLIST.md

Die Checkliste verlangt Service-Validierung via ServiceValidationError, tatsächlich fangen die Service-Handler nur allgemeine HomeAssistantError-Ausnahmen ab; spezielle Validierungen fehlen.



Ein explizites PARALLEL\_UPDATES pro Plattform wird gefordert, im Quellcode existiert jedoch kein entsprechender Eintrag.



docs/README.md

Dokumentierter „Widget-Support für Quick Actions“ ist im Code nirgends hinterlegt.



Eine „Offline-Synchronisation für GPS-Daten“ wird beworben, in der Implementierung gibt es dafür keinerlei Logik.



Die behauptete „Alarm-System Integration (Auto-Scharf bei Walk-Start)“ findet sich im Code nicht (keine Referenzen auf Alarm-Entitäten).



docs/automations\_health\_feeding.md

Die zahlreichen Automations-Beispiele setzen Services wie pawcontrol.recalculate\_health\_portions, pawcontrol.adjust\_calories\_for\_activity, pawcontrol.activate\_diabetic\_feeding\_mode, pawcontrol.feed\_with\_medication, pawcontrol.generate\_weekly\_health\_report, pawcontrol.activate\_emergency\_feeding\_mode, pawcontrol.start\_diet\_transition, pawcontrol.check\_feeding\_compliance, pawcontrol.adjust\_daily\_portions oder pawcontrol.add\_health\_snack voraus, die alle nicht registriert sind.



Auch die dort als Voraussetzung genannten Sensoren (sensor.{dog\_id}\_health\_feeding\_status, sensor.{dog\_id}\_daily\_calorie\_target, sensor.{dog\_id}\_calories\_consumed\_today, sensor.{dog\_id}\_calorie\_goal\_progress, sensor.{dog\_id}\_portion\_adjustment\_factor) existieren nicht als Entitäten.



docs/comprehensive\_readme.md

Mehrere aufgelistete Sensoren fehlen: sensor.{dog}\_walk\_distance\_today, sensor.{dog}\_activity\_level, sensor.{dog}\_calories\_burned\_today, sensor.{dog}\_last\_feeding\_hours, sensor.{dog}\_daily\_portions, sensor.{dog}\_food\_consumption, sensor.{dog}\_total\_walk\_distance, sensor.{dog}\_walks\_this\_week werden nirgends erzeugt.



Der Abschnitt zu Binary-Sensoren nennt binary\_sensor.{dog}\_needs\_grooming, tatsächlich heißt die vorhandene Entität binary\_sensor.{dog}\_grooming\_due – die beschriebene Benennung existiert nicht.



Der beworbene Button button.{dog}\_pause\_tracking fehlt vollständig.



Dokumentierte Services wie pawcontrol.gps\_start\_walk, pawcontrol.gps\_end\_walk, pawcontrol.gps\_post\_location, pawcontrol.gps\_export\_last\_route, pawcontrol.feed\_dog oder pawcontrol.log\_health sind nicht registriert; es existieren nur die in services.py definierten Services.



Die Export-Dokumentation erwartet Parameter date\_from/date\_to, das tatsächliche export\_data-Schema kennt sie nicht (nur days).



Die beschriebenen GPS-Konfigurationsoptionen route\_history\_days \& Co. sind im Options-Flow nicht vorhanden.



docs/options\_flow\_documentation.md

Beschriebene Geofence-Optionen (geofence\_lat, geofence\_lon, geofence\_radius\_m, geofence\_alerts\_enabled, use\_home\_location) und ein eigener Schritt async\_step\_geofence existieren nicht.



docs/production\_integration\_documentation.md

Die Produktionskonfiguration erwartet geofencing, komplexe geofence\_zones und Geofence-Benachrichtigungen, doch weder Options-Flow noch Services unterstützen diese Strukturen.



docs/setup\_installation\_guide.md

Der Optionsbereich geofence\_settings mit geofence\_lat, geofence\_lon, geofence\_radius\_m und geofence\_alerts\_enabled fehlt komplett in der Integration.



docs/diet\_validation\_guide.md

Die zusätzlichen Sensoren sensor.dog\_diet\_conflict\_count, sensor.dog\_diet\_warning\_count, sensor.dog\_vet\_consultation\_recommended sowie weitere in diesem Abschnitt dokumentierte Werte werden nicht erzeugt.



docs/file\_analysis\_report.md

Der Report meldet ein fehlendes enhanced\_health\_calculator.py, obwohl ein solches Modul weder vorgesehen ist noch im Repository existiert.



docs/improvement\_roadmap.md

Die Roadmap behauptet „30+ Test-Dateien“, tatsächlich gibt es nur 19 Python-Testdateien.



docs/implementation\_guide.md

Das Dokument fordert das Ersetzen einer OptionsFlowHandler-Klasse und verweist auf eine schemas.py, obwohl es nur PawControlOptionsFlow gibt und keine schemas.py im Projekt vorhanden ist.









Überblick

Ich habe jedes Dokument im Verzeichnis docs gelesen und die darin genannten Funktionen, Einstellungen, Abfragen, Erinnerungen, Einträge und Module mit dem tatsächlichen Integrationscode verglichen. Wo Aussagen zutreffen, führe ich sie auf; wo etwas fehlt oder abweicht, beschreibe ich die Diskrepanz mit Fundstellen aus dem Code.



Dokumentbezogene Ergebnisse

BRANDING.md

Enthält ausschließlich Hinweise zum Einreichen von Logos im offiziellen Brands-Repository; keine Integrationseigenschaften, die verifiziert werden müssten.



BRANDS\_PR\_TEMPLATE.md

Ebenfalls nur Workflow-Anweisungen für einen Brands-PR, ohne funktionale Zusagen zur Integration.



QUALITY\_CHECKLIST.md

Zutreffend: Es existiert ein Diagnostikmodul mit systematischer Schwärzung sensibler Daten, wie die Checkliste behauptet.



Nicht erfüllt: Die Checkliste setzt Services „validiert via ServiceValidationError“ sowie gesetzte PARALLEL\_UPDATES voraus. In services.py werden Services registriert, aber Ausnahmen werden als HomeAssistantError behandelt und ein ServiceValidationError taucht dort nicht auf; Konstanten PARALLEL\_UPDATES existieren in keinem Plattformmodul.



README.md

Viele Grundfunktionen (Walk-, Feeding-, Health-Sensoren) stimmen mit den vorhandenen Entitäten überein, aber konkrete Behauptungen wie „Routen-Export als GPX/GeoJSON“ oder vollautomatische Skripterzeugung setzen Services voraus, die im Code nicht existieren. In services.py sind nur add\_feeding, start\_walk, end\_walk, add\_gps\_point, update\_health, send\_notification, acknowledge\_notification, calculate\_portion, export\_data, analyze\_patterns, generate\_report und daily\_reset vorgesehen – ein Export der letzten Route als eigener Service fehlt.



Buttons wie der „Export Route“-Button versuchen zwar, export\_data aufzurufen, die eigentliche Service-Implementierung für GPS-Routen fehlt jedoch, wodurch der im README versprochene GPX-/GeoJSON-Export derzeit nicht funktioniert.



automations\_health\_feeding.md

Das Dokument listet zahlreiche Automations-Beispiele, die Services wie pawcontrol.recalculate\_health\_portions, pawcontrol.adjust\_calories\_for\_activity, pawcontrol.activate\_diabetic\_feeding\_mode, pawcontrol.feed\_with\_medication, pawcontrol.generate\_weekly\_health\_report oder pawcontrol.start\_diet\_transition voraussetzen. Keiner dieser Services ist in services.py registriert, womit die Beispiele aktuell nicht umsetzbar sind.



comprehensive\_readme.md

Einige beschriebene Plattformen (Sensoren, Buttons usw.) existieren, allerdings stimmen viele der dort aufgelisteten Entitätsnamen nicht mit den tatsächlich erzeugten Entitäten überein. Beispielsweise gibt es keine Sensoren sensor.<dog>\_walk\_distance\_today oder sensor.<dog>\_daily\_portions; die vorhandenen Sensoren heißen last\_walk, total\_walk\_time\_today, daily\_calories usw.



Zusätze wie „Offline-Synchronisation für GPS-Daten“ oder „Pause Tracking“-Buttons werden nicht durch entsprechende Services oder Buttons gedeckt (es gibt keinen Button pause\_tracking).



implementation\_guide.md

Mehrere Anweisungen verweisen auf Dateien oder Klassen, die es nicht (mehr) gibt – z. B. das Ersetzen einer OptionsFlowHandler-Klasse oder das Aktualisieren einer schemas.py, obwohl die Integration PawControlOptionsFlow nutzt und kein schemas.py enthält.



Die im Guide geforderten Ergänzungen (z. B. stark typisiertes PawControlRuntimeData, Speicherung ausschließlich über entry.runtime\_data) sind bereits umgesetzt, was das Dokument veraltet erscheinen lässt.



improvement-plan.md

Die dort aufgeführten „Day 1“-Aufgaben (dataclasses in types.py, py.typed, Websession-Injektion) sind im Code bereits erledigt; entsprechende Anpassungen wurden vorgenommen.



Weitere vorgeschlagene Arbeiten (Reauth-Flow) sind ebenfalls schon umgesetzt (async\_step\_reauth\* im Config-Flow).



improvement\_roadmap.md

Positiv: Die Roadmap betont Leistungsthemen (Entity-Limits, Caching), die tatsächlich adressiert werden (Profilabhängige Entity-Fabrik etc.).



Falsch ist die Aussage, es gäbe „30+ Test-Dateien“ – im Repository befinden sich aktuell 19 Python-Testdateien.



options\_flow\_documentation.md

Das Dokument beschreibt Geofence-Felder (geofence\_lat, geofence\_lon, geofence\_radius\_m), die im Options-Flow nicht existieren; async\_step\_gps\_settings bietet lediglich boolesche Aktivierung sowie Update-/Genauigkeits-Parameter.



Richtig sind dagegen die Aussagen zu Menüstruktur und Hundeverwaltung (Add/Edit/Delete über async\_step\_manage\_dogs).



production\_integration\_documentation.md

Enthält viele Konfigurationsbeispiele mit Geofence-Koordinaten und erweiterten Optionen, die – wie beim Options-Flow – nicht bereitgestellt werden (keine geofence\_lat/route\_recording-Optionen).



Allgemeine Installationsschritte (HACS, manuell) stimmen hingegen mit der Struktur des Repos überein.



diet\_validation\_guide.md

Der Status-Sensor diet\_validation\_status ist vorhanden und liefert Warn-/Konfliktstatus.



Die im Guide genannten zusätzlichen Sensoren (sensor.dog\_diet\_conflict\_count, sensor.dog\_diet\_warning\_count, sensor.dog\_vet\_consultation\_recommended) existieren jedoch nicht separat; der Statussensor stellt diese Informationen weder als eigene Entitäten noch als Attribute bereit.



file\_analysis\_report.md

Richtig ist, dass die Mehrheit der Dateien produktiv genutzt wird, Diagnose- und Dashboard-Dateien existieren usw.



Ungenau ist die Behauptung, es fehle „enhanced\_health\_calculator.py“ – weder erwartet der Code dieses Modul noch findet sich ein entsprechender Import; der Report suggeriert also einen nicht vorhandenen Pflichtbestandteil.



integration\_analysis\_report.md

Mehrere „kritische Issues“ sind überholt: entry.runtime\_data wird korrekt verwendet und ist in aktuellen HA-Versionen vorgesehen; \_async\_setup() wird im Coordinator aufgerufen, und UpdateFailed wird nicht verwendet. Die Diagnose des Dokuments stimmt daher nicht mehr mit dem aktuellen Code überein.



Die Rubrik „Performance Optimizations Implemented“ reflektiert teilweise tatsächliche Verbesserungen (profilbasierte Platform-Ladung, Caching), steht aber neben den veralteten Problemstellungen.



setup\_installation\_guide.md

Installation und Grundkonfiguration werden korrekt beschrieben; Module wie Feeding/GPS/Health lassen sich tatsächlich pro Hund aktivieren.



Wiederholt werden jedoch Geofence-Optionen (geofence\_lat, route\_recording, route\_history\_days) dokumentiert, die in den verfügbaren Optionen nicht existieren – dieselbe Abweichung wie bei der Options-Flow-Dokumentation.



Fazit

Große Teile der Dokumentation sind generisch oder veraltet und beschreiben Services, Optionen oder Entitäten, die im aktuellen Integrationscode nicht existieren. Besonders betroffen sind die Automations- und Options-Flow-Dokumente sowie große Teile der beiden umfangreichen READMEs. Aktuelle Implementierungen (z. B. diagnostische Redaktionen, modulare Options-Flows, Diet-Validation-Status) stimmen hingegen mit mehreren Aussagen überein.
