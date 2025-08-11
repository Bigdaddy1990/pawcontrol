# Example Automations for Paw Control

## 1. Automatic Walk Detection via Door Sensor

```yaml
alias: "Paw Control - Auto Walk Detection"
description: "Automatically start walk when door opens and dog leaves"
trigger:
  - platform: state
    entity_id: binary_sensor.front_door
    from: "off"
    to: "on"
condition:
  - condition: state
    entity_id: binary_sensor.pawcontrol_rex_walk_in_progress
    state: "off"
action:
  - delay:
      seconds: 30
  - condition: state
    entity_id: person.owner
    state: "not_home"
  - service: pawcontrol.start_walk
    data:
      dog_id: "rex"
      source: "door"
```

## 2. Feeding Reminder

```yaml
alias: "Paw Control - Dinner Reminder"
description: "Remind to feed dog at dinner time"
trigger:
  - platform: time
    at: "18:00:00"
condition:
  - condition: numeric_state
    entity_id: sensor.pawcontrol_rex_feeding_dinner
    below: 1
action:
  - service: notify.mobile_app_phone
    data:
      title: "🍽️ Dinner Time"
      message: "Time to feed Rex!"
      data:
        actions:
          - action: "FEED_CONFIRM"
            title: "Fed ✅"
          - action: "SNOOZE_15"
            title: "Later ⏰"
```

## 3. Walk Needed Alert

```yaml
alias: "Paw Control - Walk Needed"
description: "Alert when dog needs a walk"
trigger:
  - platform: state
    entity_id: binary_sensor.pawcontrol_rex_needs_walk
    to: "on"
    for:
      minutes: 30
condition:
  - condition: state
    entity_id: person.owner
    state: "home"
  - condition: time
    after: "07:00:00"
    before: "22:00:00"
action:
  - service: notify.mobile_app_phone
    data:
      title: "🚶 Walk Time"
      message: "Rex hasn't been walked in 8 hours"
      data:
        actions:
          - action: "START_WALK"
            title: "Start Walk 🐕"
```

## 4. Medication Reminder

```yaml
alias: "Paw Control - Medication Reminder"
description: "Remind to give medication"
trigger:
  - platform: time
    at: "08:00:00"
  - platform: time
    at: "20:00:00"
action:
  - service: notify.mobile_app_phone
    data:
      title: "💊 Medication Time"
      message: "Time for Rex's medication"
      data:
        persistent: true
        actions:
          - action: "MED_GIVEN"
            title: "Given ✅"
```

## 5. Grooming Due Alert

```yaml
alias: "Paw Control - Grooming Due"
description: "Alert when grooming is needed"
trigger:
  - platform: state
    entity_id: binary_sensor.pawcontrol_rex_needs_grooming
    to: "on"
  - platform: time
    at: "09:00:00"
condition:
  - condition: state
    entity_id: binary_sensor.pawcontrol_rex_needs_grooming
    state: "on"
action:
  - service: notify.mobile_app_phone
    data:
      title: "✂️ Grooming Needed"
      message: "Rex is due for grooming ({{ states('sensor.pawcontrol_rex_days_since_grooming') }} days)"
```

## 6. Daily Summary Report

```yaml
alias: "Paw Control - Daily Summary"
description: "Send daily summary at bedtime"
trigger:
  - platform: time
    at: "22:00:00"
action:
  - service: notify.mobile_app_phone
    data:
      title: "🐾 Daily Summary for Rex"
      message: |
        Walks: {{ states('sensor.pawcontrol_rex_walks_today') }}
        Total Distance: {{ states('sensor.pawcontrol_rex_total_distance_today') }}m
        Meals: B{{ states('sensor.pawcontrol_rex_feeding_breakfast') }} L{{ states('sensor.pawcontrol_rex_feeding_lunch') }} D{{ states('sensor.pawcontrol_rex_feeding_dinner') }}
        Activity Level: {{ states('sensor.pawcontrol_rex_activity_level') }}
        Calories Burned: {{ states('sensor.pawcontrol_rex_calories_burned_today') }}
```

## 7. Weather-Based Walk Suggestion

```yaml
alias: "Paw Control - Good Weather Walk"
description: "Suggest walk during good weather"
trigger:
  - platform: numeric_state
    entity_id: weather.home
    attribute: temperature
    above: 10
    below: 25
condition:
  - condition: state
    entity_id: weather.home
    state: "sunny"
  - condition: numeric_state
    entity_id: sensor.pawcontrol_rex_walks_today
    below: 2
  - condition: time
    after: "14:00:00"
    before: "18:00:00"
action:
  - service: notify.mobile_app_phone
    data:
      title: "☀️ Perfect Walk Weather"
      message: "Great weather for a walk with Rex!"
```

## 8. Visitor Mode Automation

```yaml
alias: "Paw Control - Visitor Mode Auto"
description: "Enable visitor mode when guests arrive"
trigger:
  - platform: state
    entity_id: calendar.family_calendar
    attribute: message
    to: "Dog Sitter Visit"
action:
  - service: pawcontrol.toggle_visitor_mode
    data:
      enabled: true
  - service: notify.mobile_app_phone
    data:
      title: "👥 Visitor Mode"
      message: "Visitor mode enabled for dog sitter"
```

## 9. Emergency Alert

```yaml
alias: "Paw Control - Emergency Alert"
description: "Send emergency alert if dog escapes"
trigger:
  - platform: state
    entity_id: binary_sensor.pawcontrol_rex_is_home
    from: "on"
    to: "off"
condition:
  - condition: state
    entity_id: binary_sensor.pawcontrol_rex_walk_in_progress
    state: "off"
action:
  - service: pawcontrol.activate_emergency_mode
    data:
      level: "critical"
      note: "Rex may have escaped!"
  - service: notify.all_devices
    data:
      title: "🚨 EMERGENCY"
      message: "Rex is not home and no walk was started!"
      data:
        priority: high
        ttl: 0
```

## 10. Feeding Overprotection

```yaml
alias: "Paw Control - Overfeeding Protection"
description: "Warn about overfeeding"
trigger:
  - platform: numeric_state
    entity_id: sensor.pawcontrol_rex_feeding_snack
    above: 3
action:
  - service: notify.mobile_app_phone
    data:
      title: "⚠️ Overfeeding Warning"
      message: "Rex has had {{ states('sensor.pawcontrol_rex_feeding_snack') }} snacks today!"
  - service: switch.turn_on
    entity_id: switch.pawcontrol_rex_overfeeding_protection
```
