# SPDX-FileCopyrightText: 2020 jack-mil
#
# SPDX-License-Identifier: MIT

"""Small shared utilities used across the codebase.

Kept here so parsers in :mod:`bing_rewards.rewards.parse` and
:mod:`bing_rewards.earn.dashboard` don't duplicate the same tolerant
extraction logic.
"""

from __future__ import annotations

import math
import re


def _first_int(obj: object, default: int = 0) -> int:
    """Best-effort int extraction from JSON numbers or numeric strings.

    Booleans are rejected (``bool`` is a subclass of ``int``).  NaN/Inf
    floats fall back to ``default``.
    """
    if isinstance(obj, bool):
        return default
    if isinstance(obj, int):
        return obj
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return default
        return int(obj)
    if isinstance(obj, str):
        m = re.search(r'\d+', obj)
        return int(m.group(0)) if m else default
    return default


def _as_mapping(obj: object) -> dict[str, object]:
    """Return ``obj`` if it is a dict, otherwise an empty dict."""
    return obj if isinstance(obj, dict) else {}
