# SPDX-FileCopyrightText: 2020 jack-mil
#
# SPDX-License-Identifier: MIT

"""Selenium backend: drive a real Chrome session with the saved profile."""

from __future__ import annotations

import time
from argparse import Namespace
from typing import TYPE_CHECKING

from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait

from bing_rewards import login
from bing_rewards.browser import chrome_driver
from bing_rewards.log import get_logger
from bing_rewards.options import resolve_delay
from bing_rewards.search.types import SearchOutcome

if TYPE_CHECKING:
    from collections.abc import Iterator

log = get_logger('search.selenium')

BING_HOME = 'https://www.bing.com'
SEARCH_BOX_ID = 'sb_form_q'


def search(
    count: int,
    words: Iterator[str],
    agent: str,
    options: Namespace,
    profile: str,
) -> SearchOutcome:
    """Perform searches in a Chrome session driven by Selenium.

    Raises `LoginRequiredError` when the persistent profile is signed out,
    so the `auto` backend can fall back to keyboard typing.
    """
    outcome = SearchOutcome(backend='selenium')
    headed = not bool(getattr(options, 'headless', False))

    with chrome_driver(options, agent, headed=headed) as driver:
        wait = WebDriverWait(driver, options.timeout)
        log.info('Using persistent profile %s', login.profile_dir_label(options))

        for i in range(count):
            query = next(words)

            if options.dryrun:
                log.info('Search %d: %s (dryrun)', i + 1, query)
                outcome.searches += 1
                time.sleep(resolve_delay(options.search_delay))
                continue

            try:
                driver.get(BING_HOME)
            except WebDriverException as e:
                outcome.error = f'browser navigation failed: {e}'
                log.error('%s', outcome.error)
                return outcome
            time.sleep(options.load_delay)

            if i == 0 and not login.bing_logged_in(driver):
                raise login.LoginRequiredError(
                    f'Bing does not appear logged in (profile "{profile}"). '
                    'Points will NOT count. Run once: bing-rewards --setup-login'
                )

            try:
                search_box = wait.until(
                    expected_conditions.presence_of_element_located((By.ID, SEARCH_BOX_ID))
                )
                search_box.clear()
                search_box.send_keys(query)
                search_box.send_keys(Keys.RETURN)
            except WebDriverException as e:
                outcome.error = f'search input failed: {e}'
                log.error('%s', outcome.error)
                return outcome

            log.info('Search %d: %s', i + 1, query)
            outcome.searches += 1
            time.sleep(resolve_delay(options.search_delay))

        outcome.complete = True
        return outcome


def _profile_namespace(options: Namespace, profile: str) -> Namespace:
    """Copy of options with a single profile value (never mutates input)."""
    copy = Namespace(**vars(options))
    copy.profile = profile
    return copy
