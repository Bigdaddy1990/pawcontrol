# PawControl Automation Examples

Complete collection of automation examples for PawControl integration.

## Table of Contents

- [Walk Automations](#walk-automations)
- [Feeding Automations](#feeding-automations)
- [Location & Geofencing](#location--geofencing)
- [Health & Wellness](#health--wellness)
- [Multi-Dog Scenarios](#multi-dog-scenarios)
- [Advanced Automations](#advanced-automations)

---

## Walk Automations

### 1. Daily Walk Reminder

Remind yourself to walk your dog at specific times.

```yaml
alias: "Daily Walk Reminder - Buddy"
trigger:
  - platform: time
    at: "08:00:00"
  - platform: time
    at: "18:00:00"
condition:
  - condition: state
    entity_id: binary_sensor.buddy_walk_in_progress
    state: "off"
  - condition: template
    value_template: >
      {{ (now() - states.sensor.buddy_last_walk_time.last_changed).total_seconds() > 21600 }}
action:
  - service: notify.mobile_app
    data:
      title: "🐕 Walk Time!"
      message: "Time for Buddy's walk"
      data:
        actions:
          - action: "START_WALK"
            title: "Start Walk"
```

### 2. Walk Statistics Summary

Daily summary of walk activity.

```yaml
alias: "Daily Walk Summary - Buddy"
trigger:
  - platform: time
    at: "21:00:00"
action:
  - service: notify.mobile_app
    data:
      title: "📊 Buddy's Walk Summary"
      message: >
        Today's walks:
        🚶 {{ states('sensor.buddy_walks_today') }} walks
        📏 {{ states('sensor.buddy_total_distance_today') }} km
        ⏱ {{ states('sensor.buddy_total_walk_time_today') }} minutes
```

### 3. Long Walk Celebration

Celebrate when your dog has a long walk!

```yaml
alias: "Long Walk Achievement - Buddy"
trigger:
  - platform: state
    entity_id: binary_sensor.buddy_walk_in_progress
    to: "off"
condition:
  - condition: numeric_state
    entity_id: sensor.buddy_last_walk_distance
    above: 5
action:
  - service: notify.mobile_app
    data:
      title: "🏆 Achievement Unlocked!"
      message: "Buddy walked {{ states('sensor.buddy_last_walk_distance') }} km today!"
  - service: tts.google_translate_say
    data:
      entity_id: media_player.living_room
      message: "Great job! Buddy walked over 5 kilometers today!"
```

### 4. Weather-Based Walk Suggestion

Suggest walks when weather is nice.

```yaml
alias: "Good Weather Walk Suggestion - Buddy"
trigger:
  - platform: numeric_state
    entity_id: sensor.outdoor_temperature
    above: 15
    below: 25
condition:
  - condition: state
    entity_id: weather.home
    state: "sunny"
  - condition: state
    entity_id: binary_sensor.buddy_walk_in_progress
    state: "off"
  - condition: time
    after: "09:00:00"
    before: "20:00:00"
action:
  - service: notify.mobile_app
    data:
      title: "☀️ Perfect Walk Weather!"
      message: "It's {{ states('sensor.outdoor_temperature') }}°C and sunny - great time for a walk!"
```

---

## Feeding Automations

### 5. Feeding Schedule Reminder

Never miss a meal time.

```yaml
alias: "Feeding Reminder - Buddy"
trigger:
  - platform: time
    at: "07:00:00"
  - platform: time
    at: "18:00:00"
condition:
  - condition: template
    value_template: >
      {{ (now() - states.sensor.buddy_last_meal_time.last_changed).total_seconds() > 36000 }}
action:
  - service: notify.mobile_app
    data:
      title: "🍽️ Feeding Time"
      message: "Time to feed Buddy!"
      data:
        actions:
          - action: "FED_BUDDY"
            title: "Fed"
```

### 6. Overfeeding Alert

Prevent accidental overfeeding.

```yaml
alias: "Overfeeding Alert - Buddy"
trigger:
  - platform: state
    entity_id: sensor.buddy_meals_today
condition:
  - condition: numeric_state
    entity_id: sensor.buddy_meals_today
    above: 2
action:
  - service: notify.mobile_app
    data:
      title: "⚠️ Feeding Alert"
      message: "Buddy has been fed {{ states('sensor.buddy_meals_today') }} times today. Check if correct."
      data:
        priority: high
```

### 7. Calorie Tracking

Monitor daily calorie intake.

```yaml
alias: "Daily Calorie Summary - Buddy"
trigger:
  - platform: time
    at: "20:00:00"
action:
  - service: notify.mobile_app
    data:
      title: "🍖 Calorie Report"
      message: >
        Buddy consumed {{ states('sensor.buddy_daily_calories') }} calories today.
        Target: {{ state_attr('sensor.buddy_daily_calories', 'target') }}
```

---

## Location & Geofencing

### 8. Escape Alert

Critical alert when dog leaves safe zone.

```yaml
alias: "Escape Alert - Buddy"
trigger:
  - platform: state
    entity_id: binary_sensor.buddy_in_safe_zone
    to: "off"
    for:
      minutes: 2
action:
  - service: notify.mobile_app
    data:
      title: "🚨 ALERT: Buddy Left Safe Zone"
      message: "Buddy is outside the safe zone!"
      data:
        priority: critical
        ttl: 0
        channel: emergency
  - service: tts.google_translate_say
    data:
      entity_id: media_player.all
      message: "Alert! Buddy has left the safe zone!"
```

### 9. Return Home Notification

Welcome your dog home.

```yaml
alias: "Welcome Home - Buddy"
trigger:
  - platform: state
    entity_id: binary_sensor.buddy_in_safe_zone
    to: "on"
condition:
  - condition: template
    value_template: >
      {{ (now() - trigger.from_state.last_changed).total_seconds() > 1800 }}
action:
  - service: notify.mobile_app
    data:
      title: "🏠 Buddy is Home"
      message: "Buddy has returned to the safe zone"
```

### 10. Location Sharing

Share dog's location with family.

```yaml
alias: "Share Buddy Location - On Request"
trigger:
  - platform: event
    event_type: mobile_app_notification_action
    event_data:
      action: "SHARE_LOCATION"
action:
  - service: notify.family
    data:
      title: "📍 Buddy's Location"
      message: >
        Buddy is at:
        Lat: {{ state_attr('device_tracker.buddy', 'latitude') }}
        Lon: {{ state_attr('device_tracker.buddy', 'longitude') }}
      data:
        url: >
          https://www.google.com/maps?q={{
            state_attr('device_tracker.buddy', 'latitude')
          }},{{
            state_attr('device_tracker.buddy', 'longitude')
          }}
```

---

## Health & Wellness

### 11. Low Battery Warning

Ensure device stays charged.

```yaml
alias: "Low Battery - Buddy Collar"
trigger:
  - platform: numeric_state
    entity_id: sensor.buddy_battery_level
    below: 20
action:
  - service: notify.mobile_app
    data:
      title: "🔋 Low Battery"
      message: "Buddy's collar battery is {{ states('sensor.buddy_battery_level') }}%"
      data:
        actions:
          - action: "CHARGE_REMINDER"
            title: "Remind Me Later"
```

### 12. Activity Level Monitoring

Track if dog is getting enough exercise.

```yaml
alias: "Low Activity Alert - Buddy"
trigger:
  - platform: time
    at: "19:00:00"
condition:
  - condition: numeric_state
    entity_id: sensor.buddy_total_distance_today
    below: 2
action:
  - service: notify.mobile_app
    data:
      title: "😴 Low Activity Today"
      message: "Buddy only walked {{ states('sensor.buddy_total_distance_today') }} km today"
```

### 13. Temperature Alert

Alert when it's too hot or cold for walks.

```yaml
alias: "Extreme Temperature Alert"
trigger:
  - platform: numeric_state
    entity_id: sensor.outdoor_temperature
    above: 30
  - platform: numeric_state
    entity_id: sensor.outdoor_temperature
    below: -10
condition:
  - condition: state
    entity_id: binary_sensor.buddy_walk_in_progress
    state: "on"
action:
  - service: notify.mobile_app
    data:
      title: "🌡️ Temperature Warning"
      message: >
        Current temperature: {{ states('sensor.outdoor_temperature') }}°C
        Consider ending walk soon for Buddy's safety.
      data:
        priority: high
```

---

## Multi-Dog Scenarios

### 14. All Dogs Home Check

Verify all dogs are safe at night.

```yaml
alias: "All Dogs Home - Night Check"
trigger:
  - platform: time
    at: "22:00:00"
action:
  - choose:
      - conditions:
          - condition: and
            conditions:
              - condition: state
                entity_id: binary_sensor.buddy_in_safe_zone
                state: "on"
              - condition: state
                entity_id: binary_sensor.max_in_safe_zone
                state: "on"
        sequence:
          - service: notify.mobile_app
            data:
              title: "✅ All Dogs Home"
              message: "Buddy and Max are both in the safe zone"
    default:
      - service: notify.mobile_app
        data:
          title: "⚠️ Dog Missing"
          message: >
            {% set missing = [] %}
            {% if is_state('binary_sensor.buddy_in_safe_zone', 'off') %}
              {% set missing = missing + ['Buddy'] %}
            {% endif %}
            {% if is_state('binary_sensor.max_in_safe_zone', 'off') %}
              {% set missing = missing + ['Max'] %}
            {% endif %}
            {{ missing | join(' and ') }} not in safe zone
          data:
            priority: high
```

### 15. Group Walk Detection

Detect when multiple dogs walk together.

```yaml
alias: "Group Walk - Buddy and Max"
trigger:
  - platform: state
    entity_id:
      - binary_sensor.buddy_walk_in_progress
      - binary_sensor.max_walk_in_progress
    to: "on"
condition:
  - condition: state
    entity_id: binary_sensor.buddy_walk_in_progress
    state: "on"
  - condition: state
    entity_id: binary_sensor.max_walk_in_progress
    state: "on"
action:
  - service: notify.mobile_app
    data:
      title: "🐕🐕 Group Walk"
      message: "Buddy and Max are both on a walk!"
```

---

## Advanced Automations

### 16. Intelligent Walk Scheduler

AI-based walk suggestions using patterns.

```yaml
alias: "Smart Walk Scheduler - Buddy"
trigger:
  - platform: time_pattern
    hours: "*"
condition:
  - condition: template
    value_template: >
      {% set last_walk = as_timestamp(states.sensor.buddy_last_walk_time.last_changed) %}
      {% set hours_since = (now().timestamp() - last_walk) / 3600 %}
      {% set typical_interval = state_attr('sensor.buddy_walk_pattern', 'average_interval_hours') | float %}
      {{ hours_since >= (typical_interval * 0.9) }}
  - condition: state
    entity_id: weather.home
    state:
      - "sunny"
      - "cloudy"
  - condition: time
    after: "07:00:00"
    before: "21:00:00"
action:
  - service: notify.mobile_app
    data:
      title: "🤖 Smart Walk Suggestion"
      message: >
        Based on Buddy's pattern, it's time for a walk!
        Usual interval: {{ state_attr('sensor.buddy_walk_pattern', 'average_interval_hours') }} hours
```

### 17. Automated Vacation Mode

Adjust expectations when on vacation.

```yaml
alias: "Vacation Mode - Adjust Expectations"
trigger:
  - platform: state
    entity_id: input_boolean.vacation_mode
    to: "on"
action:
  - service: automation.turn_off
    target:
      entity_id:
        - automation.daily_walk_reminder_buddy
        - automation.feeding_reminder_buddy
  - service: notify.mobile_app
    data:
      title: "✈️ Vacation Mode Active"
      message: "Walk and feeding reminders paused"
```

### 18. Integration with Person Tracking

Coordinate with person location.

```yaml
alias: "Auto-Start Walk - Phone Movement"
trigger:
  - platform: state
    entity_id: person.owner
    to: "not_home"
condition:
  - condition: time
    after: "06:00:00"
    before: "22:00:00"
  - condition: template
    value_template: >
      {{ distance(states.person.owner, states.device_tracker.buddy) < 0.1 }}
action:
  - service: switch.turn_on
    target:
      entity_id: switch.buddy_walk_detection
  - delay:
      seconds: 30
  - condition: state
    entity_id: binary_sensor.buddy_walk_in_progress
    state: "on"
  - service: notify.mobile_app
    data:
      title: "🚶 Walk Auto-Detected"
      message: "Walk tracking started for Buddy"
```

### 19. Node-RED Integration Example

Complex flow using Node-RED.

```json
[
  {
    "id": "walk_monitor",
    "type": "server-state-changed",
    "name": "Buddy Walk State",
    "server": "home_assistant",
    "entityid": "binary_sensor.buddy_walk_in_progress",
    "outputs": 2,
    "wires": [
      ["walk_started"],
      ["walk_ended"]
    ]
  },
  {
    "id": "walk_started",
    "type": "api-call-service",
    "name": "Start Walk Timer",
    "server": "home_assistant",
    "service_domain": "timer",
    "service": "start",
    "data": "{\"entity_id\":\"timer.buddy_walk\"}",
    "wires": [["notify_walk_start"]]
  }
]
```

### 20. AppDaemon Script

Python-based automation using AppDaemon.

```python
import appdaemon.plugins.hass.hassapi as hass

class BuddyWalkManager(hass.Hass):
    def initialize(self):
        self.listen_state(
            self.walk_state_changed,
            "binary_sensor.buddy_walk_in_progress"
        )
        
        self.walk_start_time = None
        self.walk_history = []
    
    def walk_state_changed(self, entity, attribute, old, new, kwargs):
        if new == "on":
            self.walk_start_time = self.datetime()
            self.log(f"Walk started at {self.walk_start_time}")
        elif new == "off" and self.walk_start_time:
            duration = (self.datetime() - self.walk_start_time).total_seconds()
            distance = float(self.get_state("sensor.buddy_last_walk_distance"))
            
            self.walk_history.append({
                "date": self.date(),
                "duration": duration,
                "distance": distance
            })
            
            # Calculate statistics
            if len(self.walk_history) >= 7:
                avg_distance = sum(w["distance"] for w in self.walk_history[-7:]) / 7
                
                if distance > avg_distance * 1.5:
                    self.call_service(
                        "notify/mobile_app",
                        title="🏆 Long Walk!",
                        message=f"Buddy walked {distance:.2f}km - above average!"
                    )
```

---

## Tips for Writing Automations

### Best Practices

1. **Use Descriptive Aliases**: Name automations clearly
2. **Add Conditions**: Prevent unwanted triggers
3. **Test Thoroughly**: Use Developer Tools → Services
4. **Use Templates**: Make automations dynamic
5. **Document Your Code**: Add comments for complex logic

### Template Helpers

Common templates for PawControl:

```yaml
# Time since last walk (hours)
{{ (now() - states.sensor.buddy_last_walk_time.last_changed).total_seconds() / 3600 }}

# Distance from home
{{ distance('device_tracker.buddy', 'zone.home') }}

# Battery percentage with formatting
{{ states('sensor.buddy_battery_level') | int }}%

# Check if walk was recent (< 6 hours)
{{ (now() - states.sensor.buddy_last_walk_time.last_changed).total_seconds() < 21600 }}
```

### Debugging

Enable automation traces:

1. Go to **Settings** → **Automations & Scenes**
2. Click on your automation
3. Click **"..."** → **"Enable Traces"**
4. Trigger automation
5. View trace details

---

## Blueprint Conversions

Many of these automations are available as blueprints!

See the [Blueprint Library](blueprints.md) for ready-to-use blueprints.

---

## Community Automations

Share your automations in the [Community Forum](https://community.home-assistant.io/tag/pawcontrol)!

**Popular Community Automations:**
- Photo capture on walk completion
- Spotify playlist based on walk duration
- Calendar integration for walk scheduling
- Weather forecast integration
- Smart speaker announcements

---

**Next Steps:**
- [Advanced Configuration](advanced_config.md)
- [Blueprint Library](blueprints.md)
- [API Reference](api_reference.md)
