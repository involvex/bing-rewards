# SPDX-FileCopyrightText: 2020 jack-mil
#
# SPDX-License-Identifier: MIT

"""Tests for bing_rewards.cli (count resolution and error handling)."""

from __future__ import annotations

import json
from argparse import Namespace
from unittest.mock import MagicMock

from bing_rewards import cli
from bing_rewards import options as app_options
from bing_rewards.cli import _format_error, _resolve_count
from bing_rewards.report import STATUS_FAILED, RunReport
from bing_rewards.search.plan import SearchBudget, SearchContext, SearchPlan


def _search_ctx() -> SearchContext:
    opts = Namespace(headless=True, mobile=False, desktop=False)
    return SearchContext(
        options=opts,
        plan=SearchPlan(),
        budget=SearchBudget(),
        words=iter([]),
    )


class TestResolveCount:
    def test_count_absent_uses_desktop_config(self) -> None:
        """Regression: --count is absent from Namespace when not passed.

        get_options() only merges CLI args whose value is not None, so a run
        without --count has no ``count`` attribute at all. Accessing
        ``options.count`` directly raised AttributeError and killed the
        search worker thread.
        """
        opts = Namespace(desktop_count=33, mobile_count=23)
        assert _resolve_count(opts, desktop=True) == 33

    def test_count_absent_uses_mobile_config(self) -> None:
        opts = Namespace(desktop_count=33, mobile_count=23)
        assert _resolve_count(opts, desktop=False) == 23

    def test_config_overrides_honored(self) -> None:
        """Per-mode config values must win over the hardcoded constants."""
        opts = Namespace(desktop_count=40, mobile_count=30)
        assert _resolve_count(opts, desktop=True) == 40
        assert _resolve_count(opts, desktop=False) == 30

    def test_count_override(self) -> None:
        """An explicit --count overrides both modes."""
        opts = Namespace(desktop_count=33, mobile_count=23, count=50)
        assert _resolve_count(opts, desktop=True) == 50
        assert _resolve_count(opts, desktop=False) == 50

    def test_count_zero_falls_back(self) -> None:
        """A falsy --count (0) is treated as no override."""
        opts = Namespace(desktop_count=33, mobile_count=23, count=0)
        assert _resolve_count(opts, desktop=True) == 33


class TestSearchErrorCapture:
    def test_worker_exception_is_captured(self, monkeypatch) -> None:
        """A crash in the worker thread must not be swallowed by threading."""

        def boom(*_args, **_kwargs) -> None:
            raise RuntimeError('Chrome failed to start')

        monkeypatch.setattr(cli, '_search_loop', boom)
        searches, error = cli._run_searches_for_profile(_search_ctx(), 'Default')
        assert searches == 0
        assert isinstance(error, RuntimeError)

    def test_failed_search_recorded_in_report(self, monkeypatch) -> None:
        """The account must be marked failed, not silently 'completed'."""

        def boom(*_args, **_kwargs) -> None:
            raise RuntimeError('Chrome crashed')

        monkeypatch.setattr(cli, '_search_loop', boom)
        report = RunReport(version='test', backend='selenium')
        cli._run_searches(_search_ctx(), 'Default', report)

        assert len(report.accounts) == 1
        account = report.accounts[0]
        assert account.status == STATUS_FAILED
        assert account.searches == 0
        assert 'Chrome crashed' in (account.error or '')
        report.finish()
        assert report.status == STATUS_FAILED


class TestFormatError:
    def test_condenses_stacktrace(self) -> None:
        err = RuntimeError(
            'session not created: Chrome failed to start\n'
            'Stacktrace:\n  at foo\n  at bar\n'
            'For documentation on this error, please visit: https://example.com'
        )
        result = _format_error(err)
        assert 'Stacktrace' not in result
        assert 'For documentation' not in result
        assert 'RuntimeError' in result
        assert 'Chrome failed to start' in result


class TestFetchSnapshot:
    def test_skips_without_cookie_file(self, monkeypatch, tmp_path) -> None:
        """No cookie file -> no HTTP call and no warning (just default counts)."""
        monkeypatch.setattr(app_options, 'cookies_location', lambda: tmp_path / 'missing.json')

        def unexpected_http(**_kwargs):
            raise AssertionError('no HTTP client should be created')

        monkeypatch.setattr(cli, 'RewardsHttp', unexpected_http)
        opts = Namespace(cookies_file=None)
        assert cli._fetch_snapshot(opts) is None

    def test_uses_default_cookie_file(self, monkeypatch, tmp_path) -> None:
        """--setup-login's exported cookie file is picked up automatically."""
        cookie_file = tmp_path / 'cookies.json'
        cookie_file.write_text(json.dumps({'MC1': 'abc'}))
        monkeypatch.setattr(app_options, 'cookies_location', lambda: cookie_file)

        captured: dict[str, object] = {}

        def fake_http(**kwargs):
            captured.update(kwargs)
            return MagicMock()

        client = MagicMock()
        client.fetch_snapshot.return_value = 'snapshot'

        def fake_client(**_kwargs):
            return client

        monkeypatch.setattr(cli, 'RewardsHttp', fake_http)
        monkeypatch.setattr(cli, 'RewardsClient', fake_client)

        opts = Namespace(cookies_file=None)
        assert cli._fetch_snapshot(opts) == 'snapshot'
        assert captured['cookies'] == {'MC1': 'abc'}
