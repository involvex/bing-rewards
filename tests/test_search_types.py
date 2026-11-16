# SPDX-FileCopyrightText: 2020 jack-mil
#
# SPDX-License-Identifier: MIT

"""Tests for bing_rewards.search.types."""

from __future__ import annotations

from argparse import Namespace

from bing_rewards.search.types import BACKENDS, SearchOutcome, resolve_backend


class TestSearchOutcome:
    def test_defaults(self) -> None:
        o = SearchOutcome()
        assert o.backend == ''
        assert o.searches == 0
        assert o.points_gained is None
        assert o.complete is False

    def test_points_gained(self) -> None:
        o = SearchOutcome(points_before=100, points_after=130)
        assert o.points_gained == 30

    def test_points_gained_none(self) -> None:
        o = SearchOutcome(points_before=100)
        assert o.points_gained is None


class TestResolveBackend:
    def test_auto_defaults_to_selenium(self) -> None:
        opts = Namespace(backend='auto')
        assert resolve_backend(opts) == 'selenium'

    def test_explicit_backends(self) -> None:
        for b in ('pynput', 'selenium', 'api'):
            opts = Namespace(backend=b)
            assert resolve_backend(opts) == b

    def test_unknown_backend_defaults_to_selenium(self) -> None:
        opts = Namespace(backend='bogus')
        assert resolve_backend(opts) == 'selenium'


class TestBackends:
    def test_contains_expected(self) -> None:
        assert 'auto' in BACKENDS
        assert 'pynput' in BACKENDS
        assert 'selenium' in BACKENDS
        assert 'api' in BACKENDS
