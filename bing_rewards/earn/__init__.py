# SPDX-FileCopyrightText: 2020 jack-mil
#
# SPDX-License-Identifier: MIT

"""Earn automation on dashboard JSON (Phase 3).

Replaces the DOM-scraping ``earn.py`` with a clean-room, HTTP-driven earn
client that reads the ``dapi/me`` dashboard snapshot, parses daily-set
promotions and other earnable offers, and completes reportable ones via the
``reportActivity`` endpoint — no browser required.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from bing_rewards.earn.client import EarnClient
from bing_rewards.earn.dashboard import parse_earn_offers
from bing_rewards.earn.models import EarnOffer, EarnReport
from bing_rewards.log import get_logger
from bing_rewards.rewards.http import DAPI_ME_URL, RewardsHttp, load_cookies

if TYPE_CHECKING:
    from argparse import Namespace

log = get_logger("earn")

SKIP_TITLE_MARKERS = (
    "edge-browsing",
    "edge browsing",
    "edge herunter",
    "download edge",
    "microsoft edge",
    "bing-app",
    "bing app",
)


def _filter_offers(
    offers: list[EarnOffer],
    options: Namespace,
) -> tuple[list[EarnOffer], list[str]]:
    """Apply --daily-set-only / --explore-only and skip non-auto-completable.

    Returns ``(filtered_offers, skipped_messages)`` without mutating any
    external state.
    """
    daily_only = bool(getattr(options, "daily_set_only", False))
    explore_only = bool(getattr(options, "explore_only", False))
    filtered: list[EarnOffer] = []
    skipped: list[str] = []

    for offer in offers:
        low = f"{offer.title} {offer.destination_url}".lower()
        if any(m in low for m in SKIP_TITLE_MARKERS):
            skipped.append(f"{offer.title} (not auto-completable)")
            continue
        if explore_only and offer.offer_type not in ("urlreward", "search", "purchase"):
            skipped.append(f"{offer.title} (not explore)")
            continue
        if (
            daily_only
            and offer.offer_type not in ("urlreward", "quiz", "poll")
            and "daily" not in low
        ):
            skipped.append(f"{offer.title} (not daily set)")
            continue
        filtered.append(offer)
    return filtered, skipped


def run_earn(options: Namespace) -> EarnReport:
    """Discover and complete earn activities from the dashboard JSON.

    Returns an :class:`EarnReport`.  Never raises: network/parse failures are
    logged and the affected offers are counted as failed.
    """
    report = EarnReport()

    cookies_file = getattr(options, "cookies_file", None) or ""
    if not cookies_file:
        report.failed.append("--backend api/--earn requires --cookies-file <path>")
        log.error(report.failed[-1])
        return report

    try:
        cookies = load_cookies(cookies_file)
    except (OSError, ValueError, TypeError) as e:
        report.failed.append(f"could not load cookies file {cookies_file}: {e}")
        log.error(report.failed[-1])
        return report

    http = RewardsHttp(
        cookies=cookies, user_agent=getattr(options, "desktop_agent", "")
    )

    # The raw dashboard payload is needed for dailySetPromotions; the parsed
    # RewardsSnapshot only exposes counters/points, not the offer list.
    try:
        raw = http.json_get(DAPI_ME_URL)
    except Exception as e:  # noqa: BLE001 - network is flaky
        log.warning("Could not fetch raw dashboard: %s", e)
        report.failed.append(f"dashboard raw: {e}")
        return report

    offers = parse_earn_offers(raw)
    log.info("Found %d earnable offer(s) on the dashboard.", len(offers))

    offers, skipped = _filter_offers(offers, options)
    report.skipped.extend(skipped)
    log.info("%d offer(s) remain after filtering.", len(offers))

    earn_client = EarnClient(
        http=http,
        user_agent=getattr(options, "desktop_agent", ""),
        earn_delay=getattr(options, "earn_delay", None),
    )
    dryrun = bool(getattr(options, "dryrun", False))
    result = earn_client.run(iter(offers), dryrun=dryrun)

    report.completed.extend(result.completed)
    report.skipped.extend(result.skipped)
    report.failed.extend(result.failed)
    report.points_earned += result.points_earned
    return report
