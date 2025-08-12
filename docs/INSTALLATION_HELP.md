
# Installations-Hilfe (Paw Control)

Diese Anleitung führt dich Schritt-für-Schritt durch die Installation – auch wenn du Home Assistant noch nicht lange nutzt.

## A) Installation über HACS (empfohlen)
1. **HACS öffnen** → *Integrations* → unten rechts **+**.
2. **Custom repositories** öffnen (drei Punkte oben rechts) → **Add**:
   - **URL**: (füge hier die URL deines Repositories ein)
   - **Kategorie**: *Integration*
3. Nach **Paw Control** suchen → **Installieren**.
4. Home Assistant **neu starten**.
5. **Einstellungen → Geräte & Dienste → Integration hinzufügen → Paw Control** auswählen.
6. **Optionen** öffnen und zuerst **Hunde verwalten** ausfüllen (eine Zeile je Hund `id:name`).

## B) Manuelle Installation (ZIP)
1. Die Datei `pawcontrol_final_full_hacs_vXX.zip` entpacken.
2. Den Ordner `custom_components/pawcontrol/` in deinen Home Assistant `config/`-Ordner kopieren → Ergebnis:
   - `/config/custom_components/pawcontrol/` (dieser Ordner muss die Dateien enthalten).
3. Home Assistant **neu starten**.
4. Integration hinzufügen wie in A) beschrieben.

## Ersteinrichtung (Optionen)
- **Hunde verwalten** – `id:name` je Zeile, z. B. `rex:Rex`.
- **Module aktivieren** – GPS/Feeding/Health/Walk … nach Bedarf.
- **Medikations-Zuordnung** – pro Hund und **Slot 1–3** die **Mahlzeiten** (Mehrfachauswahl) wählen.
- **Sicherheitszonen** – für jeden Hund **Lat/Lon/Radius** eintragen und ggf. **Alerts aktivieren**.
- **Zeitplan & Ruhezeiten** – tägliche **Reset-Zeit**, **Reminder-Intervalle** und **Snooze**.
- **Erweitert** – Limits (Routen-Historie), Diagnosen usw.

## Prüfen, ob alles läuft
- In den **Entwicklerwerkzeugen → Zustände** nach `sensor.pawcontrol_<hund>_walk_*` suchen.
- **Geräte** → `Hund <Name>` sollte Entities für GPS/Walk etc. enthalten.
- **Benachrichtigungen** → Bei Safe-Zone-Ereignissen erscheinen Einträge im Logbuch und (optional) Notifications.

## Fehlerbehebung
- **Keine Entities sichtbar?** → In den Optionen mindestens **einen Hund** eintragen.
- **HACS findet das Repo nicht?** → Prüfe `hacs.json` im Repo-Root.
- **Fehler im Log** → `pawcontrol.gps_generate_diagnostics` ausführen und die erzeugten Dateien dem Issue anhängen.
