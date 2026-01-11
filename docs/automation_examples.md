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
