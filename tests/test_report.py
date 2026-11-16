# SPDX-FileCopyrightText: 2020 jack-mil
#
# SPDX-License-Identifier: MIT

"""Tests for bing_rewards.report."""

from __future__ import annotations

import json

from bing_rewards.report import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_NO_POINTS,
    STATUS_PARTIAL,
    AccountRun,
    QuotaStats,
    RunReport,
    render_text_summary,
)


class TestQuotaStats:
    def test_unknown_quota(self) -> None:
        q = QuotaStats()
        assert q.label == 'unknown'
        assert q.known is False

    def test_known_quota(self) -> None:
        q = QuotaStats(earned=10, maximum=33, remaining=23, known=True)
        assert q.label == '10/33'
        assert q.known is True

    def test_to_dict(self) -> None:
        q = QuotaStats(earned=5, maximum=23, remaining=18, known=True)
        assert q.to_dict() == {
            'earned': 5,
            'maximum': 23,
            'remaining': 18,
            'known': True,
        }


class TestAccountRun:
    def test_points_gained_none_when_missing(self) -> None:
        a = AccountRun(profile='Default')
        assert a.points_gained is None

    def test_points_gained(self) -> None:
        a = AccountRun(profile='Default', points_before=100, points_after=130)
        assert a.points_gained == 30

    def test_to_dict(self) -> None:
        a = AccountRun(
            profile='Default',
            backend='selenium',
            searches=10,
            points_before=100,
            points_after=130,
        )
        d = a.to_dict()
        assert d['profile'] == 'Default'
        assert d['backend'] == 'selenium'
        assert d['searches'] == 10
        assert d['points_gained'] == 30


class TestRunReport:
    def test_points_gained_none_when_no_accounts(self) -> None:
        r = RunReport(version='3.3.0')
        assert r.points_gained is None

    def test_points_gained_sum(self) -> None:
        r = RunReport(version='3.3.0')
        r.accounts.append(AccountRun(profile='a', points_before=100, points_after=130))
        r.accounts.append(AccountRun(profile='b', points_before=200, points_after=210))
        assert r.points_gained == 40

    def test_derive_status_no_points(self) -> None:
        r = RunReport(version='3.3.0')
        r.accounts.append(AccountRun(profile='a', points_before=100, points_after=100))
        r.finish()
        assert r.status == STATUS_NO_POINTS

    def test_derive_status_completed(self) -> None:
        r = RunReport(version='3.3.0')
        r.accounts.append(AccountRun(profile='a', points_before=100, points_after=110))
        r.finish()
        assert r.status == STATUS_COMPLETED

    def test_derive_status_failed(self) -> None:
        r = RunReport(version='3.3.0')
        r.accounts.append(AccountRun(profile='a', status=STATUS_FAILED))
        r.finish()
        assert r.status == STATUS_FAILED

    def test_derive_status_partial(self) -> None:
        r = RunReport(version='3.3.0')
        r.accounts.append(AccountRun(profile='a', status=STATUS_PARTIAL))
        r.finish()
        assert r.status == STATUS_PARTIAL

    def test_render_json(self) -> None:
        r = RunReport(version='3.3.0')
        r.accounts.append(AccountRun(profile='Default', searches=5))
        r.finish()
        data = json.loads(r.render_json())
        assert data['version'] == '3.3.0'
        assert data['status'] == r.status
        assert len(data['accounts']) == 1

    def test_render_text_summary(self) -> None:
        r = RunReport(version='3.3.0')
        r.accounts.append(AccountRun(profile='Default', searches=5))
        r.finish()
        text = render_text_summary(r)
        assert 'bing-rewards v3.3.0' in text
        assert 'Default' in text
