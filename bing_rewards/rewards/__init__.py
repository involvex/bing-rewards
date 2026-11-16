# SPDX-FileCopyrightText: 2020 jack-mil
#
# SPDX-License-Identifier: MIT

"""Microsoft Rewards dashboard read-out (Phase 1).

Clean-room reimplementation of the dashboard transport pattern from
Microsoft-Rewards-Script (AccountData.ts / DashboardMapper): dapi/me →
panelflyout → legacy getuserinfo, with tolerant parsing and graceful
degradation when sections are missing.
"""

from bing_rewards.rewards.api import RewardsClient
from bing_rewards.rewards.http import (
    DAPI_ME_URL,
    GETUSERINFO_URL,
    PANELFLYOUT_URL,
    RewardsHttp,
    RewardsHttpError,
    load_cookies,
    save_cookies,
)
from bing_rewards.rewards.models import RewardsSnapshot, SearchQuota, StreakInfo
from bing_rewards.rewards.parse import (
    parse_dapi_me,
    parse_getuserinfo,
    parse_html_sign_in,
    parse_panelflyout,
)

__all__ = [
    "DAPI_ME_URL",
    "GETUSERINFO_URL",
    "PANELFLYOUT_URL",
    "RewardsClient",
    "RewardsHttp",
    "RewardsHttpError",
    "RewardsSnapshot",
    "SearchQuota",
    "StreakInfo",
    "load_cookies",
    "parse_dapi_me",
    "parse_getuserinfo",
    "parse_html_sign_in",
    "parse_panelflyout",
    "save_cookies",
]
