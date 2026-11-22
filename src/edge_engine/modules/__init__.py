"""Registry of playable modules."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from ..core import GameModule
from ..rng import Rng
from .dice import DiceDemo
from .kelly import CoinFlip
from .kelly import lab as kelly_lab
from .mental import MentalMaths

REGISTRY: dict[str, type[GameModule]] = {
    DiceDemo.name: DiceDemo,
    MentalMaths.name: MentalMaths,
    CoinFlip.name: CoinFlip,
}

# Non-interactive analyses: name -> run(config, rng) -> text
LABS: dict[str, Callable[[Mapping[str, Any], Rng], str]] = {
    "kelly": kelly_lab.run,
}


def get_module(name: str) -> GameModule:
    try:
        return REGISTRY[name]()
    except KeyError:
        known = ", ".join(sorted(REGISTRY))
        raise KeyError(f"unknown module {name!r}; known: {known}") from None
