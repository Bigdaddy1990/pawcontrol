from __future__ import annotations

from datetime import timedelta
from typing import cast

import pytest
from custom_components.pawcontrol.const import (
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOGS,
    CONF_MODULES,
    DOMAIN,
    EVENT_WALK_ENDED,
    EVENT_WALK_STARTED,
    MODULE_WALK,
)
from custom_components.pawcontrol.helpers import PawControlData
from custom_components.pawcontrol.types import (
    JSONMutableMapping,
    WalkHistoryEntry,
    ensure_dog_config_data,
)
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry


@pytest.mark.integration
@pytest.mark.asyncio
async def test_walk_history_reload_persists_json_only(hass: HomeAssistant) -> None:
    """Walk history should remain JSON-only across start/end cycles and reloads."""

    base_time = dt_util.utcnow().replace(microsecond=0)
    initial_timestamp = (base_time - timedelta(days=1)).isoformat()
    start_timestamp = base_time.isoformat()
    progress_timestamp = (base_time + timedelta(minutes=12)).isoformat()
    end_timestamp = (base_time + timedelta(minutes=25)).isoformat()

    dog_payload = {
        CONF_DOG_ID: "buddy",
        CONF_DOG_NAME: "Buddy",
        CONF_MODULES: {MODULE_WALK: True},
    }
    typed_dog = ensure_dog_config_data(dog_payload)
    assert typed_dog is not None

    entry = MockConfigEntry(domain=DOMAIN, data={CONF_DOGS: [typed_dog]})
    entry.add_to_hass(hass)

    data = PawControlData(hass, entry)

    initial_history: list[WalkHistoryEntry] = [
        cast(
            WalkHistoryEntry,
            {
                "session_id": "session-0",
                "action": "end",
                "timestamp": initial_timestamp,
                "duration": 1800,
                "route": "evening-loop",
            },
        )
    ]
    await data.storage._stores["walks"].async_save(  # type: ignore[attr-defined]
        {
            "buddy": {
                "active": None,
                "history": initial_history,
                "metadata": {"surface": "trail"},
            }
        }
    )

    await data.async_load_data()

    events: list[tuple[str, dict[str, object]]] = []

    def _capture_event(event):
        events.append((event.event_type, dict(event.data)))

    unsub_start = hass.bus.async_listen(EVENT_WALK_STARTED, _capture_event)
    unsub_end = hass.bus.async_listen(EVENT_WALK_ENDED, _capture_event)

    try:
        await data.async_start_walk(
            "buddy",
            {
                "action": "start",
                "session_id": "session-1",
                "timestamp": start_timestamp,
                "route": "river-park",
                "leash": "standard",
            },
        )
        await data.storage._batch_save(delay=0)  # type: ignore[attr-defined]

        walk_events = [
            {
                "type": "walk",
                "dog_id": "buddy",
                "timestamp": progress_timestamp,
                "data": cast(
                    JSONMutableMapping,
                    {"session_id": "session-1", "distance_m": 1350, "pace_m_s": 1.4},
                ),
            },
            {
                "type": "walk",
                "dog_id": "buddy",
                "timestamp": end_timestamp,
                "data": cast(
                    JSONMutableMapping,
                    {
                        "action": "end",
                        "session_id": "session-1",
                        "duration": 1500,
                        "temperature_c": 18.5,
                    },
                ),
            },
        ]

        await data._process_walk_batch(walk_events)
        await data.storage._batch_save(delay=0)  # type: ignore[attr-defined]

        await hass.async_block_till_done()

        assert (EVENT_WALK_STARTED, {"dog_id": "buddy", "session_id": "session-1"}) in [
            (
                event,
                {
                    "dog_id": payload.get("dog_id"),
                    "session_id": payload.get("session_id"),
                },
            )
            for event, payload in events
        ]
        assert (EVENT_WALK_ENDED, {"dog_id": "buddy", "session_id": "session-1"}) in [
            (
                event,
                {
                    "dog_id": payload.get("dog_id"),
                    "session_id": payload.get("session_id"),
                },
            )
            for event, payload in events
        ]
    finally:
        unsub_start()
        unsub_end()

    await data.async_shutdown()

    reloaded = PawControlData(hass, entry)
    await reloaded.async_load_data()

    walk_namespace = reloaded._ensure_namespace("walks")
    dog_snapshot = cast(dict[str, object], walk_namespace["buddy"])
    history = cast(list[WalkHistoryEntry], dog_snapshot["history"])

    assert dog_snapshot["active"] is None
    assert len(history) == 2
    assert all(isinstance(entry, dict) for entry in history)
    assert history[0]["session_id"] == "session-1"
    assert history[0]["route"] == "river-park"
    assert history[0]["duration"] == 1500
    assert history[0]["distance_m"] == 1350
    assert history[1]["session_id"] == "session-0"
    assert history[1]["route"] == "evening-loop"

    stored_payload = await reloaded.storage._stores["walks"].async_load()  # type: ignore[attr-defined]
    assert isinstance(stored_payload, dict)

    dog_blob = cast(dict[str, object], stored_payload["buddy"])
    assert dog_blob["active"] is None
    stored_history = cast(list[object], dog_blob["history"])
    assert len(stored_history) == 2
    assert all(isinstance(entry, dict) for entry in stored_history)

    await reloaded.async_shutdown()
