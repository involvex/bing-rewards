# SPDX-FileCopyrightText: 2020 jack-mil
#
# SPDX-License-Identifier: MIT

"""Pytest configuration and shared fixtures for bing-rewards tests."""

from __future__ import annotations

from argparse import Namespace

import pytest

import bing_rewards.options as app_options
from bing_rewards.options import (  # noqa: F401  (re-exported for test modules)
    resolve_delay,
    resolve_earn_delay,
)


@pytest.fixture
def base_options() -> Namespace:
    """Return a minimal options Namespace for tests."""
    return Namespace(
        search_delay=6.0,
        earn_delay=None,
        desktop_count=33,
        mobile_count=23,
        count=None,
        backend='auto',
        headless=False,
        dryrun=False,
        log_level='info',
        log_file=None,
        cookies_file=None,
        max_searches=None,
        run_on_zero_points=False,
        json=False,
        points=False,
        profile=['Default'],
        desktop_agent='Mozilla/5.0',
        mobile_agent='Mozilla/5.0 Mobile',
        load_delay=1.5,
        timeout=10.0,
        window_size='1280,720',
        window=True,
        exit=True,
        no_window=False,
        no_exit=False,
        bing=False,
        ime=False,
        setup_login=False,
        earn=False,
        earn_headed=False,
        daily_set_only=False,
        explore_only=False,
        browser_path='chrome',
        user_data_dir=None,
        open_rewards=False,
    )


@pytest.fixture
def monkeypatch_tmpdir(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Redirect config dir to a temp path so tests don't touch real config."""
    monkeypatch.setattr(app_options, 'config_location', lambda: tmp_path / 'config.json')
