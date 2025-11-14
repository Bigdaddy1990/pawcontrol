# Scribe-Playbook

Dieses Living-Document ergänzt den Abschnitt „Dokumentation & Scribes“ in
`dev.md` und bietet sofort nutzbare Vorlagen für Rotation, Monitoring und
Übergaben. Die Inhalte orientieren sich an den Home-Assistant-Vorgaben sowie den
Platinum-Anforderungen der PawControl-Integration.

## Rollenübersicht

| Rolle | Kernverantwortung | Zeitaufwand |
| --- | --- | --- |
| Hauptscribe | Steuerung der wöchentlichen Monitoring-Reviews, Pflege des Sprint-Boards in `dev.md`, Abstimmung mit QA/Release-Verantwortlichen | ca. 4 h pro Woche |
| Schattenscribe | Unterstützung beim Monitoring, Vorbereitung des Übergabereports, Eskalationen dokumentieren und nachverfolgen | ca. 2 h pro Woche |
| Rotation Owner | Pflegt die Einsatzhistorie, erinnert an Synchronisationsläufe (`python -m script.sync_contributor_guides`) und aktualisiert Eskalations-Tickets | ca. 30 min pro Sprint |

## Wöchentlicher Ablauf

1. **Montag – Monitoring-Lauf planen**
   - Checkliste aus „Scribe-Notizen“ in `dev.md` durchgehen.
   - Neue CI-Ergebnisse der Jobs `scheduled-pytest`, `vendor-pyyaml-monitor` und
     `typed-dict-audit` prüfen.
   - Auffälligkeiten als Issues/Pull Requests erfassen und im Sprint-Board
     verlinken.
2. **Mittwoch – Dokumentationsabgleich**
   - Änderungen an README, `info.md`, Produktions- und Compliance-Dokumentation
     sowie Lokalisierungen prüfen.
   - Abweichungen gegen `docs/markdown_compliance_review.md` spiegeln.
   - Falls Anpassungen nötig sind, Task im Verbesserungs-Backlog aktualisieren
     und verantwortliche Personen informieren.
3. **Freitag – Übergabe vorbereiten**
   - Ergebnisse der Woche in „Scribe-Notizen“ dokumentieren.
   - `python -m script.sync_contributor_guides` ausführen und den Link zum
     Lauf speichern.
   - Sprint-Board in `dev.md` aktualisieren (Monitoring-Fokus, Eskalationen,
     Sync-Nachweis).
   - Schattenrolle in offene Punkte einweisen; Nachverfolgung für die kommende
     Woche definieren.

## Monitoring-Vorlagen

### CI-Review (Markdown-Vorlage)

```markdown
#### CI-Review – Kalenderwoche ${KW}
- scheduled-pytest: ✅ / ⚠️ / ❌ – Link zum Workflow-Run
- vendor-pyyaml-monitor: ✅ / ⚠️ / ❌ – Link zum Workflow-Run
- typed-dict-audit: ✅ / ⚠️ / ❌ – Link zum Workflow-Run
- Auffälligkeiten & Eskalationen: <!-- Kurzbeschreibung -->
```

### Dokumentationsabgleich

| Datei | Status | Notizen | Ticket/PR |
| --- | --- | --- | --- |
| README.md | ✅ konsistent / ⚠️ Anpassung nötig | <!-- Details --> | <!-- Link --> |
| info.md | ✅ |  |  |
| docs/production_integration_documentation.md | ✅ |  |  |
| docs/compliance_gap_analysis.md | ✅ |  |  |
| INSTALLATION.md | ✅ |  |  |
| Lokalisierungen (`custom_components/pawcontrol/translations/`) | ✅ |  |  |

### Eskalations-Tracker

| Datum | Thema | Kontakt | Status | Link |
| --- | --- | --- | --- | --- |
| <!-- 2024-10-07 --> | <!-- Beispiel: CI-Fehler vendor-pyyaml-monitor --> | <!-- Name --> | Offen | <!-- Issue/PR --> |

### Artefakt-Log (Sprint-Archiv)

| Kalenderwoche | Workflow/Script | Link | Highlights |
| --- | --- | --- | --- |
| <!-- 2025-KW12 --> | <!-- z. B. scheduled-pytest, sync_contributor_guides --> | <!-- https://github.com/... --> | <!-- Nachträge, Beobachtungen --> |

## Übergabe-Checklist

1. Sprint-Board in `dev.md` aktualisieren (Aktueller Sprint + Einsatzhistorie).
2. Alle Monitoring-Protokolle mit Links zum Workflow-Run versehen.
3. Scribe-Notizen mit Dokumentationsstatus, Monitoring-Ergebnissen und
   Eskalationen befüllen.
4. Sync-Nachweis (`python -m script.sync_contributor_guides`) dokumentieren.
5. Offene Aufgaben in „Monitoring & nächste Schritte“ von `dev.md` ergänzen.
6. Schattenrolle schriftlich bestätigen lassen, dass die Übergabe erfolgt ist
   (z. B. Kommentar im Wochenprotokoll oder Chat-Protokoll verlinken).

## Onboarding-Leitfaden

1. **Vorwissen sammeln**
   - `dev.md` komplett lesen und aktive Backlog-Punkte markieren.
   - Letzte drei Einträge der Einsatzhistorie studieren.
2. **Zugang einrichten**
   - Zugriff auf CI-Läufe (GitHub Actions) überprüfen.
   - Schreibrechte für Dokumentation sicherstellen.
3. **Werkzeuge installieren**
   - Lokale Umgebung gemäß `.github/copilot-instructions.md` einrichten.
   - `python -m script.sync_contributor_guides` testweise ausführen.
4. **Shadow-Phase**
   - Eine Woche als Schattenscribe teilnehmen.
   - Eigenständiges Monitoring-Protokoll verfassen und vom Hauptscribe reviewen
     lassen.
5. **Aktive Rotation**
   - Woche übernehmen, Checklisten befolgen, Feedback einholen.
   - Verbesserungen oder neue Vorlagen direkt in diesem Playbook dokumentieren.

## Kommunikationspfade

- **Eskalationen:** Issues im Repository oder Slack-Kanal `#pawcontrol-sre`.
- **Release-Abstimmung:** Wöchentliches Sync-Meeting (Kalender-Eintrag im Team
  Kalender) plus Eintrag im Sprint-Board.
- **Dokumentationsupdates:** Pull Request mit Hinweis auf `python -m
  script.sync_contributor_guides` und Link zum Step-Summary.

## Pflegehinweise

- Änderungen an diesem Dokument benötigen einen gleichzeitigen Hinweis in
  `dev.md`, damit das Team auf neue Vorlagen aufmerksam wird.
- Bei größeren Überarbeitungen das Kapitel „Dokumentation & Scribes“ im
  Verbesserungs-Backlog aktualisieren und ggf. neue Aufgaben aufnehmen.
- Mindestens quartalsweise überprüfen, ob die Monitoring-Jobs oder Skripte neue
  Parameter erhalten haben.
