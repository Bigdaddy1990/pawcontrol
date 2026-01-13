Aktueller Verbesserungsfahrplan für Paw Control

Dieser Fahrplan ergänzt und aktualisiert den ursprünglichen Verbesserungsplan. Er bündelt kurzfristige Qualitätsarbeiten und mittelfristige Funktions‑Updates. Die Reihenfolge der Punkte gibt die empfohlene Bearbeitungsreihenfolge an.

## 0. Qualität, Typisierung & Architektur

- **JSON‑Kompatibilität & Entitätsattribute**: Alle Entitätsklassen sollen ihre `extra_state_attributes` als `JSONMutableMapping` zurückgeben. Nicht serialisierbare Typen (z. B. `datetime`, `timedelta`, Dataclasses) werden mit der in `diagnostics.py` beschriebenen Normalisierungslogik in JSON‑kompatible Werte umgewandelt【938345194430286†L964-L983】.
- **myPy‑Säuberung & Typisierung**: Bestehende mypy‑Fehler (derzeit ~280 gemeldete Fälle【793654332192246†L19-L23】) in den Config‑Flows, Options‑Flows und Platform‑Dateien beheben. Dazu gehören konsequente Verwendung von `TypedDict`, `Literal` und klaren Rückgabetypen.
- **Modularisierung der Flows**: Die voluminösen Dateien `config_flow.py` und `options_flow.py` in logisch getrennte Module (z. B. GPS‑Konfiguration, Notifications, Health‑Settings) aufteilen, um Wartbarkeit und Testbarkeit zu verbessern.
- **Zentralisierte Validierung & Fehlerbehandlung**: Validierungsfunktionen (für Eingabewerte wie Hundename, Koordinaten, Timer) in ein gemeinsames Modul auslagern. Exceptions aus `exceptions.py` konsistent einsetzen, damit Reauth‑ und Reparatur‑Flows korrekt ausgelöst werden.
- **Dokumentationspflege**: Nach jeder Code‑Änderung `README`, `docs/` und `strings.json` aktualisieren, damit Übersetzungen und Hinweise zum Qualitätslevel synchron bleiben.

## 1. Basis‑Setup & GPS‑Kernfunktionen

- Config‑Flow überprüfen und vereinfachen, sodass die im Info‑Dokument genannten Parameter (Hundename, GPS‑Quelle, Auto‑Tracking, Sicherheitsradius) vollständig unterstützt und validiert werden.
- Den automatischen Service `pawcontrol.setup_automatic_gps` absichern: Pflichtfelder prüfen, Fehlerfeedback verbessern und eine Erfolgsmeldung für das UI ergänzen.
- Sicherstellen, dass das GPS‑Tracking nahtlos für Tractive, Companion‑App‑Tracker und DIY‑Integrationen funktioniert; ggf. Beispiel‑Blueprints ergänzen.
- **Neue Aufgabe:** JSON‑Schema‑Validierung für GPS‑Parameter (Update‑Intervalle, Genauigkeit) einbauen, um Null‑ oder ungültige Werte frühzeitig abzufangen.

## 2. Spaziergangs‑ & Gartenlogik

- Binary‑Sensoren für `*_on_walk`, `*_in_safe_zone` und Gartenaufenthalte konsistent aktualisieren und mit Dauer‑/Historienwerten verknüpfen.
- Automatische Spaziergang‑Erkennung gegenüber den dokumentierten Benachrichtigungen testen und Optimierungen (z. B. Verzögerungen, Mindestdauer) dokumentieren.
- Sicherheitszonenlogik mit Warn‑Timeout (2 Minuten) als Standardautomation anbieten und auf Mehr‑Hund‑Szenarien prüfen.
- **Neue Aufgabe:** Walk‑ und Garden‑Sensoren sollen die vereinheitlichte Attributbasis aus Abschnitt 0 nutzen (JSON‑Mapping, Zeitstempel serialisieren)【947475147972407†L335-L343】【385432702482431†L799-L811】.

## 3. Push‑Benachrichtigungen & Rückfragen

- Dynamische Personenerkennung für `person.*`‑Entitäten gegen reale Home‑Assistant‑States testen und Fallback‑Kette (mobile_app) robust implementieren.
- Interaktive Rückfragen vereinheitlichen: gleiche Texte, Emojis und Quittierungs‑Logik gemäß Info‑Dokument.
- Push‑Test‑Service verbessern, damit Benutzer:innen Feedback zur Zustellung sehen (Erfolg/Fehler pro Gerät).
- **Neue Aufgabe:** Fehlerbehandlung in der Benachrichtigungs‑Pipeline zentralisieren; Service‑Guard‑Metriken in die Diagnostik integrieren, um abgelehnte/fehlgeschlagene Nachrichten sichtbar zu machen.

## 4. Fütterung & Gesundheitsüberwachung

- Vier Mahlzeiten als optionale Module mit eigenen Countern, Rückfragen und Überfütterungswarnungen implementieren.
- Gesundheits‑/Kot‑Tracking erweitern: Notfallstatus, Tierarzt‑Erinnerungen und optionale Wetterabhängigkeiten vorbereiten.
- Tagesübersichten validieren (Reset um 23:59 Uhr), inklusive konfigurierbarer Uhrzeit pro Hund.
- **Neue Aufgabe:** Vorbereitung auf KI‑gestützte Gesundheitsanalyse (geplant für v1.1): Datenströme standardisieren und API‑Hook definieren, um Trends (Gewicht, Aktivität, Futtermenge) evaluieren zu können.

## 5. Dashboard & UI‑Erlebnis

- Lovelace‑Layout ausliefern, das Mushroom‑Karten, Statusindikatoren und Schnellaktionen gemäß Info‑Versprechen nutzt.
- Responsive Varianten für Desktop/Mobile testen; bei Bedarf CSS/Template‑Anpassungen dokumentieren.
- Besucherhund‑Modus visuell klar abgrenzen (Farbcode, Icon, eigener Abschnitt) und Aktivierungs‑Workflow beschreiben.
- **Neue Aufgabe:** Dashboard‑Komponenten auf die neuen Metriken und Guard‑Telemetrie (Service‑Guard‑Ergebnisse) erweitern, sodass Qualitätsscale‑Berichte direkt im UI sichtbar sind.

## 6. Automationen & Skripte

- Auto‑generierte Skripte (Rückfrage, Reset, Push‑Test) gegen neue Entitäten aktualisieren und YAML‑Beispiele aus dem Info‑Dokument bereitstellen.
- Standard‑Automationen für Spaziergang und Sicherheitszone als Blueprints/Rezepte veröffentlichen.
- Service‑Schemas validieren und alle Services mit ausführlicher Fehlerbehandlung (`ServiceValidationError`) versehen.
- **Neue Aufgabe:** Integrations‑Blueprints bereitstellen, die die neuen Validierungsfunktionen und Fehlerabfangmechanismen nutzen; Service‑Guard‑Telemetrie als Bedingung in Automationen verwenden.

## 7. Erweiterbarkeit & Mehr‑Hund‑Unterstützung

- Manager‑Logiken für mehrere Hunde testen: getrennte Historien, Farben, Icons und individuelle Einstellungen sicherstellen.
- Besucherhund‑Modus so erweitern, dass er sämtliche Sensoren, Benachrichtigungen und Statistiken isoliert behandelt.
- Vorbereitung für weitere Sensoren (Futterschale, Wasserspender) skizzieren und Schnittstellen definieren.
- **Neue Aufgabe:** Mehr‑Tier‑Architektur (v2.0) anreißen: Datenmodelle generalisieren, Config‑Flows tierunabhängig gestalten und einen Pet‑Profile‑Manager vorsehen.

---

**Hinweis:** Dieser Fahrplan soll regelmäßig aktualisiert werden. Nach Abschluss jedes Abschnitts sind die Belege im `quality_scale.yaml` zu aktualisieren und die Dokumentation entsprechend anzupassen.
