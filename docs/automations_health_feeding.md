# Enhanced Health-Aware Feeding Automations for Paw Control

## Quality Scale: Platinum | HA 2025.9.0+ | Python 3.13+

This document provides comprehensive automation examples for the health-integrated feeding system. These automations leverage the advanced health calculation features in the feeding_manager and health_calculator modules.

## =============================================================================
## HEALTH-INTEGRATED FEEDING AUTOMATIONS
## =============================================================================

### 1. Dynamic Portion Adjustment Based on Body Condition
```yaml
alias: "PawControl - Dynamic Portion Adjustment"
description: "Automatically adjust portions based on body condition score changes"
trigger:
  - platform: state
    entity_id: sensor.rex_body_condition_score
    for:
      hours: 24  # Only adjust after sustained change
condition:
  - condition: template
    value_template: >
      {{ trigger.from_state.state != 'unknown' and
         trigger.to_state.state != 'unknown' and
         trigger.from_state.state != trigger.to_state.state }}
action:
  - service: pawcontrol.recalculate_health_portions
    data:
      dog_id: "rex"
      trigger_reason: "body_condition_change"
      old_bcs: "{{ trigger.from_state.state }}"
      new_bcs: "{{ trigger.to_state.state }}"
  - service: notify.mobile_app_phone
    data:
      title: "🔬 Portion Adjustment"
      message: >
        Rex's body condition changed from {{ trigger.from_state.state }} to {{ trigger.to_state.state }}.
        Portions automatically recalculated.
      data:
        actions:
          - action: "VIEW_PORTIONS"
            title: "View New Portions 📊"
          - action: "UNDO_ADJUSTMENT"
            title: "Undo ↶"
```

### 2. Calorie Goal Progress Tracking
```yaml
alias: "PawControl - Daily Calorie Goal Check"
description: "Monitor daily calorie intake vs health-calculated target"
trigger:
  - platform: time
    at: "20:00:00"  # Evening check
  - platform: numeric_state
    entity_id: sensor.rex_calorie_goal_progress
    above: 100  # Overfeeding
condition:
  - condition: state
    entity_id: binary_sensor.rex_health_aware_feeding
    state: "on"
action:
  - choose:
      # Calorie goal exceeded
      - conditions:
          - condition: numeric_state
            entity_id: sensor.rex_calorie_goal_progress
            above: 110
        sequence:
          - service: notify.mobile_app_phone
            data:
              title: "⚠️ Calorie Goal Exceeded"
              message: >
                Rex has consumed {{ states('sensor.rex_calories_consumed_today') }} calories
                ({{ states('sensor.rex_calorie_goal_progress') }}% of target).
                Consider reducing evening portion.
              data:
                priority: high
                actions:
                  - action: "REDUCE_PORTIONS"
                    title: "Reduce Evening Portion 📉"
                  - action: "SKIP_SNACKS"
                    title: "Skip Snacks Tonight 🚫"
      # Calorie goal not met
      - conditions:
          - condition: numeric_state
            entity_id: sensor.rex_calorie_goal_progress
            below: 80
          - condition: time
            after: "18:00:00"
        sequence:
          - service: notify.mobile_app_phone
            data:
              title: "📈 Low Calorie Intake"
              message: >
                Rex has only consumed {{ states('sensor.rex_calorie_goal_progress') }}%
                of daily calorie target. Consider adding healthy snack.
              data:
                actions:
                  - action: "ADD_SNACK"
                    title: "Add Healthy Snack 🦴"
                  - action: "INCREASE_DINNER"
                    title: "Increase Dinner Portion 🍽️"
    # Normal range
    default:
      - service: notify.mobile_app_phone
        data:
          title: "✅ Calorie Goal On Track"
          message: >
            Rex's calorie intake is perfect at {{ states('sensor.rex_calorie_goal_progress') }}%
            of target ({{ states('sensor.rex_calories_consumed_today') }} calories).
```

### 3. Weight Goal Achievement Monitoring
```yaml
alias: "PawControl - Weight Goal Progress Alert"
description: "Alert on significant weight goal progress or setbacks"
trigger:
  - platform: state
    entity_id: sensor.rex_weight_goal_progress
    for:
      days: 3  # Sustained change
condition:
  - condition: template
    value_template: >
      {{ trigger.from_state.state not in ['unknown', 'unavailable'] and
         trigger.to_state.state not in ['unknown', 'unavailable'] and
         (trigger.to_state.state | float - trigger.from_state.state | float) | abs >= 5 }}
action:
  - choose:
      # Positive progress
      - conditions:
          - condition: template
            value_template: >
              {{ (trigger.to_state.state | float - trigger.from_state.state | float) > 0 }}
        sequence:
          - service: notify.mobile_app_phone
            data:
              title: "🎉 Weight Goal Progress!"
              message: >
                Great news! Rex's weight goal progress improved by
                {{ (trigger.to_state.state | float - trigger.from_state.state | float) | round(1) }}%
                over the last 3 days.
              data:
                actions:
                  - action: "VIEW_PROGRESS"
                    title: "View Progress Chart 📈"
                  - action: "MAINTAIN_PLAN"
                    title: "Continue Current Plan ✅"
      # Negative trend
      - conditions:
          - condition: template
            value_template: >
              {{ (trigger.to_state.state | float - trigger.from_state.state | float) < 0 }}
        sequence:
          - service: pawcontrol.adjust_weight_goal_strategy
            data:
              dog_id: "rex"
              adjustment_type: "course_correction"
              progress_decline: "{{ (trigger.from_state.state | float - trigger.to_state.state | float) | round(1) }}"
          - service: notify.mobile_app_phone
            data:
              title: "⚠️ Weight Goal Setback"
              message: >
                Rex's weight progress declined by
                {{ (trigger.from_state.state | float - trigger.to_state.state | float) | round(1) }}%.
                Feeding plan adjusted automatically.
              data:
                priority: high
                actions:
                  - action: "VIEW_ADJUSTMENTS"
                    title: "View Adjustments 🔧"
                  - action: "CONSULT_VET"
                    title: "Consult Vet 👨‍⚕️"
```

### 4. Health Condition-Based Feeding Alerts
```yaml
alias: "PawControl - Health Condition Feeding Alert"
description: "Adjust feeding based on health condition requirements"
trigger:
  - platform: state
    entity_id: sensor.rex_health_conditions
    attribute: active_conditions
  - platform: state
    entity_id: sensor.rex_medication_schedule
    attribute: next_medication
condition:
  - condition: state
    entity_id: binary_sensor.rex_health_aware_feeding
    state: "on"
action:
  - choose:
      # Diabetes detected - strict calorie control
      - conditions:
          - condition: template
            value_template: >
              {{ 'diabetes' in state_attr('sensor.rex_health_conditions', 'active_conditions') }}
        sequence:
          - service: pawcontrol.activate_diabetic_feeding_mode
            data:
              dog_id: "rex"
              strict_scheduling: true
              portion_precision: "high"
          - service: notify.mobile_app_phone
            data:
              title: "🩺 Diabetic Feeding Mode"
              message: "Diabetes detected. Activated strict feeding schedule with precise portions."

      # Kidney disease - modified protein/phosphorus
      - conditions:
          - condition: template
            value_template: >
              {{ 'kidney_disease' in state_attr('sensor.rex_health_conditions', 'active_conditions') }}
        sequence:
          - service: pawcontrol.adjust_feeding_for_kidney_disease
            data:
              dog_id: "rex"
              protein_restriction: "moderate"
              phosphorus_limit: "low"
          - service: notify.mobile_app_phone
            data:
              title: "🫘 Kidney Support Diet"
              message: "Kidney disease detected. Modified portions for renal support."

      # Heart disease - weight management critical
      - conditions:
          - condition: template
            value_template: >
              {{ 'heart_disease' in state_attr('sensor.rex_health_conditions', 'active_conditions') }}
        sequence:
          - service: pawcontrol.activate_cardiac_feeding_mode
            data:
              dog_id: "rex"
              sodium_restriction: "strict"
              weight_management: "critical"
          - service: notify.mobile_app_phone
            data:
              title: "❤️ Cardiac Diet Mode"
              message: "Heart condition detected. Activated low-sodium, weight-controlled feeding."
```

### 5. Medication-Timed Feeding Automation
```yaml
alias: "PawControl - Medication Feeding Reminder"
description: "Coordinate feeding with medication schedule for optimal absorption"
trigger:
  - platform: template
    value_template: >
      {{ states('sensor.rex_next_medication_time') != 'unknown' and
         (as_timestamp(states('sensor.rex_next_medication_time')) - as_timestamp(now())) <= 900 }}
condition:
  - condition: state
    entity_id: binary_sensor.rex_medication_with_meals
    state: "on"
  - condition: template
    value_template: >
      {{ states('sensor.rex_last_fed_hours') | float >= 3 }}  # Avoid overfeeding
action:
  - service: notify.mobile_app_phone
    data:
      title: "💊 Medication Feeding Time"
      message: >
        Rex's medication is due in 15 minutes.
        Portion: {{ states('sensor.rex_medication_meal_portion') }}g
        Medication: {{ states('sensor.rex_current_medication') }}
      data:
        actions:
          - action: "FEED_WITH_MED"
            title: "Feed + Give Medication 💊"
          - action: "DELAY_15MIN"
            title: "Delay 15 minutes ⏰"
          - action: "MED_WITHOUT_FOOD"
            title: "Medication Only 🩺"
mode: single
```

### 6. Activity-Based Calorie Adjustment
```yaml
alias: "PawControl - Activity Calorie Adjustment"
description: "Adjust calories based on daily activity level"
trigger:
  - platform: state
    entity_id: sensor.rex_daily_activity_level
    for:
      hours: 2  # Wait for stable reading
condition:
  - condition: template
    value_template: >
      {{ trigger.from_state.state != 'unknown' and
         trigger.to_state.state != 'unknown' and
         trigger.from_state.state != trigger.to_state.state }}
action:
  - choose:
      # Very high activity - increase calories
      - conditions:
          - condition: state
            entity_id: sensor.rex_daily_activity_level
            state: "very_high"
        sequence:
          - service: pawcontrol.adjust_calories_for_activity
            data:
              dog_id: "rex"
              activity_level: "very_high"
              calorie_adjustment: 1.3
          - service: notify.mobile_app_phone
            data:
              title: "🏃 High Activity Detected"
              message: "Rex had very high activity today. Increased calories by 30%."

      # Low activity - reduce calories
      - conditions:
          - condition: state
            entity_id: sensor.rex_daily_activity_level
            state: "low"
        sequence:
          - service: pawcontrol.adjust_calories_for_activity
            data:
              dog_id: "rex"
              activity_level: "low"
              calorie_adjustment: 0.9
          - service: notify.mobile_app_phone
            data:
              title: "😴 Low Activity Day"
              message: "Rex was less active today. Reduced calories by 10%."

    # Normal activity - maintain baseline
    default:
      - service: pawcontrol.reset_activity_adjustments
        data:
          dog_id: "rex"
```

### 7. Weekly Health Report Generation
```yaml
alias: "PawControl - Weekly Health Report"
description: "Generate comprehensive health feeding report"
trigger:
  - platform: time
    at: "08:00:00"
  - platform: template
    value_template: >
      {{ now().weekday() == 6 }}  # Sunday
condition:
  - condition: state
    entity_id: binary_sensor.rex_health_aware_feeding
    state: "on"
action:
  - service: pawcontrol.generate_weekly_health_report
    data:
      dog_id: "rex"
      include_sections:
        - "calorie_analysis"
        - "weight_progress"
        - "portion_adjustments"
        - "health_correlations"
        - "recommendations"
  - delay:
      seconds: 30  # Allow report generation
  - service: notify.mobile_app_phone
    data:
      title: "📊 Weekly Health Report Ready"
      message: >
        Rex's weekly health feeding report is ready.
        Weight change: {{ states('sensor.rex_weekly_weight_change') }}kg
        Avg calorie adherence: {{ states('sensor.rex_weekly_calorie_adherence') }}%
      data:
        actions:
          - action: "VIEW_REPORT"
            title: "View Full Report 📋"
          - action: "SHARE_VET"
            title: "Share with Vet 👨‍⚕️"
```

### 8. Emergency Health Feeding Override
```yaml
alias: "PawControl - Emergency Health Override"
description: "Override normal feeding for health emergencies"
trigger:
  - platform: state
    entity_id: binary_sensor.rex_health_emergency
    to: "on"
condition:
  - condition: state
    entity_id: binary_sensor.rex_health_aware_feeding
    state: "on"
action:
  - service: pawcontrol.activate_emergency_feeding_mode
    data:
      dog_id: "rex"
      emergency_type: "{{ state_attr('binary_sensor.rex_health_emergency', 'emergency_type') }}"
      override_portions: true
      strict_monitoring: true
  - service: notify.all_devices
    data:
      title: "🚨 HEALTH EMERGENCY"
      message: >
        Emergency feeding mode activated for Rex.
        Type: {{ state_attr('binary_sensor.rex_health_emergency', 'emergency_type') }}
        All normal feeding schedules overridden.
      data:
        priority: critical
        ttl: 0
        actions:
          - action: "VET_EMERGENCY"
            title: "Call Vet NOW 📞"
          - action: "VIEW_INSTRUCTIONS"
            title: "Emergency Instructions 📋"
```

### 9. Special Diet Transition Automation
```yaml
alias: "PawControl - Special Diet Transition"
description: "Gradually transition to new special diet"
trigger:
  - platform: state
    entity_id: select.rex_special_diet_type
condition:
  - condition: template
    value_template: >
      {{ trigger.from_state.state != 'unknown' and
         trigger.to_state.state != 'unknown' and
         trigger.from_state.state != trigger.to_state.state }}
action:
  - service: pawcontrol.start_diet_transition
    data:
      dog_id: "rex"
      from_diet: "{{ trigger.from_state.state }}"
      to_diet: "{{ trigger.to_state.state }}"
      transition_days: 7
      gradual_mixing: true
  - service: notify.mobile_app_phone
    data:
      title: "🥘 Diet Transition Started"
      message: >
        Starting 7-day transition from {{ trigger.from_state.state }}
        to {{ trigger.to_state.state }} diet.
        Today's mix: {{ states('sensor.rex_diet_transition_ratio') }}
      data:
        actions:
          - action: "VIEW_SCHEDULE"
            title: "View Transition Schedule 📅"
          - action: "ADJUST_TIMELINE"
            title: "Adjust Timeline ⏱️"
```

### 10. Health Feeding Compliance Monitoring
```yaml
alias: "PawControl - Feeding Compliance Check"
description: "Monitor adherence to health feeding recommendations"
trigger:
  - platform: time_pattern
    hours: "/4"  # Every 4 hours
condition:
  - condition: state
    entity_id: binary_sensor.rex_health_aware_feeding
    state: "on"
  - condition: time
    after: "06:00:00"
    before: "22:00:00"
action:
  - service: pawcontrol.check_feeding_compliance
    data:
      dog_id: "rex"
      check_type: "routine"
  - choose:
      # Poor compliance
      - conditions:
          - condition: numeric_state
            entity_id: sensor.rex_feeding_compliance_score
            below: 70
        sequence:
          - service: notify.mobile_app_phone
            data:
              title: "⚠️ Poor Feeding Compliance"
              message: >
                Rex's feeding compliance is {{ states('sensor.rex_feeding_compliance_score') }}%.
                Recent issues: {{ state_attr('sensor.rex_compliance_issues', 'recent_issues') | join(', ') }}
              data:
                actions:
                  - action: "FIX_COMPLIANCE"
                    title: "Fix Issues 🔧"
                  - action: "SIMPLIFY_PLAN"
                    title: "Simplify Plan 📝"

      # Excellent compliance
      - conditions:
          - condition: numeric_state
            entity_id: sensor.rex_feeding_compliance_score
            above: 95
        sequence:
          - service: notify.mobile_app_phone
            data:
              title: "🌟 Excellent Compliance!"
              message: >
                Perfect feeding compliance at {{ states('sensor.rex_feeding_compliance_score') }}%!
                Rex's health plan is working great.
```

## =============================================================================
## HEALTH FEEDING RESPONSE AUTOMATIONS
## =============================================================================

### Response to Feeding Compliance Actions
```yaml
alias: "PawControl - Handle Feeding Actions"
description: "Handle user responses to health feeding notifications"
trigger:
  - platform: event
    event_type: mobile_app_notification_action
    event_data:
      action: "FEED_WITH_MED"
  - platform: event
    event_type: mobile_app_notification_action
    event_data:
      action: "REDUCE_PORTIONS"
  - platform: event
    event_type: mobile_app_notification_action
    event_data:
      action: "ADD_SNACK"
action:
  - choose:
      # Feed with medication
      - conditions:
          - condition: template
            value_template: "{{ trigger.event.data.action == 'FEED_WITH_MED' }}"
        sequence:
          - service: pawcontrol.feed_with_medication
            data:
              dog_id: "rex"
              auto_calculate_portion: true
              medication_timing: "optimal"
          - service: notify.mobile_app_phone
            data:
              title: "✅ Fed with Medication"
              message: "Rex fed with health-calculated portion and medication given."

      # Reduce portions
      - conditions:
          - condition: template
            value_template: "{{ trigger.event.data.action == 'REDUCE_PORTIONS' }}"
        sequence:
          - service: pawcontrol.adjust_daily_portions
            data:
              dog_id: "rex"
              adjustment_factor: 0.9
              reason: "calorie_excess"
          - service: notify.mobile_app_phone
            data:
              title: "📉 Portions Reduced"
              message: "Daily portions reduced by 10% due to calorie excess."

      # Add healthy snack
      - conditions:
          - condition: template
            value_template: "{{ trigger.event.data.action == 'ADD_SNACK' }}"
        sequence:
          - service: pawcontrol.add_health_snack
            data:
              dog_id: "rex"
              snack_type: "low_calorie_healthy"
              portion_size: "{{ states('sensor.rex_healthy_snack_portion') }}"
          - service: notify.mobile_app_phone
            data:
              title: "🦴 Healthy Snack Added"
              message: "Added {{ states('sensor.rex_healthy_snack_portion') }}g healthy snack."
```

## ENTITY REQUIREMENTS

These automations require the following entities to be available through the PawControl integration:

### Health-Aware Feeding Sensors
- `sensor.{dog_id}_health_feeding_status`
- `sensor.{dog_id}_daily_calorie_target`
- `sensor.{dog_id}_calories_consumed_today`
- `sensor.{dog_id}_calorie_goal_progress`
- `sensor.{dog_id}_portion_adjustment_factor`
- `sensor.{dog_id}_body_condition_score`
- `sensor.{dog_id}_weight_goal_progress`
- `sensor.{dog_id}_health_conditions`
- `sensor.{dog_id}_daily_activity_level`

### Binary Sensors
- `binary_sensor.{dog_id}_health_aware_feeding`
- `binary_sensor.{dog_id}_medication_with_meals`
- `binary_sensor.{dog_id}_health_emergency`

### Services
- `pawcontrol.recalculate_health_portions`
- `pawcontrol.adjust_calories_for_activity`
- `pawcontrol.activate_diabetic_feeding_mode`
- `pawcontrol.feed_with_medication`
- `pawcontrol.generate_weekly_health_report`
- `pawcontrol.activate_emergency_feeding_mode`

## IMPLEMENTATION NOTES

1. **Entity Validation**: Always check entity existence before creating automations
2. **Error Handling**: Include fallback conditions for unavailable sensors
3. **Notification Actions**: Customize mobile app actions based on your setup
4. **Time Zones**: Adjust trigger times for your local timezone
5. **Dog ID**: Replace "rex" with your actual dog ID throughout automations
6. **Service Calls**: Ensure all service calls match your PawControl service definitions

## CUSTOMIZATION

These automations can be customized by:
- Modifying trigger conditions and thresholds
- Adjusting notification messages and actions
- Adding additional health conditions to monitors
- Implementing different calculation algorithms
- Integrating with external health monitoring devices
