# PawControl Automation Examples (EN)

This page provides **step-by-step automation examples** for common workflows.
All examples assume your entities are named in the standard Home Assistant
format (adjust names to match your instance). PawControl itself is configured
via the UI (config entries); these YAML snippets are for automations/scripts,
not `configuration.yaml` setup. Prefer the **Automation Editor** UI and
device-based triggers/actions when available, then switch to YAML mode for
fine-tuning. Home Assistant’s YAML style guide and device automation docs
describe the recommended patterns for triggers, conditions, and actions.

## 1) Feeding reminder when overdue (state trigger + notify)

**Goal:** notify you when a dog is overdue for a meal.

```yaml
alias: PawControl - feeding reminder when overdue
trigger:
  - platform: state
    entity_id: binary_sensor.pawcontrol_feeding_overdue
    to: "on"
action:
  - service: notify.mobile_app
    data:
      title: "Feeding reminder"
      message: >
        Meal overdue for
        {{ state_attr('binary_sensor.pawcontrol_feeding_overdue', 'dog_name') }}.
```

## 2) Start walk when leaving the home zone (zone trigger)

**Goal:** automatically start a walk when the dog leaves the home zone.

```yaml
alias: PawControl - auto start walk on zone exit
trigger:
  - platform: zone
    entity_id: device_tracker.pawcontrol_gps
    zone: zone.home
    event: leave
action:
  - service: pawcontrol.start_walk
    data:
      dog_id: "buddy"
```

## 3) Alert when geofence is breached (event trigger)

**Goal:** send a high-priority alert when the dog leaves a safe zone.

```yaml
alias: PawControl - geofence breach alert
trigger:
  - platform: event
    event_type: pawcontrol_geofence_left
action:
  - service: notify.mobile_app
    data:
      title: "Geofence alert"
      message: >
        {{ trigger.event.data.dog_name }} left
        {{ trigger.event.data.zone_name }}.
```

## 4) Weekly summary notification (time + template message)

**Goal:** send a weekly summary using the available sensors.

```yaml
alias: PawControl - weekly summary
trigger:
  - platform: time
    at: "08:00:00"
condition:
  - condition: time
    weekday:
      - sun
action:
  - service: notify.mobile_app
    data:
      title: "PawControl weekly summary"
      message: >
        Walks this week:
        {{ states('sensor.pawcontrol_walks_this_week') }}
        — Calories:
        {{ states('sensor.pawcontrol_calories_consumed_today') }}.
```

## 5) Garden session auto-start on door sensor (state + for)

**Goal:** automatically start a garden session when the garden door opens.

```yaml
alias: PawControl - auto garden session
trigger:
  - platform: state
    entity_id: binary_sensor.garden_door
    to: "on"
    for: "00:00:15"
action:
  - service: pawcontrol.start_garden_session
    data:
      dog_id: "buddy"
```

## 6) Health reminder on weigh-in day (scheduled)

**Goal:** remind yourself to log weight every week.

```yaml
alias: PawControl - weekly weigh-in reminder
trigger:
  - platform: time
    at: "19:00:00"
condition:
  - condition: time
    weekday:
      - sat
action:
  - service: notify.mobile_app
    data:
      title: "Weekly weigh-in"
      message: "Log Buddy's weight in PawControl."
```

## 7) Device automations (trigger, condition, action)

**Goal:** use the built-in PawControl device automations for hungry alerts and walk handling.

```yaml
alias: PawControl - device automation demo
trigger:
  - platform: device
    domain: pawcontrol
    device_id: YOUR_PAWCONTROL_DOG_DEVICE_ID
    type: hungry
condition:
  - condition: device
    domain: pawcontrol
    device_id: YOUR_PAWCONTROL_DOG_DEVICE_ID
    type: in_safe_zone
action:
  - domain: pawcontrol
    device_id: YOUR_PAWCONTROL_DOG_DEVICE_ID
    type: log_feeding
    amount: 120
    meal_type: dinner
```

## 8) Blueprint: reusable walk reminder (UI inputs)

**Goal:** create a reusable automation with inputs for different dogs.

Save this blueprint to `blueprints/automation/pawcontrol/walk-reminder.yaml`:

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

After saving, create automations in **Settings → Automations & Scenes → Create
Automation → From Blueprint** and select this blueprint.

## 9) Blueprint: walk detection alerts (included)

**Goal:** react to walk start/end based on the built-in walk sensor.

Use the included blueprint at
`blueprints/automation/pawcontrol/walk_detection.yaml`:

```yaml
alias: PawControl - walk detection alerts
use_blueprint:
  path: pawcontrol/walk_detection.yaml
  input:
    walk_sensor: binary_sensor.buddy_walk_in_progress
    walk_start_actions:
      - service: notify.mobile_app
        data:
          title: "Walk started"
          message: "Buddy just started a walk."
    walk_end_actions:
      - service: notify.mobile_app
        data:
          title: "Walk ended"
          message: "Buddy finished the walk."
```

## 10) Blueprint: safe zone alerts (included)

**Goal:** alert when a dog leaves or returns to a safe zone.

Use the included blueprint at
`blueprints/automation/pawcontrol/safe_zone_alert.yaml`:

```yaml
alias: PawControl - safe zone alerts
use_blueprint:
  path: pawcontrol/safe_zone_alert.yaml
  input:
    safe_zone_sensor: binary_sensor.buddy_in_safe_zone
    leave_delay: "00:02:00"
    left_actions:
      - service: notify.mobile_app
        data:
          title: "Safe zone alert"
          message: "Buddy left the safe zone."
    return_actions:
      - service: notify.mobile_app
        data:
          title: "Safe zone return"
          message: "Buddy is back in the safe zone."

## 11) Notification action handler (choose + trigger IDs)

**Goal:** respond to actionable notification buttons using a single automation.

```yaml
alias: PawControl - handle notification actions
mode: single
trigger:
  - platform: event
    event_type: mobile_app_notification_action
    event_data:
      action: "PAWCONTROL_FEED_NOW"
    id: feed_now
  - platform: event
    event_type: mobile_app_notification_action
    event_data:
      action: "PAWCONTROL_START_WALK"
    id: start_walk
action:
  - choose:
      - conditions:
          - condition: trigger
            id: feed_now
        sequence:
          - service: pawcontrol.add_feeding
            data:
              dog_id: "buddy"
              amount: 120
              meal_type: dinner
      - conditions:
          - condition: trigger
            id: start_walk
        sequence:
          - service: pawcontrol.start_walk
            data:
              dog_id: "buddy"
```

## References (Home Assistant Developer Docs)

- https://developers.home-assistant.io/docs/automations
- https://developers.home-assistant.io/docs/device_automation_index
- https://developers.home-assistant.io/docs/documenting/yaml-style-guide
