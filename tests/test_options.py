# SPDX-FileCopyrightText: 2020 jack-mil
#
# SPDX-License-Identifier: MIT

"""Tests for bing_rewards.options."""

from __future__ import annotations

from argparse import ArgumentTypeError
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from bing_rewards.options import (
    DESKTOP_COUNT,
    MOBILE_COUNT,
    resolve_delay,
    resolve_earn_delay,
    valid_file,
)


class TestValidFile:
    def test_valid_file_accepts_existing_file(self, tmp_path: Path) -> None:
        p = tmp_path / 'chrome.exe'
        p.write_text('')
        assert valid_file(str(p)) == p

    def test_valid_file_rejects_missing(self) -> None:
        with pytest.raises(ArgumentTypeError):
            valid_file('/nonexistent/path/chrome.exe')

    def test_valid_file_rejects_directory(self, tmp_path: Path) -> None:
        with pytest.raises(ArgumentTypeError):
            valid_file(str(tmp_path))


class TestResolveDelay:
    def test_int(self) -> None:
        assert resolve_delay(5) == 5.0

    def test_float(self) -> None:
        assert resolve_delay(6.5) == 6.5

    def test_single_element_list(self) -> None:
        assert resolve_delay([10]) == 10.0

    def test_single_element_tuple(self) -> None:
        assert resolve_delay((10,)) == 10.0

    def test_range_list(self) -> None:
        result = resolve_delay([5, 10])
        assert 5.0 <= result <= 10.0

    def test_range_tuple(self) -> None:
        result = resolve_delay((5, 10))
        assert 5.0 <= result <= 10.0

    def test_mixed_int_float_range(self) -> None:
        result = resolve_delay([5, 10.0])
        assert 5.0 <= result <= 10.0

    def test_invalid(self) -> None:
        with pytest.raises(ValueError):
            resolve_delay('not-a-number')  # type: ignore[arg-type]
        with pytest.raises(ValueError):
            resolve_delay([1, 2, 3])


class TestResolveEarnDelay:
    def test_uses_earn_delay_when_set(self, base_options) -> None:
        base_options.earn_delay = 4.0
        assert resolve_earn_delay(base_options) == 4.0

    def test_falls_back_to_search_delay(self, base_options) -> None:
        base_options.earn_delay = None
        base_options.search_delay = 8.0
        assert resolve_earn_delay(base_options) == 8.0

    def test_falls_back_to_default_search_delay(self, base_options) -> None:
        base_options.earn_delay = None
        base_options.search_delay = 6.0
        assert resolve_earn_delay(base_options) == 6.0

    def test_invalid_search_delay_raises(self, base_options) -> None:
        base_options.earn_delay = None
        base_options.search_delay = 'bad'  # type: ignore[assignment]
        with pytest.raises(ValueError):
            resolve_earn_delay(base_options)


class TestDefaults:
    def test_desktop_count(self) -> None:
        assert DESKTOP_COUNT == 33

    def test_mobile_count(self) -> None:
        assert MOBILE_COUNT == 23
