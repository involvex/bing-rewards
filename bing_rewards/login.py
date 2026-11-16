# SPDX-FileCopyrightText: 2020 jack-mil
#
# SPDX-License-Identifier: MIT

"""Microsoft account login helpers for automated browsers."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from selenium.common.exceptions import WebDriverException

from bing_rewards.browser import chrome_driver, driver_cookies, headless_profile_dir
from bing_rewards.log import get_logger
from bing_rewards.options import cookies_location
from bing_rewards.rewards.http import save_cookies

if TYPE_CHECKING:
    from argparse import Namespace

log = get_logger('login')

SIGNED_OUT_LABELS = frozenset({'sign in', 'log in', 'anmelden', 'signin'})


class LoginRequiredError(RuntimeError):
    """Raised when the persistent profile is not signed in to Microsoft."""


def bing_logged_in(driver: Any) -> bool:
    """Heuristic: is Bing logged in? Checks the account name header.

    Logged in: <span id="id_n">Lukas</span> (any non-sign-in text).
    Logged out: same element reads "Sign in"/"Anmelden" (or is missing).
    """
    try:
        name = driver.find_element('id', 'id_n').text.strip().lower()
    except WebDriverException:
        return False
    return bool(name) and name not in SIGNED_OUT_LABELS


def profile_dir_label(options: Namespace) -> str:
    """Short description of the profile dir used by Selenium runs."""
    return f'"{options.profile}" in {headless_profile_dir(options)}'


def setup_login(options: Namespace) -> int:
    """One-time login for the persistent headless profile.

    Opens a VISIBLE Chrome window using the same dedicated profile dir
    that headless runs use. The user logs into bing.com manually; on
    Enter the window closes and cookies persist for future runs.
    """
    log.info(
        'Opening a visible Chrome window (profile dir: %s).',
        headless_profile_dir(options),
    )
    log.info('Log into https://www.bing.com with your Microsoft account there.')
    try:
        with chrome_driver(options, options.desktop_agent, headed=True) as driver:
            driver.get('https://www.bing.com')
            time.sleep(options.load_delay)
            try:
                input('Press Enter HERE after you are logged in (rewards medal visible)... ')
            except (KeyboardInterrupt, EOFError):
                log.info('Login setup cancelled.')
                return 1
            if bing_logged_in(driver):
                cookie_path = cookies_location()
                cookies = driver_cookies(driver)
                if cookies:
                    save_cookies(cookies, cookie_path)
                    log.info('Login looks good! Session cookies saved to %s.', cookie_path)
                else:
                    log.warning(
                        'Login looks good, but no session cookies could be exported. '
                        'The Rewards read-out and --backend api will be unavailable.'
                    )
                return 0
            log.warning(
                'Still looks logged out. Re-run `bing-rewards --setup-login` and complete the login.'
            )
            return 1
    except Exception as e:  # noqa: BLE001 - selenium raises many exception types
        log.error('Could not open the login window: %s', e)
        return 1
