# Init für Setup-Modul


from .logic import create_feeding_helpers
import asyncio

async def setup_dynamic_feeding(hass):
    feeding_config = await create_feeding_helpers(hass)
    for domain, entities in feeding_config.items():
        for object_id, params in entities.items():
            full_entity = f'{domain}.{object_id}'
            # Hinweis: Automatische Registrierung erfordert zusätzliche Validierung in produktiver Umgebung
            hass.states.async_set(full_entity, 'off' if domain == 'input_boolean' else '00:00:00', params)
