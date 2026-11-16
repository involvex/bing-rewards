# SPDX-FileCopyrightText: 2020 jack-mil
#
# SPDX-License-Identifier: MIT

"""Quota-aware search planning (Phase 1).

Computes how many desktop/mobile searches are needed based on the Rewards
dashboard counters, so the tool searches only what is missing and stops when
the quota is satisfied or progress stagnates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from argparse import Namespace

    from bing_rewards.rewards.models import RewardsSnapshot, SearchQuota


@dataclass(slots=True)
class SearchContext:
    """Bundles everything needed for one search pass."""

    options: Namespace
    plan: SearchPlan
    budget: SearchBudget
    words: object  # Iterator[str]


@dataclass(slots=True)
class SearchPlan:
    """Plan for how many searches to run in each mode."""

    desktop_missing: int = 0
    mobile_missing: int = 0
    edge_missing: int = 0
    desktop_known: bool = False
    mobile_known: bool = False
    edge_known: bool = False

    @property
    def quota_known(self) -> bool:
        """True if at least one counter's quota is known."""
        return self.desktop_known or self.mobile_known or self.edge_known

    @property
    def do_desktop(self) -> bool:
        return self.desktop_missing > 0

    @property
    def do_mobile(self) -> bool:
        return self.mobile_missing > 0

    @property
    def total_missing(self) -> int:
        return self.desktop_missing + self.mobile_missing + self.edge_missing


@dataclass(slots=True)
class SearchBudget:
    """Tracks remaining search budget across profiles/modes."""

    max_searches: int | None = None
    spent: int = 0

    def remaining(self) -> int | None:
        if self.max_searches is None:
            return None
        return max(0, self.max_searches - self.spent)

    def allocate(self, requested: int) -> int:
        """Return how many of ``requested`` searches can still be run."""
        if self.max_searches is None:
            return requested
        remaining = self.remaining()
        if remaining is None or remaining <= 0:
            return 0
        return min(requested, remaining)

    def spend(self, count: int) -> None:
        self.spent += count


def plan_searches(snapshot: RewardsSnapshot) -> SearchPlan:
    """Compute how many searches are needed for each mode.

    Uses ``snapshot.counters`` (desktop/mobile/edge quotas).  When a counter
    is unknown (missing from the dashboard), the missing count is 0 and the
    caller should fall back to its configured default count.
    """
    desktop = snapshot.desktop
    mobile = snapshot.mobile
    edge = snapshot.edge

    desktop_missing = max(0, desktop.remaining) if desktop.known else 0
    mobile_missing = max(0, mobile.remaining) if mobile.known else 0
    edge_missing = max(0, edge.remaining) if edge.known else 0

    return SearchPlan(
        desktop_missing=desktop_missing,
        mobile_missing=mobile_missing,
        edge_missing=edge_missing,
        desktop_known=desktop.known,
        mobile_known=mobile.known,
        edge_known=edge.known,
    )


def quota_from_snapshot(snapshot: RewardsSnapshot) -> dict[str, SearchQuota]:
    """Return the snapshot's counters as a plain dict (for backwards compat)."""
    return dict(snapshot.counters)
