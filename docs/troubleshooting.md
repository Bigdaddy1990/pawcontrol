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

## Geofence errors or missing updates

**Symptoms**
- No geofence events
- Errors mentioning invalid coordinates or radius

**Fix**
1. Check latitude/longitude ranges and radius limits in the options flow.
2. Ensure GPS module is enabled and providing recent coordinates.
3. Verify the dog has a GPS source assigned.

## Missing entities or translations

**Symptoms**
- Entity names show raw keys
- Some entities are missing after setup

**Fix**
1. Confirm `strings.json` and `translations/*.json` contain the new keys.
2. Re-run Home Assistant or reload the integration entry.

## Diagnostics collection fails

**Symptoms**
- Diagnostics file is empty or errors appear

**Fix**
1. Ensure the integration is loaded and has runtime data.
2. Retry after at least one successful coordinator update.

## Collecting logs

1. Enable debug logging for `custom_components.pawcontrol`.
2. Reproduce the issue.
3. Provide logs along with diagnostics when filing issues.
