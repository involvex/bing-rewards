# SPDX-FileCopyrightText: 2020 jack-mil
#
# SPDX-License-Identifier: MIT

"""Tests for bing_rewards.search.plan (quota-aware searching, Phase 1)."""

from __future__ import annotations

from bing_rewards.rewards.models import RewardsSnapshot, SearchQuota
from bing_rewards.search.plan import SearchBudget, SearchPlan, plan_searches


class TestSearchPlan:
    def test_defaults(self) -> None:
        p = SearchPlan()
        assert p.desktop_missing == 0
        assert p.mobile_missing == 0
        assert p.do_desktop is False
        assert p.do_mobile is False
        assert p.total_missing == 0
        assert p.quota_known is False

    def test_with_missing(self) -> None:
        p = SearchPlan(desktop_missing=10, mobile_missing=5, desktop_known=True, mobile_known=True)
        assert p.do_desktop is True
        assert p.do_mobile is True
        assert p.total_missing == 15
        assert p.quota_known is True


class TestSearchBudget:
    def test_unlimited(self) -> None:
        b = SearchBudget()
        assert b.remaining() is None
        assert b.allocate(100) == 100
        b.spend(30)
        assert b.remaining() is None

    def test_limited(self) -> None:
        b = SearchBudget(max_searches=50)
        assert b.remaining() == 50
        assert b.allocate(30) == 30
        b.spend(30)
        assert b.remaining() == 20
        assert b.allocate(50) == 20  # capped by remaining
        b.spend(20)
        assert b.remaining() == 0
        assert b.allocate(10) == 0

    def test_spend_exceeds(self) -> None:
        b = SearchBudget(max_searches=10)
        b.spend(15)
        assert b.remaining() == 0


class TestPlanSearches:
    def test_all_known(self) -> None:
        snapshot = RewardsSnapshot(
            available_points=1000,
            counters={
                'desktop': SearchQuota(
                    counter_key='desktop', earned=20, maximum=33, remaining=13, known=True
                ),
                'mobile': SearchQuota(
                    counter_key='mobile', earned=5, maximum=23, remaining=18, known=True
                ),
                'edge': SearchQuota(
                    counter_key='edge', earned=0, maximum=0, remaining=0, known=True
                ),
            },
        )
        plan = plan_searches(snapshot)
        assert plan.desktop_missing == 13
        assert plan.mobile_missing == 18
        assert plan.edge_missing == 0
        assert plan.desktop_known is True
        assert plan.mobile_known is True
        assert plan.edge_known is True
        assert plan.quota_known is True
        assert plan.do_desktop is True
        assert plan.do_mobile is True

    def test_unknown_quotas(self) -> None:
        snapshot = RewardsSnapshot(available_points=1000)
        plan = plan_searches(snapshot)
        assert plan.desktop_missing == 0
        assert plan.mobile_missing == 0
        assert plan.quota_known is False
        assert plan.do_desktop is False
        assert plan.do_mobile is False

    def test_partial_known(self) -> None:
        snapshot = RewardsSnapshot(
            available_points=1000,
            counters={
                'desktop': SearchQuota(
                    counter_key='desktop', earned=10, maximum=33, remaining=23, known=True
                ),
            },
        )
        plan = plan_searches(snapshot)
        assert plan.desktop_missing == 23
        assert plan.mobile_missing == 0  # unknown -> 0
        assert plan.desktop_known is True
        assert plan.mobile_known is False
        assert plan.quota_known is True  # at least one known

    def test_negative_remaining_clamped(self) -> None:
        snapshot = RewardsSnapshot(
            available_points=1000,
            counters={
                'desktop': SearchQuota(
                    counter_key='desktop', earned=40, maximum=33, remaining=-7, known=True
                ),
            },
        )
        plan = plan_searches(snapshot)
        assert plan.desktop_missing == 0  # negative clamped to 0
