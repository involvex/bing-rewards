# SPDX-FileCopyrightText: 2020 jack-mil
#
# SPDX-License-Identifier: MIT

"""Data models for the Microsoft Rewards dashboard read-out (Phase 1).

All dataclasses are plain data: no network, no Selenium, no side effects.
They are produced by :mod:`bing_rewards.rewards.parse` from raw HTTP/HTML
responses and consumed by :mod:`bing_rewards.rewards.api` and the CLI.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class SearchQuota:
    """Points earned / available for one search counter (desktop/mobile/edge)."""

    counter_key: str | None = None
    earned: int = 0
    maximum: int = 0
    remaining: int = 0
    known: bool = False

    @property
    def label(self) -> str:
        return f"{self.earned}/{self.maximum}" if self.known else "unknown"

    def to_dict(self) -> dict[str, object]:
        return {
            "counter_key": self.counter_key,
            "earned": self.earned,
            "maximum": self.maximum,
            "remaining": self.remaining,
            "known": self.known,
        }


@dataclass(slots=True)
class StreakInfo:
    """Progress for one streak (bing-search, daily-set, edge-browsing, ...)."""

    kind: str
    is_on: bool = False
    remaining_days: int = 0
    current: int = 0
    target: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "is_on": self.is_on,
            "remaining_days": self.remaining_days,
            "current": self.current,
            "target": self.target,
        }


@dataclass(slots=True)
class RewardsSnapshot:
    """A point-in-time read-out of the Microsoft Rewards account.

    ``source`` names the transport that provided the data
    (``dapi/me``, ``panelflyout``, ``getuserinfo``). ``missing_sections`` lists
    dashboard sections that were unavailable so callers can degrade gracefully
    instead of crashing.
    """

    available_points: int = 0
    level: int = 0
    lifetime_earn: int = 0
    counters: dict[str, SearchQuota] = field(default_factory=dict)
    streaks: dict[str, StreakInfo] = field(default_factory=dict)
    promotions: int = 0
    punch_cards: int = 0
    source: str = ""
    missing_sections: list[str] = field(default_factory=list)

    @property
    def desktop(self) -> SearchQuota:
        return self.counters.get("desktop", SearchQuota(counter_key="desktop"))

    @property
    def mobile(self) -> SearchQuota:
        return self.counters.get("mobile", SearchQuota(counter_key="mobile"))

    @property
    def edge(self) -> SearchQuota:
        return self.counters.get("edge", SearchQuota(counter_key="edge"))

    def to_dict(self) -> dict[str, object]:
        return {
            "available_points": self.available_points,
            "level": self.level,
            "lifetime_earn": self.lifetime_earn,
            "counters": {k: v.to_dict() for k, v in self.counters.items()},
            "streaks": {k: v.to_dict() for k, v in self.streaks.items()},
            "promotions": self.promotions,
            "punch_cards": self.punch_cards,
            "source": self.source,
            "missing_sections": list(self.missing_sections),
        }
