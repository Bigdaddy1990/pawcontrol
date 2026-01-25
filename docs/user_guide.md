# PawControl User Guide (EN)

PawControl is a **custom Home Assistant integration**. It targets the Platinum
quality scale but does **not** receive an official Platinum badge from Home
Assistant because custom integrations are not graded.

## Feature overview

PawControl bundles focused modules that can be enabled per dog profile:

- **GPS**: live location, geofencing, GPS health checks, low-battery alerts.
- **Walks**: start/stop walks, distance/time tracking, walk reminders.
- **Garden**: backyard sessions, activities (play/pee/poop), quick buttons.
- **Feeding**: schedules, portions, reminders, compliance stats.
- **Health**: weight tracking, vet reminders, medication/grooming tasks.
- **Dashboards**: auto-generated UI cards and summaries.
- **Notifications**: mobile, persistent, and optional external channels.

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
   - Enable Feeding, Walk, Garden, Health, GPS, Notifications, and Dashboard as
     needed.
6. **Finish setup**
   - Review the created entities and optional dashboards.

## After setup

- **Entities**: available under *Settings → Devices & Services → Paw Control*.
- **Services**: `pawcontrol.*` services appear in the Services UI.
- **Dashboards**: use the generated cards in Lovelace or customize further.

## Discovery & config flow overview

When Home Assistant detects a PawControl device (DHCP, USB, Zeroconf, HomeKit,
or Bluetooth), it automatically starts the **config flow** and adds a suggested
integration card under *Settings → Devices & Services*. Open the suggestion to
review the detected device and confirm the setup. If multiple devices are
found, select the correct profile and proceed with the guided steps before the
entry is created.

## Module setup details

### GPS

1. Open **Settings → Devices & Services → Paw Control → Configure**.
2. In *GPS & Geofence*, pick a location source (device tracker, person, or GPS
   integration) and set update intervals.
3. Configure **geofences** with radius + coordinates, then test entry/exit
   events.

**Validated fields:**
- Update interval: 5-600 seconds.
- Accuracy filter: 5-500 meters.
- Distance filter: 1-2000 meters.
- Route history retention: 1-365 days.
- Geofence radius: 5-5000 meters.
- Latitude/longitude: -90 to 90 / -180 to 180.

**Tip:** If the dog does not move often, increase the update interval to reduce
noise, but keep a shorter interval for walk detection.

### Walks

1. Enable Walk tracking in the dog profile.
2. Use the **Walk controls** buttons or `pawcontrol.start_walk` /
   `pawcontrol.end_walk`.
3. Add reminders by enabling walk notifications in the options flow.

**Best practice:** Pair a door sensor to auto-start walks and let GPS confirm
distance/time.

### Garden

1. Enable Garden tracking in the dog profile.
2. Use **Garden session** buttons or `pawcontrol.start_garden_session` /
   `pawcontrol.end_garden_session`.
3. Log activities with `pawcontrol.add_garden_activity` or the provided button
   entities (play, pee, poop).

**Tip:** Add a binary sensor for the garden door and connect it to an automation
to auto-start/stop sessions.

### Feeding

1. Enable Feeding tracking in the dog profile.
2. Define schedules and portion sizes in **Options → Feeding**.
3. Use `pawcontrol.log_feeding` or the feeding buttons to log meals.

**Tip:** Combine feeding reminders with a mobile notification action to quickly
log a meal from your phone.

### Health

1. Enable Health tracking in the dog profile.
2. Add weight and vet reminder sensors to your dashboard.
3. Use `pawcontrol.log_weight`, `pawcontrol.log_medication`, and
   `pawcontrol.log_grooming` services for manual logging.

**Tip:** Create a weekly automation that reminds you to weigh your dog on the
same day and time.

## Creating automations

Use Home Assistant’s automation editor or YAML. Recommended workflow:

1. Identify the relevant **sensor or event** (e.g., `pawcontrol_walk_started`).
2. Decide whether you need a **condition** (e.g., only during daytime).
3. Pick an **action** (`notify`, `pawcontrol.*`, or a script).
4. Test by manually triggering the service to verify entity IDs and data.

### Example: blueprint-style automation

The snippet below shows a lightweight blueprint you can save under
`blueprints/automation/pawcontrol/walk-alert.yaml` and reuse across dogs.

```yaml
blueprint:
  name: PawControl - Walk reminder
  description: Notify when a walk is overdue.
  domain: automation
  input:
    overdue_sensor:
      name: Walk overdue sensor
      selector:
        entity:
          domain: binary_sensor
    notify_target:
      name: Notification service
      selector:
        text: {}
trigger:
  - platform: state
    entity_id: !input overdue_sensor
    to: "on"
action:
  - service: !input notify_target
    data:
      title: "Walk reminder"
      message: >
        Walk overdue for
        {{ state_attr(trigger.entity_id, 'dog_name') }}.
```

### YAML example: garden auto-session

```yaml
alias: PawControl - auto garden session
trigger:
  - platform: state
    entity_id: binary_sensor.garden_door
    to: "on"
action:
  - service: pawcontrol.start_garden_session
    data:
      dog_id: "buddy"
```

## Recommended screenshots

Screenshots make setup easier to follow. Helpful captures include:

- **Integration setup wizard** (module selection screen).
- **Options flow** for GPS/geofences and feeding schedules.
- **Dashboard cards** for Walks, Garden, and Health.
- **Automation editor** showing a PawControl service action.

## Related guides

- Automation examples: [`docs/automation_examples.md`](automation_examples.md)
- Troubleshooting: [`docs/troubleshooting.md`](troubleshooting.md)
