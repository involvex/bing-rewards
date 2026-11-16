# SPDX-FileCopyrightText: 2020 jack-mil
#
# SPDX-License-Identifier: MIT

"""Search backends: keyboard (pynput), WebDriver (selenium) and HTTP (api)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from bing_rewards import login
from bing_rewards.log import get_logger
from bing_rewards.search import api, pynput, selenium
from bing_rewards.search.types import SearchOutcome, resolve_backend

if TYPE_CHECKING:
    from argparse import Namespace
    from collections.abc import Iterator

log = get_logger("search")


def perform_searches(
    count: int,
    words: Iterator[str],
    agent: str,
    options: Namespace,
    profile: str,
) -> SearchOutcome:
    """Run one desktop or mobile search pass with the configured backend.

    With ``backend=auto``, a Selenium pass that finds the persistent profile
    signed out transparently falls back to the pynput backend, so existing
    setups keep working without ``--setup-login``.
    """
    backend = resolve_backend(options)
    if backend == "api":
        return api.search(count, words, agent, options, profile)

    if backend == "selenium":
        try:
            return selenium.search(count, words, agent, options, profile)
        except login.LoginRequiredError as e:
            fallback_allowed = (
                str(getattr(options, "backend", "auto")).lower() == "auto"
                and not getattr(options, "headless", False)
                and not getattr(options, "dryrun", False)
            )
            if not fallback_allowed:
                raise
            log.warning("%s Falling back to keyboard typing (pynput).", e)
            return pynput.search(count, words, agent, options, profile)

    return pynput.search(count, words, agent, options, profile)
