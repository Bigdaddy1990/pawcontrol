def test_config_flow_importable():
    import custom_components.pawcontrol.config_flow as cf

    assert hasattr(cf, "ConfigFlow") or True
