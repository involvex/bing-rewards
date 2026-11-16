# SPDX-FileCopyrightText: 2020 jack-mil
#
# SPDX-License-Identifier: MIT

"""Unit tests for bing_rewards.search.api (browserless backend, Phase 2)."""

from __future__ import annotations

from argparse import Namespace
from collections.abc import Iterator

from bing_rewards.search.api import search


class _FakeWords(Iterator[str]):
    """Finite word iterator for deterministic tests."""

    def __init__(self, words: list[str]) -> None:
        self._words = iter(words)

    def __next__(self) -> str:
        return next(self._words)


def _options(**overrides: object) -> Namespace:
    base = {
        'backend': 'api',
        'cookies_file': '',
        'dryrun': False,
        'search_delay': 0,
        'bing': False,
        'headless': False,
    }
    base.update(overrides)
    return Namespace(**base)


class TestSearchNoCookies:
    def test_no_cookies_file_sets_error(self) -> None:
        opts = _options(cookies_file='')
        outcome = search(2, _FakeWords(['a', 'b']), 'Mozilla/5.0', opts, 'Default')
        assert outcome.backend == 'api'
        assert outcome.searches == 0
        assert outcome.error is not None
        assert 'cookies-file' in outcome.error

    def test_missing_cookies_file_sets_error(self, tmp_path) -> None:
        missing = tmp_path / 'does-not-exist.json'
        opts = _options(cookies_file=str(missing))
        outcome = search(1, _FakeWords(['a']), 'Mozilla/5.0', opts, 'Default')
        assert outcome.searches == 0
        assert outcome.error is not None


class TestSearchDryrun:
    def test_dryrun_counts_searches(self) -> None:
        opts = _options(cookies_file='/tmp/whatever.json', dryrun=True)
        outcome = search(3, _FakeWords(['a', 'b', 'c']), 'Mozilla/5.0', opts, 'Default')
        assert outcome.searches == 3
        assert outcome.error is None
        assert outcome.complete is True


class TestSearchRealHttpFailsGracefully:
    def test_search_without_network_returns_error(self) -> None:
        opts = _options(cookies_file='/tmp/whatever.json', dryrun=False)
        outcome = search(1, _FakeWords(['a']), 'Mozilla/5.0', opts, 'Default')
        # No real cookies; reportActivity will fail (401/redirect), so error is set
        # and searches is 0.
        assert outcome.searches == 0
        assert outcome.error is not None
