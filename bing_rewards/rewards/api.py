# SPDX-FileCopyrightText: 2020 jack-mil
#
# SPDX-License-Identifier: MIT

"""Rewards API client: read the dashboard snapshot via HTTP (Phase 1).

Transports are tried in order: ``dapi/me`` (primary), ``panelflyout``,
``getuserinfo`` (legacy fallback).  The first transport that returns usable
data wins; missing sections are reported so the CLI can degrade gracefully.
"""

from __future__ import annotations

from bing_rewards.log import get_logger
from bing_rewards.rewards.http import (
    DAPI_ME_URL,
    GETUSERINFO_URL,
    PANELFLYOUT_URL,
    RewardsHttp,
    RewardsHttpError,
)
from bing_rewards.rewards.models import RewardsSnapshot
from bing_rewards.rewards.parse import (
    parse_dapi_me,
    parse_getuserinfo,
    parse_html_sign_in,
    parse_panelflyout,
)

log = get_logger("rewards.api")


class RewardsClient:
    """Fetch a :class:`RewardsSnapshot` from the Microsoft Rewards endpoints."""

    def __init__(
        self,
        http: RewardsHttp | None = None,
        user_agent: str = "",
    ) -> None:
        self.http = http or RewardsHttp(user_agent=user_agent)

    def fetch_snapshot(self) -> RewardsSnapshot:
        """Try each transport until one returns usable data.

        Returns a snapshot even if all transports fail (all zeros, with
        ``missing_sections`` listing every section).
        """
        last_error: str | None = None

        for name, url, parser in (
            ("dapi/me", DAPI_ME_URL, parse_dapi_me),
            ("panelflyout", PANELFLYOUT_URL, parse_panelflyout),
            ("getuserinfo", GETUSERINFO_URL, parse_getuserinfo),
        ):
            try:
                data = self.http.json_get(url)
            except RewardsHttpError as e:
                last_error = str(e)
                log.debug("%s transport failed: %s", name, e)
                continue
            except Exception as e:  # noqa: BLE001 - network is inherently flaky
                last_error = str(e)
                log.debug("%s transport error: %s", name, e)
                continue

            snapshot = parser(data)
            if snapshot.available_points > 0 or snapshot.counters:
                log.info(
                    "Rewards snapshot from %s: %d points, %d counter(s)",
                    name,
                    snapshot.available_points,
                    len(snapshot.counters),
                )
                return snapshot

            log.debug("%s returned empty data", name)

        log.warning(
            "All Rewards transports failed (last error: %s); returning empty snapshot.",
            last_error or "unknown",
        )
        return RewardsSnapshot(source="none", missing_sections=["all"])

    def check_signed_in(self, html: str) -> bool:
        """Return True if ``html`` looks like a sign-in page (session expired)."""
        return parse_html_sign_in(html)
