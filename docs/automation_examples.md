# PawControl Automation Examples (EN)

This page provides **step-by-step automation examples** for common workflows.
All examples assume your entities are named in the standard Home Assistant
format (adjust names to match your instance).

## 1) Feeding reminder when overdue

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

## 2) Start walk when leaving home zone

**Goal:** automatically start a walk when the dog leaves the home zone.

```yaml
alias: PawControl - auto start walk on zone exit
trigger:
  - platform: state
    entity_id: device_tracker.pawcontrol_gps
    from: "home"
    to: "not_home"
action:
  - service: pawcontrol.start_walk
    data:
      dog_id: "buddy"
```

## 3) Alert when geofence is breached

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

## 4) Weekly summary notification

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

## 5) Garden session auto-start on door sensor

**Goal:** automatically start a garden session when the garden door opens.

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

## 6) Health reminder on weigh-in day

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

## 8) Blueprint: reusable walk reminder

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
