# SPDX-FileCopyrightText: 2020 jack-mil
#
# SPDX-License-Identifier: MIT

"""Backwards-compatible shim.

``bing_rewards.app.main`` is now implemented in :mod:`bing_rewards.cli`.
This module re-exports it so existing entry points and ``python -m bing_rewards``
keep working.
"""

from __future__ import annotations

from bing_rewards.cli import main

__all__ = ["main"]
