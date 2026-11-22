"""Registry of playable modules."""

from __future__ import annotations

from ..core import GameModule
from .dice import DiceDemo
from .mental import MentalMaths

REGISTRY: dict[str, type[GameModule]] = {
    DiceDemo.name: DiceDemo,
    MentalMaths.name: MentalMaths,
}


def get_module(name: str) -> GameModule:
    try:
        return REGISTRY[name]()
    except KeyError:
        known = ", ".join(sorted(REGISTRY))
        raise KeyError(f"unknown module {name!r}; known: {known}") from None
