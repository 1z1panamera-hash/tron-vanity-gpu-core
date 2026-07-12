from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
BASE58_SET = frozenset(BASE58_ALPHABET)
TRON_ADDRESS_LENGTH = 34
TRON_PAYLOAD_MIN = 0x41 << (24 * 8)
TRON_PAYLOAD_MAX = (0x42 << (24 * 8)) - 1


class PatternError(ValueError):
    """Raised when a customer pattern cannot be accepted."""


class TaskClass(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


@dataclass(frozen=True)
class PatternSpec:
    prefix: str
    suffix: str
    task_class: TaskClass
    canonical: str

    @property
    def custom_length(self) -> int:
        return len(self.prefix) + len(self.suffix)


def _base58_number(value: str) -> int:
    result = 0
    for character in value:
        result = result * 58 + BASE58_ALPHABET.index(character)
    return result


def _prefix_can_be_tron(prefix: str) -> bool:
    full_prefix = "T" + prefix
    remaining = TRON_ADDRESS_LENGTH - len(full_prefix)
    if remaining < 0:
        return False
    prefix_value = _base58_number(full_prefix)
    scale = 58**remaining
    low = prefix_value * scale
    high = (prefix_value + 1) * scale - 1
    return high >= TRON_PAYLOAD_MIN and low <= TRON_PAYLOAD_MAX


def classify_pattern(prefix: str, suffix: str) -> PatternSpec:
    if not isinstance(prefix, str) or not isinstance(suffix, str):
        raise PatternError("prefix and suffix must be strings")
    if any(character not in BASE58_SET for character in prefix + suffix):
        raise PatternError("pattern contains a non-Base58 character")

    total = len(prefix) + len(suffix)
    if not prefix and len(suffix) == 5:
        task_class = TaskClass.P0
    elif prefix and total in (6, 7, 8):
        task_class = TaskClass.P1
    elif not prefix and len(suffix) in (6, 7, 8):
        task_class = TaskClass.P2
    else:
        raise PatternError("pattern must be P0 suffix5 or a 6/7/8 custom pattern")

    if prefix and not _prefix_can_be_tron(prefix):
        raise PatternError("prefix cannot occur in a 34-character TRON address")

    return PatternSpec(
        prefix=prefix,
        suffix=suffix,
        task_class=task_class,
        canonical=f"T{prefix}*{suffix}",
    )


def pattern_from_mapping(value: Mapping[str, Any]) -> PatternSpec:
    allowed = {"prefix", "suffix"}
    unknown = set(value) - allowed
    if unknown:
        raise PatternError(f"unknown request fields: {','.join(sorted(unknown))}")
    return classify_pattern(value.get("prefix", ""), value.get("suffix", ""))


def address_matches(pattern: PatternSpec, address: str) -> bool:
    if len(address) != TRON_ADDRESS_LENGTH or not address.startswith("T"):
        return False
    if pattern.prefix and not address.startswith("T" + pattern.prefix):
        return False
    return not pattern.suffix or address.endswith(pattern.suffix)
