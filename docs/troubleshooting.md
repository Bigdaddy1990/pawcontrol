# PawControl Troubleshooting (EN)

This guide lists common issues, symptoms, and fixes.

## Integration setup fails

**Symptoms**
- Setup aborts or shows “Setup failed”
- Logs mention authentication or invalid configuration

**Fix**
1. Verify the API endpoint/token in the integration options.
2. Remove and re-add the integration if the config entry is corrupted.
3. Restart Home Assistant after changes.

## Reauth/Reconfigure (Zugriff erneuern & Profil anpassen)

**Wann Home Assistant eine Reauth auslöst**
- Wenn die Integration eine fehlgeschlagene Authentifizierung meldet (z. B.
  HTTP 401 vom PawControl API‑Endpunkt), löst Home Assistant eine Reauth aus.
  In PawControl geschieht das über `ConfigEntryAuthFailed` bei geschützten
  API‑Requests.【F:custom_components/pawcontrol/device_api.py†L120-L191】

**Welche Schritte im UI folgen (Flow‑Namen)**
1. Home Assistant startet den Reauth‑Flow **`reauth`**.
2. Du siehst eine Bestätigungsmaske aus **`reauth_confirm`**; dort bestätigst
   du die erneute Anmeldung und die Konfiguration wird aktualisiert.【F:custom_components/pawcontrol/config_flow_reauth.py†L152-L394】

**Reconfigure manuell auslösen (Flow‑Name `reconfigure`)**
1. Öffne *Einstellungen → Geräte & Dienste → Paw Control*.
2. Wähle den Eintrag und öffne das Drei‑Punkte‑Menü (**⋮**), dann **Reconfigure**.
3. Wähle das gewünschte Entity‑Profil und bestätige den Dialog; der
   **`reconfigure`**‑Schritt aktualisiert die Optionen und lädt die
   Integration neu.【F:custom_components/pawcontrol/config_flow_main.py†L1522-L1700】

## Walk or garden automations do not trigger

**Symptoms**
- Walk/garden automations never fire
- Door sensor changes but no PawControl events appear

**Fix**
1. Confirm the correct `dog_id` is set in the service call.
2. Ensure the door sensor entity is included in your automation trigger.
3. Verify that the Walk/Garden modules are enabled in the profile options.

## Geofence errors or missing updates

**Symptoms**
- No geofence events
- Errors mentioning invalid coordinates or radius

**Fix**
1. Check latitude/longitude ranges and radius limits in the options flow.
2. Ensure GPS module is enabled and providing recent coordinates.
3. Verify the dog has a GPS source assigned.

## GPS updates look stale

**Symptoms**
- Device tracker updates but PawControl location is unchanged
- GPS sensors show `unknown` for extended periods

**Fix**
1. Confirm the GPS source entity is correct in the options flow.
2. Reduce the GPS update interval temporarily to validate the pipeline.
3. Reload the integration entry after changing the GPS source.

## Discovery does not find devices

**Symptoms**
- Device never appears under **Settings → Devices & Services**
- Discovery card disappears before setup completes
- Wrong device is suggested

**Fix**
1. Verify Home Assistant and the device are in the same network segment/VLAN.
2. Check that DHCP or Zeroconf/mDNS traffic is not blocked by the router.
3. For USB devices, confirm USB passthrough and `/dev` access in Docker/VMs.
4. Ensure HomeKit devices use a unique, matching name to avoid wrong suggestions.
5. If the integration expects a hostname pattern, confirm the device advertises
   the expected hostname (rename the device if needed).

## Missing entities or translations

**Symptoms**
- Entity names show raw keys
- Some entities are missing after setup

**Fix**
1. Confirm `strings.json` and `translations/*.json` contain the new keys.
2. Re-run Home Assistant or reload the integration entry.

## Services return validation errors

**Symptoms**
- Service call returns a message about invalid input
- Logs show schema validation warnings

**Fix**
1. Review service data in **Developer Tools → Services**.
2. Check required fields such as `dog_id`, `session_id`, and durations.
3. Use existing entities/buttons to populate data before custom automations.

## Diagnostics collection fails

**Symptoms**
- Diagnostics file is empty or errors appear

**Fix**
1. Ensure the integration is loaded and has runtime data.
2. Retry after at least one successful coordinator update.

## Feeding reminders not firing

**Symptoms**
- Feeding reminders never arrive
- Overdue sensor stays off even when meals are late

**Fix**
1. Ensure Feeding is enabled and a schedule is configured.
2. Confirm notification services are configured and available.
3. Check that the feeding sensors are not disabled in the entity registry.

## Collecting logs

1. Enable debug logging for `custom_components.pawcontrol`.
2. Reproduce the issue.
3. Provide logs along with diagnostics when filing issues.
