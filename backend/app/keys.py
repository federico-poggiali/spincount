"""Musical keys: Camelot codes ('8A'), their names ('A minor') and wheel order. Parsing is bpmkey's."""
from bpmkey.camelot import camelot_to_key_index, to_camelot
from bpmkey.keydetect import NAMES

__all__ = ["key_name", "to_camelot", "wheel_order"]


def key_name(camelot: str | None) -> str | None:
    index = camelot_to_key_index(camelot) if camelot else None
    if index is None:
        return None
    return f"{NAMES[index % 12]} {'minor' if index >= 12 else 'major'}"


def wheel_order(camelot: str) -> tuple[int, str]:
    """Sort key: 1A, 1B, 2A ... 12B."""
    return int(camelot[:-1]), camelot[-1]
