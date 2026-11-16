# SPDX-FileCopyrightText: 2020 jack-mil
#
# SPDX-License-Identifier: MIT

"""Tests for bing_rewards.rewards (dashboard read-out, Phase 1)."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from bing_rewards.rewards.http import load_cookies
from bing_rewards.rewards.models import RewardsSnapshot, SearchQuota, StreakInfo
from bing_rewards.rewards.parse import (
    parse_dapi_me,
    parse_getuserinfo,
    parse_html_sign_in,
    parse_panelflyout,
)


class TestSearchQuota:
    def test_defaults(self) -> None:
        q = SearchQuota()
        assert q.label == 'unknown'
        assert q.known is False

    def test_known(self) -> None:
        q = SearchQuota(counter_key='desktop', earned=10, maximum=33, remaining=23, known=True)
        assert q.label == '10/33'
        assert q.known is True

    def test_to_dict(self) -> None:
        q = SearchQuota(counter_key='mobile', earned=5, maximum=23, remaining=18, known=True)
        assert q.to_dict() == {
            'counter_key': 'mobile',
            'earned': 5,
            'maximum': 23,
            'remaining': 18,
            'known': True,
        }


class TestStreakInfo:
    def test_defaults(self) -> None:
        s = StreakInfo(kind='bing-search')
        assert s.kind == 'bing-search'
        assert s.is_on is False
        assert s.remaining_days == 0

    def test_to_dict(self) -> None:
        s = StreakInfo(kind='daily-set', is_on=True, remaining_days=3, current=5, target=7)
        assert s.to_dict() == {
            'kind': 'daily-set',
            'is_on': True,
            'remaining_days': 3,
            'current': 5,
            'target': 7,
        }


class TestRewardsSnapshot:
    def test_defaults(self) -> None:
        s = RewardsSnapshot()
        assert s.available_points == 0
        assert s.level == 0
        assert s.source == ''
        assert s.desktop.known is False
        assert s.mobile.known is False
        assert s.edge.known is False

    def test_to_dict(self) -> None:
        s = RewardsSnapshot(
            available_points=1234,
            level=10,
            lifetime_earn=5000,
            source='dapi/me',
        )
        d = s.to_dict()
        assert d['available_points'] == 1234
        assert d['level'] == 10
        assert d['lifetime_earn'] == 5000
        assert d['source'] == 'dapi/me'


class TestParseDapiMe:
    def test_full_shape(self) -> None:
        data = {
            'userStatus': {
                'availablePoints': 1234,
                'level': 10,
                'lifetimeEarn': 5000,
                'counters': [
                    {
                        'counterId': 'pcSearch',
                        'pointProgress': 10,
                        'pointProgressMax': 33,
                        'remaining': 23,
                    },
                    {
                        'counterId': 'mobileSearch',
                        'pointProgress': 5,
                        'pointProgressMax': 23,
                        'remaining': 18,
                    },
                ],
                'streaks': [
                    {'kind': 'bing-search', 'isOn': True, 'current': 5, 'target': 7},
                ],
            }
        }
        s = parse_dapi_me(data)
        assert s.source == 'dapi/me'
        assert s.available_points == 1234
        assert s.level == 10
        assert s.lifetime_earn == 5000
        assert s.desktop.known is True
        assert s.desktop.earned == 10
        assert s.desktop.maximum == 33
        assert s.desktop.remaining == 23
        assert s.mobile.known is True
        assert s.mobile.earned == 5
        assert s.streaks['bing-search'].is_on is True

    def test_empty_shape(self) -> None:
        s = parse_dapi_me({})
        assert s.source == 'dapi/me'
        assert s.available_points == 0
        assert 'counters' in s.missing_sections
        assert 'available_points' in s.missing_sections

    def test_counter_key_normalization(self) -> None:
        data = {
            'userStatus': {
                'availablePoints': 100,
                'counters': [
                    {'counterId': 'desktopSearch', 'pointProgress': 3, 'pointProgressMax': 33},
                    {'counterId': 'mobileSearch', 'pointProgress': 1, 'pointProgressMax': 23},
                    {'counterId': 'edgeSearch', 'pointProgress': 0, 'pointProgressMax': 0},
                ],
            }
        }
        s = parse_dapi_me(data)
        assert 'desktop' in s.counters
        assert 'mobile' in s.counters
        assert 'edge' in s.counters
        assert s.counters['desktop'].earned == 3
        assert s.counters['mobile'].earned == 1


class TestParsePanelflyout:
    def test_full_shape(self) -> None:
        data = {
            'dashboard': {
                'availablePoints': 500,
                'level': 5,
                'counters': [
                    {'name': 'pcSearch', 'earned': 20, 'max': 33, 'remaining': 13},
                ],
            }
        }
        s = parse_panelflyout(data)
        assert s.source == 'panelflyout'
        assert s.available_points == 500
        assert s.level == 5
        assert s.desktop.known is True
        assert s.desktop.earned == 20

    def test_empty_shape(self) -> None:
        s = parse_panelflyout({})
        assert s.available_points == 0
        assert 'counters' in s.missing_sections


class TestParseGetuserinfo:
    def test_legacy_shape(self) -> None:
        data = {'availablePoints': 999, 'level': 3, 'lifetimeEarn': 777}
        s = parse_getuserinfo(data)
        assert s.source == 'getuserinfo'
        assert s.available_points == 999
        assert s.level == 3
        assert s.lifetime_earn == 777
        assert 'counters' in s.missing_sections
        assert 'streaks' in s.missing_sections


class TestParseHtmlSignIn:
    def test_signed_in(self) -> None:
        assert parse_html_sign_in('<html><body>Welcome, Lukas</body></html>') is False

    def test_sign_in_page(self) -> None:
        assert parse_html_sign_in('<title>Sign in to Microsoft</title>') is True
        assert parse_html_sign_in('Anmelden - Microsoft') is True
        assert parse_html_sign_in('login.live.com') is True
        assert parse_html_sign_in('account.microsoft.com') is True


class TestLoadCookies:
    def test_load_dict_cookies(self, tmp_path) -> None:
        p = tmp_path / 'cookies.json'
        p.write_text('{"MC1": "abc", "SRCHHPGUSR": "xyz"}')
        cookies = load_cookies(p)
        assert cookies == {'MC1': 'abc', 'SRCHHPGUSR': 'xyz'}

    def test_load_list_cookies(self, tmp_path) -> None:
        p = tmp_path / 'cookies.json'
        p.write_text('[{"name": "MC1", "value": "abc"}, {"name": "SRCHHPGUSR", "value": "xyz"}]')
        cookies = load_cookies(p)
        assert cookies == {'MC1': 'abc', 'SRCHHPGUSR': 'xyz'}

    def test_load_malformed_list_missing_key(self, tmp_path) -> None:
        p = tmp_path / 'cookies.json'
        p.write_text('[{"name": "MC1"}, {"name": "SRCHHPGUSR", "value": "xyz"}]')
        with pytest.raises(ValueError, match='missing required key'):
            load_cookies(p)

    def test_load_non_object_entry(self, tmp_path) -> None:
        p = tmp_path / 'cookies.json'
        p.write_text('["not-an-object"]')
        with pytest.raises(TypeError, match='non-object entry'):
            load_cookies(p)

    def test_load_not_object_or_list(self, tmp_path) -> None:
        p = tmp_path / 'cookies.json'
        p.write_text('"just a string"')
        with pytest.raises(TypeError, match='must contain a JSON object or list'):
            load_cookies(p)

    def test_world_readable_cookie_rejected_mocked(self, tmp_path, monkeypatch) -> None:
        """POSIX permission check: world-readable cookie file is refused."""
        p = tmp_path / 'cookies.json'
        p.write_text('{"MC1": "abc"}')

        class FakeStatResult:
            st_mode = 0o100644  # regular file, rw-r--r-- (world-readable)

        monkeypatch.setattr(os, 'name', 'posix')
        with (
            patch('os.stat', return_value=FakeStatResult()),
            pytest.raises(ValueError, match='readable by others'),
        ):
            load_cookies(p)

    def test_private_cookie_accepted_mocked(self, tmp_path, monkeypatch) -> None:
        """POSIX permission check: 600 cookie file is accepted."""
        p = tmp_path / 'cookies.json'
        p.write_text('{"MC1": "abc"}')

        class FakeStatResult:
            st_mode = 0o100600  # regular file, rw-------

        monkeypatch.setattr(os, 'name', 'posix')
        with patch('os.stat', return_value=FakeStatResult()):
            cookies = load_cookies(p)
            assert cookies == {'MC1': 'abc'}
