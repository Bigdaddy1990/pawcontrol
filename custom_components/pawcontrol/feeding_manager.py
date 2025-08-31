from __future__ import annotations
import datetime

class FeedingManager:
    def __init__(self) -> None:
        self._feedings: dict[str, list[dict[str, str]]] = {}

    def add_feeding(self, dog_id: str, amount: float) -> None:
        self._feedings.setdefault(dog_id, []).append(
            {"time": datetime.datetime.now().isoformat(), "amount": amount}
        )

    def get_feedings(self, dog_id: str):
        return self._feedings.get(dog_id, [])
