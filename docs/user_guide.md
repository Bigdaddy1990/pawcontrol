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

## Home Assistant UI patterns (recommended)

Follow the Home Assistant UI workflow to keep your setup aligned with current
platform guidance:

- **Automation Editor first**: build automations in the UI and switch to YAML
  only when you need advanced templates or `choose` logic.
- **Device automations**: use the PawControl device in **Settings → Devices &
  Services** to access built-in triggers, conditions, and actions.
- **Helpers**: create helpers (input helpers, schedules) via **Settings →
  Devices & Services → Helpers** instead of hard-coded YAML.
- **Dashboards**: start with Sections/Tile cards, then refine with YAML only
  when necessary.

These patterns mirror the Home Assistant developer guidance for automations,
device automation, and YAML style.

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
- **Device automations**: open the PawControl device to attach triggers,
  conditions, and actions directly in the automation editor.

## Data update cadence

- **Coordinator refresh**: core data updates follow the integration's
  coordinator interval and adapt to options changes.
- **GPS interval**: GPS updates follow the per-dog interval configured in the
  options flow; shorter intervals improve responsiveness but may increase device
  battery usage.

## Validation & attribute normalization

PawControl validates and normalizes inputs to keep config flows, options, and
service calls consistent:

- **Flow validation** trims and normalizes dog IDs, checks name uniqueness,
  and clamps age/weight/size ranges before entries are saved.
- **Service validation** rejects malformed payloads and missing required data
  (for example, feeding amounts and GPS intervals).
- **Attribute normalization** ensures entity attributes and diagnostics payloads
  stay JSON-safe and consistently shaped across platforms.

## Discovery & config flow overview

When Home Assistant detects a PawControl device (DHCP, USB, Zeroconf, or
Bluetooth), it automatically starts the **config flow** and adds a suggested
integration card under *Settings → Devices & Services*. Open the suggestion to
review the detected device and confirm the setup. If multiple devices are
found, select the correct profile and proceed with the guided steps before the
entry is created.

**Config flow steps you will see in the UI:**

1. **Dog profile & identity** – enter the dog ID, name, breed, and baseline
   details (validated and normalized before save).【F:custom_components/pawcontrol/config_flow_dogs.py†L1-L335】【F:custom_components/pawcontrol/flow_validation.py†L1-L260】
2. **Module selection** – enable Feeding, Walk, Garden, Health, GPS, and other
   modules for that profile.【F:custom_components/pawcontrol/config_flow_modules.py†L1-L326】
3. **External entity bindings** – map device trackers, door sensors, weather
   entities, and external endpoints to the dog profile when required.【F:custom_components/pawcontrol/config_flow_external.py†L1-L286】
4. **Dashboard & summary** – optional dashboard generation plus a summary
   step before the entry is created.【F:custom_components/pawcontrol/config_flow_dashboard_extension.py†L1-L230】【F:custom_components/pawcontrol/config_flow_main.py†L760-L1000】

**Reauth + reconfigure** flows re-use the same validation and module summaries
so updating credentials or profile settings mirrors the initial setup
experience.【F:custom_components/pawcontrol/config_flow_reauth.py†L1-L394】【F:custom_components/pawcontrol/config_flow_main.py†L1460-L1700】

## Options flow overview

The options flow uses a menu-based UX to group settings:

- **Dog management**: edit profile details and module toggles.
- **GPS & geofencing**: update intervals, accuracy filters, and zones.
- **Door sensors**: auto-start/auto-end walk settings and safety thresholds.
- **Feeding & health**: schedules, portion defaults, and reminders.
- **System settings**: diagnostics, analytics, and resilience flags.

These sections are implemented as dedicated handlers, so validation and defaults
stay consistent across entry reloads and tests.【F:custom_components/pawcontrol/options_flow_menu.py†L1-L284】【F:custom_components/pawcontrol/options_flow_dogs_management.py†L1-L457】【F:custom_components/pawcontrol/options_flow_feeding.py†L1-L310】【F:custom_components/pawcontrol/options_flow_door_sensor.py†L1-L260】【F:custom_components/pawcontrol/options_flow_system_settings.py†L1-L240】【F:tests/unit/test_options_flow.py†L1-L870】

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
3. Use `pawcontrol.add_feeding` to log meals (the legacy `pawcontrol.feed_dog`
   alias remains available but is deprecated).

**Tip:** Combine feeding reminders with a mobile notification action to quickly
log a meal from your phone.

### Health

1. Enable Health tracking in the dog profile.
2. Add weight and vet reminder sensors to your dashboard.
3. Use `pawcontrol.log_health_data`, `pawcontrol.log_medication`, and
   `pawcontrol.start_grooming` / `pawcontrol.end_grooming` services for manual
   logging.

**Tip:** Create a weekly automation that reminds you to weigh your dog on the
same day and time.

## Creating automations

Use Home Assistant’s automation editor or YAML. Recommended workflow:

1. Identify the relevant **sensor or event** (e.g., `pawcontrol_walk_started`).
2. Decide whether you need a **condition** (e.g., only during daytime).
3. Pick an **action** (`notify`, `pawcontrol.*`, or a script).
4. Test by manually triggering the service to verify entity IDs and data.
5. Prefer **device automations** when available for PawControl devices; they
   remain stable as entity IDs change.

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
mode: single
trigger:
  - platform: state
    entity_id: binary_sensor.garden_door
    to: "on"
action:
  - service: pawcontrol.start_garden_session
    data:
      dog_id: "buddy"
```

## Service catalog (quick reference)

PawControl exposes a full service catalog in Home Assistant’s Services UI. Key
service groups:

- **Feeding**: `pawcontrol.add_feeding` (deprecated alias: `pawcontrol.feed_dog`),
  `pawcontrol.calculate_portion`.
- **Walks & garden**: `pawcontrol.start_walk`, `pawcontrol.end_walk`,
  `pawcontrol.start_garden_session`, `pawcontrol.end_garden_session`,
  `pawcontrol.add_garden_activity`.
- **Health & grooming**: `pawcontrol.log_health_data`,
  `pawcontrol.log_medication`, `pawcontrol.start_grooming`,
  `pawcontrol.end_grooming`.
- **Notifications & diagnostics helpers**: test notification and validation
  services surfaced by the integration.

Service schemas live in `services.yaml`, and the handlers are implemented in
`services.py` with service telemetry coverage in the unit tests.【F:custom_components/pawcontrol/services.yaml†L1-L200】【F:custom_components/pawcontrol/services.py†L1-L420】【F:tests/unit/test_services.py†L1-L610】

## Recommended screenshots

Screenshots make setup easier to follow. Helpful captures include:

- **Integration setup wizard** (module selection screen).
- **Options flow** for GPS/geofences and feeding schedules.
- **Dashboard cards** for Walks, Garden, and Health.
- **Automation editor** showing a PawControl service action.

## Related guides

- Automation examples: [`docs/automation_examples.md`](automation_examples.md)
- Troubleshooting: [`docs/troubleshooting.md`](troubleshooting.md)

## References (Home Assistant Developer Docs)

- https://developers.home-assistant.io/docs/automations
- https://developers.home-assistant.io/docs/device_automation_index
- https://developers.home-assistant.io/docs/documenting/yaml-style-guide
