

def test_actions_module_importable():
    import custom_components.pawcontrol.device_action as device_action

    assert hasattr(device_action, "async_get_actions")
    assert "toggle_geofence_alerts" in device_action.ACTION_TYPES
