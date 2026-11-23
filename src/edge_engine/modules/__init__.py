"""Registry of playable modules."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from ..core import GameModule
from ..rng import Rng
from .backgammon import Backgammon
from .backgammon import lab as backgammon_lab
from .blackjack import Blackjack
from .blackjack import lab as blackjack_lab
from .chess import Chess
from .chess import lab as chess_lab
from .dice import DiceDemo
from .kelly import CoinFlip
from .kelly import lab as kelly_lab
from .market import MarketMaking
from .market import lab as market_lab
from .mental import MentalMaths
from .poker import Poker
from .poker import lab as poker_lab

REGISTRY: dict[str, type[GameModule]] = {
    DiceDemo.name: DiceDemo,
    MentalMaths.name: MentalMaths,
    CoinFlip.name: CoinFlip,
    Blackjack.name: Blackjack,
    MarketMaking.name: MarketMaking,
    Poker.name: Poker,
    Backgammon.name: Backgammon,
    Chess.name: Chess,
}

# Non-interactive analyses: name -> run(config, rng) -> text
LABS: dict[str, Callable[[Mapping[str, Any], Rng], str]] = {
    "kelly": kelly_lab.run,
    "blackjack": blackjack_lab.run,
    "market": market_lab.run,
    "poker": poker_lab.run,
    "backgammon": backgammon_lab.run,
    "chess": chess_lab.run,
}


def get_module(name: str) -> GameModule:
    try:
        return REGISTRY[name]()
    except KeyError:
        known = ", ".join(sorted(REGISTRY))
        raise KeyError(f"unknown module {name!r}; known: {known}") from None
