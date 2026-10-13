"""Adapter registry: which adapters exist, which are switched on, how a level runs them."""
from __future__ import annotations

import importlib
import inspect
from typing import Iterable

from .. import config
from .base import Adapter, AdapterError

__all__ = ["Adapter", "AdapterError", "Registry", "default_registry", "BUILTIN"]

# (module, class) in level order; modules that do not exist yet are skipped.
BUILTIN: list[tuple[str, str]] = [
    ("local_files", "LocalFiles"),
    ("manual_link", "ManualLink"),
    ("discogs_youtube", "DiscogsYouTube"),
    ("youtube_music", "YouTubeMusic"),
    ("itunes", "ITunesPreview"),
    ("bandcamp", "Bandcamp"),
    ("soundcloud_tracks", "SoundCloudTracks"),
    ("soundcloud_sets", "SoundCloudSets"),
    ("beatport_tracks", "BeatportTracks"),
    ("beatport_releases", "BeatportReleases"),
    ("stores.deejay_de", "DeejayDe"),
    ("stores.decks_de", "DecksDe"),
    ("stores.hardwax", "Hardwax"),
    ("stores.clone", "Clone"),
    ("stores.kalahari_oyster_cult", "KalahariOysterCult"),
]


class Registry:
    def __init__(self, adapters: Iterable[Adapter] = (), disabled: Iterable[str] | None = None):
        self._adapters: list[Adapter] = []
        self.disabled: set[str] = set(config.disabled_adapters() if disabled is None else disabled)
        for a in adapters:
            self.add(a)

    def add(self, adapter: Adapter) -> Adapter:
        self._adapters.append(adapter)
        return adapter

    def get(self, name: str) -> Adapter | None:
        return next((a for a in self._adapters if a.name == name), None)

    def switch(self, name: str, on: bool) -> None:
        (self.disabled.discard if on else self.disabled.add)(name)

    def all(self) -> list[Adapter]:
        return list(self._adapters)

    def for_level(self, level: int) -> list[Adapter]:
        return [a for a in self._adapters if a.level == level and a.name not in self.disabled]

    def groups(self, level: int) -> list[list[Adapter]]:
        """Adapters of one level, as groups that run in parallel; inside a group, in order."""
        groups: dict[str, list[Adapter]] = {}
        for a in self.for_level(level):
            groups.setdefault(a.group_key, []).append(a)
        return list(groups.values())


def default_registry(disabled: Iterable[str] | None = None, store=None) -> Registry:
    reg = Registry(disabled=disabled)
    for module, cls in BUILTIN:
        full = f"{__name__}.{module}"
        try:
            mod = importlib.import_module(full)
        except ModuleNotFoundError as e:
            if e.name == full or (e.name and full.startswith(e.name)):
                continue  # adapter not built yet
            raise
        klass = getattr(mod, cls)
        reg.add(klass(store=store) if "store" in inspect.signature(klass.__init__).parameters else klass())
    return reg
