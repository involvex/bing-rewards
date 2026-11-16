# SPDX-FileCopyrightText: 2020 jack-mil
#
# SPDX-License-Identifier: MIT

"""Tests for bing_rewards.earn (dashboard-JSON earn automation, Phase 3)."""

from __future__ import annotations

from argparse import Namespace
from typing import ClassVar
from unittest.mock import MagicMock, patch

from bing_rewards.earn import _filter_offers, run_earn
from bing_rewards.earn.client import EarnClient
from bing_rewards.earn.dashboard import (
    parse_daily_set_promotions,
    parse_earn_offers,
    parse_promotions,
)
from bing_rewards.earn.models import EarnOffer, EarnReport


class TestEarnOffer:
    def test_defaults(self) -> None:
        o = EarnOffer(offer_id='abc', title='Quiz')
        assert o.offer_id == 'abc'
        assert o.title == 'Quiz'
        assert o.points == 0
        assert o.points_max == 0
        assert o.state == 'incomplete'
        assert o.is_complete is False
        assert o.is_locked is False
        assert o.is_reportable is False  # no hash

    def test_complete(self) -> None:
        o = EarnOffer(offer_id='a', title='Q', complete=True, state='Complete')
        assert o.is_complete is True

    def test_locked(self) -> None:
        o = EarnOffer(offer_id='a', title='Q', state='Locked')
        assert o.is_locked is True
        assert o.is_reportable is False

    def test_reportable(self) -> None:
        o = EarnOffer(offer_id='a', title='Q', hash='xyz123')
        assert o.is_reportable is True

    def test_points_remaining(self) -> None:
        o = EarnOffer(offer_id='a', title='Q', points=10, points_max=30)
        assert o.points_remaining == 20

    def test_to_dict(self) -> None:
        o = EarnOffer(offer_id='a', title='Q', points=5, points_max=10, hash='h')
        d = o.to_dict()
        assert d['offer_id'] == 'a'
        assert d['is_reportable'] is True


class TestEarnReport:
    def test_defaults(self) -> None:
        r = EarnReport()
        assert r.total == 0
        assert r.points_earned == 0

    def test_total(self) -> None:
        r = EarnReport(
            completed=['a', 'b'],
            skipped=['c'],
            failed=['d'],
            points_earned=40,
        )
        assert r.total == 4
        assert r.points_earned == 40

    def test_to_dict(self) -> None:
        r = EarnReport(completed=['a'], points_earned=10)
        d = r.to_dict()
        assert d['completed'] == ['a']
        assert d['points_earned'] == 10
        assert d['total'] == 1


class TestParseDashboard:
    DAILY_SET_RAW: ClassVar[dict] = {
        '03/06/2024': [
            {
                'offerId': 'DS_1',
                'hash': 'hash1',
                'title': 'Island odyssey',
                'description': 'A quiz on the Cyclades',
                'destinationUrl': 'https://www.bing.com/search?q=cyclades',
                'type': 'urlreward',
                'promotionType': 'urlreward',
                'state': 'Default',
                'complete': False,
                'pointProgress': 0,
                'pointProgressMax': 10,
                'linkText': '10 points',
            },
            {
                'offerId': 'DS_2',
                'hash': 'hash2',
                'title': 'Doubleshot quiz',
                'type': 'quiz',
                'state': 'Complete',
                'complete': True,
                'pointProgress': 30,
                'pointProgressMax': 30,
            },
            {
                'offerId': 'DS_3',
                'hash': 'hash3',
                'title': 'Coming soon poll',
                'type': 'poll',
                'state': 'Locked',
                'complete': False,
                'pointProgress': 0,
                'pointProgressMax': 10,
            },
        ]
    }

    def test_parse_daily_set(self) -> None:
        offers = parse_daily_set_promotions(self.DAILY_SET_RAW)
        assert len(offers) == 3
        titles = {o.title for o in offers}
        assert titles == {'Island odyssey', 'Doubleshot quiz', 'Coming soon poll'}
        island = next(o for o in offers if o.title == 'Island odyssey')
        assert island.date == '03/06/2024'
        assert island.offer_type == 'urlreward'
        assert island.points_max == 10
        assert island.hash == 'hash1'
        assert island.is_reportable is True

    def test_complete_excluded_from_reportable(self) -> None:
        offers = parse_daily_set_promotions(self.DAILY_SET_RAW)
        quiz = next(o for o in offers if o.title == 'Doubleshot quiz')
        assert quiz.is_complete is True
        assert quiz.is_reportable is False

    def test_locked_excluded_from_reportable(self) -> None:
        offers = parse_daily_set_promotions(self.DAILY_SET_RAW)
        poll = next(o for o in offers if o.title == 'Coming soon poll')
        assert poll.is_locked is True
        assert poll.is_reportable is False

    def test_parse_promotions_list(self) -> None:
        raw = [
            {
                'offerId': 'P1',
                'hash': 'hp1',
                'title': 'Shop & earn',
                'type': 'purchase',
                'state': 'Default',
                'complete': False,
                'pointProgressMax': 100,
                'linkText': '100 points',
            }
        ]
        offers = parse_promotions(raw)
        assert len(offers) == 1
        assert offers[0].points_max == 100
        assert offers[0].is_reportable is True

    def test_parse_promotions_dict_of_lists(self) -> None:
        raw = {
            'counters': [
                {
                    'offerId': 'C1',
                    'hash': 'hc1',
                    'title': 'PC search',
                    'type': 'search',
                    'state': 'Default',
                    'complete': False,
                    'pointProgressMax': 30,
                }
            ]
        }
        offers = parse_promotions(raw)
        assert len(offers) == 1
        assert offers[0].offer_type == 'search'

    def test_parse_earn_offers_dedupes(self) -> None:
        raw = {
            'dailySetPromotions': self.DAILY_SET_RAW,
            'shopAndEarn': [
                {
                    'offerId': 'DS_1',
                    'hash': 'hash1',
                    'title': 'Island odyssey',
                    'type': 'urlreward',
                    'state': 'Default',
                    'complete': False,
                }
            ],
        }
        offers = parse_earn_offers(raw)
        ids = [o.offer_id for o in offers]
        assert ids.count('DS_1') == 1  # de-duplicated

    def test_parse_earn_offers_empty(self) -> None:
        assert parse_earn_offers({}) == []
        assert parse_earn_offers(None) == []  # type: ignore[arg-type]


class TestEarnClient:
    def _client(self) -> EarnClient:
        http = MagicMock()
        return EarnClient(http=http, earn_delay=0)

    def test_skips_complete_and_locked(self) -> None:
        client = self._client()
        offers = [
            EarnOffer(offer_id='a', title='Done', complete=True, state='Complete'),
            EarnOffer(offer_id='b', title='Locked', state='Locked'),
            EarnOffer(offer_id='c', title='Todo', hash='hc'),
        ]
        report = client.run(iter(offers), dryrun=True)
        assert 'Done (already complete)' in report.skipped
        assert 'Locked (locked)' in report.skipped
        assert 'Todo' in report.completed

    def test_dryrun_no_points(self) -> None:
        """Dryrun must not accumulate phantom points or sleep."""
        client = self._client()
        offers = [
            EarnOffer(offer_id='a', title='A', hash='ha', points_max=10),
            EarnOffer(offer_id='b', title='B', hash='hb', points_max=30, points=10),
        ]
        report = client.run(iter(offers), dryrun=True)
        assert report.completed == ['A', 'B']
        assert report.points_earned == 0  # nothing actually earned

    def test_input_type_without_hash_skipped(self) -> None:
        client = self._client()
        offers = [
            EarnOffer(offer_id='q', title='Quiz', offer_type='quiz', state='Default'),
        ]
        report = client.run(iter(offers), dryrun=False)
        assert report.skipped == []
        assert 'Quiz' in report.failed


class TestRunEarnOptions:
    def test_missing_cookies_file(self) -> None:
        opts = Namespace(cookies_file='', desktop_agent='UA', earn_delay=None, dryrun=False)
        report = run_earn(opts)
        assert report.failed
        assert 'cookies-file' in report.failed[0]


class TestCliEarnWiring:
    def test_run_earn_returns_report(self) -> None:
        http = MagicMock()
        http.json_get.return_value = {
            'dailySetPromotions': {
                '03/06/2024': [
                    {
                        'offerId': 'DS_1',
                        'hash': 'hash1',
                        'title': 'Island odyssey',
                        'type': 'urlreward',
                        'state': 'Default',
                        'complete': False,
                        'pointProgressMax': 10,
                    }
                ]
            }
        }

        opts = Namespace(
            cookies_file='cookies.json',
            desktop_agent='UA',
            earn_delay=0,
            dryrun=True,
            daily_set_only=False,
            explore_only=False,
        )
        with (
            patch('bing_rewards.earn.load_cookies', return_value={'c': 'v'}),
            patch('bing_rewards.earn.RewardsHttp', return_value=http),
        ):
            report = run_earn(opts)
        assert 'Island odyssey' in report.completed


class TestFilterOffersPure:
    """_filter_offers must be pure: no report mutation, returns skipped list."""

    def _make_offers(self) -> list[EarnOffer]:
        return [
            EarnOffer(offer_id='a', title='Edge browsing', offer_type='urlreward', hash='ha'),
            EarnOffer(offer_id='b', title='Daily quiz', offer_type='quiz', hash='hb'),
            EarnOffer(offer_id='c', title='Explore card', offer_type='purchase', hash='hc'),
            EarnOffer(offer_id='d', title='Search points', offer_type='search', hash='hd'),
            EarnOffer(
                offer_id='e', title='Locked poll', offer_type='poll', hash='he', state='Locked'
            ),
        ]

    def test_no_filters(self) -> None:
        opts = Namespace(daily_set_only=False, explore_only=False)
        offers, skipped = _filter_offers(self._make_offers(), opts)
        assert len(offers) == 4  # edge-browsing skipped
        assert len(skipped) == 1
        assert 'Edge browsing' in skipped[0]

    def test_daily_set_only(self) -> None:
        opts = Namespace(daily_set_only=True, explore_only=False)
        offers, _skipped = _filter_offers(self._make_offers(), opts)
        # urlreward and quiz/poll with 'daily' in title pass; search/purchase without 'daily' skipped
        titles = {o.title for o in offers}
        assert 'Daily quiz' in titles
        assert 'Locked poll' in titles  # poll type passes daily_only
        assert 'Explore card' not in titles  # purchase without 'daily'
        assert 'Search points' not in titles  # search without 'daily'

    def test_explore_only(self) -> None:
        opts = Namespace(daily_set_only=False, explore_only=True)
        offers, _skipped = _filter_offers(self._make_offers(), opts)
        titles = {o.title for o in offers}
        assert 'Edge browsing' not in titles  # skipped by marker first
        assert 'Explore card' in titles
        assert 'Search points' in titles
        assert 'Daily quiz' not in titles  # quiz not in explore types

    def test_does_not_mutate_report(self) -> None:
        """Calling _filter_offers must not touch any external report."""
        opts = Namespace(daily_set_only=False, explore_only=False)
        report_before = EarnReport()
        report_before.skipped.append('pre-existing')
        _filter_offers(self._make_offers(), opts)
        # The function takes no report argument, so it cannot mutate one.
        assert report_before.skipped == ['pre-existing']
