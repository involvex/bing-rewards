# SPDX-FileCopyrightText: 2020 jack-mil
#
# SPDX-License-Identifier: MIT

"""Shared types for the search backends."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from bing_rewards.report import QuotaStats

if TYPE_CHECKING:
    from argparse import Namespace

BACKENDS = ('auto', 'pynput', 'selenium', 'api')


@dataclass(slots=True)
class SearchOutcome:
    """What one desktop or mobile search pass achieved."""

    backend: str = ''
    searches: int = 0
    points_before: int | None = None
    points_after: int | None = None
    quota: QuotaStats = field(default_factory=QuotaStats)
    error: str | None = None
    complete: bool = False

    @property
    def points_gained(self) -> int | None:
        if self.points_before is None or self.points_after is None:
            return None
        return self.points_after - self.points_before


def resolve_backend(options: Namespace) -> str:
    """Pick the concrete backend name for this run.

    `auto` prefers Selenium (no window focus stealing, works with a saved
    profile) and falls back to the legacy pynput typing only when the
    persistent profile is not signed in.
    """
    backend = str(getattr(options, 'backend', 'auto')).lower()
    if backend in ('pynput', 'selenium', 'api'):
        return backend
    return 'selenium'
