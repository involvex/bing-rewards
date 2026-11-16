# SPDX-FileCopyrightText: 2020 jack-mil
#
# SPDX-License-Identifier: MIT

"""Browserless search backend (Phase 2).

Uses the Microsoft Rewards ``reportActivity`` HTTP endpoint so searches can be
reported without launching Chrome.  Requires a valid cookie file
(``--cookies-file``) from a session that is signed into bing.com; without it
every request returns 401 and the run degrades to zero searches.

Clean-room reimplementation: endpoint URLs are taken from the public URL
constants (facts); request shape and response handling are written from scratch.
"""

from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING

from bing_rewards.log import get_logger
from bing_rewards.options import resolve_delay
from bing_rewards.rewards.api import RewardsClient
from bing_rewards.rewards.http import (
    BING_ORIGIN,
    REPORT_ACTIVITY_URL,
    RewardsHttp,
    RewardsHttpError,
    load_cookies,
)
from bing_rewards.search.types import SearchOutcome

if TYPE_CHECKING:
    from argparse import Namespace
    from collections.abc import Iterator

log = get_logger('search.api')

BING_SEARCH_URL = f'{BING_ORIGIN}/search'


def _new_guid() -> str:
    """Return a lowercase UUID4 string (CVID / IG / activity id)."""
    return str(uuid.uuid4())


def search(
    count: int,
    words: Iterator[str],
    agent: str,
    options: Namespace,
    profile: str,
) -> SearchOutcome:
    """Perform ``count`` browserless searches via the reportActivity endpoint.

    Returns a :class:`SearchOutcome` with ``backend='api'``.  Points before/after
    are read from the dashboard snapshot (best-effort) so the report shows
    ``points_gained`` when the dashboard is reachable.
    """
    outcome = SearchOutcome(backend='api')

    # Dryrun never touches the network, so no cookies file is required.
    if options.dryrun:
        for i in range(count):
            query = next(words)
            log.info('Search %d: %s (dryrun)', i + 1, query)
            outcome.searches += 1
        outcome.complete = True
        return outcome

    cookies_file = getattr(options, 'cookies_file', None) or ''
    if not cookies_file:
        outcome.error = f'--backend api requires --cookies-file <path> (profile "{profile}")'
        log.error(outcome.error)
        return outcome

    try:
        cookies = load_cookies(cookies_file)
    except (OSError, ValueError, TypeError) as e:
        outcome.error = f'could not load cookies file {cookies_file}: {e}'
        log.error(outcome.error)
        return outcome

    http = RewardsHttp(cookies=cookies, user_agent=agent)

    # Best-effort points-before snapshot.
    points_before = _points(http)

    cvid = _new_guid()
    ig = _new_guid()

    for i in range(count):
        query = next(words)

        # 1) Load the search results page so the session/cvid is established.
        try:
            http.get(
                BING_SEARCH_URL,
                query_params={'q': query, 'cvid': cvid, 'FORM': 'ANNTA1'},
            )
        except RewardsHttpError as e:
            outcome.error = f'search request failed: {e}'
            log.error(outcome.error)
            break

        # 2) Report the search activity to Microsoft Rewards.
        activity_id = _new_guid()
        try:
            http.get(
                REPORT_ACTIVITY_URL,
                query_params={
                    'IG': ig,
                    'activityType': 'Search',
                    'activityId': activity_id,
                    'cvid': cvid,
                },
            )
        except RewardsHttpError as e:
            outcome.error = f'reportActivity failed: {e}'
            log.error(outcome.error)
            break

        log.info('Search %d: %s', i + 1, query)
        outcome.searches += 1
        time.sleep(resolve_delay(options.search_delay))

    # Best-effort points-after snapshot.
    points_after = _points(http)
    outcome.points_before = points_before
    outcome.points_after = points_after
    outcome.complete = bool(outcome.error is None or outcome.searches == count)
    return outcome


def _points(http: RewardsHttp) -> int | None:
    """Best-effort available-points read from the dashboard snapshot."""
    try:
        client = RewardsClient(http=http)
        snapshot = client.fetch_snapshot()
    except RewardsHttpError as e:
        log.debug('points read-out skipped: %s', e)
        return None
    return snapshot.available_points or None
