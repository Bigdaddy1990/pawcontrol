"""Additional coverage for compatibility helpers."""

import pytest

from custom_components.pawcontrol import compat


@pytest.mark.asyncio
async def test_support_hooks_reflect_registered_handler_capabilities() -> None:
    """Support helpers should check the handler registry for known hooks."""

    class HandlerWithHooks:
        async def async_unload_entry(self) -> bool:  # pragma: no cover - shape only
            return True

        async def async_remove_config_entry_device(self) -> bool:  # pragma: no cover
            return True

    compat.HANDLERS.clear()
    compat.HANDLERS["pawcontrol"] = HandlerWithHooks()

    assert await compat.support_entry_unload(None, "pawcontrol") is True
    assert await compat.support_remove_from_device(None, "pawcontrol") is True


@pytest.mark.asyncio
async def test_support_hooks_return_false_for_unknown_or_partial_handlers() -> None:
    """Support helpers should fail closed when hooks are missing."""

    class HandlerWithoutHooks:
        pass

    compat.HANDLERS.clear()
    compat.HANDLERS["pawcontrol"] = HandlerWithoutHooks()

    assert await compat.support_entry_unload(None, "pawcontrol") is False
    assert await compat.support_remove_from_device(None, "pawcontrol") is False
    assert await compat.support_entry_unload(None, "missing") is False


def test_config_entry_state_from_value_supports_name_and_raw_value() -> None:
    """ConfigEntryState conversion should handle both enum names and values."""
    assert (
        compat.ConfigEntryState.from_value("loaded")
        is compat.ConfigEntryState.LOADED
    )
    assert (
        compat.ConfigEntryState.from_value("SETUP_RETRY")
        is compat.ConfigEntryState.SETUP_RETRY
    )

    with pytest.raises(ValueError):
        compat.ConfigEntryState.from_value("definitely_unknown")


def test_build_subentries_normalizes_input() -> None:
    """Subentry builder should coerce optional fields into deterministic structures."""
    built = compat._build_subentries(
        [
            {
                "subentry_type": "dog",
                "title": "Rex",
                "data": {"age": 3},
                "unique_id": 42,
            },
            {
                "subentry_id": "garden",
                "data": "not_a_mapping",
                "title": "Backyard",
            },
        ],
    )

    assert set(built) == {"subentry_1", "garden"}
    assert built["subentry_1"].data == {"age": 3}
    assert built["subentry_1"].unique_id == "42"
    assert built["garden"].data == {}
    assert built["garden"].subentry_type == "subentry"
