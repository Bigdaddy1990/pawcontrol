from __future__ import annotations
import datetime
from typing import Any

class WalkManager:
    def __init__(self) -> None:
        self._walks: dict[str, list[dict[str, Any]]] = {}

    def start_walk(self, dog_id: str) -> None:
        self._walks.setdefault(dog_id, []).append(
            {"start": datetime.datetime.now().isoformat(), "end": None, "distance": 0}
        )

    def end_walk(self, dog_id: str, distance: float) -> None:
        if dog_id in self._walks and self._walks[dog_id]:
            self._walks[dog_id][-1]["end"] = datetime.datetime.now().isoformat()
            self._walks[dog_id][-1]["distance"] = distance

    def get_walks(self, dog_id: str):
        return self._walks.get(dog_id, [])
