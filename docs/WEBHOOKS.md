
# GPS Webhooks

Die Integration erzeugt pro Hund eine **Webhook-ID** für `/api/webhook/<ID>`. 
Nutzdaten (JSON) für Aufrufe:

```json
{ "lat": 52.52, "lon": 13.405, "accuracy": 8.5 }
```

Alternativ funktionieren die Schlüssel `latitude`, `longitude`, `acc`.

## URLs abrufen
- Service `pawcontrol.gps_list_webhooks` ausführen → Datei `config/pawcontrol_diagnostics/webhooks.json` enthält pro Hund die vollständigen URLs.

## IDs neu erzeugen
- Service `pawcontrol.gps_regenerate_webhooks` ausführen.
