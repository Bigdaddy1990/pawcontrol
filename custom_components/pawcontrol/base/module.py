class BaseModule:
    def __init__(self, hass, name):
        self.hass = hass
        self.name = name

    async def async_setup(self):
        raise NotImplementedError

    async def async_unload(self):
        raise NotImplementedError
