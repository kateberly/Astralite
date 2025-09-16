"""Utilities for retrieving Astralite gameplay data from GitHub."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping

import requests

from .config import DATA_URLS


@dataclass(slots=True)
class RemoteDataLoader:
    """Fetches JSON blobs from the public Astralite data repository."""

    session: requests.Session | None = None
    urls: Mapping[str, str] = field(default_factory=lambda: DATA_URLS.copy())
    _session: requests.Session = field(init=False, repr=False)
    _cache: Dict[str, Any] = field(init=False, repr=False, default_factory=dict)

    def __post_init__(self) -> None:
        self._session = self.session or requests.Session()

    def fetch_json(self, name: str) -> Any:
        """Return the parsed JSON for ``name`` from the configured URLs."""

        if name not in self.urls:
            raise KeyError(f"Unknown dataset: {name}")
        if name not in self._cache:
            response = self._session.get(self.urls[name], timeout=30)
            response.raise_for_status()
            self._cache[name] = response.json()
        return self._cache[name]

    # Convenience aliases for clarity when reading call sites.
    def __call__(self, name: str) -> Any:  # pragma: no cover - trivial alias
        return self.fetch_json(name)

