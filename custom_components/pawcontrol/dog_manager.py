from __future__ import annotations
from typing import Any


class DogDataManager:
    def __init__(self) -> None:
        self._dogs: dict[str, dict[str, Any]] = {}

    def ensure_dog(self, dog_id: str, defaults: dict[str, Any]) -> None:
        if dog_id not in self._dogs:
            self._dogs[dog_id] = defaults.copy()

    def update_dog(self, dog_id: str, data: dict[str, Any]) -> None:
        self._dogs.setdefault(dog_id, {}).update(data)

    def remove_dog(self, dog_id: str) -> None:
        if dog_id in self._dogs:
            del self._dogs[dog_id]

    def all_dogs(self) -> dict[str, dict[str, Any]]:
        return self._dogs
