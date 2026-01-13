"""Regression coverage for Home Assistant compatibility stubs."""

from __future__ import annotations

import asyncio
import sys
import types
from datetime import UTC, datetime

from tests.helpers import install_homeassistant_stubs


def test_repairs_flow_stub_matches_home_assistant_contract() -> None:
    """Ensure the repairs flow stub mirrors Home Assistant's base API."""

    install_homeassistant_stubs()

    from homeassistant.components import repairs

    flow = repairs.RepairsFlow()

    form_result = flow.async_show_form(
        step_id='init',
        data_schema={'schema': True},
        description_placeholders={'placeholder': 'value'},
        errors={'base': 'issue'},
    )
    assert form_result == {
        'type': 'form',
        'step_id': 'init',
        'data_schema': {'schema': True},
        'description_placeholders': {'placeholder': 'value'},
        'errors': {'base': 'issue'},
    }

    external_result = flow.async_external_step(
        step_id='external', url='https://example.com'
    )
    assert external_result == {
        'type': 'external',
        'step_id': 'external',
        'url': 'https://example.com',
    }

    create_result = flow.async_create_entry(title='title', data={'k': 'v'})
    assert create_result == {
        'type': 'create_entry',
        'title': 'title',
        'data': {'k': 'v'},
    }

    abort_result = flow.async_abort(reason='done')
    assert abort_result == {'type': 'abort', 'reason': 'done'}

    menu_result = flow.async_show_menu(
        step_id='menu',
        menu_options=['one', 'two'],
        description_placeholders={'menu': 'placeholder'},
    )
    assert menu_result == {
        'type': 'menu',
        'step_id': 'menu',
        'menu_options': ['one', 'two'],
        'description_placeholders': {'menu': 'placeholder'},
    }

    progress_result = flow.async_show_progress(
        step_id='progress',
        progress_action='waiting',
        description_placeholders={'progress': 'placeholder'},
    )
    assert progress_result == {
        'type': 'progress',
        'step_id': 'progress',
        'progress_action': 'waiting',
        'description_placeholders': {'progress': 'placeholder'},
    }

    progress_done_result = flow.async_show_progress_done(
        next_step_id='next',
        description_placeholders={'progress_done': 'placeholder'},
    )
    assert progress_done_result == {
        'type': 'progress_done',
        'next_step_id': 'next',
        'description_placeholders': {'progress_done': 'placeholder'},
    }

    external_done_result = flow.async_external_step_done(next_step_id='finish')
    assert external_done_result == {'type': 'external_done', 'next_step_id': 'finish'}


def test_repairs_flow_stub_populates_default_placeholders() -> None:
    """Ensure optional placeholders default to empty mappings."""

    install_homeassistant_stubs()

    from homeassistant.components import repairs

    flow = repairs.RepairsFlow()

    menu_result = flow.async_show_menu(step_id='menu', menu_options=['only'])
    assert menu_result == {
        'type': 'menu',
        'step_id': 'menu',
        'menu_options': ['only'],
        'description_placeholders': {},
    }

    progress_result = flow.async_show_progress(
        step_id='progress', progress_action='waiting'
    )
    assert progress_result == {
        'type': 'progress',
        'step_id': 'progress',
        'progress_action': 'waiting',
        'description_placeholders': {},
    }

    progress_done_result = flow.async_show_progress_done(next_step_id='next')
    assert progress_done_result == {
        'type': 'progress_done',
        'next_step_id': 'next',
        'description_placeholders': {},
    }


def test_options_flow_stub_supports_create_entry_and_form_helpers() -> None:
    """Exercise OptionsFlow helpers to mirror Home Assistant behaviour."""

    install_homeassistant_stubs()

    from homeassistant.config_entries import FlowResult, OptionsFlow

    class SampleOptionsFlow(OptionsFlow):
        async def async_step_user(self, user_input: dict[str, object] | None = None):
            assert isinstance(self.async_show_form(step_id='user'), FlowResult)
            return await self.async_step_init(user_input)

    flow = SampleOptionsFlow()
    flow_result = flow.async_show_form(
        step_id='init',
        data_schema={'schema': True},
        description_placeholders={'placeholder': 'value'},
        errors={'base': 'issue'},
    )
    assert flow_result == {
        'type': 'form',
        'step_id': 'init',
        'data_schema': {'schema': True},
        'description_placeholders': {'placeholder': 'value'},
        'errors': {'base': 'issue'},
    }

    menu_result = flow.async_show_menu(
        step_id='menu',
        menu_options=['first', 'second'],
        description_placeholders={'menu': 'placeholder'},
    )
    assert menu_result == {
        'type': 'menu',
        'step_id': 'menu',
        'menu_options': ['first', 'second'],
        'description_placeholders': {'menu': 'placeholder'},
    }

    progress_result = flow.async_show_progress(
        step_id='progress',
        progress_action='waiting',
        description_placeholders={'progress': 'placeholder'},
    )
    assert progress_result == {
        'type': 'progress',
        'step_id': 'progress',
        'progress_action': 'waiting',
        'description_placeholders': {'progress': 'placeholder'},
    }

    progress_done_result = flow.async_show_progress_done(
        next_step_id='done',
        description_placeholders={'progress_done': 'placeholder'},
    )
    assert progress_done_result == {
        'type': 'progress_done',
        'next_step_id': 'done',
        'description_placeholders': {'progress_done': 'placeholder'},
    }

    abort_result = flow.async_abort(reason='duplicate')
    assert abort_result == {'type': 'abort', 'reason': 'duplicate'}

    init_result = flow.async_create_entry(title='Options', data={'k': 'v'})
    assert init_result == {
        'type': 'create_entry',
        'title': 'Options',
        'data': {'k': 'v'},
    }

    final_result = flow.async_show_form(step_id='final')
    assert final_result == {
        'type': 'form',
        'step_id': 'final',
        'data_schema': None,
        'description_placeholders': {},
        'errors': {},
    }

    options_result = flow.async_create_entry(data={'from_user': True})
    assert options_result == {
        'type': 'create_entry',
        'data': {'from_user': True},
    }


def test_options_flow_stub_handles_external_and_progress_results() -> None:
    """Verify OptionsFlow covers external steps and default placeholders."""

    install_homeassistant_stubs()

    from homeassistant.config_entries import OptionsFlow

    class SampleOptionsFlow(OptionsFlow):
        async def async_step_user(self, user_input: dict[str, object] | None = None):
            return self.async_abort(reason='stopped')

    flow = SampleOptionsFlow()

    external_result = flow.async_external_step(
        step_id='external', url='https://example.com/continue'
    )
    assert external_result == {
        'type': 'external',
        'step_id': 'external',
        'url': 'https://example.com/continue',
    }

    progress_result = flow.async_show_progress(
        step_id='progress', progress_action='working'
    )
    assert progress_result == {
        'type': 'progress',
        'step_id': 'progress',
        'progress_action': 'working',
        'description_placeholders': {},
    }

    progress_done_result = flow.async_show_progress_done(next_step_id='finish')
    assert progress_done_result == {
        'type': 'progress_done',
        'next_step_id': 'finish',
        'description_placeholders': {},
    }

    external_done_result = flow.async_external_step_done(next_step_id='complete')
    assert external_done_result == {
        'type': 'external_done',
        'next_step_id': 'complete',
    }


def test_flow_result_aliases_stay_consistent_with_home_assistant() -> None:
    """Ensure FlowResult exports remain aligned across HA modules."""

    install_homeassistant_stubs()

    from homeassistant.components import repairs
    from homeassistant.config_entries import FlowResult as ConfigEntriesFlowResult
    from homeassistant.data_entry_flow import FlowResult as DataEntryFlowResult

    from tests.helpers.homeassistant_test_stubs import FlowResult

    flow = repairs.RepairsFlow()
    assert flow.async_show_form(step_id='user') == {
        'type': 'form',
        'step_id': 'user',
        'data_schema': None,
        'description_placeholders': {},
        'errors': {},
    }

    assert ConfigEntriesFlowResult is DataEntryFlowResult is FlowResult


def test_config_entry_states_track_home_assistant_flags() -> None:
    """ConfigEntryState should mirror Home Assistant values and recoverability."""

    install_homeassistant_stubs()

    from homeassistant.config_entries import ConfigEntry, ConfigEntryState

    expected_values = {
        'LOADED': 'loaded',
        'SETUP_ERROR': 'setup_error',
        'MIGRATION_ERROR': 'migration_error',
        'SETUP_RETRY': 'setup_retry',
        'NOT_LOADED': 'not_loaded',
        'FAILED_UNLOAD': 'failed_unload',
        'SETUP_IN_PROGRESS': 'setup_in_progress',
        'UNLOAD_IN_PROGRESS': 'unload_in_progress',
    }
    assert {state.name: state.value for state in ConfigEntryState} == expected_values

    expected_recoverable = {
        'LOADED': True,
        'SETUP_ERROR': True,
        'MIGRATION_ERROR': False,
        'SETUP_RETRY': True,
        'NOT_LOADED': True,
        'FAILED_UNLOAD': False,
        'SETUP_IN_PROGRESS': False,
        'UNLOAD_IN_PROGRESS': False,
    }
    assert {
        state.name: state.recoverable for state in ConfigEntryState
    } == expected_recoverable

    entry = ConfigEntry()
    assert entry.state == ConfigEntryState.NOT_LOADED
    assert isinstance(entry.state, ConfigEntryState)


def test_config_entry_support_metadata_defaults() -> None:
    """ConfigEntry stub should expose Home Assistant support flags and timestamps."""

    install_homeassistant_stubs()

    from homeassistant.config_entries import ConfigEntry

    entry = ConfigEntry()

    assert entry._supports_unload is None
    assert entry._supports_remove_device is None
    assert entry._supports_options is None
    assert entry._supports_reconfigure is None
    assert entry._supported_subentry_types is None
    assert entry.discovery_keys == {}
    assert entry.subentries == {}
    assert entry.update_listeners == []
    assert entry.unique_id is None
    assert entry.pref_disable_new_entities is False
    assert entry.pref_disable_polling is False
    assert entry.pref_disable_discovery is False
    assert entry.reason is None
    assert entry.error_reason_translation_key is None
    assert entry.error_reason_translation_placeholders == {}
    assert entry.created_at.tzinfo is UTC
    assert entry.modified_at == entry.created_at
    assert entry.supports_unload is False
    assert entry.supports_remove_device is False


def test_config_entry_support_metadata_can_be_overridden() -> None:
    """ConfigEntry stub should accept Home Assistant support metadata overrides."""

    install_homeassistant_stubs()

    from homeassistant.config_entries import ConfigEntry

    created_at = datetime(2024, 1, 1, tzinfo=UTC)
    modified_at = datetime(2024, 1, 2, tzinfo=UTC)
    entry = ConfigEntry(
        created_at=created_at,
        modified_at=modified_at,
        discovery_keys={'dhcp': ('key',)},
        pref_disable_new_entities=True,
        pref_disable_polling=True,
        supports_unload=True,
        supports_remove_device=False,
        supports_options=True,
        supports_reconfigure=False,
        supported_subentry_types={'type': {'add': True}},
        pref_disable_discovery=True,
        subentries_data=[
            {
                'data': {'id': 1},
                'subentry_id': 'child-1',
                'subentry_type': 'child',
                'title': 'Child',
                'unique_id': 'child-unique',
            }
        ],
        reason='failed',
        error_reason_translation_key='error.reason',
        error_reason_translation_placeholders={'placeholder': 'value'},
    )

    assert entry.created_at is created_at
    assert entry.modified_at is modified_at
    assert entry.discovery_keys == {'dhcp': ('key',)}
    assert entry._supports_unload is True
    assert entry._supports_remove_device is False
    assert entry._supports_options is True
    assert entry._supports_reconfigure is False
    assert entry._supported_subentry_types == {'type': {'add': True}}
    assert entry.pref_disable_new_entities is True
    assert entry.pref_disable_polling is True
    assert entry.pref_disable_discovery is True
    assert entry.subentries['child-1'].data == {'id': 1}
    assert entry.subentries['child-1'].subentry_type == 'child'
    assert entry.subentries['child-1'].title == 'Child'
    assert entry.subentries['child-1'].unique_id == 'child-unique'
    assert entry.reason == 'failed'
    assert entry.error_reason_translation_key == 'error.reason'
    assert entry.error_reason_translation_placeholders == {'placeholder': 'value'}
    assert entry.supports_unload is True
    assert entry.supports_remove_device is False


def test_config_entry_support_properties_follow_home_assistant_defaults() -> None:
    """ConfigEntry support helpers should mimic Home Assistant defaults."""

    install_homeassistant_stubs()

    from homeassistant.config_entries import HANDLERS, ConfigEntry

    entry = ConfigEntry()

    assert entry._supports_unload is None
    assert entry._supports_remove_device is None
    assert entry.supports_options is False
    assert entry.supports_reconfigure is False
    assert entry.supports_unload is False
    assert entry.supports_remove_device is False
    assert entry.supported_subentry_types == {}

    entry.options['option'] = True

    assert entry.supports_options is False
    assert entry.supports_reconfigure is False

    class FlowHandler:
        @staticmethod
        def async_supports_options_flow(config_entry: ConfigEntry) -> bool:
            return bool(config_entry.options)

        @staticmethod
        def async_unload_entry(config_entry: ConfigEntry) -> bool:
            del config_entry
            return True

        @staticmethod
        def async_remove_config_entry_device(config_entry: ConfigEntry) -> bool:
            del config_entry
            return True

        @staticmethod
        def async_supports_reconfigure_flow(config_entry: ConfigEntry) -> bool:
            return bool(config_entry.options)

        @staticmethod
        def async_get_supported_subentry_types(
            config_entry: ConfigEntry,
        ) -> dict[str, object]:
            del config_entry
            return {
                'child': object(),
                'reconfigurable': types.SimpleNamespace(
                    async_step_reconfigure=lambda self: self
                ),
            }

    HANDLERS[entry.domain] = FlowHandler()

    assert entry.supports_options is True
    assert entry.supports_reconfigure is True
    assert entry.supports_unload is True
    assert entry.supports_remove_device is True
    assert entry.supported_subentry_types == {
        'child': {'supports_reconfigure': False},
        'reconfigurable': {'supports_reconfigure': True},
    }

    override = ConfigEntry(
        supports_options=False,
        supports_reconfigure=True,
        supports_unload=False,
        supports_remove_device=False,
        supported_subentry_types={'child': {'add': True}},
    )

    assert override.supports_options is False
    assert override.supports_reconfigure is True
    assert override.supports_unload is False
    assert override.supports_remove_device is False
    assert override.supported_subentry_types == {'child': {'add': True}}

    HANDLERS.clear()


def test_support_helpers_follow_handler_hooks() -> None:
    """Handler-based support helpers should mirror Home Assistant defaults."""

    install_homeassistant_stubs()

    from homeassistant.config_entries import (
        HANDLERS,
        ConfigEntry,
        support_entry_unload,
        support_remove_from_device,
    )

    class FlowHandler:
        @staticmethod
        def async_unload_entry(config_entry: ConfigEntry) -> bool:
            del config_entry
            return True

        @staticmethod
        def async_remove_config_entry_device(config_entry: ConfigEntry) -> bool:
            del config_entry
            return True

    HANDLERS.clear()
    HANDLERS['with_support'] = FlowHandler()

    assert asyncio.run(support_entry_unload(object(), 'with_support')) is True
    assert asyncio.run(support_remove_from_device(object(), 'with_support')) is True
    assert asyncio.run(support_entry_unload(object(), 'missing')) is False
    assert asyncio.run(support_remove_from_device(object(), 'missing')) is False


def test_compat_config_entry_states_include_unload_progress() -> None:
    """Compat ConfigEntryState should expose all Home Assistant enum members."""

    from custom_components.pawcontrol.compat import ConfigEntryState

    expected_recoverable = {
        'NOT_LOADED': True,
        'LOADED': True,
        'SETUP_IN_PROGRESS': False,
        'SETUP_RETRY': True,
        'SETUP_ERROR': True,
        'MIGRATION_ERROR': False,
        'FAILED_UNLOAD': False,
        'UNLOAD_IN_PROGRESS': False,
    }

    assert {state.name: state.value for state in ConfigEntryState} == {
        'NOT_LOADED': 'not_loaded',
        'LOADED': 'loaded',
        'SETUP_IN_PROGRESS': 'setup_in_progress',
        'SETUP_RETRY': 'setup_retry',
        'SETUP_ERROR': 'setup_error',
        'MIGRATION_ERROR': 'migration_error',
        'FAILED_UNLOAD': 'failed_unload',
        'UNLOAD_IN_PROGRESS': 'unload_in_progress',
    }
    assert {state.name: state.recoverable for state in ConfigEntryState} == (
        expected_recoverable
    )


def test_compat_config_entry_defaults_match_home_assistant() -> None:
    """Compat ConfigEntry should mirror Home Assistant default metadata."""

    from custom_components.pawcontrol.compat import ConfigEntry

    entry = ConfigEntry()

    assert entry.discovery_keys == {}
    assert entry._supports_unload is None
    assert entry._supports_remove_device is None
    assert entry._supports_options is None
    assert entry._supports_reconfigure is None
    assert entry._supported_subentry_types is None
    assert entry.reason is None
    assert entry.error_reason_translation_key is None
    assert entry.error_reason_translation_placeholders == {}
    assert entry.subentries == {}
    assert entry.unique_id is None
    assert entry.pref_disable_new_entities is False
    assert entry.pref_disable_polling is False
    assert entry.pref_disable_discovery is False
    assert entry.supports_options is False
    assert entry.supports_reconfigure is False
    assert entry.supports_unload is False
    assert entry.supports_remove_device is False
    assert entry.supported_subentry_types == {}
    assert entry.created_at.tzinfo is UTC
    assert entry.modified_at == entry.created_at


def test_compat_config_entry_preference_overrides() -> None:
    """Compat ConfigEntry should accept preference overrides like Home Assistant."""

    from custom_components.pawcontrol.compat import ConfigEntry

    entry = ConfigEntry(
        pref_disable_new_entities=True,
        pref_disable_polling=True,
        pref_disable_discovery=True,
    )

    assert entry.pref_disable_new_entities is True
    assert entry.pref_disable_polling is True
    assert entry.pref_disable_discovery is True


def test_compat_config_entry_support_flags_follow_handler_defaults() -> None:
    """Compat ConfigEntry should derive support flags from handler hooks."""

    from custom_components.pawcontrol.compat import ConfigEntry

    entry = ConfigEntry()
    entry.options['option'] = True

    assert entry.supports_options is False
    assert entry.supports_reconfigure is False
    assert entry.supports_unload is False
    assert entry.supports_remove_device is False

    class FlowHandler:
        @staticmethod
        def async_supports_options_flow(config_entry: ConfigEntry) -> bool:
            return bool(config_entry.options)

        @staticmethod
        def async_unload_entry(config_entry: ConfigEntry) -> bool:
            del config_entry
            return True

        @staticmethod
        def async_remove_config_entry_device(config_entry: ConfigEntry) -> bool:
            del config_entry
            return True

        @staticmethod
        def async_supports_reconfigure_flow(config_entry: ConfigEntry) -> bool:
            return False

        @staticmethod
        def async_get_supported_subentry_types(
            config_entry: ConfigEntry,
        ) -> dict[str, object]:
            del config_entry
            return {'child': object()}

    handlers = getattr(sys.modules[ConfigEntry.__module__], 'HANDLERS', None)
    if handlers is None:
        from custom_components.pawcontrol.compat import HANDLERS as COMPAT_HANDLERS

        handlers = COMPAT_HANDLERS

    handlers[entry.domain] = FlowHandler()

    assert entry.supports_options is True
    assert entry.supports_reconfigure is False
    assert entry.supports_unload is True
    assert entry.supports_remove_device is True
    assert entry.supported_subentry_types == {
        'child': {'supports_reconfigure': False},
    }

    handlers.clear()


def test_compat_support_helpers_follow_handler_hooks() -> None:
    """Compat support helpers should mirror Home Assistant handler checks."""

    from custom_components.pawcontrol.compat import (
        HANDLERS,
        ConfigEntry,
        support_entry_unload,
        support_remove_from_device,
    )

    class FlowHandler:
        @staticmethod
        def async_unload_entry(config_entry: ConfigEntry) -> bool:
            del config_entry
            return True

        @staticmethod
        def async_remove_config_entry_device(config_entry: ConfigEntry) -> bool:
            del config_entry
            return True

    HANDLERS.clear()
    HANDLERS['with_support'] = FlowHandler()

    assert asyncio.run(support_entry_unload(object(), 'with_support')) is True
    assert asyncio.run(support_remove_from_device(object(), 'with_support')) is True
    assert asyncio.run(support_entry_unload(object(), 'missing')) is False
    assert asyncio.run(support_remove_from_device(object(), 'missing')) is False


def test_compat_config_entry_metadata_can_be_overridden() -> None:
    """Compat ConfigEntry should honor support metadata overrides."""

    from custom_components.pawcontrol.compat import ConfigEntry

    created_at = datetime(2024, 1, 1, tzinfo=UTC)
    modified_at = datetime(2024, 1, 2, tzinfo=UTC)
    entry = ConfigEntry(
        created_at=created_at,
        modified_at=modified_at,
        discovery_keys={'dhcp': ('key',)},
        supports_unload=True,
        supports_remove_device=False,
        supports_options=True,
        supports_reconfigure=False,
        supported_subentry_types={'child': {'add': True}},
        pref_disable_discovery=True,
        subentries_data=[
            {
                'data': {'meta': 'value'},
                'subentry_id': 'child-1',
                'subentry_type': 'child',
                'title': 'Child',
                'unique_id': 'child-unique',
            }
        ],
        reason='failed',
        error_reason_translation_key='error.reason',
        error_reason_translation_placeholders={'placeholder': 'value'},
    )

    assert entry.created_at is created_at
    assert entry.modified_at is modified_at
    assert entry.discovery_keys == {'dhcp': ('key',)}
    assert entry._supports_unload is True
    assert entry._supports_remove_device is False
    assert entry._supports_options is True
    assert entry._supports_reconfigure is False
    assert entry._supported_subentry_types == {'child': {'add': True}}
    assert entry.pref_disable_discovery is True
    assert entry.subentries['child-1'].data == {'meta': 'value'}
    assert entry.subentries['child-1'].subentry_type == 'child'
    assert entry.subentries['child-1'].title == 'Child'
    assert entry.subentries['child-1'].unique_id == 'child-unique'
    assert entry.reason == 'failed'
    assert entry.error_reason_translation_key == 'error.reason'
    assert entry.error_reason_translation_placeholders == {'placeholder': 'value'}
    assert entry.supports_options is True
    assert entry.supports_reconfigure is False
    assert entry.supports_unload is True
    assert entry.supports_remove_device is False
    assert entry.supported_subentry_types == {'child': {'add': True}}


def test_registry_singletons_are_shared_between_helpers() -> None:
    """Device and entity registry helpers should return shared instances."""

    install_homeassistant_stubs()

    from homeassistant.helpers import device_registry, entity_registry

    device_registry_first = device_registry.async_get(None)
    device_registry_second = device_registry.async_get(None)
    assert device_registry_first is device_registry_second

    stored_device = device_registry_first.async_get_or_create(
        id='device-one', config_entry_id='entry-id'
    )
    assert device_registry_second.async_entries_for_config_entry('entry-id') == [
        stored_device
    ]

    entity_registry_first = entity_registry.async_get(None)
    entity_registry_second = entity_registry.async_get(None)
    assert entity_registry_first is entity_registry_second

    stored_entity = entity_registry_first.async_get_or_create(
        'sensor.shared', config_entry_id='entry-id'
    )
    assert entity_registry_second.async_entries_for_config_entry('entry-id') == [
        stored_entity
    ]


def test_entity_and_device_registry_factories_track_entries() -> None:
    """Validate registry stubs used by entity factory helpers."""

    install_homeassistant_stubs()

    from homeassistant.helpers import device_registry, entity_registry

    device_registry_get = device_registry.async_get
    entity_registry_get = entity_registry.async_get

    created_at = datetime(2024, 1, 1, tzinfo=UTC)
    updated_at = datetime(2024, 6, 1, tzinfo=UTC)

    device_registry_stub = device_registry_get(None)
    device = device_registry_stub.async_get_or_create(
        id='device-one',
        config_entry_id='entry-id',
        identifiers={('domain', 'one')},
        connections={('mac', '00:11'), ('mac', '00:11')},
        name='device',
        manufacturer='Example',
        model='Model',
        model_id='model-123',
        area_id='kitchen',
        suggested_area='hallway',
        disabled_by='user',
        primary_config_entry='entry-id',
        created_at=created_at,
        modified_at=created_at,
    )
    other_device = device_registry_stub.async_get_or_create(
        id='device-two', config_entry_id='other'
    )
    updated_device = device_registry_stub.async_update_device(
        device.id,
        name='updated',
        config_entry_id='entry-id',
        configuration_url='https://example.com',
        config_entries={'entry-id', 'extra'},
        name_by_user='friendly',
        area_id='kitchen',
        suggested_area='hallway',
        disabled_by='user',
        primary_config_entry='entry-id',
        preferred_area_id='kitchen',
        model_id='model-456',
        modified_at=updated_at,
    )

    device_entries = device_registry_stub.async_entries_for_config_entry('entry-id')
    assert device_entries == [device]
    assert device.config_entries == {'entry-id', 'extra'}
    assert device.identifiers == {('domain', 'one')}
    assert device.connections == {('mac', '00:11')}
    assert device.model_id == 'model-456'
    assert updated_device.name == 'updated'
    assert updated_device.configuration_url == 'https://example.com'
    assert updated_device.area_id == 'kitchen'
    assert updated_device.suggested_area == 'hallway'
    assert updated_device.disabled_by == 'user'
    assert updated_device.primary_config_entry == 'entry-id'
    assert updated_device.name_by_user == 'friendly'
    assert updated_device.preferred_area_id == 'kitchen'
    assert device_registry.async_entries_for_config_entry(
        device_registry_stub, 'other'
    ) == [other_device]

    entity_registry_stub = entity_registry_get(None)
    entity = entity_registry_stub.async_get_or_create(
        'sensor.test',
        device_id=device.id,
        config_entry_id='entry-id',
        unique_id='uid',
        platform='sensor',
        original_name='Original',
        original_device_class='battery',
        aliases={'alias-one'},
        area_id='kitchen',
        disabled_by='user',
        entity_category='diagnostic',
        icon='mdi:dog',
        original_icon='mdi:cat',
        unit_of_measurement='°C',
        original_unit_of_measurement='°C',
        preferred_area_id='kitchen',
        hidden_by='integration',
        created_at=created_at,
        modified_at=created_at,
    )
    other_entity = entity_registry_stub.async_get_or_create(
        'sensor.other', device_id=device.id, config_entry_id='other'
    )
    updated_entity = entity_registry_stub.async_update_entity(
        entity.entity_id,
        name='sensor',
        config_entry_id='entry-id',
        config_entries={'entry-id', 'extra'},
        translation_key='translation',
        aliases={'alias-two'},
        area_id='kitchen',
        disabled_by='user',
        entity_category='diagnostic',
        icon='mdi:dog',
        original_icon='mdi:cat',
        unit_of_measurement='°C',
        original_unit_of_measurement='°F',
        preferred_area_id='kitchen',
        hidden_by='integration',
        modified_at=updated_at,
    )
    assert updated_entity.device_id == device.id
    assert updated_entity.name == 'sensor'
    assert updated_entity.unique_id == 'uid'
    assert updated_entity.config_entries == {'entry-id', 'extra'}
    assert updated_entity.original_device_class == 'battery'
    assert updated_entity.translation_key == 'translation'
    assert updated_entity.aliases == {'alias-two'}
    assert updated_entity.area_id == 'kitchen'
    assert updated_entity.preferred_area_id == 'kitchen'
    assert updated_entity.hidden_by == 'integration'
    assert updated_entity.disabled_by == 'user'
    assert updated_entity.entity_category == 'diagnostic'
    assert updated_entity.icon == 'mdi:dog'
    assert updated_entity.original_icon == 'mdi:cat'
    assert updated_entity.unit_of_measurement == '°C'
    assert updated_entity.original_unit_of_measurement == '°F'
    assert device.created_at == created_at
    assert device.modified_at == updated_at
    assert updated_entity.created_at == created_at
    assert updated_entity.modified_at == updated_at
    assert entity_registry_stub.async_entries_for_config_entry('entry-id') == [entity]
    assert entity_registry.async_entries_for_config_entry(
        entity_registry_stub, 'other'
    ) == [other_entity]


def test_device_registry_lookup_matches_identifiers_and_connections() -> None:
    """Device registry lookups should mirror Home Assistant helper behaviour."""

    install_homeassistant_stubs()

    from homeassistant.helpers import device_registry

    registry = device_registry.async_get(None)
    matched = registry.async_get_or_create(
        id='device-one',
        identifiers={('domain', 'one')},
        connections={('mac', '00:11:22:33:44:55')},
    )
    registry.async_get_or_create(
        id='device-two',
        identifiers={('domain', 'two')},
        connections={('mac', 'aa:bb:cc:dd:ee:ff')},
    )

    assert registry.async_get_device(identifiers={('domain', 'one')}) is matched
    assert (
        device_registry.async_get_device(
            registry, connections={('mac', '00:11:22:33:44:55')}
        )
        is matched
    )
    assert device_registry.async_get_device(registry, identifiers=set()) is None
    assert (
        device_registry.async_get_device(
            registry, connections={('mac', 'ff:ee:dd:cc:bb:aa')}
        )
        is None
    )


def test_device_registry_merges_existing_devices_by_hints() -> None:
    """Device registry should reuse entries matching identifiers or connections."""

    install_homeassistant_stubs()

    from homeassistant.helpers import device_registry

    registry = device_registry.async_get(None)

    primary = registry.async_get_or_create(
        id='device-one',
        config_entry_id='entry-one',
        identifiers={('domain', 'one')},
        connections={('mac', '00:11:22:33:44:55')},
    )
    merged = registry.async_get_or_create(
        id='device-two',
        config_entry_id='entry-two',
        identifiers={('domain', 'one')},
        connections={('mac', '00:11:22:33:44:55'), ('mdns', 'paw.local')},
    )

    assert merged is primary
    assert set(registry.devices) == {'device-one'}
    assert primary.connections == {
        ('mac', '00:11:22:33:44:55'),
        ('mdns', 'paw.local'),
    }
    assert primary.identifiers == {('domain', 'one')}
    assert primary.config_entries == {'entry-one', 'entry-two'}


def test_device_registry_generates_unique_ids_without_hints() -> None:
    """Device registry should mint unique IDs when none are provided."""

    install_homeassistant_stubs()

    from homeassistant.helpers import device_registry

    registry = device_registry.async_get(None)

    first = registry.async_get_or_create(config_entry_id='entry-one')
    second = registry.async_get_or_create(config_entry_id='entry-two')

    assert first is not second
    assert first.id != second.id
    assert first.id.startswith('device-')
    assert second.id.startswith('device-')
    assert registry.devices[first.id] is first
    assert registry.devices[second.id] is second


def test_device_registry_tracks_prefix_ids_when_minting_new_devices() -> None:
    """Device registry should avoid colliding with explicit device-* IDs."""

    install_homeassistant_stubs()

    from homeassistant.helpers import device_registry

    registry = device_registry.async_get(None)

    manual = registry.async_get_or_create(id='device-10')
    first = registry.async_get_or_create()
    second = registry.async_get_or_create()

    assert manual.id == 'device-10'
    assert first.id == 'device-11'
    assert second.id == 'device-12'
    assert set(registry.devices) == {'device-10', 'device-11', 'device-12'}


def test_device_registry_fetches_devices_by_id() -> None:
    """Device registry should resolve devices by ID like Home Assistant."""

    install_homeassistant_stubs()

    from homeassistant.helpers import device_registry

    registry = device_registry.async_get(None)

    stored = registry.async_get_or_create(id='device-one')
    matched = registry.async_get('device-one')
    helper_matched = device_registry.async_get_device(registry, device_id='device-one')

    assert matched is stored
    assert helper_matched is stored
    assert registry.async_get('missing') is None
    assert device_registry.async_get_device(registry, device_id='missing') is None


def test_device_registry_accumulates_identifiers_and_connections() -> None:
    """Device registry should merge new hints into existing entries."""

    install_homeassistant_stubs()

    from homeassistant.helpers import device_registry

    registry = device_registry.async_get(None)

    device = registry.async_get_or_create(
        id='device-one',
        config_entry_id='entry-one',
        identifiers={('domain', 'one')},
        connections={('mac', '00:11:22:33:44:55')},
    )
    merged = registry.async_get_or_create(
        id='device-one',
        config_entry_id='entry-two',
        identifiers={('domain', 'two')},
        connections={('mdns', 'paw.local')},
    )

    assert merged is device
    assert device.identifiers == {('domain', 'one'), ('domain', 'two')}
    assert device.connections == {
        ('mac', '00:11:22:33:44:55'),
        ('mdns', 'paw.local'),
    }
    assert device.config_entries == {'entry-one', 'entry-two'}
    assert (
        device_registry.async_get_device(registry, identifiers={('domain', 'two')})
        is device
    )
    assert (
        device_registry.async_get_device(registry, connections={('mdns', 'paw.local')})
        is device
    )


def test_entity_registry_entries_filter_by_device_id() -> None:
    """Entity registry should support device-specific filtering like HA."""

    install_homeassistant_stubs()

    from homeassistant.helpers import entity_registry

    registry = entity_registry.async_get(None)
    first = registry.async_get_or_create(
        'sensor.first', device_id='device-one', config_entry_id='entry-id'
    )
    second = registry.async_get_or_create(
        'sensor.second', device_id='device-two', config_entry_id='entry-id'
    )

    assert registry.async_entries_for_device('device-one') == [first]
    assert entity_registry.async_entries_for_device(registry, 'device-two') == [second]
    assert entity_registry.async_entries_for_device(registry, 'missing') == []


def test_entity_registry_merges_entries_by_unique_id_and_platform() -> None:
    """Entity registry should reuse entities sharing unique IDs and platforms."""

    install_homeassistant_stubs()

    from homeassistant.helpers import entity_registry

    registry = entity_registry.async_get(None)

    primary = registry.async_get_or_create(
        'sensor.first',
        device_id='device-one',
        config_entry_id='entry-one',
        unique_id='unique',
        platform='sensor',
    )
    merged = registry.async_get_or_create(
        'sensor.second',
        device_id='device-two',
        config_entry_id='entry-two',
        unique_id='unique',
        platform='sensor',
    )

    assert merged is primary
    assert set(registry.entities) == {'sensor.first'}
    assert primary.device_id == 'device-two'
    assert primary.config_entries == {'entry-one', 'entry-two'}


def test_device_registry_remove_follows_home_assistant_helper() -> None:
    """Device removal should be exposed via registry and module helpers."""

    install_homeassistant_stubs()

    from homeassistant.helpers import device_registry

    registry = device_registry.async_get(None)
    device = registry.async_get_or_create(
        id='device-one', config_entry_id='entry-id', identifiers={('domain', 'one')}
    )

    assert registry.async_entries_for_config_entry('entry-id') == [device]
    assert device_registry.async_entries_for_config_entry(registry, 'entry-id') == [
        device
    ]
    assert registry.async_remove_device('device-one')
    assert device_registry.async_remove_device(registry, 'device-one') is False
    assert registry.async_entries_for_config_entry('entry-id') == []
    assert device_registry.async_entries_for_config_entry(registry, 'entry-id') == []


def test_entity_registry_remove_follows_home_assistant_helper() -> None:
    """Entity removal should be exposed via registry and module helpers."""

    install_homeassistant_stubs()

    from homeassistant.helpers import entity_registry

    registry = entity_registry.async_get(None)
    entity = registry.async_get_or_create(
        'sensor.test', device_id='device-one', config_entry_id='entry-id'
    )

    assert registry.async_entries_for_device('device-one') == [entity]
    assert entity_registry.async_entries_for_config_entry(registry, 'entry-id') == [
        entity
    ]
    assert registry.async_remove('sensor.test')
    assert entity_registry.async_remove(registry, 'sensor.test') is False
    assert registry.async_entries_for_device('device-one') == []
    assert entity_registry.async_entries_for_config_entry(registry, 'entry-id') == []


def test_issue_registry_helpers_store_and_remove_issues() -> None:
    """Issue registry stubs should mirror Home Assistant helpers."""

    install_homeassistant_stubs()

    from homeassistant.helpers import issue_registry

    registry = issue_registry.async_get(object())
    issue_severity_cls = issue_registry.IssueSeverity
    assert issue_registry.async_get(object()) is registry
    assert (
        issue_registry.async_get_issue(object(), 'test_domain', 'missing_config')
        is None
    )

    created = issue_registry.async_create_issue(
        object(),
        'test_domain',
        'missing_config',
        active=True,
        is_persistent=True,
        issue_domain='upstream',
        translation_domain='custom_domain',
        translation_key='missing_config',
        translation_placeholders={'path': '/config'},
        severity=issue_severity_cls.ERROR,
        is_fixable=True,
        breaks_in_ha_version='2025.1',
        learn_more_url='https://example.test',
        data={'context': 'details'},
        dismissed_version='2024.9',
    )

    created_at = created['created']
    dismissed_at = created['dismissed']
    assert created == registry.issues[('test_domain', 'missing_config')]
    assert created['translation_domain'] == 'custom_domain'
    assert created['translation_placeholders'] == {'path': '/config'}
    assert created['data'] == {'context': 'details'}
    assert created['is_persistent'] is True
    assert created['issue_domain'] == 'upstream'
    assert created['dismissed_version'] == '2024.9'
    assert created['ignored'] is False
    assert created['active'] is True
    assert created['severity'] is issue_severity_cls.ERROR
    assert isinstance(created_at, datetime)
    assert created_at.tzinfo is UTC
    assert isinstance(dismissed_at, datetime)
    assert dismissed_at.tzinfo is UTC
    assert (
        issue_registry.async_get_issue(object(), 'test_domain', 'missing_config')
        == created
    )

    updated = issue_registry.async_create_issue(
        object(),
        'test_domain',
        'missing_config',
        active=True,
        translation_key='updated_key',
        translation_placeholders={'path': '/new'},
        severity='warning',
    )

    assert updated == registry.issues[('test_domain', 'missing_config')]
    assert updated['translation_key'] == 'updated_key'
    assert updated['translation_domain'] == 'custom_domain'
    assert updated['translation_placeholders'] == {'path': '/new'}
    assert updated['severity'] is issue_severity_cls.WARNING
    assert updated['is_fixable'] is True
    assert updated['created'] == created_at
    assert updated['dismissed'] == dismissed_at
    assert updated['is_persistent'] is True
    assert updated['issue_domain'] == 'upstream'
    assert updated['learn_more_url'] == 'https://example.test'
    assert updated['breaks_in_ha_version'] == '2025.1'
    assert updated['dismissed_version'] == '2024.9'
    assert updated['ignored'] is False
    assert updated['active'] is True
    assert (
        issue_registry.async_get_issue(object(), 'test_domain', 'missing_config')
        == updated
    )

    redismissed = issue_registry.async_create_issue(
        object(),
        'test_domain',
        'missing_config',
        active=True,
        dismissed_version='2026.2',
    )

    assert redismissed['dismissed_version'] == '2026.2'
    assert redismissed['translation_key'] == 'updated_key'
    assert redismissed['translation_domain'] == 'custom_domain'
    assert redismissed['dismissed'] == dismissed_at
    assert redismissed['ignored'] is False
    assert redismissed['active'] is True

    from homeassistant import const

    ignored = issue_registry.async_ignore_issue(
        object(), 'test_domain', 'missing_config', True
    )
    assert ignored['dismissed_version'] == const.__version__
    assert ignored['dismissed'] != dismissed_at
    assert ignored['ignored'] is True
    assert ignored['active'] is False
    assert (
        issue_registry.async_get_issue(object(), 'test_domain', 'missing_config')
        == ignored
    )

    unignored = issue_registry.async_ignore_issue(
        object(), 'test_domain', 'missing_config', False
    )
    assert unignored['dismissed_version'] is None
    assert unignored['dismissed'] is None
    assert unignored['ignored'] is False
    assert unignored['active'] is True
    assert (
        issue_registry.async_get_issue(object(), 'test_domain', 'missing_config')
        == unignored
    )

    defaulted = issue_registry.async_create_issue(
        object(), 'another_domain', 'missing_translation'
    )
    assert defaulted['severity'] is issue_severity_cls.WARNING
    assert defaulted['translation_domain'] == 'another_domain'
    assert defaulted['translation_key'] == 'missing_translation'
    assert defaulted['issue_domain'] == 'another_domain'

    assert issue_registry.async_delete_issue(object(), 'test_domain', 'missing_config')
    assert ('test_domain', 'missing_config') not in registry.issues
    assert (
        issue_registry.async_delete_issue(object(), 'test_domain', 'missing_config')
        is False
    )
    assert issue_registry.async_delete_issue(object(), 'test_domain', 'absent') is False
    assert (
        issue_registry.async_get_issue(object(), 'test_domain', 'missing_config')
        is None
    )


def test_issue_registry_preserves_optional_metadata() -> None:
    """Issue registry stubs should retain optional metadata when not provided."""

    install_homeassistant_stubs()

    from homeassistant.helpers import issue_registry

    registry = issue_registry.async_get(object())

    defaulted = issue_registry.async_create_issue(
        object(), 'domain', 'missing_metadata'
    )

    assert defaulted['data'] is None
    assert defaulted['translation_placeholders'] is None
    assert defaulted['is_fixable'] is False
    assert defaulted['is_persistent'] is False
    assert defaulted['translation_key'] == 'missing_metadata'
    assert defaulted['issue_domain'] == 'domain'

    seeded = issue_registry.async_create_issue(
        object(),
        'domain',
        'missing_metadata',
        translation_placeholders={'path': '/config'},
        data={'context': 'details'},
        is_fixable=True,
        is_persistent=True,
        severity='error',
    )

    assert seeded['translation_placeholders'] == {'path': '/config'}
    assert seeded['data'] == {'context': 'details'}
    assert seeded['is_fixable'] is True
    assert seeded['is_persistent'] is True

    retained = issue_registry.async_create_issue(
        object(),
        'domain',
        'missing_metadata',
        translation_key='carry_existing',
    )

    assert retained['translation_placeholders'] == {'path': '/config'}
    assert retained['data'] == {'context': 'details'}
    assert retained['is_fixable'] is True
    assert retained['is_persistent'] is True
    assert registry.issues[('domain', 'missing_metadata')] == retained
