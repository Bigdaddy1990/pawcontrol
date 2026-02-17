"""Regression coverage for Home Assistant compatibility stubs."""

import asyncio
from collections.abc import Awaitable, Callable, MutableMapping
from datetime import UTC, datetime
import sys
import types

from tests.helpers import install_homeassistant_stubs


def _assert_support_helpers_follow_handler_hooks(
    handlers: MutableMapping[str, object],
    support_entry_unload: Callable[[object, str], Awaitable[bool]],
    support_remove_from_device: Callable[[object, str], Awaitable[bool]],
    config_entry_type: type,
) -> None:
    class FlowHandler:  # noqa: E111
        @staticmethod
        def async_unload_entry(config_entry: config_entry_type) -> bool:
            del config_entry  # noqa: E111
            return True  # noqa: E111

        @staticmethod
        def async_remove_config_entry_device(config_entry: config_entry_type) -> bool:
            del config_entry  # noqa: E111
            return True  # noqa: E111

    handlers.clear()  # noqa: E111
    handlers["with_support"] = FlowHandler()  # noqa: E111

    assert asyncio.run(support_entry_unload(object(), "with_support")) is True  # noqa: E111
    assert (  # noqa: E111
        asyncio.run(
            support_remove_from_device(
                object(),
                "with_support",
            ),
        )
        is True
    )
    assert asyncio.run(support_entry_unload(object(), "missing")) is False  # noqa: E111
    assert (  # noqa: E111
        asyncio.run(
            support_remove_from_device(
                object(),
                "missing",
            ),
        )
        is False
    )


def test_repairs_flow_stub_matches_home_assistant_contract() -> None:
    """Ensure the repairs flow stub mirrors Home Assistant's base API."""  # noqa: E111

    install_homeassistant_stubs()  # noqa: E111

    from homeassistant.components import repairs  # noqa: E111

    flow = repairs.RepairsFlow()  # noqa: E111

    form_result = flow.async_show_form(  # noqa: E111
        step_id="init",
        data_schema={"schema": True},
        description_placeholders={"placeholder": "value"},
        errors={"base": "issue"},
    )
    assert form_result == {  # noqa: E111
        "type": "form",
        "step_id": "init",
        "data_schema": {"schema": True},
        "description_placeholders": {"placeholder": "value"},
        "errors": {"base": "issue"},
    }

    external_result = flow.async_external_step(  # noqa: E111
        step_id="external",
        url="https://example.com",
    )
    assert external_result == {  # noqa: E111
        "type": "external",
        "step_id": "external",
        "url": "https://example.com",
    }

    create_result = flow.async_create_entry(title="title", data={"k": "v"})  # noqa: E111
    assert create_result == {  # noqa: E111
        "type": "create_entry",
        "title": "title",
        "data": {"k": "v"},
    }

    abort_result = flow.async_abort(reason="done")  # noqa: E111
    assert abort_result == {"type": "abort", "reason": "done"}  # noqa: E111

    menu_result = flow.async_show_menu(  # noqa: E111
        step_id="menu",
        menu_options=["one", "two"],
        description_placeholders={"menu": "placeholder"},
    )
    assert menu_result == {  # noqa: E111
        "type": "menu",
        "step_id": "menu",
        "menu_options": ["one", "two"],
        "description_placeholders": {"menu": "placeholder"},
    }

    progress_result = flow.async_show_progress(  # noqa: E111
        step_id="progress",
        progress_action="waiting",
        description_placeholders={"progress": "placeholder"},
    )
    assert progress_result == {  # noqa: E111
        "type": "progress",
        "step_id": "progress",
        "progress_action": "waiting",
        "description_placeholders": {"progress": "placeholder"},
    }

    progress_done_result = flow.async_show_progress_done(  # noqa: E111
        next_step_id="next",
        description_placeholders={"progress_done": "placeholder"},
    )
    assert progress_done_result == {  # noqa: E111
        "type": "progress_done",
        "next_step_id": "next",
        "description_placeholders": {"progress_done": "placeholder"},
    }

    external_done_result = flow.async_external_step_done(next_step_id="finish")  # noqa: E111
    assert external_done_result == {  # noqa: E111
        "type": "external_done",
        "next_step_id": "finish",
    }


def test_repairs_flow_stub_populates_default_placeholders() -> None:
    """Ensure optional placeholders default to empty mappings."""  # noqa: E111

    install_homeassistant_stubs()  # noqa: E111

    from homeassistant.components import repairs  # noqa: E111

    flow = repairs.RepairsFlow()  # noqa: E111

    menu_result = flow.async_show_menu(step_id="menu", menu_options=["only"])  # noqa: E111
    assert menu_result == {  # noqa: E111
        "type": "menu",
        "step_id": "menu",
        "menu_options": ["only"],
        "description_placeholders": {},
    }

    progress_result = flow.async_show_progress(  # noqa: E111
        step_id="progress",
        progress_action="waiting",
    )
    assert progress_result == {  # noqa: E111
        "type": "progress",
        "step_id": "progress",
        "progress_action": "waiting",
        "description_placeholders": {},
    }

    progress_done_result = flow.async_show_progress_done(next_step_id="next")  # noqa: E111
    assert progress_done_result == {  # noqa: E111
        "type": "progress_done",
        "next_step_id": "next",
        "description_placeholders": {},
    }


def test_options_flow_stub_supports_create_entry_and_form_helpers() -> None:
    """Exercise OptionsFlow helpers to mirror Home Assistant behaviour."""  # noqa: E111

    install_homeassistant_stubs()  # noqa: E111

    from homeassistant.config_entries import FlowResult, OptionsFlow  # noqa: E111

    class SampleOptionsFlow(OptionsFlow):  # noqa: E111
        async def async_step_user(self, user_input: dict[str, object] | None = None):
            assert isinstance(self.async_show_form(step_id="user"), FlowResult)  # noqa: E111
            return await self.async_step_init(user_input)  # noqa: E111

    flow = SampleOptionsFlow()  # noqa: E111
    flow_result = flow.async_show_form(  # noqa: E111
        step_id="init",
        data_schema={"schema": True},
        description_placeholders={"placeholder": "value"},
        errors={"base": "issue"},
    )
    assert flow_result == {  # noqa: E111
        "type": "form",
        "step_id": "init",
        "data_schema": {"schema": True},
        "description_placeholders": {"placeholder": "value"},
        "errors": {"base": "issue"},
    }

    menu_result = flow.async_show_menu(  # noqa: E111
        step_id="menu",
        menu_options=["first", "second"],
        description_placeholders={"menu": "placeholder"},
    )
    assert menu_result == {  # noqa: E111
        "type": "menu",
        "step_id": "menu",
        "menu_options": ["first", "second"],
        "description_placeholders": {"menu": "placeholder"},
    }

    progress_result = flow.async_show_progress(  # noqa: E111
        step_id="progress",
        progress_action="waiting",
        description_placeholders={"progress": "placeholder"},
    )
    assert progress_result == {  # noqa: E111
        "type": "progress",
        "step_id": "progress",
        "progress_action": "waiting",
        "description_placeholders": {"progress": "placeholder"},
    }

    progress_done_result = flow.async_show_progress_done(  # noqa: E111
        next_step_id="done",
        description_placeholders={"progress_done": "placeholder"},
    )
    assert progress_done_result == {  # noqa: E111
        "type": "progress_done",
        "next_step_id": "done",
        "description_placeholders": {"progress_done": "placeholder"},
    }

    abort_result = flow.async_abort(reason="duplicate")  # noqa: E111
    assert abort_result == {"type": "abort", "reason": "duplicate"}  # noqa: E111

    init_result = flow.async_create_entry(title="Options", data={"k": "v"})  # noqa: E111
    assert init_result == {  # noqa: E111
        "type": "create_entry",
        "title": "Options",
        "data": {"k": "v"},
    }

    final_result = flow.async_show_form(step_id="final")  # noqa: E111
    assert final_result == {  # noqa: E111
        "type": "form",
        "step_id": "final",
        "data_schema": None,
        "description_placeholders": {},
        "errors": {},
    }

    options_result = flow.async_create_entry(data={"from_user": True})  # noqa: E111
    assert options_result == {  # noqa: E111
        "type": "create_entry",
        "data": {"from_user": True},
    }


def test_options_flow_stub_handles_external_and_progress_results() -> None:
    """Verify OptionsFlow covers external steps and default placeholders."""  # noqa: E111

    install_homeassistant_stubs()  # noqa: E111

    from homeassistant.config_entries import OptionsFlow  # noqa: E111

    class SampleOptionsFlow(OptionsFlow):  # noqa: E111
        async def async_step_user(self, user_input: dict[str, object] | None = None):
            return self.async_abort(reason="stopped")  # noqa: E111

    flow = SampleOptionsFlow()  # noqa: E111

    external_result = flow.async_external_step(  # noqa: E111
        step_id="external",
        url="https://example.com/continue",
    )
    assert external_result == {  # noqa: E111
        "type": "external",
        "step_id": "external",
        "url": "https://example.com/continue",
    }

    progress_result = flow.async_show_progress(  # noqa: E111
        step_id="progress",
        progress_action="working",
    )
    assert progress_result == {  # noqa: E111
        "type": "progress",
        "step_id": "progress",
        "progress_action": "working",
        "description_placeholders": {},
    }

    progress_done_result = flow.async_show_progress_done(next_step_id="finish")  # noqa: E111
    assert progress_done_result == {  # noqa: E111
        "type": "progress_done",
        "next_step_id": "finish",
        "description_placeholders": {},
    }

    external_done_result = flow.async_external_step_done(  # noqa: E111
        next_step_id="complete",
    )
    assert external_done_result == {  # noqa: E111
        "type": "external_done",
        "next_step_id": "complete",
    }


def test_flow_result_aliases_stay_consistent_with_home_assistant() -> None:
    """Ensure FlowResult exports remain aligned across HA modules."""  # noqa: E111

    install_homeassistant_stubs()  # noqa: E111

    from homeassistant.components import repairs  # noqa: E111
    from homeassistant.config_entries import (  # noqa: E111
        FlowResult as ConfigEntriesFlowResult,  # noqa: E111
    )
    from homeassistant.data_entry_flow import (  # noqa: E111
        FlowResult as DataEntryFlowResult,  # noqa: E111
    )

    from tests.helpers.homeassistant_test_stubs import FlowResult  # noqa: E111

    flow = repairs.RepairsFlow()  # noqa: E111
    assert flow.async_show_form(step_id="user") == {  # noqa: E111
        "type": "form",
        "step_id": "user",
        "data_schema": None,
        "description_placeholders": {},
        "errors": {},
    }

    assert ConfigEntriesFlowResult is DataEntryFlowResult is FlowResult  # noqa: E111


def test_config_entry_states_track_home_assistant_flags() -> None:
    """ConfigEntryState should mirror Home Assistant values and recoverability."""  # noqa: E111

    install_homeassistant_stubs()  # noqa: E111

    from homeassistant.config_entries import ConfigEntry, ConfigEntryState  # noqa: E111

    expected_values = {  # noqa: E111
        "LOADED": "loaded",
        "SETUP_ERROR": "setup_error",
        "MIGRATION_ERROR": "migration_error",
        "SETUP_RETRY": "setup_retry",
        "NOT_LOADED": "not_loaded",
        "FAILED_UNLOAD": "failed_unload",
        "SETUP_IN_PROGRESS": "setup_in_progress",
        "UNLOAD_IN_PROGRESS": "unload_in_progress",
    }
    assert {state.name: state.value for state in ConfigEntryState} == expected_values  # noqa: E111

    expected_recoverable = {  # noqa: E111
        "LOADED": True,
        "SETUP_ERROR": True,
        "MIGRATION_ERROR": False,
        "SETUP_RETRY": True,
        "NOT_LOADED": True,
        "FAILED_UNLOAD": False,
        "SETUP_IN_PROGRESS": False,
        "UNLOAD_IN_PROGRESS": False,
    }
    assert {  # noqa: E111
        state.name: state.recoverable for state in ConfigEntryState
    } == expected_recoverable

    entry = ConfigEntry()  # noqa: E111
    assert entry.state == ConfigEntryState.NOT_LOADED  # noqa: E111
    assert isinstance(entry.state, ConfigEntryState)  # noqa: E111


def test_config_entry_support_metadata_defaults() -> None:
    """ConfigEntry stub should expose Home Assistant support flags and timestamps."""  # noqa: E111

    install_homeassistant_stubs()  # noqa: E111

    from homeassistant.config_entries import ConfigEntry  # noqa: E111

    entry = ConfigEntry()  # noqa: E111

    assert entry._supports_unload is None  # noqa: E111
    assert entry._supports_remove_device is None  # noqa: E111
    assert entry._supports_options is None  # noqa: E111
    assert entry._supports_reconfigure is None  # noqa: E111
    assert entry._supported_subentry_types is None  # noqa: E111
    assert entry.discovery_keys == {}  # noqa: E111
    assert entry.subentries == {}  # noqa: E111
    assert entry.update_listeners == []  # noqa: E111
    assert entry.unique_id is None  # noqa: E111
    assert entry.pref_disable_new_entities is False  # noqa: E111
    assert entry.pref_disable_polling is False  # noqa: E111
    assert entry.pref_disable_discovery is False  # noqa: E111
    assert entry.reason is None  # noqa: E111
    assert entry.error_reason_translation_key is None  # noqa: E111
    assert entry.error_reason_translation_placeholders == {}  # noqa: E111
    assert entry.created_at.tzinfo is UTC  # noqa: E111
    assert entry.modified_at == entry.created_at  # noqa: E111
    assert entry.supports_unload is False  # noqa: E111
    assert entry.supports_remove_device is False  # noqa: E111


def test_config_entry_support_metadata_can_be_overridden() -> None:
    """ConfigEntry stub should accept Home Assistant support metadata overrides."""  # noqa: E111

    install_homeassistant_stubs()  # noqa: E111

    from homeassistant.config_entries import ConfigEntry  # noqa: E111

    created_at = datetime(2024, 1, 1, tzinfo=UTC)  # noqa: E111
    modified_at = datetime(2024, 1, 2, tzinfo=UTC)  # noqa: E111
    entry = ConfigEntry(  # noqa: E111
        created_at=created_at,
        modified_at=modified_at,
        discovery_keys={"dhcp": ("key",)},
        pref_disable_new_entities=True,
        pref_disable_polling=True,
        supports_unload=True,
        supports_remove_device=False,
        supports_options=True,
        supports_reconfigure=False,
        supported_subentry_types={"type": {"add": True}},
        pref_disable_discovery=True,
        subentries_data=[
            {
                "data": {"id": 1},
                "subentry_id": "child-1",
                "subentry_type": "child",
                "title": "Child",
                "unique_id": "child-unique",
            },
        ],
        reason="failed",
        error_reason_translation_key="error.reason",
        error_reason_translation_placeholders={"placeholder": "value"},
    )

    assert entry.created_at is created_at  # noqa: E111
    assert entry.modified_at is modified_at  # noqa: E111
    assert entry.discovery_keys == {"dhcp": ("key",)}  # noqa: E111
    assert entry._supports_unload is True  # noqa: E111
    assert entry._supports_remove_device is False  # noqa: E111
    assert entry._supports_options is True  # noqa: E111
    assert entry._supports_reconfigure is False  # noqa: E111
    assert entry._supported_subentry_types == {"type": {"add": True}}  # noqa: E111
    assert entry.pref_disable_new_entities is True  # noqa: E111
    assert entry.pref_disable_polling is True  # noqa: E111
    assert entry.pref_disable_discovery is True  # noqa: E111
    assert entry.subentries["child-1"].data == {"id": 1}  # noqa: E111
    assert entry.subentries["child-1"].subentry_type == "child"  # noqa: E111
    assert entry.subentries["child-1"].title == "Child"  # noqa: E111
    assert entry.subentries["child-1"].unique_id == "child-unique"  # noqa: E111
    assert entry.reason == "failed"  # noqa: E111
    assert entry.error_reason_translation_key == "error.reason"  # noqa: E111
    assert entry.error_reason_translation_placeholders == {  # noqa: E111
        "placeholder": "value",
    }
    assert entry.supports_unload is True  # noqa: E111
    assert entry.supports_remove_device is False  # noqa: E111


def test_config_entry_support_properties_follow_home_assistant_defaults() -> None:
    """ConfigEntry support helpers should mimic Home Assistant defaults."""  # noqa: E111

    install_homeassistant_stubs()  # noqa: E111

    from homeassistant.config_entries import HANDLERS, ConfigEntry  # noqa: E111

    entry = ConfigEntry()  # noqa: E111

    assert entry._supports_unload is None  # noqa: E111
    assert entry._supports_remove_device is None  # noqa: E111
    assert entry.supports_options is False  # noqa: E111
    assert entry.supports_reconfigure is False  # noqa: E111
    assert entry.supports_unload is False  # noqa: E111
    assert entry.supports_remove_device is False  # noqa: E111
    assert entry.supported_subentry_types == {}  # noqa: E111

    entry.options["option"] = True  # noqa: E111

    assert entry.supports_options is False  # noqa: E111
    assert entry.supports_reconfigure is False  # noqa: E111

    class FlowHandler:  # noqa: E111
        @staticmethod
        def async_supports_options_flow(config_entry: ConfigEntry) -> bool:
            return bool(config_entry.options)  # noqa: E111

        @staticmethod
        def async_unload_entry(config_entry: ConfigEntry) -> bool:
            del config_entry  # noqa: E111
            return True  # noqa: E111

        @staticmethod
        def async_remove_config_entry_device(config_entry: ConfigEntry) -> bool:
            del config_entry  # noqa: E111
            return True  # noqa: E111

        @staticmethod
        def async_supports_reconfigure_flow(config_entry: ConfigEntry) -> bool:
            return bool(config_entry.options)  # noqa: E111

        @staticmethod
        def async_get_supported_subentry_types(
            config_entry: ConfigEntry,
        ) -> dict[str, object]:
            del config_entry  # noqa: E111
            return {  # noqa: E111
                "child": object(),
                "reconfigurable": types.SimpleNamespace(
                    async_step_reconfigure=lambda self: self,
                ),
            }

    HANDLERS[entry.domain] = FlowHandler()  # noqa: E111

    assert entry.supports_options is True  # noqa: E111
    assert entry.supports_reconfigure is True  # noqa: E111
    assert entry.supports_unload is True  # noqa: E111
    assert entry.supports_remove_device is True  # noqa: E111
    assert entry.supported_subentry_types == {  # noqa: E111
        "child": {"supports_reconfigure": False},
        "reconfigurable": {"supports_reconfigure": True},
    }

    override = ConfigEntry(  # noqa: E111
        supports_options=False,
        supports_reconfigure=True,
        supports_unload=False,
        supports_remove_device=False,
        supported_subentry_types={"child": {"add": True}},
    )

    assert override.supports_options is False  # noqa: E111
    assert override.supports_reconfigure is True  # noqa: E111
    assert override.supports_unload is False  # noqa: E111
    assert override.supports_remove_device is False  # noqa: E111
    assert override.supported_subentry_types == {"child": {"add": True}}  # noqa: E111

    HANDLERS.clear()  # noqa: E111


def test_support_helpers_follow_handler_hooks() -> None:
    """Handler-based support helpers should mirror Home Assistant defaults."""  # noqa: E111

    install_homeassistant_stubs()  # noqa: E111

    from homeassistant.config_entries import (  # noqa: E111
        HANDLERS,
        ConfigEntry,
        support_entry_unload,
        support_remove_from_device,
    )

    _assert_support_helpers_follow_handler_hooks(  # noqa: E111
        HANDLERS,
        support_entry_unload,
        support_remove_from_device,
        ConfigEntry,
    )


def test_compat_config_entry_states_include_unload_progress() -> None:
    """Compat ConfigEntryState should expose all Home Assistant enum members."""  # noqa: E111

    from custom_components.pawcontrol.compat import ConfigEntryState  # noqa: E111

    expected_recoverable = {  # noqa: E111
        "NOT_LOADED": True,
        "LOADED": True,
        "SETUP_IN_PROGRESS": False,
        "SETUP_RETRY": True,
        "SETUP_ERROR": True,
        "MIGRATION_ERROR": False,
        "FAILED_UNLOAD": False,
        "UNLOAD_IN_PROGRESS": False,
    }

    assert {state.name: state.value for state in ConfigEntryState} == {  # noqa: E111
        "NOT_LOADED": "not_loaded",
        "LOADED": "loaded",
        "SETUP_IN_PROGRESS": "setup_in_progress",
        "SETUP_RETRY": "setup_retry",
        "SETUP_ERROR": "setup_error",
        "MIGRATION_ERROR": "migration_error",
        "FAILED_UNLOAD": "failed_unload",
        "UNLOAD_IN_PROGRESS": "unload_in_progress",
    }
    assert {state.name: state.recoverable for state in ConfigEntryState} == (  # noqa: E111
        expected_recoverable
    )


def test_compat_config_entry_defaults_match_home_assistant() -> None:
    """Compat ConfigEntry should mirror Home Assistant default metadata."""  # noqa: E111

    from custom_components.pawcontrol.compat import ConfigEntry  # noqa: E111

    entry = ConfigEntry()  # noqa: E111

    assert entry.discovery_keys == {}  # noqa: E111
    assert entry._supports_unload is None  # noqa: E111
    assert entry._supports_remove_device is None  # noqa: E111
    assert entry._supports_options is None  # noqa: E111
    assert entry._supports_reconfigure is None  # noqa: E111
    assert entry._supported_subentry_types is None  # noqa: E111
    assert entry.reason is None  # noqa: E111
    assert entry.error_reason_translation_key is None  # noqa: E111
    assert entry.error_reason_translation_placeholders == {}  # noqa: E111
    assert entry.subentries == {}  # noqa: E111
    assert entry.unique_id is None  # noqa: E111
    assert entry.pref_disable_new_entities is False  # noqa: E111
    assert entry.pref_disable_polling is False  # noqa: E111
    assert entry.pref_disable_discovery is False  # noqa: E111
    assert entry.supports_options is False  # noqa: E111
    assert entry.supports_reconfigure is False  # noqa: E111
    assert entry.supports_unload is False  # noqa: E111
    assert entry.supports_remove_device is False  # noqa: E111
    assert entry.supported_subentry_types == {}  # noqa: E111
    assert entry.created_at.tzinfo is UTC  # noqa: E111
    assert entry.modified_at == entry.created_at  # noqa: E111


def test_compat_config_entry_preference_overrides() -> None:
    """Compat ConfigEntry should accept preference overrides like Home Assistant."""  # noqa: E111

    from custom_components.pawcontrol.compat import ConfigEntry  # noqa: E111

    entry = ConfigEntry(  # noqa: E111
        pref_disable_new_entities=True,
        pref_disable_polling=True,
        pref_disable_discovery=True,
    )

    assert entry.pref_disable_new_entities is True  # noqa: E111
    assert entry.pref_disable_polling is True  # noqa: E111
    assert entry.pref_disable_discovery is True  # noqa: E111


def test_compat_config_entry_support_flags_follow_handler_defaults() -> None:
    """Compat ConfigEntry should derive support flags from handler hooks."""  # noqa: E111

    from custom_components.pawcontrol.compat import ConfigEntry  # noqa: E111

    entry = ConfigEntry()  # noqa: E111
    entry.options["option"] = True  # noqa: E111

    assert entry.supports_options is False  # noqa: E111
    assert entry.supports_reconfigure is False  # noqa: E111
    assert entry.supports_unload is False  # noqa: E111
    assert entry.supports_remove_device is False  # noqa: E111

    class FlowHandler:  # noqa: E111
        @staticmethod
        def async_supports_options_flow(config_entry: ConfigEntry) -> bool:
            return bool(config_entry.options)  # noqa: E111

        @staticmethod
        def async_unload_entry(config_entry: ConfigEntry) -> bool:
            del config_entry  # noqa: E111
            return True  # noqa: E111

        @staticmethod
        def async_remove_config_entry_device(config_entry: ConfigEntry) -> bool:
            del config_entry  # noqa: E111
            return True  # noqa: E111

        @staticmethod
        def async_supports_reconfigure_flow(config_entry: ConfigEntry) -> bool:
            return False  # noqa: E111

        @staticmethod
        def async_get_supported_subentry_types(
            config_entry: ConfigEntry,
        ) -> dict[str, object]:
            del config_entry  # noqa: E111
            return {"child": object()}  # noqa: E111

    handlers = getattr(sys.modules[ConfigEntry.__module__], "HANDLERS", None)  # noqa: E111
    if handlers is None:  # noqa: E111
        from custom_components.pawcontrol.compat import HANDLERS as COMPAT_HANDLERS

        handlers = COMPAT_HANDLERS

    handlers[entry.domain] = FlowHandler()  # noqa: E111

    assert entry.supports_options is True  # noqa: E111
    assert entry.supports_reconfigure is False  # noqa: E111
    assert entry.supports_unload is True  # noqa: E111
    assert entry.supports_remove_device is True  # noqa: E111
    assert entry.supported_subentry_types == {  # noqa: E111
        "child": {"supports_reconfigure": False},
    }

    handlers.clear()  # noqa: E111


def test_compat_support_helpers_follow_handler_hooks() -> None:
    """Compat support helpers should mirror Home Assistant handler checks."""  # noqa: E111

    from custom_components.pawcontrol.compat import (  # noqa: E111
        HANDLERS,
        ConfigEntry,
        support_entry_unload,
        support_remove_from_device,
    )

    _assert_support_helpers_follow_handler_hooks(  # noqa: E111
        HANDLERS,
        support_entry_unload,
        support_remove_from_device,
        ConfigEntry,
    )


def test_compat_config_entry_metadata_can_be_overridden() -> None:
    """Compat ConfigEntry should honor support metadata overrides."""  # noqa: E111

    from custom_components.pawcontrol.compat import ConfigEntry  # noqa: E111

    created_at = datetime(2024, 1, 1, tzinfo=UTC)  # noqa: E111
    modified_at = datetime(2024, 1, 2, tzinfo=UTC)  # noqa: E111
    entry = ConfigEntry(  # noqa: E111
        created_at=created_at,
        modified_at=modified_at,
        discovery_keys={"dhcp": ("key",)},
        supports_unload=True,
        supports_remove_device=False,
        supports_options=True,
        supports_reconfigure=False,
        supported_subentry_types={"child": {"add": True}},
        pref_disable_discovery=True,
        subentries_data=[
            {
                "data": {"meta": "value"},
                "subentry_id": "child-1",
                "subentry_type": "child",
                "title": "Child",
                "unique_id": "child-unique",
            },
        ],
        reason="failed",
        error_reason_translation_key="error.reason",
        error_reason_translation_placeholders={"placeholder": "value"},
    )

    assert entry.created_at is created_at  # noqa: E111
    assert entry.modified_at is modified_at  # noqa: E111
    assert entry.discovery_keys == {"dhcp": ("key",)}  # noqa: E111
    assert entry._supports_unload is True  # noqa: E111
    assert entry._supports_remove_device is False  # noqa: E111
    assert entry._supports_options is True  # noqa: E111
    assert entry._supports_reconfigure is False  # noqa: E111
    assert entry._supported_subentry_types == {"child": {"add": True}}  # noqa: E111
    assert entry.pref_disable_discovery is True  # noqa: E111
    assert entry.subentries["child-1"].data == {"meta": "value"}  # noqa: E111
    assert entry.subentries["child-1"].subentry_type == "child"  # noqa: E111
    assert entry.subentries["child-1"].title == "Child"  # noqa: E111
    assert entry.subentries["child-1"].unique_id == "child-unique"  # noqa: E111
    assert entry.reason == "failed"  # noqa: E111
    assert entry.error_reason_translation_key == "error.reason"  # noqa: E111
    assert entry.error_reason_translation_placeholders == {  # noqa: E111
        "placeholder": "value",
    }
    assert entry.supports_options is True  # noqa: E111
    assert entry.supports_reconfigure is False  # noqa: E111
    assert entry.supports_unload is True  # noqa: E111
    assert entry.supports_remove_device is False  # noqa: E111
    assert entry.supported_subentry_types == {"child": {"add": True}}  # noqa: E111


def test_registry_singletons_are_shared_between_helpers() -> None:
    """Device and entity registry helpers should return shared instances."""  # noqa: E111

    install_homeassistant_stubs()  # noqa: E111

    from homeassistant.helpers import device_registry, entity_registry  # noqa: E111

    device_registry_first = device_registry.async_get(None)  # noqa: E111
    device_registry_second = device_registry.async_get(None)  # noqa: E111
    assert device_registry_first is device_registry_second  # noqa: E111

    stored_device = device_registry_first.async_get_or_create(  # noqa: E111
        id="device-one",
        config_entry_id="entry-id",
    )
    assert device_registry_second.async_entries_for_config_entry("entry-id") == [  # noqa: E111
        stored_device,
    ]

    entity_registry_first = entity_registry.async_get(None)  # noqa: E111
    entity_registry_second = entity_registry.async_get(None)  # noqa: E111
    assert entity_registry_first is entity_registry_second  # noqa: E111

    stored_entity = entity_registry_first.async_get_or_create(  # noqa: E111
        "sensor.shared",
        config_entry_id="entry-id",
    )
    assert entity_registry_second.async_entries_for_config_entry("entry-id") == [  # noqa: E111
        stored_entity,
    ]


def test_entity_and_device_registry_factories_track_entries() -> None:
    """Validate registry stubs used by entity factory helpers."""  # noqa: E111

    install_homeassistant_stubs()  # noqa: E111

    from homeassistant.helpers import device_registry, entity_registry  # noqa: E111

    device_registry_get = device_registry.async_get  # noqa: E111
    entity_registry_get = entity_registry.async_get  # noqa: E111

    created_at = datetime(2024, 1, 1, tzinfo=UTC)  # noqa: E111
    updated_at = datetime(2024, 6, 1, tzinfo=UTC)  # noqa: E111

    device_registry_stub = device_registry_get(None)  # noqa: E111
    device = device_registry_stub.async_get_or_create(  # noqa: E111
        id="device-one",
        config_entry_id="entry-id",
        identifiers={("domain", "one")},
        connections={("mac", "00:11"), ("mac", "00:11")},
        name="device",
        manufacturer="Example",
        model="Model",
        model_id="model-123",
        area_id="kitchen",
        suggested_area="hallway",
        disabled_by="user",
        primary_config_entry="entry-id",
        created_at=created_at,
        modified_at=created_at,
    )
    other_device = device_registry_stub.async_get_or_create(  # noqa: E111
        id="device-two",
        config_entry_id="other",
    )
    updated_device = device_registry_stub.async_update_device(  # noqa: E111
        device.id,
        name="updated",
        config_entry_id="entry-id",
        configuration_url="https://example.com",
        config_entries={"entry-id", "extra"},
        name_by_user="friendly",
        area_id="kitchen",
        suggested_area="hallway",
        disabled_by="user",
        primary_config_entry="entry-id",
        preferred_area_id="kitchen",
        model_id="model-456",
        modified_at=updated_at,
    )

    device_entries = device_registry_stub.async_entries_for_config_entry(  # noqa: E111
        "entry-id",
    )
    assert device_entries == [device]  # noqa: E111
    assert device.config_entries == {"entry-id", "extra"}  # noqa: E111
    assert device.identifiers == {("domain", "one")}  # noqa: E111
    assert device.connections == {("mac", "00:11")}  # noqa: E111
    assert device.model_id == "model-456"  # noqa: E111
    assert updated_device.name == "updated"  # noqa: E111
    assert updated_device.configuration_url == "https://example.com"  # noqa: E111
    assert updated_device.area_id == "kitchen"  # noqa: E111
    assert updated_device.suggested_area == "hallway"  # noqa: E111
    assert updated_device.disabled_by == "user"  # noqa: E111
    assert updated_device.primary_config_entry == "entry-id"  # noqa: E111
    assert updated_device.name_by_user == "friendly"  # noqa: E111
    assert updated_device.preferred_area_id == "kitchen"  # noqa: E111
    assert device_registry.async_entries_for_config_entry(  # noqa: E111
        device_registry_stub,
        "other",
    ) == [other_device]

    entity_registry_stub = entity_registry_get(None)  # noqa: E111
    entity = entity_registry_stub.async_get_or_create(  # noqa: E111
        "sensor.test",
        device_id=device.id,
        config_entry_id="entry-id",
        unique_id="uid",
        platform="sensor",
        original_name="Original",
        original_device_class="battery",
        aliases={"alias-one"},
        area_id="kitchen",
        disabled_by="user",
        entity_category="diagnostic",
        icon="mdi:dog",
        original_icon="mdi:cat",
        unit_of_measurement="°C",
        original_unit_of_measurement="°C",
        preferred_area_id="kitchen",
        hidden_by="integration",
        created_at=created_at,
        modified_at=created_at,
    )
    other_entity = entity_registry_stub.async_get_or_create(  # noqa: E111
        "sensor.other",
        device_id=device.id,
        config_entry_id="other",
    )
    updated_entity = entity_registry_stub.async_update_entity(  # noqa: E111
        entity.entity_id,
        name="sensor",
        config_entry_id="entry-id",
        config_entries={"entry-id", "extra"},
        translation_key="translation",
        aliases={"alias-two"},
        area_id="kitchen",
        disabled_by="user",
        entity_category="diagnostic",
        icon="mdi:dog",
        original_icon="mdi:cat",
        unit_of_measurement="°C",
        original_unit_of_measurement="°F",
        preferred_area_id="kitchen",
        hidden_by="integration",
        modified_at=updated_at,
    )
    assert updated_entity.device_id == device.id  # noqa: E111
    assert updated_entity.name == "sensor"  # noqa: E111
    assert updated_entity.unique_id == "uid"  # noqa: E111
    assert updated_entity.config_entries == {"entry-id", "extra"}  # noqa: E111
    assert updated_entity.original_device_class == "battery"  # noqa: E111
    assert updated_entity.translation_key == "translation"  # noqa: E111
    assert updated_entity.aliases == {"alias-two"}  # noqa: E111
    assert updated_entity.area_id == "kitchen"  # noqa: E111
    assert updated_entity.preferred_area_id == "kitchen"  # noqa: E111
    assert updated_entity.hidden_by == "integration"  # noqa: E111
    assert updated_entity.disabled_by == "user"  # noqa: E111
    assert updated_entity.entity_category == "diagnostic"  # noqa: E111
    assert updated_entity.icon == "mdi:dog"  # noqa: E111
    assert updated_entity.original_icon == "mdi:cat"  # noqa: E111
    assert updated_entity.unit_of_measurement == "°C"  # noqa: E111
    assert updated_entity.original_unit_of_measurement == "°F"  # noqa: E111
    assert device.created_at == created_at  # noqa: E111
    assert device.modified_at == updated_at  # noqa: E111
    assert updated_entity.created_at == created_at  # noqa: E111
    assert updated_entity.modified_at == updated_at  # noqa: E111
    assert entity_registry_stub.async_entries_for_config_entry(  # noqa: E111
        "entry-id",
    ) == [entity]
    assert entity_registry.async_entries_for_config_entry(  # noqa: E111
        entity_registry_stub,
        "other",
    ) == [other_entity]


def test_device_registry_lookup_matches_identifiers_and_connections() -> None:
    """Device registry lookups should mirror Home Assistant helper behaviour."""  # noqa: E111

    install_homeassistant_stubs()  # noqa: E111

    from homeassistant.helpers import device_registry  # noqa: E111

    registry = device_registry.async_get(None)  # noqa: E111
    matched = registry.async_get_or_create(  # noqa: E111
        id="device-one",
        identifiers={("domain", "one")},
        connections={("mac", "00:11:22:33:44:55")},
    )
    registry.async_get_or_create(  # noqa: E111
        id="device-two",
        identifiers={("domain", "two")},
        connections={("mac", "aa:bb:cc:dd:ee:ff")},
    )

    assert (  # noqa: E111
        registry.async_get_device(
            identifiers={("domain", "one")},
        )
        is matched
    )
    assert (  # noqa: E111
        device_registry.async_get_device(
            registry,
            connections={("mac", "00:11:22:33:44:55")},
        )
        is matched
    )
    assert (  # noqa: E111
        device_registry.async_get_device(
            registry,
            identifiers=set(),
        )
        is None
    )
    assert (  # noqa: E111
        device_registry.async_get_device(
            registry,
            connections={("mac", "ff:ee:dd:cc:bb:aa")},
        )
        is None
    )


def test_device_registry_merges_existing_devices_by_hints() -> None:
    """Device registry should reuse entries matching identifiers or connections."""  # noqa: E111

    install_homeassistant_stubs()  # noqa: E111

    from homeassistant.helpers import device_registry  # noqa: E111

    registry = device_registry.async_get(None)  # noqa: E111

    primary = registry.async_get_or_create(  # noqa: E111
        id="device-one",
        config_entry_id="entry-one",
        identifiers={("domain", "one")},
        connections={("mac", "00:11:22:33:44:55")},
    )
    merged = registry.async_get_or_create(  # noqa: E111
        id="device-two",
        config_entry_id="entry-two",
        identifiers={("domain", "one")},
        connections={("mac", "00:11:22:33:44:55"), ("mdns", "paw.local")},
    )

    assert merged is primary  # noqa: E111
    assert set(registry.devices) == {"device-one"}  # noqa: E111
    assert primary.connections == {  # noqa: E111
        ("mac", "00:11:22:33:44:55"),
        ("mdns", "paw.local"),
    }
    assert primary.identifiers == {("domain", "one")}  # noqa: E111
    assert primary.config_entries == {"entry-one", "entry-two"}  # noqa: E111


def test_device_registry_generates_unique_ids_without_hints() -> None:
    """Device registry should mint unique IDs when none are provided."""  # noqa: E111

    install_homeassistant_stubs()  # noqa: E111

    from homeassistant.helpers import device_registry  # noqa: E111

    registry = device_registry.async_get(None)  # noqa: E111

    first = registry.async_get_or_create(config_entry_id="entry-one")  # noqa: E111
    second = registry.async_get_or_create(config_entry_id="entry-two")  # noqa: E111

    assert first is not second  # noqa: E111
    assert first.id != second.id  # noqa: E111
    assert first.id.startswith("device-")  # noqa: E111
    assert second.id.startswith("device-")  # noqa: E111
    assert registry.devices[first.id] is first  # noqa: E111
    assert registry.devices[second.id] is second  # noqa: E111


def test_device_registry_tracks_prefix_ids_when_minting_new_devices() -> None:
    """Device registry should avoid colliding with explicit device-* IDs."""  # noqa: E111

    install_homeassistant_stubs()  # noqa: E111

    from homeassistant.helpers import device_registry  # noqa: E111

    registry = device_registry.async_get(None)  # noqa: E111

    manual = registry.async_get_or_create(id="device-10")  # noqa: E111
    first = registry.async_get_or_create()  # noqa: E111
    second = registry.async_get_or_create()  # noqa: E111

    assert manual.id == "device-10"  # noqa: E111
    assert first.id == "device-11"  # noqa: E111
    assert second.id == "device-12"  # noqa: E111
    assert set(registry.devices) == {"device-10", "device-11", "device-12"}  # noqa: E111


def test_device_registry_fetches_devices_by_id() -> None:
    """Device registry should resolve devices by ID like Home Assistant."""  # noqa: E111

    install_homeassistant_stubs()  # noqa: E111

    from homeassistant.helpers import device_registry  # noqa: E111

    registry = device_registry.async_get(None)  # noqa: E111

    stored = registry.async_get_or_create(id="device-one")  # noqa: E111
    matched = registry.async_get("device-one")  # noqa: E111
    helper_matched = device_registry.async_get_device(  # noqa: E111
        registry,
        device_id="device-one",
    )

    assert matched is stored  # noqa: E111
    assert helper_matched is stored  # noqa: E111
    assert registry.async_get("missing") is None  # noqa: E111
    assert (  # noqa: E111
        device_registry.async_get_device(
            registry,
            device_id="missing",
        )
        is None
    )


def test_device_registry_accumulates_identifiers_and_connections() -> None:
    """Device registry should merge new hints into existing entries."""  # noqa: E111

    install_homeassistant_stubs()  # noqa: E111

    from homeassistant.helpers import device_registry  # noqa: E111

    registry = device_registry.async_get(None)  # noqa: E111

    device = registry.async_get_or_create(  # noqa: E111
        id="device-one",
        config_entry_id="entry-one",
        identifiers={("domain", "one")},
        connections={("mac", "00:11:22:33:44:55")},
    )
    merged = registry.async_get_or_create(  # noqa: E111
        id="device-one",
        config_entry_id="entry-two",
        identifiers={("domain", "two")},
        connections={("mdns", "paw.local")},
    )

    assert merged is device  # noqa: E111
    assert device.identifiers == {("domain", "one"), ("domain", "two")}  # noqa: E111
    assert device.connections == {  # noqa: E111
        ("mac", "00:11:22:33:44:55"),
        ("mdns", "paw.local"),
    }
    assert device.config_entries == {"entry-one", "entry-two"}  # noqa: E111
    assert (  # noqa: E111
        device_registry.async_get_device(
            registry,
            identifiers={("domain", "two")},
        )
        is device
    )
    assert (  # noqa: E111
        device_registry.async_get_device(
            registry,
            connections={("mdns", "paw.local")},
        )
        is device
    )


def test_entity_registry_entries_filter_by_device_id() -> None:
    """Entity registry should support device-specific filtering like HA."""  # noqa: E111

    install_homeassistant_stubs()  # noqa: E111

    from homeassistant.helpers import entity_registry  # noqa: E111

    registry = entity_registry.async_get(None)  # noqa: E111
    first = registry.async_get_or_create(  # noqa: E111
        "sensor.first",
        device_id="device-one",
        config_entry_id="entry-id",
    )
    second = registry.async_get_or_create(  # noqa: E111
        "sensor.second",
        device_id="device-two",
        config_entry_id="entry-id",
    )

    assert registry.async_entries_for_device("device-one") == [first]  # noqa: E111
    assert entity_registry.async_entries_for_device(  # noqa: E111
        registry,
        "device-two",
    ) == [second]
    assert entity_registry.async_entries_for_device(registry, "missing") == []  # noqa: E111


def test_entity_registry_merges_entries_by_unique_id_and_platform() -> None:
    """Entity registry should reuse entities sharing unique IDs and platforms."""  # noqa: E111

    install_homeassistant_stubs()  # noqa: E111

    from homeassistant.helpers import entity_registry  # noqa: E111

    registry = entity_registry.async_get(None)  # noqa: E111

    primary = registry.async_get_or_create(  # noqa: E111
        "sensor.first",
        device_id="device-one",
        config_entry_id="entry-one",
        unique_id="unique",
        platform="sensor",
    )
    merged = registry.async_get_or_create(  # noqa: E111
        "sensor.second",
        device_id="device-two",
        config_entry_id="entry-two",
        unique_id="unique",
        platform="sensor",
    )

    assert merged is primary  # noqa: E111
    assert set(registry.entities) == {"sensor.first"}  # noqa: E111
    assert primary.device_id == "device-two"  # noqa: E111
    assert primary.config_entries == {"entry-one", "entry-two"}  # noqa: E111


def test_device_registry_remove_follows_home_assistant_helper() -> None:
    """Device removal should be exposed via registry and module helpers."""  # noqa: E111

    install_homeassistant_stubs()  # noqa: E111

    from homeassistant.helpers import device_registry  # noqa: E111

    registry = device_registry.async_get(None)  # noqa: E111
    device = registry.async_get_or_create(  # noqa: E111
        id="device-one",
        config_entry_id="entry-id",
        identifiers={("domain", "one")},
    )

    assert registry.async_entries_for_config_entry("entry-id") == [device]  # noqa: E111
    assert device_registry.async_entries_for_config_entry(registry, "entry-id") == [  # noqa: E111
        device,
    ]
    assert registry.async_remove_device("device-one")  # noqa: E111
    assert device_registry.async_remove_device(registry, "device-one") is False  # noqa: E111
    assert registry.async_entries_for_config_entry("entry-id") == []  # noqa: E111
    assert (  # noqa: E111
        device_registry.async_entries_for_config_entry(
            registry,
            "entry-id",
        )
        == []
    )


def test_entity_registry_remove_follows_home_assistant_helper() -> None:
    """Entity removal should be exposed via registry and module helpers."""  # noqa: E111

    install_homeassistant_stubs()  # noqa: E111

    from homeassistant.helpers import entity_registry  # noqa: E111

    registry = entity_registry.async_get(None)  # noqa: E111
    entity = registry.async_get_or_create(  # noqa: E111
        "sensor.test",
        device_id="device-one",
        config_entry_id="entry-id",
    )

    assert registry.async_entries_for_device("device-one") == [entity]  # noqa: E111
    assert entity_registry.async_entries_for_config_entry(registry, "entry-id") == [  # noqa: E111
        entity,
    ]
    assert registry.async_remove("sensor.test")  # noqa: E111
    assert entity_registry.async_remove(registry, "sensor.test") is False  # noqa: E111
    assert registry.async_entries_for_device("device-one") == []  # noqa: E111
    assert (  # noqa: E111
        entity_registry.async_entries_for_config_entry(
            registry,
            "entry-id",
        )
        == []
    )


def test_issue_registry_helpers_store_and_remove_issues() -> None:
    """Issue registry stubs should mirror Home Assistant helpers."""  # noqa: E111

    install_homeassistant_stubs()  # noqa: E111

    from homeassistant.helpers import issue_registry  # noqa: E111

    registry = issue_registry.async_get(object())  # noqa: E111
    issue_severity_cls = issue_registry.IssueSeverity  # noqa: E111
    assert issue_registry.async_get(object()) is registry  # noqa: E111
    assert (  # noqa: E111
        issue_registry.async_get_issue(
            object(),
            "test_domain",
            "missing_config",
        )
        is None
    )

    created = issue_registry.async_create_issue(  # noqa: E111
        object(),
        "test_domain",
        "missing_config",
        active=True,
        is_persistent=True,
        issue_domain="upstream",
        translation_domain="custom_domain",
        translation_key="missing_config",
        translation_placeholders={"path": "/config"},
        severity=issue_severity_cls.ERROR,
        is_fixable=True,
        breaks_in_ha_version="2025.1",
        learn_more_url="https://example.test",
        data={"context": "details"},
        dismissed_version="2024.9",
    )

    created_at = created["created"]  # noqa: E111
    dismissed_at = created["dismissed"]  # noqa: E111
    assert created == registry.issues[("test_domain", "missing_config")]  # noqa: E111
    assert created["translation_domain"] == "custom_domain"  # noqa: E111
    assert created["translation_placeholders"] == {"path": "/config"}  # noqa: E111
    assert created["data"] == {"context": "details"}  # noqa: E111
    assert created["is_persistent"] is True  # noqa: E111
    assert created["issue_domain"] == "upstream"  # noqa: E111
    assert created["dismissed_version"] == "2024.9"  # noqa: E111
    assert created["ignored"] is False  # noqa: E111
    assert created["active"] is True  # noqa: E111
    assert created["severity"] is issue_severity_cls.ERROR  # noqa: E111
    assert isinstance(created_at, datetime)  # noqa: E111
    assert created_at.tzinfo is UTC  # noqa: E111
    assert isinstance(dismissed_at, datetime)  # noqa: E111
    assert dismissed_at.tzinfo is UTC  # noqa: E111
    assert (  # noqa: E111
        issue_registry.async_get_issue(
            object(),
            "test_domain",
            "missing_config",
        )
        == created
    )

    updated = issue_registry.async_create_issue(  # noqa: E111
        object(),
        "test_domain",
        "missing_config",
        active=True,
        translation_key="updated_key",
        translation_placeholders={"path": "/new"},
        severity="warning",
    )

    assert updated == registry.issues[("test_domain", "missing_config")]  # noqa: E111
    assert updated["translation_key"] == "updated_key"  # noqa: E111
    assert updated["translation_domain"] == "custom_domain"  # noqa: E111
    assert updated["translation_placeholders"] == {"path": "/new"}  # noqa: E111
    assert updated["severity"] is issue_severity_cls.WARNING  # noqa: E111
    assert updated["is_fixable"] is True  # noqa: E111
    assert updated["created"] == created_at  # noqa: E111
    assert updated["dismissed"] == dismissed_at  # noqa: E111
    assert updated["is_persistent"] is True  # noqa: E111
    assert updated["issue_domain"] == "upstream"  # noqa: E111
    assert updated["learn_more_url"] == "https://example.test"  # noqa: E111
    assert updated["breaks_in_ha_version"] == "2025.1"  # noqa: E111
    assert updated["dismissed_version"] == "2024.9"  # noqa: E111
    assert updated["ignored"] is False  # noqa: E111
    assert updated["active"] is True  # noqa: E111
    assert (  # noqa: E111
        issue_registry.async_get_issue(
            object(),
            "test_domain",
            "missing_config",
        )
        == updated
    )

    redismissed = issue_registry.async_create_issue(  # noqa: E111
        object(),
        "test_domain",
        "missing_config",
        active=True,
        dismissed_version="2026.2",
    )

    assert redismissed["dismissed_version"] == "2026.2"  # noqa: E111
    assert redismissed["translation_key"] == "updated_key"  # noqa: E111
    assert redismissed["translation_domain"] == "custom_domain"  # noqa: E111
    assert redismissed["dismissed"] == dismissed_at  # noqa: E111
    assert redismissed["ignored"] is False  # noqa: E111
    assert redismissed["active"] is True  # noqa: E111

    from homeassistant import const  # noqa: E111

    ignored = issue_registry.async_ignore_issue(  # noqa: E111
        object(),
        "test_domain",
        "missing_config",
        True,
    )
    assert ignored["dismissed_version"] == const.__version__  # noqa: E111
    assert ignored["dismissed"] != dismissed_at  # noqa: E111
    assert ignored["ignored"] is True  # noqa: E111
    assert ignored["active"] is False  # noqa: E111
    assert (  # noqa: E111
        issue_registry.async_get_issue(
            object(),
            "test_domain",
            "missing_config",
        )
        == ignored
    )

    unignored = issue_registry.async_ignore_issue(  # noqa: E111
        object(),
        "test_domain",
        "missing_config",
        False,
    )
    assert unignored["dismissed_version"] is None  # noqa: E111
    assert unignored["dismissed"] is None  # noqa: E111
    assert unignored["ignored"] is False  # noqa: E111
    assert unignored["active"] is True  # noqa: E111
    assert (  # noqa: E111
        issue_registry.async_get_issue(
            object(),
            "test_domain",
            "missing_config",
        )
        == unignored
    )

    defaulted = issue_registry.async_create_issue(  # noqa: E111
        object(),
        "another_domain",
        "missing_translation",
    )
    assert defaulted["severity"] is issue_severity_cls.WARNING  # noqa: E111
    assert defaulted["translation_domain"] == "another_domain"  # noqa: E111
    assert defaulted["translation_key"] == "missing_translation"  # noqa: E111
    assert defaulted["issue_domain"] == "another_domain"  # noqa: E111

    assert issue_registry.async_delete_issue(  # noqa: E111
        object(),
        "test_domain",
        "missing_config",
    )
    assert ("test_domain", "missing_config") not in registry.issues  # noqa: E111
    assert (  # noqa: E111
        issue_registry.async_delete_issue(
            object(),
            "test_domain",
            "missing_config",
        )
        is False
    )
    assert (  # noqa: E111
        issue_registry.async_delete_issue(
            object(),
            "test_domain",
            "absent",
        )
        is False
    )
    assert (  # noqa: E111
        issue_registry.async_get_issue(
            object(),
            "test_domain",
            "missing_config",
        )
        is None
    )


def test_issue_registry_preserves_optional_metadata() -> None:
    """Issue registry stubs should retain optional metadata when not provided."""  # noqa: E111

    install_homeassistant_stubs()  # noqa: E111

    from homeassistant.helpers import issue_registry  # noqa: E111

    registry = issue_registry.async_get(object())  # noqa: E111

    defaulted = issue_registry.async_create_issue(  # noqa: E111
        object(),
        "domain",
        "missing_metadata",
    )

    assert defaulted["data"] is None  # noqa: E111
    assert defaulted["translation_placeholders"] is None  # noqa: E111
    assert defaulted["is_fixable"] is False  # noqa: E111
    assert defaulted["is_persistent"] is False  # noqa: E111
    assert defaulted["translation_key"] == "missing_metadata"  # noqa: E111
    assert defaulted["issue_domain"] == "domain"  # noqa: E111

    seeded = issue_registry.async_create_issue(  # noqa: E111
        object(),
        "domain",
        "missing_metadata",
        translation_placeholders={"path": "/config"},
        data={"context": "details"},
        is_fixable=True,
        is_persistent=True,
        severity="error",
    )

    assert seeded["translation_placeholders"] == {"path": "/config"}  # noqa: E111
    assert seeded["data"] == {"context": "details"}  # noqa: E111
    assert seeded["is_fixable"] is True  # noqa: E111
    assert seeded["is_persistent"] is True  # noqa: E111

    retained = issue_registry.async_create_issue(  # noqa: E111
        object(),
        "domain",
        "missing_metadata",
        translation_key="carry_existing",
    )

    assert retained["translation_placeholders"] == {"path": "/config"}  # noqa: E111
    assert retained["data"] == {"context": "details"}  # noqa: E111
    assert retained["is_fixable"] is True  # noqa: E111
    assert retained["is_persistent"] is True  # noqa: E111
    assert registry.issues[("domain", "missing_metadata")] == retained  # noqa: E111
