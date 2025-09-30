# 🌤️ PawControl Weather Integration Guide

## Overview

PawControl's advanced weather integration provides comprehensive health monitoring for dogs based on real-time weather conditions. This guide demonstrates practical automation examples using the sophisticated weather health system.

**Quality Scale:** Platinum+ | **Enterprise Ready** | **Production Validated**

### Key Features

- **🎯 0-100 Health Scoring**: Real-time weather safety assessment
- **🐕 Breed-Specific Intelligence**: Customized recommendations for 50+ breeds
- **⚠️ Multi-Level Alert System**: 6 types of weather-based health alerts
- **🏥 Health Condition Integration**: Special considerations for medical conditions
- **🌍 Multi-Language Support**: Complete English and German translations
- **🔄 Automated Responses**: Smart automation triggers and actions

## Weather Health System Architecture

### Core Components

```yaml
# Weather Health Entities (per dog)
sensor.{dog_id}_weather_health_score     # 0-100 safety score
sensor.{dog_id}_temperature_impact       # Temperature health impact
sensor.{dog_id}_uv_exposure_level       # UV exposure risk level
sensor.{dog_id}_active_weather_alerts   # Number of active alerts
sensor.{dog_id}_weather_recommendations # Current weather advice

# Weather Safety Binary Sensors
binary_sensor.{dog_id}_weather_safe        # Overall weather safety
binary_sensor.{dog_id}_heat_stress_alert   # Heat stress warning
binary_sensor.{dog_id}_cold_stress_alert   # Cold stress warning  
binary_sensor.{dog_id}_uv_exposure_alert   # UV protection needed
binary_sensor.{dog_id}_storm_warning       # Storm safety alert
binary_sensor.{dog_id}_paw_protection_needed # Paw protection required
```

### Weather Services

```yaml
# Core Weather Services
pawcontrol.update_weather_data          # Update weather health data
pawcontrol.get_weather_recommendations  # Get personalized recommendations
pawcontrol.calculate_weather_health_score # Calculate safety score
pawcontrol.weather_alert_actions        # Manage weather alerts
```

## Comprehensive Automation Examples

### 1. Intelligent Walk Planning System

**Basic Weather-Aware Walk Scheduling:**

```yaml
automation:
  - alias: "Smart Walk Planning - Perfect Weather"
    id: pawcontrol_smart_walk_perfect
    trigger:
      - platform: numeric_state
        entity_id: sensor.buddy_weather_health_score
        above: 80
        for: "00:15:00"
    condition:
      - condition: numeric_state
        entity_id: sensor.buddy_last_walk_hours
        above: 4
      - condition: time
        after: "06:00:00"
        before: "20:00:00"
      - condition: state
        entity_id: person.owner
        state: "home"
    action:
      - service: notify.mobile_app_phone
        data:
          title: "🌤️ Perfect Walk Weather!"
          message: >
            Weather Score: {{ states('sensor.buddy_weather_health_score') }}/100
            Temperature: {{ states('sensor.temperature') }}°C
            Conditions: {{ states('weather.home') }}
            Last Walk: {{ states('sensor.buddy_last_walk_hours') }}h ago
          data:
            priority: normal
            color: green
            actions:
              - action: "START_WALK"
                title: "🚶 Start Walk"
              - action: "WEATHER_DETAILS"
                title: "📊 Weather Details"
              - action: "REMIND_LATER"
                title: "⏰ Remind in 1h"

  - alias: "Handle Walk Start from Notification"
    id: pawcontrol_walk_start_notification
    trigger:
      - platform: event
        event_type: mobile_app_notification_action
        event_data:
          action: "START_WALK"
    action:
      - service: pawcontrol.gps_start_walk
        data:
          dog_id: "buddy"
          label: "Weather-optimized walk"
          route_recording: true
          weather_check: true
      - service: notify.mobile_app_phone
        data:
          title: "🚶 Walk Started"
          message: "GPS tracking active. Have a great walk with Buddy!"
          data:
            tag: "walk_notification"
```

**Advanced Weather Condition Walk Planning:**

```yaml
automation:
  - alias: "Weather-Conditional Walk Recommendations"
    id: pawcontrol_weather_conditional_walks
    trigger:
      - platform: time_pattern
        hours: "/2"  # Check every 2 hours
      - platform: state
        entity_id: weather.home
    condition:
      - condition: numeric_state
        entity_id: sensor.buddy_last_walk_hours
        above: 3
    action:
      - choose:
          # Perfect conditions (Score 80+)
          - conditions:
              - condition: numeric_state
                entity_id: sensor.buddy_weather_health_score
                above: 80
            sequence:
              - service: script.recommend_long_walk
                data:
                  dog_id: "buddy"
                  message: "Perfect conditions for extended outdoor time!"
          
          # Good conditions (Score 60-79)
          - conditions:
              - condition: numeric_state
                entity_id: sensor.buddy_weather_health_score
                above: 60
                below: 80
            sequence:
              - service: script.recommend_normal_walk
                data:
                  dog_id: "buddy"
                  message: "Good weather for a regular walk with minor precautions."
          
          # Moderate concerns (Score 40-59)
          - conditions:
              - condition: numeric_state
                entity_id: sensor.buddy_weather_health_score
                above: 40
                below: 60
            sequence:
              - service: script.recommend_short_walk
                data:
                  dog_id: "buddy"
                  message: "Weather requires caution - consider a shorter walk."
          
          # Poor conditions (Score <40)
          - conditions:
              - condition: numeric_state
                entity_id: sensor.buddy_weather_health_score
                below: 40
            sequence:
              - service: script.recommend_indoor_activity
                data:
                  dog_id: "buddy"
                  message: "Weather conditions not suitable for outdoor activities."

script:
  recommend_long_walk:
    sequence:
      - service: notify.mobile_app_phone
        data:
          title: "🌟 Extended Walk Weather"
          message: "{{ message }} Great time for a long adventure!"
          data:
            actions:
              - action: "START_LONG_WALK"
                title: "🚶‍♂️ Long Walk (60+ min)"
              - action: "START_NORMAL_WALK"  
                title: "🚶 Normal Walk (30 min)"

  recommend_normal_walk:
    sequence:
      - service: pawcontrol.get_weather_recommendations
        data:
          dog_id: "{{ dog_id }}"
          include_breed_specific: true
        response_variable: weather_advice
      - service: notify.mobile_app_phone
        data:
          title: "🚶 Walk Time"
          message: >
            {{ message }}
            💡 Tip: {{ weather_advice.recommendations[0] }}
          data:
            actions:
              - action: "START_WALK"
                title: "🚶 Start Walk"
              - action: "VIEW_TIPS"
                title: "💡 Weather Tips"

  recommend_short_walk:
    sequence:
      - service: notify.mobile_app_phone
        data:
          title: "⚠️ Cautious Walk Weather"
          message: >
            {{ message }}
            Active Alerts: {{ states('sensor.buddy_active_weather_alerts') }}
          data:
            priority: high
            color: orange
            actions:
              - action: "SHORT_WALK"
                title: "🚶 Quick Walk (15 min)"
              - action: "WEATHER_ALERTS"
                title: "⚠️ View Alerts"

  recommend_indoor_activity:
    sequence:
      - service: notify.mobile_app_phone
        data:
          title: "🏠 Indoor Activity Time"
          message: >
            {{ message }}
            Consider indoor exercises like training or puzzle toys.
          data:
            priority: high
            color: red
            actions:
              - action: "INDOOR_ACTIVITIES"
                title: "🧩 Indoor Ideas"
              - action: "CHECK_FORECAST"
                title: "🔮 Check Forecast"
```

### 2. Heat Stress Protection System

**Comprehensive Heat Alert Management:**

```yaml
automation:
  - alias: "Heat Stress Alert - Multi-Level Response"
    id: pawcontrol_heat_stress_protection
    trigger:
      - platform: state
        entity_id: binary_sensor.buddy_heat_stress_alert
        to: "on"
    action:
      - service: pawcontrol.get_weather_recommendations
        data:
          dog_id: "buddy"
          include_breed_specific: true
          include_health_conditions: true
        response_variable: heat_recommendations
      
      - variables:
          temp_current: "{{ states('sensor.temperature') | float }}"
          feels_like: "{{ state_attr('weather.home', 'temperature') | float }}"
          heat_index: "{{ states('sensor.buddy_temperature_impact') }}"
          severity: >
            {% if temp_current >= 35 %}extreme
            {% elif temp_current >= 30 %}high
            {% else %}moderate{% endif %}

      - choose:
          # Extreme heat (35°C+)
          - conditions:
              - condition: template
                value_template: "{{ temp_current >= 35 }}"
            sequence:
              - service: notify.mobile_app_phone
                data:
                  title: "🚨 EXTREME HEAT ALERT"
                  message: >
                    🌡️ {{ temp_current }}°C (feels like {{ feels_like }}°C)
                    ⚠️ DANGER: Keep Buddy indoors immediately!
                    💡 {{ heat_recommendations.recommendations[0] }}
                  data:
                    priority: high
                    color: red
                    tag: "heat_emergency"
                    actions:
                      - action: "EMERGENCY_COOLING"
                        title: "❄️ Emergency Cooling"
                      - action: "VET_HOTLINE"
                        title: "🏥 Vet Hotline"
              
              # Activate emergency cooling
              - service: climate.set_temperature
                data:
                  entity_id: climate.living_room
                  temperature: 20
              - service: switch.turn_on
                entity_id: switch.ceiling_fans
              - service: switch.turn_on
                entity_id: switch.air_purifier
              
              # Disable walk automations
              - service: automation.turn_off
                entity_id: 
                  - automation.buddy_walk_reminders
                  - automation.automatic_walk_detection
              
              # Schedule re-enabling after temperature drops
              - delay: "06:00:00"
              - wait_template: "{{ states('sensor.temperature') | float < 30 }}"
                timeout: "12:00:00"
              - service: automation.turn_on
                entity_id:
                  - automation.buddy_walk_reminders
                  - automation.automatic_walk_detection

          # High heat (30-34°C)  
          - conditions:
              - condition: template
                value_template: "{{ temp_current >= 30 and temp_current < 35 }}"
            sequence:
              - service: notify.mobile_app_phone
                data:
                  title: "🔥 High Heat Warning"
                  message: >
                    🌡️ {{ temp_current }}°C - Too hot for walks
                    ⏰ Wait until evening (after 6 PM)
                    💧 Ensure fresh water is available
                  data:
                    priority: high
                    color: orange
                    actions:
                      - action: "COOLING_TIPS"
                        title: "❄️ Cooling Tips"
                      - action: "SET_EVENING_REMINDER"
                        title: "⏰ Evening Walk Reminder"
              
              # Postpone walks until evening
              - service: input_datetime.set_datetime
                data:
                  entity_id: input_datetime.buddy_next_walk_reminder
                  datetime: "{{ today_at('18:00') }}"

          # Moderate heat (25-29°C)
          - conditions:
              - condition: template
                value_template: "{{ temp_current >= 25 and temp_current < 30 }}"
            sequence:
              - service: notify.mobile_app_phone
                data:
                  title: "☀️ Heat Caution"
                  message: >
                    🌡️ {{ temp_current }}°C - Use caution for walks
                    🕘 Best times: Before 10 AM or after 6 PM
                    💧 Bring extra water and seek shade
                  data:
                    actions:
                      - action: "EARLY_WALK"
                        title: "🌅 Early Walk"
                      - action: "EVENING_WALK" 
                        title: "🌇 Evening Walk"
```

**Heat Stress Monitoring with Breed Considerations:**

```yaml
automation:
  - alias: "Breed-Specific Heat Monitoring"
    id: pawcontrol_breed_heat_monitoring
    trigger:
      - platform: numeric_state
        entity_id: sensor.temperature
        above: 25
    condition:
      - condition: template
        value_template: >
          {{ states('sensor.buddy_weather_health_score') | int < 70 }}
    action:
      - service: pawcontrol.get_weather_recommendations
        data:
          dog_id: "buddy"
          include_breed_specific: true
        response_variable: breed_advice
      
      - variables:
          dog_breed: "{{ state_attr('sensor.buddy_profile', 'breed') }}"
          is_brachycephalic: >
            {{ dog_breed.lower() in ['bulldog', 'pug', 'boston terrier', 
                                     'french bulldog', 'pekingese', 'boxer'] }}
          is_thick_coat: >
            {{ dog_breed.lower() in ['golden retriever', 'husky', 'german shepherd',
                                     'saint bernard', 'bernese mountain dog'] }}
          is_small_breed: >
            {{ dog_breed.lower() in ['chihuahua', 'yorkshire terrier', 'pomeranian',
                                     'maltese', 'papillon'] }}

      - choose:
          # Brachycephalic breeds (breathing difficulties)
          - conditions:
              - condition: template
                value_template: "{{ is_brachycephalic }}"
            sequence:
              - service: notify.mobile_app_phone
                data:
                  title: "🫁 Breathing Alert - {{ dog_breed }}"
                  message: >
                    {{ dog_breed }}s are prone to breathing difficulties in heat.
                    🌡️ Current: {{ states('sensor.temperature') }}°C
                    ⚠️ Watch for: Heavy panting, drooling, lethargy
                    💡 {{ breed_advice.recommendations[0] }}
                  data:
                    priority: high
                    actions:
                      - action: "MONITOR_BREATHING"
                        title: "👁️ Monitor Breathing"
                      - action: "EMERGENCY_COOLING"
                        title: "❄️ Cool Down Now"

          # Thick coat breeds (heat retention)
          - conditions:
              - condition: template
                value_template: "{{ is_thick_coat }}"
            sequence:
              - service: notify.mobile_app_phone
                data:
                  title: "🐕 Thick Coat Alert - {{ dog_breed }}"
                  message: >
                    {{ dog_breed }}s retain heat due to thick coats.
                    💡 Consider: Cooling mats, shade, shorter walks
                    🕘 Best walk times: Early morning or late evening
                  data:
                    actions:
                      - action: "GROOMING_CHECK"
                        title: "✂️ Check Grooming"
                      - action: "COOLING_PRODUCTS"
                        title: "❄️ Cooling Products"

# Supporting scripts for heat management
script:
  emergency_cooling_protocol:
    sequence:
      - service: notify.mobile_app_phone
        data:
          title: "❄️ Emergency Cooling Protocol"
          message: >
            Immediate actions for heat stress:
            1. Move to air-conditioned area
            2. Provide cool (not cold) water
            3. Apply cool towels to paw pads
            4. Contact vet if symptoms persist
          data:
            tag: "cooling_protocol"
      
      - service: climate.set_temperature
        data:
          entity_id: climate.living_room
          temperature: 18
      
      - service: switch.turn_on
        entity_id: switch.ceiling_fans
      
      - delay: "00:30:00"
      
      - service: notify.mobile_app_phone
        data:
          title: "🌡️ Heat Status Check"
          message: "How is Buddy doing? Monitor for continued heavy panting."
          data:
            actions:
              - action: "BUDDY_IMPROVING"
                title: "✅ Improving"
              - action: "CALL_VET"
                title: "🏥 Call Vet"
```

### 3. Cold Weather Protection System

**Comprehensive Cold Stress Management:**

```yaml
automation:
  - alias: "Cold Weather Protection Protocol"
    id: pawcontrol_cold_protection
    trigger:
      - platform: state
        entity_id: binary_sensor.buddy_cold_stress_alert
        to: "on"
    action:
      - variables:
          temp_current: "{{ states('sensor.temperature') | float }}"
          wind_chill: "{{ states('sensor.buddy_wind_chill') | float | default(temp_current) }}"
          dog_size: "{{ state_attr('sensor.buddy_profile', 'size') }}"
          has_thick_coat: "{{ state_attr('sensor.buddy_profile', 'coat_type') == 'thick' }}"

      - service: pawcontrol.get_weather_recommendations
        data:
          dog_id: "buddy"
          include_breed_specific: true
        response_variable: cold_advice

      - choose:
          # Extreme cold (-10°C or below)
          - conditions:
              - condition: template
                value_template: "{{ temp_current <= -10 }}"
            sequence:
              - service: notify.mobile_app_phone
                data:
                  title: "🥶 EXTREME COLD WARNING"
                  message: >
                    🌡️ {{ temp_current }}°C (feels like {{ wind_chill }}°C)
                    ⚠️ DANGER: Limit outdoor time to absolute essentials only!
                    🧥 Use protective clothing and booties
                    💡 {{ cold_advice.recommendations[0] }}
                  data:
                    priority: high
                    color: blue
                    actions:
                      - action: "EMERGENCY_WARMTH"
                        title: "🔥 Emergency Warmth"
                      - action: "PROTECTIVE_GEAR"
                        title: "🧥 Protective Gear"
              
              # Activate heating systems
              - service: climate.set_temperature
                data:
                  entity_id: climate.living_room
                  temperature: 22
              - service: switch.turn_on
                entity_id: switch.heated_dog_bed

          # High cold (0°C to -9°C)
          - conditions:
              - condition: template
                value_template: "{{ temp_current > -10 and temp_current <= 0 }}"
            sequence:
              - service: notify.mobile_app_phone
                data:
                  title: "❄️ High Cold Advisory"
                  message: >
                    🌡️ {{ temp_current }}°C - Cold weather precautions needed
                    ⏱️ Limit outdoor time to 15-20 minutes
                    🧥 Consider protective clothing for short-haired breeds
                    🐾 Watch for ice between toes
                  data:
                    actions:
                      - action: "SHORT_COLD_WALK"
                        title: "🚶 Quick Walk (15 min)"
                      - action: "PAW_PROTECTION"
                        title: "🐾 Paw Care Tips"

          # Moderate cold (1°C to 5°C)
          - conditions:
              - condition: template
                value_template: "{{ temp_current > 0 and temp_current <= 5 }}"
            sequence:
              - choose:
                  # Small or short-haired dogs need extra protection
                  - conditions:
                      - condition: template
                        value_template: "{{ dog_size == 'small' or not has_thick_coat }}"
                    sequence:
                      - service: notify.mobile_app_phone
                        data:
                          title: "🧥 Cold Weather Gear Recommended"
                          message: >
                            🌡️ {{ temp_current }}°C - Consider protective clothing
                            {{ state_attr('sensor.buddy_profile', 'breed') }}s may need extra warmth
                            🚶 Normal walk duration is okay with protection
                          data:
                            actions:
                              - action: "PROTECTIVE_CLOTHING"
                                title: "🧥 Add Clothing"
                              - action: "NORMAL_WALK"
                                title: "🚶 Normal Walk"
                
                  # Thick-coated dogs handle cold better
                  - conditions:
                      - condition: template
                        value_template: "{{ has_thick_coat }}"
                    sequence:
                      - service: notify.mobile_app_phone
                        data:
                          title: "❄️ Cold Weather - Good for Thick Coats"
                          message: >
                            🌡️ {{ temp_current }}°C - {{ state_attr('sensor.buddy_profile', 'breed') }}s handle cold well
                            🚶 Normal activity levels are fine
                            🐾 Still check paws after walks
                          data:
                            actions:
                              - action: "NORMAL_COLD_WALK"
                                title: "🚶 Normal Walk"
                              - action: "PAW_CHECK"
                                title: "🐾 Paw Check"

  - alias: "Post-Cold Walk Paw Care Reminder"
    id: pawcontrol_cold_paw_care
    trigger:
      - platform: state
        entity_id: binary_sensor.buddy_walk_in_progress
        from: "on"
        to: "off"
    condition:
      - condition: numeric_state
        entity_id: sensor.temperature
        below: 5
    action:
      - delay: "00:02:00"  # Give time to get inside
      - service: notify.mobile_app_phone
        data:
          title: "🐾 Cold Weather Paw Care"
          message: >
            Walk completed in {{ states('sensor.temperature') }}°C weather.
            ✅ Check paws for ice, salt, or irritation
            🧽 Wipe paws dry and check between toes
            💧 Apply paw balm if needed
          data:
            actions:
              - action: "PAW_CHECKED"
                title: "✅ Paws Checked"
              - action: "PAW_CARE_GUIDE"
                title: "📋 Paw Care Guide"
```

### 4. UV Protection and Storm Warning System

**UV Exposure Management:**

```yaml
automation:
  - alias: "UV Protection Alert System"
    id: pawcontrol_uv_protection
    trigger:
      - platform: state
        entity_id: binary_sensor.buddy_uv_exposure_alert
        to: "on"
    action:
      - variables:
          uv_index: "{{ states('sensor.uv_index') | float }}"
          dog_color: "{{ state_attr('sensor.buddy_profile', 'coat_color') }}"
          has_light_coat: "{{ dog_color in ['white', 'cream', 'light', 'blonde'] }}"
          has_pink_skin: "{{ state_attr('sensor.buddy_profile', 'skin_type') == 'pink' }}"

      - choose:
          # Extreme UV (11+)
          - conditions:
              - condition: template
                value_template: "{{ uv_index >= 11 }}"
            sequence:
              - service: notify.mobile_app_phone
                data:
                  title: "☢️ EXTREME UV WARNING"
                  message: >
                    ☀️ UV Index: {{ uv_index }} - EXTREME RISK
                    🚫 Avoid outdoor activities 10 AM - 4 PM
                    🧴 Use pet-safe sunscreen on exposed areas
                    🌳 Provide constant shade when outside
                  data:
                    priority: high
                    color: purple
                    actions:
                      - action: "INDOOR_ALTERNATIVE"
                        title: "🏠 Indoor Activities"
                      - action: "UV_PROTECTION_GUIDE"
                        title: "🛡️ UV Protection"

          # High UV (8-10)
          - conditions:
              - condition: template
                value_template: "{{ uv_index >= 8 and uv_index < 11 }}"
            sequence:
              - service: notify.mobile_app_phone
                data:
                  title: "🌞 High UV Advisory"
                  message: >
                    ☀️ UV Index: {{ uv_index }} - High protection needed
                    {% if has_light_coat or has_pink_skin %}
                    🧴 {{ state_attr('sensor.buddy_profile', 'breed') }}s with light coats need extra protection
                    {% endif %}
                    🌳 Seek shade during peak hours (10 AM - 4 PM)
                  data:
                    actions:
                      - action: "SHADED_WALK"
                        title: "🌳 Shaded Walk"
                      - action: "UV_CLOTHING"
                        title: "👕 UV Clothing"

  - alias: "Storm Warning and Anxiety Management"
    id: pawcontrol_storm_management
    trigger:
      - platform: state
        entity_id: binary_sensor.buddy_storm_warning
        to: "on"
      - platform: state
        entity_id: weather.home
        to: 
          - "lightning"
          - "thunderstorms"
          - "severe-thunderstorm"
    action:
      - variables:
          is_anxious_dog: "{{ 'anxiety' in state_attr('sensor.buddy_profile', 'behavioral_traits') }}"
          storm_intensity: "{{ state_attr('weather.home', 'intensity') | default('moderate') }}"

      - service: notify.mobile_app_phone
        data:
          title: "⛈️ Storm Warning - Keep Buddy Safe"
          message: >
            ⚡ {{ state_attr('weather.home', 'condition') | title }} approaching
            🏠 Keep Buddy indoors until storm passes
            {% if is_anxious_dog %}
            😰 Anxiety management may be needed
            {% endif %}
            🆔 Ensure ID tags are secure before next outing
          data:
            priority: high
            actions:
              - action: "COMFORT_SETUP"
                title: "🛏️ Comfort Setup"
              - action: "ANXIETY_HELP"
                title: "😌 Anxiety Help"

      # Automatic actions for storm preparation
      - choose:
          - conditions:
              - condition: template
                value_template: "{{ is_anxious_dog }}"
            sequence:
              # Create calming environment
              - service: light.turn_on
                data:
                  entity_id: light.living_room
                  brightness: 30
              - service: media_player.play_media
                data:
                  entity_id: media_player.living_room_speaker
                  media_content_id: "calming_sounds_for_dogs"
                  media_content_type: "playlist"
              - service: notify.mobile_app_phone
                data:
                  title: "😌 Calming Environment Active"
                  message: "Dimmed lights and calming sounds activated for Buddy."

      # Disable outdoor-related automations during storm
      - service: automation.turn_off
        entity_id:
          - automation.buddy_walk_reminders
          - automation.automatic_walk_detection
      
      # Wait for storm to pass
      - wait_template: >
          {{ states('weather.home') not in ['lightning', 'thunderstorms', 'severe-thunderstorm'] }}
        timeout: "06:00:00"
      
      # Re-enable automations after storm
      - service: automation.turn_on
        entity_id:
          - automation.buddy_walk_reminders
          - automation.automatic_walk_detection
      
      - service: notify.mobile_app_phone
        data:
          title: "🌤️ Storm Passed"
          message: "Weather is clearing. Normal activities can resume."
```

### 5. Comprehensive Weather Forecast Planning

**24-Hour Weather Planning Automation:**

```yaml
automation:
  - alias: "Daily Weather Planning for Tomorrow"
    id: pawcontrol_daily_weather_planning
    trigger:
      - platform: time
        at: "20:00:00"  # Plan tomorrow's activities
    action:
      - service: pawcontrol.get_weather_recommendations
        data:
          dog_id: "buddy"
          time_horizon_hours: 24
          include_breed_specific: true
          include_health_conditions: true
        response_variable: tomorrow_forecast

      - variables:
          avg_temp: "{{ tomorrow_forecast.average_temperature }}"
          min_temp: "{{ tomorrow_forecast.min_temperature }}"
          max_temp: "{{ tomorrow_forecast.max_temperature }}"
          avg_score: "{{ tomorrow_forecast.average_health_score }}"
          best_times: "{{ tomorrow_forecast.optimal_walk_times }}"
          alerts_expected: "{{ tomorrow_forecast.expected_alerts }}"

      - choose:
          # Excellent weather day (Score 80+)
          - conditions:
              - condition: template
                value_template: "{{ avg_score >= 80 }}"
            sequence:
              - service: notify.mobile_app_phone
                data:
                  title: "🌟 Excellent Weather Tomorrow!"
                  message: >
                    📊 Weather Score: {{ avg_score }}/100
                    🌡️ Temperature: {{ min_temp }}°C - {{ max_temp }}°C
                    ⏰ Great for activities all day
                    💡 Consider: Extended walks, outdoor training, park visits
                  data:
                    actions:
                      - action: "PLAN_LONG_ACTIVITIES"
                        title: "🚶‍♂️ Plan Long Activities"
                      - action: "SCHEDULE_PARK_VISIT"
                        title: "🏞️ Schedule Park Visit"

          # Good weather with precautions (Score 60-79)
          - conditions:
              - condition: template
                value_template: "{{ avg_score >= 60 and avg_score < 80 }}"
            sequence:
              - service: notify.mobile_app_phone
                data:
                  title: "🌤️ Good Weather with Precautions"
                  message: >
                    📊 Weather Score: {{ avg_score }}/100
                    🌡️ Temperature: {{ min_temp }}°C - {{ max_temp }}°C
                    ⏰ Best times: {{ best_times }}
                    ⚠️ Expected alerts: {{ alerts_expected }}
                  data:
                    actions:
                      - action: "PLAN_TIMED_ACTIVITIES"
                        title: "⏰ Plan Timed Activities"
                      - action: "PREPARATION_CHECKLIST"
                        title: "📋 Preparation List"

          # Challenging weather (Score 40-59)
          - conditions:
              - condition: template
                value_template: "{{ avg_score >= 40 and avg_score < 60 }}"
            sequence:
              - service: notify.mobile_app_phone
                data:
                  title: "⚠️ Challenging Weather Tomorrow"
                  message: >
                    📊 Weather Score: {{ avg_score }}/100
                    🌡️ Temperature: {{ min_temp }}°C - {{ max_temp }}°C
                    🏠 Consider indoor alternatives
                    ⏰ Limited outdoor windows: {{ best_times }}
                  data:
                    actions:
                      - action: "INDOOR_ACTIVITY_PLAN"
                        title: "🏠 Indoor Activities"
                      - action: "SHORT_WALK_PLAN"
                        title: "🚶 Short Walk Plan"

          # Poor weather (Score <40)
          - conditions:
              - condition: template
                value_template: "{{ avg_score < 40 }}"
            sequence:
              - service: notify.mobile_app_phone
                data:
                  title: "🏠 Indoor Day Recommended"
                  message: >
                    📊 Weather Score: {{ avg_score }}/100
                    🌡️ Temperature: {{ min_temp }}°C - {{ max_temp }}°C
                    ❌ Outdoor activities not recommended
                    🧩 Plan indoor enrichment activities
                  data:
                    actions:
                      - action: "ENRICHMENT_ACTIVITIES"
                        title: "🧩 Enrichment Ideas"
                      - action: "ESSENTIAL_ONLY"
                        title: "🚪 Essential Trips Only"

  - alias: "Hourly Weather Check During Active Day"
    id: pawcontrol_hourly_weather_check
    trigger:
      - platform: time_pattern
        hours: "/1"  # Every hour during daylight
    condition:
      - condition: time
        after: "06:00:00"
        before: "21:00:00"
      - condition: template
        value_template: >
          {{ states('sensor.buddy_weather_health_score') | int != 
             state_attr('sensor.buddy_weather_health_score', 'previous_score') | int }}
    action:
      - variables:
          current_score: "{{ states('sensor.buddy_weather_health_score') | int }}"
          previous_score: "{{ state_attr('sensor.buddy_weather_health_score', 'previous_score') | int }}"
          score_change: "{{ current_score - previous_score }}"

      - choose:
          # Significant improvement (>20 points)
          - conditions:
              - condition: template
                value_template: "{{ score_change > 20 }}"
            sequence:
              - service: notify.mobile_app_phone
                data:
                  title: "📈 Weather Improving!"
                  message: >
                    Score improved from {{ previous_score }} to {{ current_score }}
                    🌤️ Better conditions for outdoor activities
                  data:
                    actions:
                      - action: "CHECK_WALK_OPPORTUNITY"
                        title: "🚶 Check Walk Opportunity"

          # Significant deterioration (>20 points drop)
          - conditions:
              - condition: template
                value_template: "{{ score_change < -20 }}"
            sequence:
              - service: notify.mobile_app_phone
                data:
                  title: "📉 Weather Deteriorating"
                  message: >
                    Score dropped from {{ previous_score }} to {{ current_score }}
                    ⚠️ Conditions worsening - take precautions
                  data:
                    priority: high
                    actions:
                      - action: "SAFETY_PRECAUTIONS"
                        title: "🛡️ Safety Precautions"
                      - action: "INDOOR_TRANSITION"
                        title: "🏠 Move Indoors"
```

### 6. Integration with Smart Home Systems

**Weather-Responsive Smart Home Automation:**

```yaml
automation:
  - alias: "Smart Home Weather Response System"
    id: pawcontrol_smart_home_weather
    trigger:
      - platform: state
        entity_id: 
          - binary_sensor.buddy_heat_stress_alert
          - binary_sensor.buddy_cold_stress_alert
          - binary_sensor.buddy_storm_warning
        to: "on"
    action:
      - variables:
          alert_type: "{{ trigger.entity_id.split('_')[-2] }}"  # heat, cold, storm
          dog_location: "{{ states('device_tracker.buddy_gps') }}"

      - choose:
          # Heat stress response
          - conditions:
              - condition: template
                value_template: "{{ alert_type == 'heat' }}"
            sequence:
              # Climate control
              - service: climate.set_temperature
                data:
                  entity_id: climate.living_room
                  temperature: 20
              - service: switch.turn_on
                entity_id: 
                  - switch.ceiling_fans
                  - switch.air_purifier
              
              # Lighting adjustments (reduce heat)
              - service: light.turn_off
                entity_id: light.high_heat_bulbs
              - service: cover.close_cover
                entity_id: cover.south_facing_blinds
              
              # Water system
              - service: switch.turn_on
                entity_id: switch.automatic_water_dispenser
              
              # Notifications to other family members
              - service: notify.family_group
                data:
                  title: "🔥 Heat Alert - Buddy"
                  message: "Heat stress protocol activated. Buddy needs cool environment."

          # Cold stress response  
          - conditions:
              - condition: template
                value_template: "{{ alert_type == 'cold' }}"
            sequence:
              # Heating system
              - service: climate.set_temperature
                data:
                  entity_id: climate.living_room
                  temperature: 22
              - service: switch.turn_on
                entity_id: switch.heated_dog_bed
              
              # Block cold drafts
              - service: cover.close_cover
                entity_id: cover.all_windows
              - service: switch.turn_off
                entity_id: switch.exhaust_fans
              
              # Lighting for warmth
              - service: light.turn_on
                data:
                  entity_id: light.warm_bulbs
                  color_temp: 2000
                  brightness: 255

          # Storm response
          - conditions:
              - condition: template
                value_template: "{{ alert_type == 'storm' }}"
            sequence:
              # Secure outdoor items
              - service: cover.close_cover
                entity_id: cover.all_outdoor_covers
              - service: switch.turn_off
                entity_id: switch.outdoor_speakers
              
              # Create calming environment
              - service: light.turn_on
                data:
                  entity_id: light.calming_lights
                  effect: "slow_color_change"
                  brightness: 50
              - service: media_player.play_media
                data:
                  entity_id: media_player.house_speakers
                  media_content_id: "white_noise_rain"
                  media_content_type: "music"
              
              # Security measures
              - service: lock.lock
                entity_id: lock.all_doors
              - service: alarm_control_panel.alarm_arm_home
                entity_id: alarm_control_panel.house

  - alias: "Weather-Based Energy Optimization"
    id: pawcontrol_energy_weather_optimization
    trigger:
      - platform: state
        entity_id: sensor.buddy_weather_health_score
    action:
      - variables:
          weather_score: "{{ states('sensor.buddy_weather_health_score') | int }}"
          energy_price: "{{ states('sensor.electricity_price') | float }}"

      - choose:
          # Perfect weather - reduce energy usage
          - conditions:
              - condition: template
                value_template: "{{ weather_score >= 80 }}"
            sequence:
              - service: climate.set_preset_mode
                data:
                  entity_id: climate.living_room
                  preset_mode: "eco"
              - service: notify.mobile_app_phone
                data:
                  title: "🌱 Energy Saving Mode"
                  message: "Perfect weather allows energy-efficient climate settings."

          # Poor weather - prioritize comfort over energy
          - conditions:
              - condition: template
                value_template: "{{ weather_score < 40 }}"
            sequence:
              - service: climate.set_preset_mode
                data:
                  entity_id: climate.living_room
                  preset_mode: "comfort"
              - service: notify.mobile_app_phone
                data:
                  title: "🏠 Comfort Priority Mode"
                  message: "Poor weather conditions - prioritizing Buddy's comfort."
```

### 7. Health Condition Specific Weather Automations

**Respiratory Condition Weather Management:**

```yaml
automation:
  - alias: "Respiratory Condition Weather Monitoring"
    id: pawcontrol_respiratory_weather
    trigger:
      - platform: numeric_state
        entity_id: sensor.temperature
        above: 25
      - platform: numeric_state
        entity_id: sensor.humidity
        above: 70
      - platform: state
        entity_id: sensor.air_quality_index
        to: 
          - "moderate" 
          - "unhealthy"
    condition:
      - condition: template
        value_template: >
          {{ 'respiratory' in state_attr('sensor.buddy_profile', 'health_conditions') }}
    action:
      - service: pawcontrol.get_weather_recommendations
        data:
          dog_id: "buddy"
          include_health_conditions: true
        response_variable: respiratory_advice

      - service: notify.mobile_app_phone
        data:
          title: "🫁 Respiratory Alert - Weather Check"
          message: >
            🌡️ Temperature: {{ states('sensor.temperature') }}°C
            💨 Humidity: {{ states('sensor.humidity') }}%
            🌫️ Air Quality: {{ states('sensor.air_quality_index') }}
            ⚠️ Monitor breathing closely: {{ respiratory_advice.recommendations[0] }}
          data:
            priority: high
            actions:
              - action: "BREATHING_CHECK"
                title: "👁️ Check Breathing"
              - action: "INDOOR_ONLY"
                title: "🏠 Keep Indoors"
              - action: "VET_CONSULT"
                title: "🏥 Vet Consultation"

      # Activate air purification systems
      - service: switch.turn_on
        entity_id: switch.air_purifier
      - service: fan.set_speed
        data:
          entity_id: fan.air_circulation
          speed: "high"

  - alias: "Senior Dog Weather Considerations"
    id: pawcontrol_senior_dog_weather
    trigger:
      - platform: state
        entity_id: sensor.buddy_weather_health_score
    condition:
      - condition: template
        value_template: >
          {{ state_attr('sensor.buddy_profile', 'age_months') | int > 84 }}  # 7+ years
    action:
      - variables:
          weather_score: "{{ states('sensor.buddy_weather_health_score') | int }}"
          age_years: "{{ (state_attr('sensor.buddy_profile', 'age_months') | int / 12) | round(1) }}"

      - choose:
          # Extra caution for senior dogs in borderline weather
          - conditions:
              - condition: template
                value_template: "{{ weather_score >= 40 and weather_score < 70 }}"
            sequence:
              - service: notify.mobile_app_phone
                data:
                  title: "👴 Senior Dog Weather Caution"
                  message: >
                    {{ age_years }}-year-old Buddy needs extra care today
                    📊 Weather Score: {{ weather_score }}/100
                    💡 Senior dogs are more sensitive to weather changes
                    ⏰ Consider shorter, more frequent outings
                  data:
                    actions:
                      - action: "SENIOR_WALK_PLAN"
                        title: "👴 Senior Walk Plan"
                      - action: "COMFORT_CHECK"
                        title: "🛏️ Comfort Check"

  - alias: "Heart Condition Weather Restrictions"
    id: pawcontrol_heart_condition_weather
    trigger:
      - platform: state
        entity_id: binary_sensor.buddy_heat_stress_alert
        to: "on"
      - platform: numeric_state
        entity_id: sensor.buddy_weather_health_score
        below: 50
    condition:
      - condition: template
        value_template: >
          {{ 'heart' in state_attr('sensor.buddy_profile', 'health_conditions') or
             'cardiac' in state_attr('sensor.buddy_profile', 'health_conditions') }}
    action:
      - service: notify.mobile_app_phone
        data:
          title: "❤️ Heart Condition - Weather Alert"
          message: >
            ⚠️ Weather conditions may stress Buddy's heart
            🚫 Avoid strenuous activities
            🏠 Keep in controlled environment
            📞 Monitor for unusual symptoms
          data:
            priority: high
            color: red
            actions:
              - action: "GENTLE_ACTIVITY_ONLY"
                title: "🐌 Gentle Activity Only"
              - action: "CARDIAC_MONITORING"
                title: "❤️ Monitor Heart"
              - action: "EMERGENCY_VET"
                title: "🚨 Emergency Vet"

      # Automatic activity restrictions
      - service: automation.turn_off
        entity_id:
          - automation.buddy_exercise_reminders
          - automation.buddy_training_sessions
      
      # Schedule re-evaluation in 2 hours
      - delay: "02:00:00"
      - condition: numeric_state
        entity_id: sensor.buddy_weather_health_score
        above: 60
      - service: automation.turn_on
        entity_id:
          - automation.buddy_exercise_reminders
          - automation.buddy_training_sessions
      - service: notify.mobile_app_phone
        data:
          title: "❤️ Heart Condition - Weather Improved"
          message: "Weather conditions improved. Normal activities can resume gradually."
```

## Service Integration Examples

### Using Weather Services in Automations

**Service Call Examples:**

```yaml
# Update weather data for specific dog
service: pawcontrol.update_weather_data
data:
  dog_id: "buddy"
  weather_entity: "weather.home"
  force_update: true

# Get personalized weather recommendations
service: pawcontrol.get_weather_recommendations
data:
  dog_id: "buddy"
  include_breed_specific: true
  include_health_conditions: true
  time_horizon_hours: 24

# Calculate current weather health score
service: pawcontrol.calculate_weather_health_score
data:
  dog_id: "buddy"
  current_conditions: true
  forecast_hours: 6

# Manage weather alerts
service: pawcontrol.weather_alert_actions
data:
  dog_id: "buddy"
  action: "acknowledge"  # acknowledge, snooze, dismiss
  alert_types: ["heat_stress", "uv_exposure"]
```

### Template Examples for Custom Automations

**Advanced Templates:**

```yaml
# Weather safety assessment
weather_safety_template: >
  {% set score = states('sensor.buddy_weather_health_score') | int %}
  {% if score >= 80 %}Perfect conditions
  {% elif score >= 60 %}Good with precautions
  {% elif score >= 40 %}Moderate concerns
  {% else %}Poor conditions{% endif %}

# Breed-specific temperature tolerance
breed_temp_tolerance: >
  {% set breed = state_attr('sensor.buddy_profile', 'breed').lower() %}
  {% set temp = states('sensor.temperature') | float %}
  {% if breed in ['husky', 'malamute', 'saint bernard'] %}
    {% if temp > 20 %}Too warm for {{ breed }}
    {% else %}Good temperature{% endif %}
  {% elif breed in ['chihuahua', 'yorkie', 'maltese'] %}
    {% if temp < 10 %}Too cold for {{ breed }}
    {% else %}Acceptable temperature{% endif %}
  {% else %}
    {% if temp < 0 or temp > 30 %}Extreme temperature
    {% else %}Acceptable range{% endif %}
  {% endif %}

# Weather alert summary
active_alerts_summary: >
  {% set alerts = states('sensor.buddy_active_weather_alerts') | int %}
  {% if alerts == 0 %}No active alerts
  {% elif alerts == 1 %}1 active weather alert
  {% else %}{{ alerts }} active weather alerts{% endif %}

# Optimal walk time calculation
optimal_walk_time: >
  {% set score = states('sensor.buddy_weather_health_score') | int %}
  {% set hour = now().hour %}
  {% if score >= 80 %}Any time is good
  {% elif score >= 60 %}
    {% if hour < 10 or hour > 18 %}Good time for walks
    {% else %}Wait for cooler hours{% endif %}
  {% else %}Indoor activities recommended{% endif %}
```

## Best Practices

### Performance Optimization

1. **Efficient Triggers**: Use specific weather score thresholds to avoid excessive automation runs
2. **Batch Processing**: Group related weather checks into single automations
3. **Caching**: Leverage the built-in weather data caching system
4. **Conditional Logic**: Use choose blocks to handle multiple weather scenarios efficiently

### User Experience

1. **Clear Messaging**: Weather notifications should be informative and actionable
2. **Progressive Disclosure**: Show basic info first, detailed recommendations on request
3. **Contextual Actions**: Provide relevant action buttons based on weather conditions
4. **Emergency Priority**: Ensure critical weather alerts override quiet hours

### Safety Considerations

1. **Conservative Thresholds**: Err on the side of caution for weather warnings
2. **Breed Awareness**: Always consider breed-specific vulnerabilities
3. **Health Conditions**: Account for pre-existing medical conditions in weather responses
4. **Emergency Protocols**: Have clear escalation paths for extreme weather conditions

## Troubleshooting

### Common Issues

**Weather data not updating:**
```yaml
# Debug weather entity availability
- service: system_log.write
  data:
    message: "Weather entity state: {{ states('weather.home') }}"
    level: info

# Test manual weather update
- service: pawcontrol.update_weather_data
  data:
    dog_id: "buddy"
    force_update: true
```

**Weather scores seem incorrect:**
```yaml
# Check breed configuration
- service: system_log.write
  data:
    message: "Dog breed: {{ state_attr('sensor.buddy_profile', 'breed') }}"
    level: debug

# Verify health conditions
- service: system_log.write
  data:
    message: "Health conditions: {{ state_attr('sensor.buddy_profile', 'health_conditions') }}"
    level: debug
```

**Alerts not triggering:**
```yaml
# Verify alert configuration
- condition: state
  entity_id: switch.buddy_weather_monitoring
  state: "on"

# Check alert thresholds
- condition: template
  value_template: >
    {{ states('sensor.buddy_weather_health_score') | int < 70 }}
```

## Conclusion

PawControl's weather integration provides comprehensive, intelligent automation capabilities that prioritize dog safety and comfort. The examples in this guide demonstrate how to leverage the sophisticated weather health system to create responsive, breed-aware, and health-conscious automations.

Key benefits:
- **🎯 Proactive Safety**: Prevent weather-related health issues before they occur
- **🐕 Personalized Care**: Breed and health condition specific recommendations
- **🏠 Smart Integration**: Seamless integration with home automation systems
- **📱 Actionable Insights**: Clear, actionable notifications with appropriate responses
- **⚡ Enterprise Ready**: Scalable for multiple dogs with individual configurations

The weather integration transforms PawControl from a basic pet tracker into an intelligent pet health guardian that actively monitors environmental conditions and responds appropriately to ensure your dog's safety and well-being.

---

**Last Updated:** 2025-01-20 - Comprehensive weather automation examples  
**Quality Level:** 🏆 **Platinum+** | **Enterprise-Ready** | **Production-Validated**
