import pytest

pytestmark = pytest.mark.asyncio


async def _make_device(hass, entry, dog_id):
    from custom_components.pawcontrol import DOMAIN
    from homeassistant.helpers import device_registry as dr

    dev_reg = dr.async_get(hass)
    return dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, dog_id)}
    )


async def test_stale_devices_issue_when_auto_false(hass, monkeypatch):
    import custom_components.pawcontrol as comp
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.helpers import issue_registry as ir

    entry = ConfigEntry(
        version=1,
        domain=comp.DOMAIN,
        title="Paw",
        data={},
        source="user",
        entry_id="e1",
        options={"auto_prune_devices": False},
    )
    await comp.async_setup_entry(hass, entry)

    # Create a stale device (dog-x not in coordinator data)
    await _make_device(hass, entry, "dog-x")

    # Manually trigger pruning pass in report-mode
    await comp._auto_prune_devices(hass, entry, auto=False)

    # An issue should exist
    registry = ir.async_get(hass)
    issues = [
        i
        for i in registry.issues.values()
        if i.domain == comp.DOMAIN and i.issue_id == "stale_devices"
    ]
    assert issues, "Expected stale_devices issue to be created"


async def test_stale_devices_auto_prunes(hass, monkeypatch):
    import custom_components.pawcontrol as comp
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.helpers import device_registry as dr

    entry = ConfigEntry(
        version=1,
        domain=comp.DOMAIN,
        title="Paw",
        data={},
        source="user",
        entry_id="e2",
        options={"auto_prune_devices": True},
    )
    await comp.async_setup_entry(hass, entry)

    dev = await _make_device(hass, entry, "dog-y")

    # Ensure device exists
    dev_reg = dr.async_get(hass)
    assert dev_reg.async_get(dev.id) is not None

    # Auto prune removes it
    removed = await comp._auto_prune_devices(hass, entry, auto=True)
    assert removed >= 1
    assert dev_reg.async_get(dev.id) is None


async def test_prune_service_removes(hass):
    import custom_components.pawcontrol as comp
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.helpers import device_registry as dr

    entry = ConfigEntry(
        version=1,
        domain=comp.DOMAIN,
        title="Paw",
        data={},
        source="user",
        entry_id="e3",
        options={},
    )
    await comp.async_setup_entry(hass, entry)

    dev_reg = dr.async_get(hass)
    dev = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(comp.DOMAIN, "dog-z")}
    )

    # call service
    await hass.services.async_call(
        comp.DOMAIN, "prune_stale_devices", {"auto": True}, blocking=True
    )
    await hass.async_block_till_done()
    # device should be gone (not in known set)
    assert dev_reg.async_get(dev.id) is None
