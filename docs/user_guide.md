# PawControl User Guide (EN)

PawControl is a **custom Home Assistant integration**. It targets the Platinum
quality scale but does **not** receive an official Platinum badge from Home
Assistant because custom integrations are not graded.

## Feature overview

- **Feeding management**: schedules, portions, reminders, compliance stats
- **Walk tracking**: durations, distances, reminders, GPS tracking
- **Health monitoring**: weight, medical history, vet reminders
- **Geofencing & GPS**: safety zones, location-based alerts
- **Dashboards**: auto-generated UI cards and summaries
- **Notifications**: mobile, persistent, and optional external channels

## Step-by-step setup (UI)

1. **Install the integration**
   - HACS: *HACS → Integrations → Explore & Download Repositories → Paw Control*
   - Manual: copy `custom_components/pawcontrol` into your HA config.
2. **Restart Home Assistant** to load the integration.
3. **Add the integration**
   - *Settings → Devices & Services → Add Integration → Paw Control*
4. **Add your first dog**
   - Provide dog ID, name, breed, age, size, and weight.
5. **Select modules**
   - Enable Feeding, Walk, Health, GPS, Notifications, and Dashboard as needed.
6. **Finish setup**
   - Review the created entities and optional dashboards.

## After setup

- **Entities**: available under *Settings → Devices & Services → Paw Control*.
- **Services**: `pawcontrol.*` services appear in the Services UI.
- **Dashboards**: use the generated cards in Lovelace or customize further.

## Related guides

- Automation examples: [`docs/automation_examples.md`](automation_examples.md)
- Troubleshooting: [`docs/troubleshooting.md`](troubleshooting.md)
