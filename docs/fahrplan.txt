Aktueller Verbesserungsfahrplan für Paw Control

1. Basis-Setup & GPS-Kernfunktionen
   - Config-Flow überprüfen und vereinfachen, sodass die im Info-Dokument genannten Parameter (Hundename, GPS-Quelle, Auto-Tracking, Sicherheitsradius) vollständig unterstützt und validiert werden.
   - Den automatischen Service `pawcontrol.setup_automatic_gps` absichern: Pflichtfelder prüfen, Fehlerfeedback verbessern und eine Erfolgsmeldung für das UI ergänzen.
   - Sicherstellen, dass das GPS-Tracking nahtlos für Tractive, Companion-App-Tracker und DIY-Integrationen funktioniert; ggf. Beispiel-Blueprints ergänzen.

2. Spaziergangs- & Gartenlogik
   - Binary-Sensoren für `*_on_walk`, `*_in_safe_zone` und Gartenaufenthalte konsistent aktualisieren und mit Dauer-/Historienwerten verknüpfen.
   - Automatische Spaziergang-Erkennung gegenüber den dokumentierten Benachrichtigungen testen und Optimierungen (z. B. Verzögerungen, Mindestdauer) dokumentieren.
   - Sicherheitszonenlogik mit Warn-Timeout (2 Minuten) als Standardautomation anbieten und auf Mehr-Hund-Szenarien prüfen.

3. Push-Benachrichtigungen & Rückfragen
   - Dynamische Personenerkennung für `person.*`-Entitäten gegen reale Home-Assistant-States testen und Fallback-Kette (mobile_app) robust implementieren.
   - Interaktive Rückfragen vereinheitlichen: gleiche Texte, Emojis und Quittierungs-Logik gemäß Info-Dokument.
   - Push-Test-Service verbessern, damit Benutzer:innen Feedback zur Zustellung sehen (Erfolg/Fehler pro Gerät).

4. Fütterung & Gesundheitsüberwachung
   - Vier Mahlzeiten als optionale Module mit eigenen Countern, Rückfragen und Überfütterungswarnungen implementieren.
   - Gesundheits-/Kot-Tracking erweitern: Notfallstatus, Tierarzt-Erinnerungen und optionale Wetterabhängigkeiten vorbereiten.
   - Tagesübersichten validieren (Reset um 23:59 Uhr), inklusive konfigurierbarer Uhrzeit pro Hund.

5. Dashboard & UI-Erlebnis
   - Lovelace-Layout ausliefern, das Mushroom-Karten, Statusindikatoren und Schnellaktionen gemäß Info-Versprechen nutzt.
   - Responsive Varianten für Desktop/Mobile testen; bei Bedarf CSS/Template-Anpassungen dokumentieren.
   - Besucherhund-Modus visuell klar abgrenzen (Farbcode, Icon, eigener Abschnitt) und Aktivierungs-Workflow beschreiben.

6. Automationen & Skripte
   - Auto-generierte Skripte (Rückfrage, Reset, Push-Test) gegen neue Entitäten aktualisieren und YAML-Beispiele aus dem Info-Dokument bereitstellen.
   - Standard-Automationen für Spaziergang und Sicherheitszone als Blueprints/Rezepte veröffentlichen.
   - Service-Schemas validieren und alle Services mit ausführlicher Fehlerbehandlung (ServiceValidationError) versehen.

7. Erweiterbarkeit & Mehr-Hund-Unterstützung
   - Manager-Logiken für mehrere Hunde testen: getrennte Historien, Farben, Icons und individuelle Einstellungen sicherstellen.
   - Besucherhund-Modus so erweitern, dass er sämtliche Sensoren, Benachrichtigungen und Statistiken isoliert behandelt.
   - Vorbereitung für weitere Sensoren (Futterschale, Wasserspender) skizzieren und Schnittstellen definieren.
