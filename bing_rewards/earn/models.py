# SPDX-FileCopyrightText: 2020 jack-mil
#
# SPDX-License-Identifier: MIT

"""Data models for the earn package (Phase 3).

Plain data: no network, no Selenium, no side effects.  Produced by
:mod:`bing_rewards.earn.dashboard` from raw ``dapi/me`` data and consumed by
:mod:`bing_rewards.earn.client` and the CLI.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class EarnOffer:
    """A single earnable reward activity discovered on the dashboard."""

    offer_id: str
    title: str
    description: str = ''
    destination_url: str = ''
    points: int = 0
    points_max: int = 0
    offer_type: str = ''  # urlreward | quiz | poll | purchase | search | ...
    state: str = 'incomplete'  # incomplete | complete | locked
    complete: bool = False
    date: str = ''  # daily-set date (MM/DD/YYYY) when from dailySetPromotions
    hash: str = ''  # activity hash usable with reportActivity

    @property
    def points_remaining(self) -> int:
        return max(0, self.points_max - self.points)

    @property
    def is_complete(self) -> bool:
        return self.complete or self.state.lower() in ('complete', 'completed')

    @property
    def is_locked(self) -> bool:
        return self.state.lower() in ('locked',)

    @property
    def is_reportable(self) -> bool:
        """True if the offer can be reported via reportActivity."""
        return bool(self.hash) and not self.is_complete and not self.is_locked

    def to_dict(self) -> dict[str, object]:
        return {
            'offer_id': self.offer_id,
            'title': self.title,
            'description': self.description,
            'destination_url': self.destination_url,
            'points': self.points,
            'points_max': self.points_max,
            'offer_type': self.offer_type,
            'state': self.state,
            'complete': self.complete,
            'date': self.date,
            'hash': self.hash,
            'is_complete': self.is_complete,
            'is_locked': self.is_locked,
            'is_reportable': self.is_reportable,
        }


@dataclass(slots=True)
class EarnReport:
    """Outcome of one run_earn() pass."""

    completed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    points_earned: int = 0

    @property
    def total(self) -> int:
        return len(self.completed) + len(self.skipped) + len(self.failed)

    def to_dict(self) -> dict[str, object]:
        return {
            'completed': list(self.completed),
            'skipped': list(self.skipped),
            'failed': list(self.failed),
            'points_earned': self.points_earned,
            'total': self.total,
        }
