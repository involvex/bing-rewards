# SPDX-FileCopyrightText: 2020 jack-mil
#
# SPDX-License-Identifier: MIT

"""Parse earn offers from a ``dapi/me`` dashboard snapshot (Phase 3).

Reads ``dailySetPromotions`` (keyed by date) plus any top-level promotion-like
items and returns :class:`bing_rewards.earn.models.EarnOffer` objects.  Parsing
is tolerant: it extracts what it can and skips malformed entries rather than
raising.
"""

from __future__ import annotations

import re

from bing_rewards.earn.models import EarnOffer
from bing_rewards.util import _as_mapping, _first_int

_POINTS_RE = re.compile(r"(\d+)\s*pts?", re.IGNORECASE)


def _parse_points(text: str) -> int:
    m = _POINTS_RE.search(text or "")
    return int(m.group(1)) if m else 0


def _parse_offer(raw: object, date: str = "") -> EarnOffer | None:
    """Build an :class:`EarnOffer` from one raw dashboard offer object."""
    data = _as_mapping(raw)
    if not data:
        return None

    offer_id = data.get("offerId") or data.get("id") or data.get("hash") or ""
    if not offer_id:
        return None

    title = str(data.get("title") or data.get("linkText") or "").strip()
    description = str(
        data.get("description") or data.get("extBannerDescription") or ""
    ).strip()
    destination_url = str(
        data.get("destinationUrl") or data.get("destination") or data.get("url") or ""
    ).strip()

    points = _first_int(data.get("pointProgress") or 0)
    points_max = _first_int(data.get("pointProgressMax") or 0)
    if points_max == 0:
        # Fall back to the linkText badge ("10 points").
        points_max = _parse_points(data.get("linkText") or data.get("title") or "")
        if points_max and points == 0:
            points = points_max if data.get("complete") else 0

    offer_type = str(data.get("type") or data.get("promotionType") or "").strip()
    state = str(data.get("state") or "").strip()
    complete = bool(data.get("complete"))
    hash_ = str(data.get("hash") or "").strip()

    return EarnOffer(
        offer_id=offer_id,
        title=title,
        description=description,
        destination_url=destination_url,
        points=points,
        points_max=points_max,
        offer_type=offer_type,
        state=state,
        complete=complete,
        date=date,
        hash=hash_,
    )


def parse_daily_set_promotions(raw: object) -> list[EarnOffer]:
    """Parse ``dailySetPromotions`` (keyed by MM/DD/YYYY date) into offers."""
    offers: list[EarnOffer] = []
    data = _as_mapping(raw)
    if not data:
        return offers

    for date, entries in data.items():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            offer = _parse_offer(entry, date=str(date))
            if offer:
                offers.append(offer)
    return offers


def parse_promotions(raw: object) -> list[EarnOffer]:
    """Parse a top-level list of promotion/counter objects into offers."""
    offers: list[EarnOffer] = []
    # Accept either a list or a dict of lists (e.g. counters by category).
    if isinstance(raw, list):
        entries: list[object] = list(raw)
    elif isinstance(raw, dict):
        entries = []
        for value in raw.values():
            if isinstance(value, list):
                entries.extend(value)
    else:
        return offers

    for entry in entries:
        offer = _parse_offer(entry)
        if offer:
            offers.append(offer)
    return offers


def parse_earn_offers(raw: object) -> list[EarnOffer]:
    """Parse all earnable offers from a raw ``dapi/me`` dashboard payload.

    Combines today's daily set promotions with any top-level promotions,
    de-duplicating by ``offer_id``.
    """
    if not isinstance(raw, dict):
        return []

    daily_set = parse_daily_set_promotions(raw.get("dailySetPromotions") or {})

    # Top-level promotion-like buckets that may contain completable offers.
    promotion_buckets = (
        raw.get("counters")
        or {}
        or raw.get("shopAndEarn")
        or []
        or raw.get("activityAndQuiz")
        or []
        or raw.get("dailyPoint")
        or []
    )
    top_level = parse_promotions(promotion_buckets)

    seen: set[str] = set()
    merged: list[EarnOffer] = []
    for offer in daily_set + top_level:
        if offer.offer_id in seen:
            continue
        seen.add(offer.offer_id)
        merged.append(offer)
    return merged
