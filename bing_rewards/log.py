# SPDX-FileCopyrightText: 2020 jack-mil
#
# SPDX-License-Identifier: MIT

"""Logging configuration for the bing-rewards CLI.

Progress and diagnostics go to stderr so that stdout stays free for the
machine-readable run summary (`--json`) and for the human summary.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

LOGGER_NAME = "bing_rewards"

LOG_LEVELS: dict[str, int] = {
    "critical": logging.CRITICAL,
    "error": logging.ERROR,
    "warning": logging.WARNING,
    "info": logging.INFO,
    "debug": logging.DEBUG,
}

DEFAULT_LOG_LEVEL = "info"


def get_logger(name: str | None = None) -> logging.Logger:
    """Return the package logger, optionally namespaced with `name`."""
    return logging.getLogger(f"{LOGGER_NAME}.{name}" if name else LOGGER_NAME)


def normalize_level(level: str | None) -> str:
    """Map user input to a known level name, defaulting to info."""
    value = (level or DEFAULT_LOG_LEVEL).strip().lower()
    return value if value in LOG_LEVELS else DEFAULT_LOG_LEVEL


def setup_logging(level: str | None = None, log_file: str | None = None) -> None:
    """(Re)configure package logging for one run.

    Safe to call multiple times: existing handlers are closed first so that
    tests and repeated `main()` calls do not accumulate handlers.
    """
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(LOG_LEVELS[normalize_level(level)])
    logger.propagate = False

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    stream = logging.StreamHandler(stream=sys.stderr)
    stream.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(stream)

    if log_file:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(path, encoding="utf-8")
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        logger.addHandler(file_handler)
