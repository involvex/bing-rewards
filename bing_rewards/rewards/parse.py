# SPDX-FileCopyrightText: 2020 jack-mil
#
# SPDX-License-Identifier: MIT

"""Pure parsers for Microsoft Rewards dashboard responses.

Each parser takes raw JSON (already decoded) or HTML text and returns a
:class:`bing_rewards.rewards.models.RewardsSnapshot`.  Parsers never raise on
unexpected shapes: they extract what they can and record
``missing_sections`` so callers can degrade gracefully.
"""

from __future__ import annotations

from bing_rewards.log import get_logger
from bing_rewards.rewards.models import RewardsSnapshot, SearchQuota, StreakInfo
from bing_rewards.util import _as_mapping, _first_int

log = get_logger('rewards.parse')

# Counter id → canonical key.  Microsoft uses several names for the same
# counter depending on transport; we normalize them all (keys are lowercase).
COUNTER_KEYS: dict[str, str] = {
    'pcsearch': 'desktop',
    'desktopsearch': 'desktop',
    'desktop': 'desktop',
    'windowssearch': 'desktop',
    'mobilesearch': 'mobile',
    'mobile': 'mobile',
    'edgesearch': 'edge',
    'edge': 'edge',
    'edgedesktop': 'edge',
}

_STREAK_KINDS = (
    'bing-search',
    'bing-app',
    'daily-set',
    'edge-browsing',
    'visual-search',
)


def _parse_counter(counter: object) -> SearchQuota | None:
    data = _as_mapping(counter)
    if not data:
        return None

    raw_key = (
        data.get('counterId') or data.get('name') or data.get('id') or data.get('counterKey') or ''
    )
    key = COUNTER_KEYS.get(str(raw_key).lower(), str(raw_key).lower() or None)

    # Microsoft uses several field-name variants for the same concept.
    earned = _first_int(
        data.get('pointProgress')
        or data.get('earned')
        or data.get('currentPoints')
        or data.get('progress')
        or 0
    )
    maximum = _first_int(
        data.get('pointProgressMax')
        or data.get('max')
        or data.get('maxPoints')
        or data.get('limit')
        or 0
    )
    remaining = _first_int(
        data.get('remaining') or data.get('remainingPoints') or max(0, maximum - earned) or 0
    )

    known = bool(raw_key) and maximum > 0
    return SearchQuota(
        counter_key=key,
        earned=earned,
        maximum=maximum,
        remaining=remaining,
        known=known,
    )


def _parse_counters(counters_obj: object) -> dict[str, SearchQuota]:
    """Accept a list or a dict of counters."""
    result: dict[str, SearchQuota] = {}
    if isinstance(counters_obj, list):
        for entry in counters_obj:
            q = _parse_counter(entry)
            if q and q.counter_key:
                result[q.counter_key] = q
    elif isinstance(counters_obj, dict):
        for name, entry in counters_obj.items():
            q = _parse_counter(entry)
            if q and q.counter_key:
                result[q.counter_key] = q
            elif q:
                result[name.lower()] = q
    return result


def _parse_streaks(streaks_obj: object) -> dict[str, StreakInfo]:
    result: dict[str, StreakInfo] = {}
    if isinstance(streaks_obj, list):
        for entry in streaks_obj:
            data = _as_mapping(entry)
            kind = str(data.get('kind') or data.get('name') or data.get('type') or '')
            if not kind:
                continue
            result[kind] = StreakInfo(
                kind=kind,
                is_on=bool(data.get('isOn') or data.get('is_on') or data.get('enabled')),
                remaining_days=_first_int(
                    data.get('remainingDays') or data.get('remaining_days') or 0
                ),
                current=_first_int(data.get('current') or data.get('streak') or 0),
                target=_first_int(data.get('target') or data.get('goal') or 0),
            )
    elif isinstance(streaks_obj, dict):
        for kind, entry in streaks_obj.items():
            data = _as_mapping(entry)
            result[kind] = StreakInfo(
                kind=kind,
                is_on=bool(data.get('isOn') or data.get('is_on') or data.get('enabled')),
                remaining_days=_first_int(
                    data.get('remainingDays') or data.get('remaining_days') or 0
                ),
                current=_first_int(data.get('current') or data.get('streak') or 0),
                target=_first_int(data.get('target') or data.get('goal') or 0),
            )
    return result


def parse_dapi_me(data: object) -> RewardsSnapshot:
    """Parse the primary ``dapi/me`` transport response."""
    snapshot = RewardsSnapshot(source='dapi/me')
    root = _as_mapping(data)

    user_status = _as_mapping(root.get('userStatus') or root.get('user') or root)
    if not user_status and root:
        # Some responses nest everything one level deeper.
        for value in root.values():
            if isinstance(value, dict):
                user_status = value
                break

    snapshot.available_points = _first_int(
        user_status.get('availablePoints')
        or user_status.get('available_points')
        or user_status.get('balance')
        or root.get('availablePoints')
        or 0
    )
    snapshot.level = _first_int(user_status.get('level') or root.get('level') or 0)
    snapshot.lifetime_earn = _first_int(
        user_status.get('lifetimeEarn')
        or user_status.get('lifetime_earn')
        or root.get('lifetimeEarn')
        or 0
    )

    counters_raw = (
        user_status.get('counters')
        or root.get('counters')
        or user_status.get('counterProgress')
        or []
    )
    snapshot.counters = _parse_counters(counters_raw)

    streaks_raw = user_status.get('streaks') or root.get('streaks') or []
    snapshot.streaks = _parse_streaks(streaks_raw)

    if not snapshot.counters:
        snapshot.missing_sections.append('counters')
    if snapshot.available_points == 0:
        snapshot.missing_sections.append('available_points')
    return snapshot


def parse_panelflyout(data: object) -> RewardsSnapshot:
    """Parse the ``panelflyout/getuserinfo`` transport response.

    Shape is similar to ``dapi/me`` but field names may differ; we reuse the
    same tolerant extraction.
    """
    snapshot = RewardsSnapshot(source='panelflyout')
    root = _as_mapping(data)

    # Panelflyout often wraps data under 'userStatus' or 'dashboard'.
    user_status = _as_mapping(
        root.get('userStatus') or root.get('dashboard') or root.get('user') or root
    )

    snapshot.available_points = _first_int(
        user_status.get('availablePoints')
        or user_status.get('points')
        or user_status.get('balance')
        or root.get('availablePoints')
        or 0
    )
    snapshot.level = _first_int(user_status.get('level') or root.get('level') or 0)
    snapshot.lifetime_earn = _first_int(
        user_status.get('lifetimeEarn') or root.get('lifetimeEarn') or 0
    )

    counters_raw = (
        user_status.get('counters')
        or root.get('counters')
        or user_status.get('searchCounters')
        or []
    )
    snapshot.counters = _parse_counters(counters_raw)

    streaks_raw = user_status.get('streaks') or root.get('streaks') or []
    snapshot.streaks = _parse_streaks(streaks_raw)

    if not snapshot.counters:
        snapshot.missing_sections.append('counters')
    if snapshot.available_points == 0:
        snapshot.missing_sections.append('available_points')
    return snapshot


def parse_getuserinfo(data: object) -> RewardsSnapshot:
    """Parse the legacy ``api/getuserinfo`` transport response.

    Microsoft marks this legacy ("avoid!"); we keep it as a last-resort
    fallback.  It typically only exposes available points and level.
    """
    snapshot = RewardsSnapshot(source='getuserinfo')
    root = _as_mapping(data)

    snapshot.available_points = _first_int(
        root.get('availablePoints')
        or root.get('points')
        or root.get('balance')
        or root.get('UserPoints')
        or 0
    )
    snapshot.level = _first_int(root.get('level') or root.get('Level') or 0)
    snapshot.lifetime_earn = _first_int(root.get('lifetimeEarn') or root.get('LifetimeEarn') or 0)

    snapshot.missing_sections.append('counters')
    snapshot.missing_sections.append('streaks')
    return snapshot


def parse_html_sign_in(html: str) -> bool:
    """Return True if the HTML looks like a Microsoft sign-in page.

    Used by the API backend to detect a signed-out session and surface an
    actionable error (run ``--setup-login``).
    """
    low = html.lower()
    markers = (
        'sign in to microsoft',
        'anmelden',
        'account.microsoft.com',
        'login.live.com',
        'login.microsoftonline.com',
        'microsoft account',
    )
    return any(m in low for m in markers)
