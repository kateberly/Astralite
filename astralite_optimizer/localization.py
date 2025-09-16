"""Helpers for working with the English localisation dictionary."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Dict, Mapping


class Localization:
    """Provides convenient access to localisation keys.

    The supplied ``data`` is the parsed ``en.json`` blob.  The structure is
    deeply nested, so we eagerly flatten all keys to enable efficient lookups
    later in the optimiser.
    """

    def __init__(self, data: Mapping[str, Any]) -> None:
        self._flat: Dict[str, str] = {}
        self._flatten(data)

    def _flatten(self, data: Any) -> None:
        if isinstance(data, Mapping):
            for key, value in data.items():
                if isinstance(value, (Mapping, list)):
                    self._flatten(value)
                elif isinstance(value, str):
                    self._flat[key] = value
        elif isinstance(data, list):
            for item in data:
                self._flatten(item)

    def get(self, key: str, default: str | None = None) -> str | None:
        return self._flat.get(key, default)

    def item_name(self, item_id: int | str) -> str:
        key = f"ItemName_{int(item_id)}"
        return self._flat.get(key, f"Item {item_id}")

    def item_desc(self, item_id: int | str) -> str | None:
        return self._flat.get(f"ItemDesc_{int(item_id)}")

    def ability_text(self, key: str) -> str | None:
        return self._flat.get(key)

    def find_any(self, keys: Iterable[str]) -> Dict[str, str]:
        return {key: self._flat[key] for key in keys if key in self._flat}

