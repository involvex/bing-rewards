# SPDX-FileCopyrightText: 2020 jack-mil
#
# SPDX-License-Identifier: MIT

"""Legacy pynput backend: type queries into a visible browser window."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING
from urllib.parse import quote_plus

from pynput import keyboard
from pynput.keyboard import Key

from bing_rewards.browser import browser_cmd, close_browser, open_browser
from bing_rewards.log import get_logger
from bing_rewards.options import resolve_delay
from bing_rewards.report import QuotaStats
from bing_rewards.search.types import SearchOutcome

if TYPE_CHECKING:
    from argparse import Namespace
    from collections.abc import Iterator

log = get_logger('search.pynput')


def search(
    count: int,
    words: Iterator[str],
    agent: str,
    options: Namespace,
    profile: str,
) -> SearchOutcome:
    """Perform the searches by typing into the focused browser window.

    Opens a browser window with user-agent `agent`, completes `count`
    searches from `words`, and terminates the browser process on completion.
    """
    outcome = SearchOutcome(backend='pynput')
    chrome = None
    if not options.no_window and not options.dryrun:
        cmd = browser_cmd(options.browser_path, agent, profile)
        chrome = open_browser(cmd)

    try:
        # Wait for Chrome to load
        time.sleep(options.load_delay)

        key_controller = keyboard.Controller()

        # Ctrl + E opens the address bar with the default search engine;
        # Alt + D focuses the address bar without using the search engine.
        key_mod, key = (Key.ctrl, 'e') if options.bing else (Key.alt, 'd')

        for i in range(count):
            query = next(words)

            # If the default search engine is Bing, type the query directly
            # into the address bar. Otherwise build the bing.com search url.
            search_url = query if options.bing else options.search_url + quote_plus(query)

            if not options.dryrun:
                _type_query(key_controller, key_mod, key, search_url, options)

            log.info('Search %d: %s', i + 1, query)
            outcome.searches += 1
            time.sleep(resolve_delay(options.search_delay))

        outcome.complete = True
        return outcome
    finally:
        # Skip killing the window if exit flag set
        if not options.no_exit:
            close_browser(chrome)


def _type_query(
    key_controller,
    key_mod,
    key,
    search_url: str,
    options: Namespace,
) -> None:
    """Send one search via the keyboard."""
    with key_controller.pressed(key_mod):
        key_controller.press(key)
        key_controller.release(key)

    if options.ime:
        # Users with a Windows IME need SHIFT to switch to English (issue #35)
        key_controller.tap(Key.shift)
    time.sleep(0.08)

    # Type the url into the address bar with a 30ms delay between keystrokes
    for char in search_url + '\n':
        key_controller.tap(char)
        time.sleep(0.03)
    key_controller.tap(Key.enter)


__all__ = ['QuotaStats', 'search']
