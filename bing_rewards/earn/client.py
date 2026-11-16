# SPDX-FileCopyrightText: 2020 jack-mil
#
# SPDX-License-Identifier: MIT

"""Browserless earn client: complete dashboard offers via HTTP (Phase 3).

Completes reportable earn offers (those with an activity ``hash``) by visiting
their ``destination_url`` and reporting activity to Microsoft Rewards via the
``reportActivity`` endpoint.  Quiz/poll offers that cannot be answered
automatically are skipped rather than fabricated.

Clean-room reimplementation: endpoint URLs come from the public URL constants
(facts); request shape and response handling are written from scratch.
"""

from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING

from bing_rewards.earn.models import EarnOffer, EarnReport
from bing_rewards.log import get_logger
from bing_rewards.rewards.http import (
    BING_ORIGIN,
    REPORT_ACTIVITY_URL,
    RewardsHttp,
    RewardsHttpError,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

log = get_logger("earn.client")

REWARDS_URL = f"{BING_ORIGIN}/"

# Offer types whose points are awarded on page view (no quiz answers needed).
PAGE_VIEW_TYPES = frozenset({"urlreward", "search", "purchase", "checkin"})

# Offer types requiring user input (quiz answers / poll choice) — skipped by
# default unless they carry a reportable hash.
INPUT_TYPES = frozenset({"quiz", "poll", "trivia"})


def _new_guid() -> str:
    """Return a lowercase UUID4 string (activity id / cvid)."""
    return str(uuid.uuid4())


class EarnClient:
    """Complete earn offers via the Rewards HTTP endpoints."""

    def __init__(
        self,
        http: RewardsHttp,
        user_agent: str = "",
        earn_delay: float | None = None,
    ) -> None:
        self.http = http
        self.user_agent = user_agent
        self.earn_delay = earn_delay

    def _delay(self) -> float:
        if self.earn_delay is not None:
            return self.earn_delay
        return 3.0

    def _activity_type(self, offer: EarnOffer) -> str:
        t = offer.offer_type.lower()
        if t in PAGE_VIEW_TYPES:
            return "UrlReward"
        if t in INPUT_TYPES:
            return t.capitalize()
        return "Activity"

    def run(self, offers: Iterator[EarnOffer], dryrun: bool = False) -> EarnReport:
        """Complete each reportable offer; return an :class:`EarnReport`."""
        report = EarnReport()

        for offer in offers:
            if offer.is_complete:
                report.skipped.append(f"{offer.title} (already complete)")
                continue
            if offer.is_locked:
                report.skipped.append(f"{offer.title} (locked)")
                continue

            if dryrun:
                log.info("Earn [%s]: %s (dryrun)", offer.offer_type, offer.title)
                report.completed.append(offer.title)
                continue

            ok = self._complete_one(offer)
            if ok:
                report.completed.append(offer.title)
                report.points_earned += offer.points_remaining
                log.info(
                    "Earn completed: %s (%d pts)", offer.title, offer.points_remaining
                )
            else:
                report.failed.append(offer.title)
                log.warning("Earn failed: %s", offer.title)
            time.sleep(self._delay())

        return report

    def _complete_one(self, offer: EarnOffer) -> bool:
        """Complete a single offer. Returns True on success."""
        log.info("Earn [%s/%spts]: %s", offer.offer_type, offer.points_max, offer.title)

        # Non-reportable offers (complete, locked, or no hash) never complete.
        if not offer.is_reportable:
            if offer.offer_type.lower() in INPUT_TYPES:
                log.info(
                    "  skipped (requires input, no reportable hash): %s", offer.title
                )
            else:
                log.info("  skipped (no reportable hash): %s", offer.title)
            return False

        # 1) Visit the destination URL to establish the session/cvid.
        if offer.destination_url:
            try:
                self.http.get(offer.destination_url)
            except RewardsHttpError as e:
                log.warning("  failed to open destination: %s", e)
                # Continue to reportActivity anyway — some offers accept a
                # direct activity report without a prior page visit.
            except Exception as e:  # noqa: BLE001 - network is flaky
                log.warning("  failed to open destination: %s", e)

        # 2) Report the activity to Microsoft Rewards.
        try:
            self.http.get(
                REPORT_ACTIVITY_URL,
                query_params={
                    "IG": _new_guid(),
                    "activityType": self._activity_type(offer),
                    "activityId": offer.hash,
                    "cvid": _new_guid(),
                },
            )
        except RewardsHttpError as e:
            log.warning("  reportActivity failed: %s", e)
            return False
        except Exception as e:  # noqa: BLE001 - network is flaky
            log.warning("  reportActivity failed: %s", e)
            return False

        return True
