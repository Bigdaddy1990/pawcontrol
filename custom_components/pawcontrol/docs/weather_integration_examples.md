# 🌤️ PawControl Weather Integration - Automation Examples

## Overview

This guide provides comprehensive automation examples for PawControl's advanced weather health monitoring system. These examples demonstrate how to create intelligent, weather-aware automations that protect your dog's health and optimize outdoor activities based on real-time weather conditions.

## Table of Contents

1. [Basic Weather Automations](#basic-weather-automations)
2. [Advanced Weather Intelligence](#advanced-weather-intelligence)
3. [Breed-Specific Automations](#breed-specific-automations)
4. [Health Condition Considerations](#health-condition-considerations)
5. [Emergency Weather Protocols](#emergency-weather-protocols)
6. [Multi-Dog Weather Management](#multi-dog-weather-management)
7. [Integration with Smart Home](#integration-with-smart-home)
8. [Dashboard and Notifications](#dashboard-and-notifications)

## Prerequisites

**Required Configuration:**
- PawControl integration with weather module enabled
- Weather entity configured (e.g., `weather.home`)
- Dog profile with breed information
- Mobile app for notifications

**Services Available:**
- `pawcontrol.update_weather_data`
- `pawcontrol.get_weather_recommendations`
- `pawcontrol.calculate_weather_health_score`
- `pawcontrol.weather_alert_actions`

## Basic Weather Automations

### 1. Daily Weather Health Check

```yaml
automation:
  - alias: "🌤️ Daily Weather Health Assessment"
    description: "Morning weather check with health recommendations"
    trigger:
      - platform: time
        at: "06:00:00"
    condition:
      - condition: state
        entity_id: switch.buddy_weather_monitoring
        state: "on"
    action:
      # Update weather data
      - service: pawcontrol.update_weather_data
        data:
          dog_id: "buddy"
          weather_entity: "weather.home"
          force_update: true
      
      # Get personalized recommendations
      - service: pawcontrol.get_weather_recommendations
        data:
          dog_id: "buddy"
          include_breed_specific: true
          include_health_conditions: true
          time_horizon_hours: 24
        response_variable: weather_recommendations
      
      # Send morning weather briefing
      - service: notify.mobile_app_phone
        data:
          title: "🌤️ Daily Weather Report for Buddy"
          message: >
            Weather Score: {{ states('sensor.buddy_weather_health_score') }}/100
            Temperature: {{ states('sensor.temperature') }}°C
            Conditions: {{ states('weather.home') }}
            
            📋 Today's Recommendations:
            {{ weather_recommendations.recommendations | join('\n• ') }}
          data:
            actions:
              - action: "VIEW_DETAILED_FORECAST"
                title: "Detailed Forecast"
              - action: "PLAN_WALKS"
                title: "Plan Walks"
```

### 2. Optimal Walk Time Notification

```yaml
automation:
  - alias: "🚶 Optimal Walk Time Alert"
    description: "Notify when weather conditions are perfect for walks"
    trigger:
      - platform: numeric_state
        entity_id: sensor.buddy_weather_health_score
        above: 75
        for: "00:15:00"
    condition:
      - condition: numeric_state
        entity_id: sensor.buddy_last_walk_hours
        above: 3
      - condition: time
        after: "07:00:00"
        before: "20:00:00"
      - condition: state
        entity_id: binary_sensor.buddy_walk_in_progress
        state: "off"
    action:
      - service: notify.mobile_app_phone
        data:
          title: "🌟 Perfect Walk Weather!"
          message: >
            🌡️ Temperature: {{ states('sensor.temperature') }}°C
            ☀️ Conditions: {{ states('weather.home') }}
            📊 Weather Score: {{ states('sensor.buddy_weather_health_score') }}/100
            
            Perfect conditions for Buddy's walk!
          data:
            priority: normal
            color: green
            actions:
              - action: "START_WALK"
                title: "Start Walk"
              - action: "DELAY_30MIN"
                title: "Remind in 30min"
              - action: "WEATHER_DETAILS"
                title: "Weather Details"
```

### 3. Weather Change Alert

```yaml
automation:
  - alias: "⚠️ Weather Condition Change Alert"
    description: "Alert when weather conditions change significantly"
    trigger:
      - platform: state
        entity_id: sensor.buddy_weather_health_score
        for: "00:05:00"
    condition:
      - condition: template
        value_template: >
          {% set old_score = trigger.from_state.state | int(0) %}
          {% set new_score = trigger.to_state.state | int(0) %}
          {{ (old_score - new_score) | abs >= 20 }}
    action:
      - service: pawcontrol.get_weather_recommendations
        data:
          dog_id: "buddy"
          include_breed_specific: true
        response_variable: updated_recommendations
      
      - service: notify.mobile_app_phone
        data:
          title: "🌤️ Weather Conditions Changed"
          message: >
            {% set old_score = trigger.from_state.state | int(0) %}
            {% set new_score = trigger.to_state.state | int(0) %}
            Weather score changed: {{ old_score }} → {{ new_score }}
            
            📋 Updated recommendations:
            {{ updated_recommendations.recommendations[:3] | join('\n• ') }}
          data:
            actions:
              - action: "VIEW_RECOMMENDATIONS"
                title: "All Recommendations"
              - action: "UPDATE_PLANS"
                title: "Update Plans"
```

## Advanced Weather Intelligence

### 4. Predictive Walk Scheduling

```yaml
automation:
  - alias: "🔮 Intelligent Walk Scheduling"
    description: "Schedule walks based on weather forecast"
    trigger:
      - platform: time_pattern
        hours: "/2"  # Check every 2 hours
    condition:
      - condition: state
        entity_id: switch.buddy_weather_monitoring
        state: "on"
      - condition: numeric_state
        entity_id: sensor.buddy_last_walk_hours
        above: 2
    action:
      # Get 6-hour weather forecast
      - service: pawcontrol.get_weather_recommendations
        data:
          dog_id: "buddy"
          time_horizon_hours: 6
          include_forecast: true
        response_variable: forecast_data
      
      # Create walk schedule based on forecast
      - choose:
          # Excellent conditions now - recommend immediate walk
          - conditions:
              - condition: numeric_state
                entity_id: sensor.buddy_weather_health_score
                above: 80
            sequence:
              - service: notify.mobile_app_phone
                data:
                  title: "🌟 Excellent Walk Weather NOW"
                  message: "Current conditions are excellent. Walk recommended within next hour!"
                  data:
                    actions:
                      - action: "START_WALK_NOW"
                        title: "Start Walk Now"
          
          # Conditions declining - recommend walk soon
          - conditions:
              - condition: template
                value_template: "{{ forecast_data.score_trend == 'declining' }}"
              - condition: numeric_state
                entity_id: sensor.buddy_weather_health_score
                above: 60
            sequence:
              - service: notify.mobile_app_phone
                data:
                  title: "⏰ Walk Soon - Conditions Declining"
                  message: >
                    Current score: {{ states('sensor.buddy_weather_health_score') }}
                    Forecast shows conditions will worsen.
                    Best time: Next {{ forecast_data.optimal_time_window }}
                  data:
                    actions:
                      - action: "SCHEDULE_WALK"
                        title: "Schedule Walk"
          
          # Poor conditions - suggest alternative
          - conditions:
              - condition: numeric_state
                entity_id: sensor.buddy_weather_health_score
                below: 40
            sequence:
              - service: notify.mobile_app_phone
                data:
                  title: "🏠 Indoor Activity Recommended"
                  message: >
                    Weather score: {{ states('sensor.buddy_weather_health_score') }}/100
                    Next good walk window: {{ forecast_data.next_optimal_time }}
                    
                    Consider indoor activities today.
```

### 5. Dynamic Exercise Adjustment

```yaml
automation:
  - alias: "🏃 Dynamic Exercise Intensity Adjustment"
    description: "Adjust exercise intensity based on weather conditions"
    trigger:
      - platform: state
        entity_id: button.buddy_start_walk
    action:
      # Calculate recommended exercise intensity
      - service: pawcontrol.calculate_weather_health_score
        data:
          dog_id: "buddy"
          current_conditions: true
        response_variable: weather_analysis
      
      # Determine exercise modifications
      - service: script.adjust_exercise_plan
        data:
          dog_id: "buddy"
          weather_score: "{{ states('sensor.buddy_weather_health_score') | int }}"
          modifications: >
            {% set score = states('sensor.buddy_weather_health_score') | int %}
            {% if score >= 80 %}
              normal_exercise
            {% elif score >= 60 %}
              reduced_intensity
            {% elif score >= 40 %}
              short_walks_only
            {% else %}
              indoor_only
            {% endif %}
      
      # Start walk with weather-appropriate settings
      - service: pawcontrol.gps_start_walk
        data:
          dog_id: "buddy"
          weather_check: true
          auto_recommendations: true
          intensity_modifier: >
            {% set score = states('sensor.buddy_weather_health_score') | int %}
            {% if score >= 80 %}1.0
            {% elif score >= 60 %}0.7
            {% elif score >= 40 %}0.5
            {% else %}0.3{% endif %}

script:
  adjust_exercise_plan:
    sequence:
      - choose:
          # Normal exercise conditions
          - conditions:
              - condition: template
                value_template: "{{ modifications == 'normal_exercise' }}"
            sequence:
              - service: notify.mobile_app_phone
                data:
                  title: "🌟 Perfect Exercise Weather"
                  message: "Normal exercise intensity recommended. Enjoy your walk!"
          
          # Reduced intensity
          - conditions:
              - condition: template
                value_template: "{{ modifications == 'reduced_intensity' }}"
            sequence:
              - service: notify.mobile_app_phone
                data:
                  title: "⚠️ Reduce Exercise Intensity"
                  message: >
                    Weather requires modified exercise:
                    • Shorter walks (15-30 min max)
                    • More rest breaks
                    • Monitor for stress signs
                    • Bring extra water
          
          # Short walks only
          - conditions:
              - condition: template
                value_template: "{{ modifications == 'short_walks_only' }}"
            sequence:
              - service: notify.mobile_app_phone
                data:
                  title: "🚶 Short Walks Only"
                  message: >
                    Weather conditions require:
                    • Maximum 15-minute walks
                    • Essential bathroom breaks only
                    • Stay in shaded areas
                    • Watch for distress signals
          
          # Indoor only
          - conditions:
              - condition: template
                value_template: "{{ modifications == 'indoor_only' }}"
            sequence:
              - service: notify.mobile_app_phone
                data:
                  title: "🏠 Indoor Activities Only"
                  message: >
                    Weather too dangerous for outdoor exercise:
                    • Indoor play and training
                    • Mental stimulation games
                    • Wait for conditions to improve
                    • Emergency potty breaks only (with protection)
```

## Breed-Specific Automations

### 6. Brachycephalic Breed Heat Protection

```yaml
automation:
  - alias: "🐶 Brachycephalic Heat Protection (Bulldog)"
    description: "Enhanced heat protection for flat-faced breeds"
    trigger:
      - platform: numeric_state
        entity_id: sensor.temperature
        above: 23  # Lower threshold for brachycephalic breeds
    condition:
      - condition: template
        value_template: >
          {{ state_attr('device_tracker.buddy_profile', 'breed').lower() in 
             ['bulldog', 'french bulldog', 'pug', 'boston terrier', 'pekingese', 'shih tzu'] }}
    action:
      # Immediate heat stress prevention
      - service: notify.mobile_app_phone
        data:
          title: "🔥 BRACHYCEPHALIC HEAT ALERT"
          message: >
            ⚠️ Temperature: {{ states('sensor.temperature') }}°C
            🐶 Buddy's flat face makes him vulnerable to heat stress
            
            IMMEDIATE ACTIONS NEEDED:
            • Cancel any planned walks
            • Ensure air conditioning is on
            • Provide cool water
            • Watch for heavy panting/distress
          data:
            priority: high
            color: red
            actions:
              - action: "EMERGENCY_COOL_DOWN"
                title: "Emergency Protocol"
              - action: "CALL_VET"
                title: "Call Vet"
      
      # Disable walk automations
      - service: automation.turn_off
        target:
          entity_id: automation.optimal_walk_time_alert
      
      # Enable cooling measures
      - service: climate.set_temperature
        target:
          entity_id: climate.main_ac
        data:
          temperature: 22
      
      # Schedule re-evaluation
      - delay: "02:00:00"
      - service: automation.turn_on
        target:
          entity_id: automation.optimal_walk_time_alert
```

### 7. Small Breed Cold Protection

```yaml
automation:
  - alias: "🧥 Small Breed Cold Protection"
    description: "Cold weather protection for small breeds"
    trigger:
      - platform: numeric_state
        entity_id: sensor.temperature
        below: 10
    condition:
      - condition: template
        value_template: >
          {{ state_attr('device_tracker.buddy_profile', 'size') == 'small' or
             state_attr('device_tracker.buddy_profile', 'weight_kg') < 10 }}
    action:
      - service: notify.mobile_app_phone
        data:
          title: "🥶 Small Dog Cold Weather Alert"
          message: >
            🌡️ Temperature: {{ states('sensor.temperature') }}°C
            🐕 Small dogs lose body heat quickly
            
            PROTECTION MEASURES:
            • Use dog coat/sweater for walks
            • Protect paws with booties
            • Limit outdoor time to <15 minutes
            • Warm up indoors between potty breaks
            • Watch for shivering
          data:
            actions:
              - action: "COLD_WEATHER_GEAR"
                title: "Gear Checklist"
              - action: "SHORT_WALK_MODE"
                title: "Enable Short Walk Mode"

script:
  enable_cold_weather_mode:
    sequence:
      # Modify walk duration limits
      - service: input_number.set_value
        target:
          entity_id: input_number.buddy_max_walk_duration
        data:
          value: 15  # Maximum 15 minutes
      
      # Enable cold weather notifications
      - service: switch.turn_on
        target:
          entity_id: switch.buddy_cold_weather_alerts
      
      # Set temperature monitoring
      - service: automation.trigger
        target:
          entity_id: automation.monitor_dog_for_cold_stress
```

### 8. Thick-Coat Breed Summer Management

```yaml
automation:
  - alias: "☀️ Thick Coat Summer Management"
    description: "Summer heat management for thick-coated breeds"
    trigger:
      - platform: numeric_state
        entity_id: sensor.temperature
        above: 20
      - platform: numeric_state
        entity_id: sensor.humidity
        above: 60
    condition:
      - condition: template
        value_template: >
          {{ state_attr('device_tracker.buddy_profile', 'breed').lower() in 
             ['golden retriever', 'german shepherd', 'husky', 'malamute', 'chow chow', 'newfoundland'] }}
    action:
      # Check combined heat index
      - service: pawcontrol.calculate_weather_health_score
        data:
          dog_id: "buddy"
          breed_specific: true
        response_variable: heat_analysis
      
      # Thick coat specific recommendations
      - service: notify.mobile_app_phone
        data:
          title: "🌡️ Thick Coat Heat Management"
          message: >
            Temperature: {{ states('sensor.temperature') }}°C
            Humidity: {{ states('sensor.humidity') }}%
            
            THICK COAT CONSIDERATIONS:
            • Early morning walks (before 8 AM)
            • Evening walks (after 7 PM)
            • Cooling mats recommended
            • Consider professional grooming
            • Extra water during activities
            • Watch for excessive panting
          data:
            actions:
              - action: "SCHEDULE_GROOMING"
                title: "Schedule Grooming"
              - action: "COOLING_PRODUCTS"
                title: "Cooling Products"
      
      # Adjust walk schedule for thick-coated breeds
      - service: automation.trigger
        target:
          entity_id: automation.adjust_walk_schedule_for_heat
        data:
          variables:
            heat_modifier: 1.5  # More conservative for thick coats
```

## Health Condition Considerations

### 9. Respiratory Condition Weather Monitoring

```yaml
automation:
  - alias: "💨 Respiratory Condition Weather Monitor"
    description: "Monitor weather impact on dogs with respiratory conditions"
    trigger:
      - platform: numeric_state
        entity_id: sensor.humidity
        above: 70
      - platform: state
        entity_id: weather.home
        to: 
          - "fog"
          - "hazy"
    condition:
      - condition: template
        value_template: >
          {{ 'respiratory' in state_attr('device_tracker.buddy_profile', 'health_conditions') or
             'asthma' in state_attr('device_tracker.buddy_profile', 'health_conditions') or
             'brachycephalic' in state_attr('device_tracker.buddy_profile', 'breed').lower() }}
    action:
      - service: notify.mobile_app_phone
        data:
          title: "💨 Respiratory Health Alert"
          message: >
            ⚠️ Weather conditions may affect breathing:
            
            🌡️ Temperature: {{ states('sensor.temperature') }}°C
            💧 Humidity: {{ states('sensor.humidity') }}%
            🌫️ Conditions: {{ states('weather.home') }}
            
            RESPIRATORY CARE:
            • Reduce exercise intensity
            • Ensure good air circulation indoors
            • Monitor breathing closely
            • Have emergency vet contact ready
            • Consider air purifier
          data:
            priority: high
            actions:
              - action: "BREATHING_PROTOCOL"
                title: "Breathing Protocol"
              - action: "EMERGENCY_VET"
                title: "Emergency Vet"
      
      # Enable enhanced monitoring
      - service: switch.turn_on
        target:
          entity_id: switch.buddy_respiratory_monitoring
      
      # Reduce activity reminders
      - service: automation.turn_off
        target:
          entity_id: automation.normal_activity_reminders
```

### 10. Senior Dog Weather Adaptation

```yaml
automation:
  - alias: "👴 Senior Dog Weather Adaptation"
    description: "Weather considerations for senior dogs"
    trigger:
      - platform: numeric_state
        entity_id: sensor.buddy_weather_health_score
        below: 70
    condition:
      - condition: template
        value_template: >
          {{ (state_attr('device_tracker.buddy_profile', 'age_months') | int) > 84 }}  # 7+ years
    action:
      # Senior-specific weather assessment
      - service: pawcontrol.get_weather_recommendations
        data:
          dog_id: "buddy"
          age_considerations: true
          health_conditions: ["senior", "arthritis"]
        response_variable: senior_recommendations
      
      - service: notify.mobile_app_phone
        data:
          title: "👴 Senior Dog Weather Considerations"
          message: >
            Weather Score: {{ states('sensor.buddy_weather_health_score') }}/100
            
            SENIOR DOG ADJUSTMENTS:
            • Shorter, more frequent outings
            • Avoid temperature extremes
            • Monitor joint stiffness
            • Extra comfort measures needed
            • Consider arthritis pain impact
            
            Recommendations:
            {{ senior_recommendations.recommendations[:3] | join('\n• ') }}
          data:
            actions:
              - action: "SENIOR_CARE_PLAN"
                title: "Senior Care Plan"
              - action: "COMFORT_MEASURES"
                title: "Comfort Measures"

script:
  senior_weather_protocol:
    sequence:
      # Adjust activity thresholds for seniors
      - service: input_number.set_value
        target:
          entity_id: input_number.buddy_weather_threshold
        data:
          value: 75  # Higher threshold for seniors
      
      # Enable joint monitoring
      - service: switch.turn_on
        target:
          entity_id: switch.buddy_arthritis_monitoring
      
      # Reduce walk intensity
      - service: input_select.select_option
        target:
          entity_id: input_select.buddy_exercise_intensity
        data:
          option: "gentle"
```

## Emergency Weather Protocols

### 11. Extreme Heat Emergency Protocol

```yaml
automation:
  - alias: "🚨 Extreme Heat Emergency Protocol"
    description: "Emergency response for dangerous heat conditions"
    trigger:
      - platform: numeric_state
        entity_id: sensor.temperature
        above: 35
      - platform: state
        entity_id: binary_sensor.buddy_heat_stress_alert
        to: "on"
        attribute: severity
        state: "extreme"
    action:
      # Immediate emergency notifications
      - service: notify.mobile_app_phone
        data:
          title: "🚨 EXTREME HEAT EMERGENCY"
          message: >
            🔥 DANGEROUS CONDITIONS - IMMEDIATE ACTION REQUIRED
            
            Temperature: {{ states('sensor.temperature') }}°C
            Heat Index: {{ state_attr('sensor.temperature', 'heat_index') }}°C
            
            ⚠️ IMMEDIATE ACTIONS:
            • Bring dog indoors IMMEDIATELY
            • Provide cool (not cold) water
            • Use cooling mats/wet towels
            • Monitor for heat stroke signs
            • Prepare for emergency vet visit
          data:
            priority: critical
            sound: "emergency"
            color: red
            actions:
              - action: "HEAT_STROKE_PROTOCOL"
                title: "Heat Stroke Protocol"
              - action: "EMERGENCY_VET_NOW"
                title: "Call Vet NOW"
              - action: "COOLING_MEASURES"
                title: "Emergency Cooling"
      
      # Disable all outdoor activities
      - service: automation.turn_off
        target:
          entity_id: 
            - automation.optimal_walk_time_alert
            - automation.walk_reminder
            - automation.outdoor_play_time
      
      # Emergency cooling activation
      - service: climate.set_temperature
        target:
          entity_id: climate.main_ac
        data:
          temperature: 20
      - service: fan.turn_on
        target:
          entity_id: fan.living_room
        data:
          speed: high
      
      # Monitor for recovery
      - repeat:
          until:
            - condition: numeric_state
              entity_id: sensor.temperature
              below: 30
          sequence:
            - delay: "00:30:00"
            - service: notify.mobile_app_phone
              data:
                title: "🌡️ Heat Emergency Update"
                message: >
                  Still monitoring extreme heat conditions.
                  Current: {{ states('sensor.temperature') }}°C
                  Continue emergency precautions.

script:
  heat_stroke_emergency_protocol:
    sequence:
      - service: notify.mobile_app_phone
        data:
          title: "🚨 HEAT STROKE EMERGENCY PROTOCOL"
          message: >
            ⚠️ HEAT STROKE SIGNS TO WATCH FOR:
            • Heavy panting/drooling
            • Vomiting or diarrhea
            • Lethargy/collapse
            • Red/dark gums
            • High body temperature
            
            🚑 EMERGENCY ACTIONS:
            1. Move to cool area immediately
            2. Apply cool (not cold) water to paws/belly
            3. Offer small amounts of cool water
            4. Call emergency vet immediately
            5. Prepare for immediate transport
          data:
            actions:
              - action: "EMERGENCY_VET_CALL"
                title: "Call Emergency Vet"
              - action: "TRANSPORT_READY"
                title: "Prepare Transport"
```

### 12. Severe Storm Safety Protocol

```yaml
automation:
  - alias: "⛈️ Severe Storm Safety Protocol"
    description: "Safety measures during severe weather"
    trigger:
      - platform: state
        entity_id: weather.home
        to:
          - "lightning"
          - "thunderstorm"
          - "severe-thunderstorm"
    condition:
      - condition: state
        entity_id: switch.buddy_weather_monitoring
        state: "on"
    action:
      # Storm safety notification
      - service: notify.mobile_app_phone
        data:
          title: "⛈️ Severe Storm Alert"
          message: >
            🌩️ Severe weather detected - Storm safety protocol activated
            
            IMMEDIATE ACTIONS:
            • Keep dog indoors
            • Secure identification tags
            • Prepare comfort items for anxiety
            • Close curtains/blinds
            • Have emergency supplies ready
            
            Weather: {{ states('weather.home') }}
            Duration: Monitor until storm passes
          data:
            actions:
              - action: "STORM_COMFORT"
                title: "Comfort Measures"
              - action: "EMERGENCY_SUPPLIES"
                title: "Emergency Supplies"
      
      # Comfort measures for storm anxiety
      - if:
          - condition: template
            value_template: >
              {{ 'anxiety' in state_attr('device_tracker.buddy_profile', 'temperament') or
                 'storm_anxiety' in state_attr('device_tracker.buddy_profile', 'health_conditions') }}
        then:
          - service: script.storm_anxiety_protocol
      
      # Monitor storm passage
      - repeat:
          until:
            - condition: not
              conditions:
                - condition: state
                  entity_id: weather.home
                  state:
                    - "lightning"
                    - "thunderstorm"
                    - "severe-thunderstorm"
          sequence:
            - delay: "00:15:00"
            - service: pawcontrol.update_weather_data
              data:
                dog_id: "buddy"
      
      # Storm cleared notification
      - service: notify.mobile_app_phone
        data:
          title: "☀️ Storm Cleared"
          message: "Storm has passed. Normal activities can resume safely."

script:
  storm_anxiety_protocol:
    sequence:
      - service: media_player.play_media
        target:
          entity_id: media_player.living_room
        data:
          media_content_id: "calming_music_for_dogs"
          media_content_type: "playlist"
      
      - service: light.turn_on
        target:
          entity_id: light.living_room
        data:
          brightness: 128
          color_name: "warm_white"
      
      - service: notify.mobile_app_phone
        data:
          title: "🎵 Storm Anxiety Protocol Activated"
          message: >
            Comfort measures activated for storm anxiety:
            • Calming music playing
            • Soft lighting enabled
            • Consider anxiety medication if prescribed
            • Stay close for reassurance
```

## Multi-Dog Weather Management

### 13. Multi-Dog Weather Coordination

```yaml
automation:
  - alias: "🐕‍🦺 Multi-Dog Weather Coordination"
    description: "Coordinate weather care for multiple dogs"
    trigger:
      - platform: time_pattern
        minutes: "/30"  # Check every 30 minutes
    condition:
      - condition: numeric_state
        entity_id: sensor.pawcontrol_total_dogs
        above: 1
    action:
      # Get weather assessment for all dogs
      - service: pawcontrol.calculate_weather_health_score
        data:
          dog_id: "buddy"
        response_variable: buddy_weather
      
      - service: pawcontrol.calculate_weather_health_score
        data:
          dog_id: "luna"
        response_variable: luna_weather
      
      # Determine group activity based on most sensitive dog
      - service: script.coordinate_multi_dog_activities
        data:
          buddy_score: "{{ buddy_weather.score }}"
          luna_score: "{{ luna_weather.score }}"
          
script:
  coordinate_multi_dog_activities:
    sequence:
      - variables:
          lowest_score: >
            {{ [buddy_score | int, luna_score | int] | min }}
          most_sensitive_dog: >
            {% if (buddy_score | int) < (luna_score | int) %}
              Buddy
            {% else %}
              Luna
            {% endif %}
      
      # Base recommendations on most weather-sensitive dog
      - choose:
          - conditions:
              - condition: template
                value_template: "{{ lowest_score | int >= 75 }}"
            sequence:
              - service: notify.mobile_app_phone
                data:
                  title: "🌟 Great Weather for Both Dogs"
                  message: >
                    Weather suitable for all dogs:
                    • Buddy: {{ buddy_score }}/100
                    • Luna: {{ luna_score }}/100
                    
                    Group walks and outdoor activities recommended!
                  data:
                    actions:
                      - action: "GROUP_WALK"
                        title: "Start Group Walk"
          
          - conditions:
              - condition: template
                value_template: "{{ lowest_score | int >= 50 }}"
            sequence:
              - service: notify.mobile_app_phone
                data:
                  title: "⚠️ Modified Activities for Both Dogs"
                  message: >
                    Weather requires modified activities:
                    • Buddy: {{ buddy_score }}/100
                    • Luna: {{ luna_score }}/100
                    • Most sensitive: {{ most_sensitive_dog }}
                    
                    Shorter walks and increased monitoring recommended.
          
          - conditions:
              - condition: template
                value_template: "{{ lowest_score | int < 50 }}"
            sequence:
              - service: notify.mobile_app_phone
                data:
                  title: "🏠 Indoor Activities for All Dogs"
                  message: >
                    Weather unsuitable for outdoor activities:
                    • Buddy: {{ buddy_score }}/100
                    • Luna: {{ luna_score }}/100
                    
                    Keep all dogs indoors with climate control.
                    {{ most_sensitive_dog }} is most vulnerable.
```

### 14. Breed-Specific Multi-Dog Management

```yaml
automation:
  - alias: "🐕 Breed-Specific Multi-Dog Weather Management"
    description: "Handle different breed needs in multi-dog household"
    trigger:
      - platform: state
        entity_id: sensor.temperature
    action:
      # Get breed-specific recommendations for each dog
      - service: pawcontrol.get_weather_recommendations
        data:
          dog_id: "buddy"  # Golden Retriever
          include_breed_specific: true
        response_variable: buddy_recommendations
      
      - service: pawcontrol.get_weather_recommendations
        data:
          dog_id: "luna"   # Chihuahua
          include_breed_specific: true
        response_variable: luna_recommendations
      
      # Handle different breed requirements
      - service: script.manage_breed_differences
        data:
          temperature: "{{ states('sensor.temperature') | float }}"
          buddy_needs: "{{ buddy_recommendations.breed_specific }}"
          luna_needs: "{{ luna_recommendations.breed_specific }}"

script:
  manage_breed_differences:
    sequence:
      - choose:
          # Cold weather - Chihuahua needs more protection
          - conditions:
              - condition: template
                value_template: "{{ temperature < 15 }}"
            sequence:
              - service: notify.mobile_app_phone
                data:
                  title: "🥶 Cold Weather - Breed Considerations"
                  message: >
                    Temperature: {{ temperature }}°C
                    
                    🐕 Buddy (Golden Retriever):
                    • Can handle cold well
                    • Normal walk duration OK
                    • Monitor paws for ice
                    
                    🐾 Luna (Chihuahua):
                    • Needs warm coat/sweater
                    • Maximum 10-minute walks
                    • Carry for longer distances
                    • Watch for shivering
                    
                    PLAN: Separate walk schedules recommended
                  data:
                    actions:
                      - action: "SEPARATE_WALKS"
                        title: "Plan Separate Walks"
                      - action: "COLD_GEAR_CHECK"
                        title: "Check Cold Gear"
          
          # Hot weather - Golden Retriever needs more care
          - conditions:
              - condition: template
                value_template: "{{ temperature > 25 }}"
            sequence:
              - service: notify.mobile_app_phone
                data:
                  title: "🔥 Hot Weather - Breed Considerations"
                  message: >
                    Temperature: {{ temperature }}°C
                    
                    🐕 Buddy (Golden Retriever):
                    • Thick coat = heat sensitive
                    • Early morning/late evening only
                    • Extra water and cooling needed
                    • Consider grooming
                    
                    🐾 Luna (Chihuahua):
                    • Better heat tolerance
                    • Still needs protection
                    • Shorter legs = closer to hot ground
                    
                    PLAN: Very early/late walks only for both
                  data:
                    actions:
                      - action: "EARLY_WALK_SCHEDULE"
                        title: "Schedule Early Walks"
                      - action: "COOLING_SETUP"
                        title: "Setup Cooling"
```

## Integration with Smart Home

### 15. Climate Control Integration

```yaml
automation:
  - alias: "🌡️ Smart Climate Control for Dog Comfort"
    description: "Automatically adjust home climate based on weather and dog needs"
    trigger:
      - platform: state
        entity_id: sensor.buddy_weather_health_score
    action:
      # Determine climate needs based on weather score
      - choose:
          # Weather score low - comfort measures needed
          - conditions:
              - condition: numeric_state
                entity_id: sensor.buddy_weather_health_score
                below: 50
            sequence:
              # Hot weather comfort
              - if:
                  - condition: numeric_state
                    entity_id: sensor.temperature
                    above: 25
                then:
                  - service: climate.set_temperature
                    target:
                      entity_id: climate.main_ac
                    data:
                      temperature: 22
                  - service: fan.turn_on
                    target:
                      entity_id: fan.all_rooms
                    data:
                      speed: medium
                  - service: switch.turn_on
                    target:
                      entity_id: switch.cooling_mats
              
              # Cold weather comfort
              - if:
                  - condition: numeric_state
                    entity_id: sensor.temperature
                    below: 10
                then:
                  - service: climate.set_temperature
                    target:
                      entity_id: climate.main_heating
                    data:
                      temperature: 21
                  - service: switch.turn_on
                    target:
                      entity_id: switch.heated_dog_beds
      
      # Notify about automatic adjustments
      - service: notify.mobile_app_phone
        data:
          title: "🏠 Climate Auto-Adjusted"
          message: >
            Weather Score: {{ states('sensor.buddy_weather_health_score') }}/100
            
            Automatic climate adjustments made for Buddy's comfort:
            {% if states('sensor.temperature') | float > 25 %}
            • AC set to 22°C
            • Fans activated
            • Cooling mats enabled
            {% elif states('sensor.temperature') | float < 10 %}
            • Heating set to 21°C
            • Heated dog beds activated
            {% endif %}
```

### 16. Automated Water Management

```yaml
automation:
  - alias: "💧 Smart Water Management System"
    description: "Ensure adequate water based on weather conditions"
    trigger:
      - platform: numeric_state
        entity_id: sensor.temperature
        above: 22
      - platform: numeric_state
        entity_id: sensor.humidity
        above: 70
    action:
      # Calculate increased water needs
      - service: script.calculate_water_needs
        data:
          temperature: "{{ states('sensor.temperature') | float }}"
          humidity: "{{ states('sensor.humidity') | float }}"
          dog_weight: "{{ state_attr('device_tracker.buddy_profile', 'weight_kg') }}"
        response_variable: water_calculation
      
      # Water system management
      - service: switch.turn_on
        target:
          entity_id: switch.automatic_water_dispensers
      
      - service: notify.mobile_app_phone
        data:
          title: "💧 Increased Water Needs"
          message: >
            🌡️ Temperature: {{ states('sensor.temperature') }}°C
            💨 Humidity: {{ states('sensor.humidity') }}%
            
            💧 WATER MANAGEMENT:
            • Automatic dispensers activated
            • Check water levels more frequently
            • Add ice cubes for cooling
            • Monitor water consumption
            • Consider electrolyte supplements
            
            Recommended daily water: {{ water_calculation.daily_ml }}ml
            ({{ water_calculation.increase_percentage }}% increase from normal)

script:
  calculate_water_needs:
    sequence:
      - variables:
          base_water_ml: "{{ (dog_weight | float * 50) | round(0) }}"  # 50ml per kg base
          temp_multiplier: >
            {% set temp = temperature | float %}
            {% if temp > 30 %}1.5
            {% elif temp > 25 %}1.3
            {% elif temp > 22 %}1.2
            {% else %}1.0{% endif %}
          humidity_multiplier: >
            {% set hum = humidity | float %}
            {% if hum > 80 %}1.2
            {% elif hum > 70 %}1.1
            {% else %}1.0{% endif %}
          total_multiplier: "{{ (temp_multiplier | float) * (humidity_multiplier | float) }}"
          daily_ml: "{{ (base_water_ml | float * total_multiplier | float) | round(0) }}"
          increase_percentage: "{{ ((total_multiplier | float - 1) * 100) | round(0) }}"
      
      - service: system_log.write
        data:
          message: >
            Water calculation: Base {{ base_water_ml }}ml, 
            Multiplier {{ total_multiplier }}, 
            Total {{ daily_ml }}ml
          level: info
```

## Dashboard and Notifications

### 17. Comprehensive Weather Dashboard

```yaml
# Dashboard configuration for weather monitoring
# Add to your dashboard YAML or use via UI

type: vertical-stack
cards:
  # Weather Health Overview
  - type: custom:mushroom-entity-card
    entity: sensor.buddy_weather_health_score
    name: Weather Safety Score
    icon: mdi:weather-partly-cloudy
    icon_color: >
      {% set score = states('sensor.buddy_weather_health_score') | int(0) %}
      {% if score >= 80 %}green
      {% elif score >= 60 %}yellow
      {% elif score >= 40 %}orange
      {% else %}red{% endif %}
    primary_info: state
    secondary_info: >
      {% set score = states('sensor.buddy_weather_health_score') | int(0) %}
      {% if score >= 80 %}Excellent Conditions
      {% elif score >= 60 %}Good Conditions
      {% elif score >= 40 %}Caution Needed
      {% else %}Dangerous Conditions{% endif %}
  
  # Active Weather Alerts
  - type: conditional
    conditions:
      - entity: binary_sensor.buddy_weather_alerts_active
        state: "on"
    card:
      type: custom:mushroom-chips-card
      chips:
        - type: entity
          entity: binary_sensor.buddy_heat_stress_alert
          icon: mdi:thermometer-high
          icon_color: red
          content_info: none
        - type: entity
          entity: binary_sensor.buddy_cold_stress_alert
          icon: mdi:snowflake
          icon_color: blue
          content_info: none
        - type: entity
          entity: binary_sensor.buddy_uv_exposure_alert
          icon: mdi:white-balance-sunny
          icon_color: orange
          content_info: none
        - type: entity
          entity: binary_sensor.buddy_storm_warning
          icon: mdi:weather-lightning
          icon_color: purple
          content_info: none
  
  # Weather Details
  - type: entities
    title: Current Weather Impact
    entities:
      - entity: sensor.buddy_temperature_impact
        name: Temperature Impact
        icon: mdi:thermometer
      - entity: sensor.buddy_humidity_impact  
        name: Humidity Impact
        icon: mdi:water-percent
      - entity: sensor.buddy_uv_exposure_level
        name: UV Exposure Level
        icon: mdi:weather-sunny
      - entity: sensor.buddy_weather_recommendations
        name: Current Recommendations
        icon: mdi:lightbulb-on
  
  # Quick Actions
  - type: custom:mushroom-chips-card
    chips:
      - type: action
        icon: mdi:weather-cloudy-clock
        tap_action:
          action: call-service
          service: pawcontrol.update_weather_data
          data:
            dog_id: buddy
      - type: action
        icon: mdi:lightbulb
        tap_action:
          action: call-service
          service: pawcontrol.get_weather_recommendations
          data:
            dog_id: buddy
            include_breed_specific: true
      - type: action
        icon: mdi:walk
        tap_action:
          action: call-service
          service: pawcontrol.gps_start_walk
          data:
            dog_id: buddy
            weather_check: true
```

### 18. Advanced Weather Notification System

```yaml
automation:
  - alias: "📱 Advanced Weather Notification Manager"
    description: "Comprehensive weather notification system"
    trigger:
      - platform: state
        entity_id: sensor.buddy_weather_health_score
      - platform: state
        entity_id: binary_sensor.buddy_heat_stress_alert
        to: "on"
      - platform: state
        entity_id: binary_sensor.buddy_cold_stress_alert
        to: "on"
      - platform: state
        entity_id: binary_sensor.buddy_uv_exposure_alert
        to: "on"
    action:
      # Determine notification priority and content
      - service: script.process_weather_notification
        data:
          trigger_entity: "{{ trigger.entity_id }}"
          old_state: "{{ trigger.from_state.state if trigger.from_state else 'unknown' }}"
          new_state: "{{ trigger.to_state.state if trigger.to_state else 'unknown' }}"

script:
  process_weather_notification:
    sequence:
      - variables:
          weather_score: "{{ states('sensor.buddy_weather_health_score') | int(0) }}"
          active_alerts: >
            {% set alerts = [] %}
            {% if is_state('binary_sensor.buddy_heat_stress_alert', 'on') %}
              {% set alerts = alerts + ['heat_stress'] %}
            {% endif %}
            {% if is_state('binary_sensor.buddy_cold_stress_alert', 'on') %}
              {% set alerts = alerts + ['cold_stress'] %}
            {% endif %}
            {% if is_state('binary_sensor.buddy_uv_exposure_alert', 'on') %}
              {% set alerts = alerts + ['uv_exposure'] %}
            {% endif %}
            {% if is_state('binary_sensor.buddy_storm_warning', 'on') %}
              {% set alerts = alerts + ['storm_warning'] %}
            {% endif %}
            {{ alerts }}
          priority_level: >
            {% if weather_score < 30 %}critical
            {% elif weather_score < 50 %}high
            {% elif weather_score < 70 %}normal
            {% else %}low{% endif %}
      
      # Send appropriate notification based on conditions
      - choose:
          # Critical weather conditions
          - conditions:
              - condition: template
                value_template: "{{ priority_level == 'critical' }}"
            sequence:
              - service: notify.mobile_app_phone
                data:
                  title: "🚨 CRITICAL WEATHER ALERT"
                  message: >
                    ⚠️ DANGEROUS CONDITIONS FOR BUDDY
                    
                    Weather Score: {{ weather_score }}/100
                    Active Alerts: {{ active_alerts | join(', ') }}
                    
                    🚑 IMMEDIATE ACTION REQUIRED:
                    {% for alert in active_alerts %}
                    {% if alert == 'heat_stress' %}
                    • HEAT: Bring indoors immediately, cool water, A/C
                    {% elif alert == 'cold_stress' %}
                    • COLD: Warm shelter, protective clothing, limit exposure
                    {% elif alert == 'uv_exposure' %}
                    • UV: Avoid sun, provide shade, protect exposed skin
                    {% elif alert == 'storm_warning' %}
                    • STORM: Keep indoors, comfort measures, secure ID
                    {% endif %}
                    {% endfor %}
                  data:
                    priority: high
                    sound: "emergency"
                    color: red
                    actions:
                      - action: "EMERGENCY_PROTOCOL"
                        title: "Emergency Protocol"
                      - action: "CALL_VET"
                        title: "Call Vet"
          
          # High priority conditions
          - conditions:
              - condition: template
                value_template: "{{ priority_level == 'high' }}"
            sequence:
              - service: notify.mobile_app_phone
                data:
                  title: "⚠️ High Weather Alert"
                  message: >
                    Weather Score: {{ weather_score }}/100
                    
                    ⚠️ PRECAUTIONS NEEDED:
                    {% for alert in active_alerts %}
                    {% if alert == 'heat_stress' %}
                    • Heat stress risk - limit outdoor time
                    {% elif alert == 'cold_stress' %}
                    • Cold stress risk - use protective gear
                    {% elif alert == 'uv_exposure' %}
                    • UV exposure risk - provide shade/protection
                    {% endif %}
                    {% endfor %}
                    
                    Monitor Buddy closely and adjust activities.
                  data:
                    priority: normal
                    color: orange
                    actions:
                      - action: "VIEW_RECOMMENDATIONS"
                        title: "Get Recommendations"
                      - action: "ADJUST_ACTIVITIES"
                        title: "Adjust Activities"
          
          # Normal monitoring notifications
          - conditions:
              - condition: template
                value_template: "{{ priority_level == 'normal' }}"
            sequence:
              - service: notify.mobile_app_phone
                data:
                  title: "🌤️ Weather Update"
                  message: >
                    Weather Score: {{ weather_score }}/100
                    
                    {% if active_alerts | length > 0 %}
                    Active considerations: {{ active_alerts | join(', ') }}
                    Moderate precautions recommended.
                    {% else %}
                    Weather conditions are manageable with basic precautions.
                    {% endif %}
                  data:
                    actions:
                      - action: "GET_RECOMMENDATIONS"
                        title: "Get Recommendations"
```

## Conclusion

These weather integration examples demonstrate the sophisticated capabilities of PawControl's weather health monitoring system. The automations provide:

### Key Benefits:

1. **🎯 Proactive Health Protection**: Prevent weather-related health issues before they occur
2. **🐕 Breed-Specific Intelligence**: Tailored recommendations for different breed characteristics
3. **🏥 Health Condition Awareness**: Special considerations for dogs with medical conditions
4. **🚨 Emergency Protocols**: Immediate response to dangerous weather conditions
5. **🏠 Smart Home Integration**: Automated climate and environmental control
6. **👥 Multi-Dog Management**: Coordinated care for households with multiple dogs

### Implementation Tips:

- **Start Simple**: Begin with basic weather monitoring, then add advanced features
- **Customize Thresholds**: Adjust temperature and alert thresholds for your specific dog's needs
- **Test Notifications**: Verify notification delivery and action buttons work correctly
- **Monitor Performance**: Check that automations don't conflict or create notification spam
- **Regular Updates**: Review and adjust automations seasonally

### Advanced Features Showcased:

- **Real-time Weather Health Scoring** (0-100 scale)
- **Breed-specific weather intelligence** for 50+ breeds
- **Multi-level alert system** with 6 different alert types
- **Emergency weather protocols** with immediate response
- **Predictive walk scheduling** based on weather forecast
- **Smart home climate integration** for automatic comfort
- **Multi-dog coordination** for households with different breeds

These examples provide a comprehensive foundation for implementing weather-aware dog care in your smart home, ensuring your four-legged family members stay safe and comfortable in all weather conditions.

---

**Remember**: Always prioritize your dog's immediate safety. These automations supplement but don't replace careful observation and professional veterinary care when needed.

**Weather Integration Version**: 1.0.0 | **Last Updated**: 2025-01-20 | **Quality**: 🏆 Platinum+
