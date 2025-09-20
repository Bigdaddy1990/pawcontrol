# Garden Tracking Automations for Paw Control

## Quality Scale: Platinum | HA 2025.9.3+ | Python 3.13+

This document provides comprehensive automation examples for the garden tracking system. These automations leverage the garden session management, activity logging, and intelligent poop confirmation features implemented in the garden_manager module.

## =============================================================================
## GARDEN SESSION AUTOMATIONS
## =============================================================================

### 1. Automatic Garden Detection via Door Sensor
```yaml
alias: "PawControl - Smart Garden Detection"
description: "Automatically detect when dog goes to garden and start session"
trigger:
  - platform: state
    entity_id: binary_sensor.garden_door
    to: "on"
    for: "00:00:30"
  - platform: state
    entity_id: binary_sensor.back_door
    to: "on"
    for: "00:00:30"
condition:
  - condition: state
    entity_id: binary_sensor.buddy_garden_session_active
    state: "off"
  - condition: time
    after: "06:00:00"
    before: "22:00:00"
  - condition: numeric_state
    entity_id: sensor.buddy_last_garden_session_hours
    above: 2  # Prevent too frequent sessions
action:
  - service: notify.mobile_app_phone
    data:
      title: "🌱 Garden Detection"
      message: "Buddy went to the garden! Start tracking session?"
      data:
        actions:
          - action: "START_GARDEN_SESSION"
            title: "✅ Start Session"
          - action: "NOT_GARDEN"
            title: "❌ Not Garden"
        timeout: 90  # 90 seconds to respond

  # Auto-start after 1.5 minutes without response
  - delay: "00:01:30"
  - condition: state
    entity_id: binary_sensor.buddy_garden_session_active
    state: "off"
  - service: pawcontrol.start_garden_session
    data:
      dog_id: "buddy"
      detection_method: "door_sensor"
      weather_conditions: "{{ states('weather.home') }}"
      temperature: "{{ states('sensor.outdoor_temperature') | float }}"
  - service: notify.mobile_app_phone
    data:
      title: "🌱 Garden Session Started"
      message: "Auto-started garden session for Buddy (door sensor detection)"
mode: single
```

### 2. Weather-Based Garden Session Suggestions
```yaml
alias: "PawControl - Weather Garden Suggestions"
description: "Suggest garden time based on good weather conditions"
trigger:
  - platform: state
    entity_id: weather.home
    to: "sunny"
    for: "00:15:00"
  - platform: numeric_state
    entity_id: sensor.outdoor_temperature
    above: 15
    below: 25
    for: "00:15:00"
condition:
  - condition: state
    entity_id: binary_sensor.buddy_garden_session_active
    state: "off"
  - condition: numeric_state
    entity_id: sensor.buddy_last_garden_session_hours
    above: 4
  - condition: time
    after: "08:00:00"
    before: "19:00:00"
  - condition: state
    entity_id: person.owner
    state: "home"
action:
  - service: notify.mobile_app_phone
    data:
      title: "☀️ Perfect Garden Weather"
      message: >
        Beautiful weather for Buddy's garden time!
        {{ states('sensor.outdoor_temperature') }}°C and {{ states('weather.home') }}
      data:
        actions:
          - action: "START_GARDEN_NOW"
            title: "🌱 Start Garden Session"
          - action: "REMIND_LATER"
            title: "⏰ Remind in 30min"
```

### 3. Garden Session Timeout Management
```yaml
alias: "PawControl - Garden Session Timeout"
description: "Handle sessions that exceed normal duration"
trigger:
  - platform: state
    entity_id: binary_sensor.buddy_garden_session_active
    to: "on"
    for: "00:45:00"  # 45 minutes timeout
condition:
  - condition: state
    entity_id: binary_sensor.buddy_garden_session_active
    state: "on"
action:
  - service: notify.mobile_app_phone
    data:
      title: "⏰ Long Garden Session"
      message: "Buddy has been in the garden for 45 minutes. Everything okay?"
      data:
        actions:
          - action: "EXTEND_SESSION"
            title: "✅ All Good"
          - action: "END_SESSION_NOW"
            title: "🏠 Bring Inside"
          - action: "CHECK_DOG"
            title: "👀 Check on Dog"
        timeout: 300

  # Auto-end after 60 minutes total
  - delay: "00:15:00"
  - condition: state
    entity_id: binary_sensor.buddy_garden_session_active
    state: "on"
  - service: pawcontrol.end_garden_session
    data:
      dog_id: "buddy"
      notes: "Auto-ended due to timeout (60 minutes)"
  - service: notify.mobile_app_phone
    data:
      title: "🏠 Garden Session Auto-Ended"
      message: "Buddy's garden session auto-ended after 60 minutes"
      data:
        priority: high
```

## =============================================================================
## POOP TRACKING AUTOMATIONS
## =============================================================================

### 4. Intelligent Poop Confirmation Request
```yaml
alias: "PawControl - Smart Poop Confirmation"
description: "Ask about poop after appropriate time in garden"
trigger:
  - platform: state
    entity_id: binary_sensor.buddy_garden_session_active
    to: "on"
    for: "00:03:00"  # After 3 minutes in garden
condition:
  - condition: template
    value_template: "{{ states('sensor.buddy_garden_poop_count_today') | int == 0 }}"
  - condition: numeric_state
    entity_id: sensor.buddy_last_poop_hours
    above: 8  # Only ask if it's been a while
action:
  - service: notify.mobile_app_phone
    data:
      title: "💩 Poop Check"
      message: "Has Buddy done his business in the garden?"
      data:
        actions:
          - action: "CONFIRM_POOP_EXCELLENT"
            title: "✅ Yes - Excellent"
          - action: "CONFIRM_POOP_NORMAL"
            title: "✅ Yes - Normal"
          - action: "CONFIRM_POOP_SOFT"
            title: "⚠️ Yes - Soft"
          - action: "NO_POOP_YET"
            title: "❌ No Poop Yet"
        timeout: 300  # 5 minutes to respond
```

### 5. Poop Quality Monitoring & Health Alerts
```yaml
alias: "PawControl - Poop Quality Health Monitor"
description: "Monitor poop quality trends and send health alerts"
trigger:
  - platform: state
    entity_id: sensor.buddy_poop_quality_trend
    for: "00:30:00"
condition:
  - condition: template
    value_template: "{{ trigger.to_state.state not in ['unknown', 'unavailable'] }}"
action:
  - choose:
      # Concerning trend - soft/loose for multiple days
      - conditions:
          - condition: template
            value_template: >
              {{ trigger.to_state.state in ['concerning', 'soft_trend', 'loose_trend'] }}
        sequence:
          - service: notify.mobile_app_phone
            data:
              title: "⚠️ Poop Quality Concern"
              message: >
                Buddy's poop quality has been {{ trigger.to_state.state }} for several days.
                Last 3 entries: {{ state_attr('sensor.buddy_recent_poop_quality', 'last_3') | join(', ') }}
              data:
                priority: high
                actions:
                  - action: "LOG_DETAILED_POOP"
                    title: "📝 Log Details"
                  - action: "CONTACT_VET"
                    title: "👨‍⚕️ Contact Vet"
                  - action: "DIET_ADJUSTMENT"
                    title: "🥘 Adjust Diet"

      # Excellent trend
      - conditions:
          - condition: template
            value_template: "{{ trigger.to_state.state == 'excellent' }}"
        sequence:
          - service: notify.mobile_app_phone
            data:
              title: "🎉 Perfect Digestive Health"
              message: "Buddy's poop quality has been excellent! Great job!"
```

### 6. Poop Confirmation Response Handler
```yaml
alias: "PawControl - Handle Poop Confirmation Responses"
description: "Process user responses to poop confirmation requests"
trigger:
  - platform: event
    event_type: mobile_app_notification_action
    event_data:
      action: "CONFIRM_POOP_EXCELLENT"
  - platform: event
    event_type: mobile_app_notification_action
    event_data:
      action: "CONFIRM_POOP_NORMAL"
  - platform: event
    event_type: mobile_app_notification_action
    event_data:
      action: "CONFIRM_POOP_SOFT"
  - platform: event
    event_type: mobile_app_notification_action
    event_data:
      action: "NO_POOP_YET"
action:
  - choose:
      # Excellent poop confirmed
      - conditions:
          - condition: template
            value_template: "{{ trigger.event.data.action == 'CONFIRM_POOP_EXCELLENT' }}"
        sequence:
          - service: pawcontrol.confirm_garden_poop
            data:
              dog_id: "buddy"
              confirmed: true
              quality: "excellent"
              size: "normal"
          - service: notify.mobile_app_phone
            data:
              title: "✅ Poop Logged - Excellent"
              message: "Buddy's excellent poop logged in garden session"

      # Normal poop confirmed
      - conditions:
          - condition: template
            value_template: "{{ trigger.event.data.action == 'CONFIRM_POOP_NORMAL' }}"
        sequence:
          - service: pawcontrol.confirm_garden_poop
            data:
              dog_id: "buddy"
              confirmed: true
              quality: "normal"
              size: "normal"
          - service: notify.mobile_app_phone
            data:
              title: "✅ Poop Logged - Normal"
              message: "Buddy's normal poop logged in garden session"

      # Soft poop - needs attention
      - conditions:
          - condition: template
            value_template: "{{ trigger.event.data.action == 'CONFIRM_POOP_SOFT' }}"
        sequence:
          - service: pawcontrol.confirm_garden_poop
            data:
              dog_id: "buddy"
              confirmed: true
              quality: "soft"
              size: "normal"
          - service: notify.mobile_app_phone
            data:
              title: "⚠️ Soft Poop Logged"
              message: "Buddy had soft poop. Monitor diet and hydration."
              data:
                actions:
                  - action: "ADD_NOTES"
                    title: "📝 Add Notes"
                  - action: "ADJUST_DIET"
                    title: "🥘 Adjust Diet"

      # No poop yet
      - conditions:
          - condition: template
            value_template: "{{ trigger.event.data.action == 'NO_POOP_YET' }}"
        sequence:
          - service: pawcontrol.confirm_garden_poop
            data:
              dog_id: "buddy"
              confirmed: false
          - delay: "00:10:00"  # Wait 10 more minutes
          - condition: state
            entity_id: binary_sensor.buddy_garden_session_active
            state: "on"
          - service: notify.mobile_app_phone
            data:
              title: "💩 Poop Check - Follow Up"
              message: "How about now? Has Buddy done his business?"
              data:
                actions:
                  - action: "CONFIRM_POOP_NOW"
                    title: "✅ Yes, Now"
                  - action: "STILL_NO_POOP"
                    title: "❌ Still No"
```

## =============================================================================
## GARDEN ACTIVITY TRACKING
## =============================================================================

### 7. Activity Detection & Logging
```yaml
alias: "PawControl - Garden Activity Detection"
description: "Detect and log specific garden activities"
trigger:
  - platform: state
    entity_id: binary_sensor.motion_garden_play_area
    to: "on"
    for: "00:01:00"
  - platform: state
    entity_id: binary_sensor.motion_garden_digging_spot
    to: "on"
    for: "00:00:30"
condition:
  - condition: state
    entity_id: binary_sensor.buddy_garden_session_active
    state: "on"
action:
  - choose:
      # Play area motion - log play activity
      - conditions:
          - condition: template
            value_template: "{{ 'play_area' in trigger.entity_id }}"
        sequence:
          - service: pawcontrol.add_garden_activity
            data:
              dog_id: "buddy"
              activity_type: "play"
              location: "play_area"
              notes: "Motion detected in play area"
              confirmed: true
          - service: notify.mobile_app_phone
            data:
              title: "🎾 Play Activity"
              message: "Buddy is playing in the garden!"

      # Digging spot motion - log digging
      - conditions:
          - condition: template
            value_template: "{{ 'digging_spot' in trigger.entity_id }}"
        sequence:
          - service: pawcontrol.add_garden_activity
            data:
              dog_id: "buddy"
              activity_type: "digging"
              location: "back_corner"
              notes: "Motion detected at known digging spot"
              confirmed: true
          - service: notify.mobile_app_phone
            data:
              title: "🕳️ Digging Alert"
              message: "Buddy is digging in the garden again!"
              data:
                actions:
                  - action: "REDIRECT_ACTIVITY"
                    title: "🎾 Redirect to Play"
                  - action: "ALLOW_DIGGING"
                    title: "✅ Allow Digging"
```

### 8. Garden Session Summary & Statistics
```yaml
alias: "PawControl - Garden Session Complete Summary"
description: "Send summary when garden session ends"
trigger:
  - platform: state
    entity_id: binary_sensor.buddy_garden_session_active
    from: "on"
    to: "off"
condition:
  - condition: template
    value_template: "{{ trigger.from_state.state == 'on' }}"
action:
  - delay: "00:00:05"  # Wait for data to update
  - service: notify.mobile_app_phone
    data:
      title: "🌱 Garden Session Complete"
      message: >
        Buddy's garden session finished!
        Duration: {{ states('sensor.buddy_last_garden_duration') }} minutes
        Activities: {{ states('sensor.buddy_garden_activities_last_session') }}
        Poop events: {{ states('sensor.buddy_garden_poop_count_today') }}
        Weather: {{ state_attr('sensor.buddy_last_garden_session', 'weather_conditions') }}
      data:
        actions:
          - action: "VIEW_FULL_SUMMARY"
            title: "📊 Full Summary"
          - action: "ADD_SESSION_NOTES"
            title: "📝 Add Notes"
```

### 9. Daily Garden Statistics Report
```yaml
alias: "PawControl - Daily Garden Statistics"
description: "Daily summary of garden activities"
trigger:
  - platform: time
    at: "21:00:00"
condition:
  - condition: numeric_state
    entity_id: sensor.buddy_garden_sessions_today
    above: 0
action:
  - service: notify.mobile_app_phone
    data:
      title: "📊 Daily Garden Report"
      message: >
        Buddy's garden day summary:
        🌱 Sessions: {{ states('sensor.buddy_garden_sessions_today') }}
        ⏱️ Total time: {{ states('sensor.buddy_garden_time_today') }} minutes
        🎾 Activities: {{ states('sensor.buddy_garden_activities_today') }}
        💩 Poop events: {{ states('sensor.buddy_garden_poop_count_today') }}
        🌤️ Weather: {{ state_attr('sensor.buddy_garden_sessions_today', 'weather_summary') }}
      data:
        actions:
          - action: "VIEW_WEEKLY_TREND"
            title: "📈 Weekly Trend"
          - action: "EXPORT_GARDEN_DATA"
            title: "📤 Export Data"
```

## =============================================================================
## GARDEN SESSION RESPONSE AUTOMATIONS
## =============================================================================

### 10. Garden Session Action Responses
```yaml
alias: "PawControl - Garden Session Action Handler"
description: "Handle user responses to garden session notifications"
trigger:
  - platform: event
    event_type: mobile_app_notification_action
    event_data:
      action: "START_GARDEN_SESSION"
  - platform: event
    event_type: mobile_app_notification_action
    event_data:
      action: "START_GARDEN_NOW"
  - platform: event
    event_type: mobile_app_notification_action
    event_data:
      action: "END_SESSION_NOW"
  - platform: event
    event_type: mobile_app_notification_action
    event_data:
      action: "EXTEND_SESSION"
action:
  - choose:
      # Start garden session
      - conditions:
          - condition: template
            value_template: >
              {{ trigger.event.data.action in ['START_GARDEN_SESSION', 'START_GARDEN_NOW'] }}
        sequence:
          - service: pawcontrol.start_garden_session
            data:
              dog_id: "buddy"
              detection_method: "manual"
              weather_conditions: "{{ states('weather.home') }}"
              temperature: "{{ states('sensor.outdoor_temperature') | float }}"
          - service: notify.mobile_app_phone
            data:
              title: "🌱 Garden Session Started"
              message: "Started garden session for Buddy manually"

      # End session now
      - conditions:
          - condition: template
            value_template: "{{ trigger.event.data.action == 'END_SESSION_NOW' }}"
        sequence:
          - service: pawcontrol.end_garden_session
            data:
              dog_id: "buddy"
              notes: "Ended manually by user"
          - service: notify.mobile_app_phone
            data:
              title: "🏠 Garden Session Ended"
              message: "Garden session ended manually"

      # Extend session
      - conditions:
          - condition: template
            value_template: "{{ trigger.event.data.action == 'EXTEND_SESSION' }}"
        sequence:
          - service: notify.mobile_app_phone
            data:
              title: "⏰ Session Extended"
              message: "Garden session extended. Will check again in 30 minutes."
          - delay: "00:30:00"
          - condition: state
            entity_id: binary_sensor.buddy_garden_session_active
            state: "on"
          - service: notify.mobile_app_phone
            data:
              title: "⏰ Garden Session Check"
              message: "Buddy has been in garden for 1.5 hours total. Still okay?"
              data:
                actions:
                  - action: "END_SESSION_NOW"
                    title: "🏠 End Session"
                  - action: "EXTEND_MORE"
                    title: "⏰ Extend More"
```

### 11. Garden Emergency Detection
```yaml
alias: "PawControl - Garden Emergency Detection"
description: "Detect potential emergencies during garden sessions"
trigger:
  - platform: numeric_state
    entity_id: sensor.outdoor_temperature
    above: 30  # Too hot
  - platform: state
    entity_id: weather.home
    to: "lightning"
  - platform: state
    entity_id: binary_sensor.garden_gate_open
    to: "on"
    for: "00:00:10"
condition:
  - condition: state
    entity_id: binary_sensor.buddy_garden_session_active
    state: "on"
action:
  - choose:
      # Too hot weather
      - conditions:
          - condition: numeric_state
            entity_id: sensor.outdoor_temperature
            above: 30
        sequence:
          - service: notify.all_devices
            data:
              title: "🌡️ HEAT WARNING"
              message: >
                Temperature is {{ states('sensor.outdoor_temperature') }}°C!
                Buddy should come inside immediately.
              data:
                priority: critical
                actions:
                  - action: "EMERGENCY_END_SESSION"
                    title: "🏠 End Session NOW"

      # Lightning detected
      - conditions:
          - condition: state
            entity_id: weather.home
            state: "lightning"
        sequence:
          - service: notify.all_devices
            data:
              title: "⚡ LIGHTNING WARNING"
              message: "Lightning detected! Bring Buddy inside immediately!"
              data:
                priority: critical
                actions:
                  - action: "EMERGENCY_END_SESSION"
                    title: "🏠 End Session NOW"

      # Gate opened (escape risk)
      - conditions:
          - condition: state
            entity_id: binary_sensor.garden_gate_open
            state: "on"
        sequence:
          - service: notify.all_devices
            data:
              title: "🚨 GATE OPEN ALERT"
              message: "Garden gate is open! Check on Buddy immediately!"
              data:
                priority: critical
                actions:
                  - action: "CHECK_DOG_LOCATION"
                    title: "📍 Check Location"
                  - action: "CLOSE_GATE"
                    title: "🚪 Close Gate"
```

## ENTITY REQUIREMENTS

These automations require the following entities to be available through the PawControl integration:

### Garden Session Sensors
- `sensor.{dog_id}_garden_time_today`
- `sensor.{dog_id}_garden_sessions_today`
- `sensor.{dog_id}_garden_poop_count_today`
- `sensor.{dog_id}_last_garden_session`
- `sensor.{dog_id}_garden_activities_count`
- `sensor.{dog_id}_last_garden_duration`
- `sensor.{dog_id}_last_garden_session_hours`

### Binary Sensors
- `binary_sensor.{dog_id}_garden_session_active`
- `binary_sensor.garden_door`
- `binary_sensor.garden_gate_open`

### Motion Sensors (Optional)
- `binary_sensor.motion_garden_play_area`
- `binary_sensor.motion_garden_digging_spot`

### Weather Integration
- `weather.home`
- `sensor.outdoor_temperature`

### Services
- `pawcontrol.start_garden_session`
- `pawcontrol.end_garden_session`
- `pawcontrol.add_garden_activity`
- `pawcontrol.confirm_garden_poop`

## IMPLEMENTATION NOTES

1. **Door Sensor Setup**: Configure door sensors for garden access points
2. **Motion Detection**: Optional motion sensors for activity detection
3. **Weather Integration**: Ensure weather integration is configured
4. **Notification Actions**: Customize based on your mobile app setup
5. **Dog ID**: Replace "buddy" with your actual dog ID throughout
6. **Time Zones**: Adjust trigger times for your local timezone
7. **Temperature Units**: Adjust temperature thresholds for your units (°C/°F)

## CUSTOMIZATION

These automations can be customized by:
- Modifying session timeout durations
- Adjusting temperature and weather thresholds
- Adding custom garden zones and activities
- Integrating with smart garden devices
- Creating breed-specific behavior patterns
- Adding health condition considerations
