# SPDX-FileCopyrightText: 2020 jack-mil
#
# SPDX-License-Identifier: MIT

"""Search query generation from the bundled keyword list."""

from __future__ import annotations

import io
import random
from importlib import resources
from typing import TYPE_CHECKING

from bing_rewards.log import get_logger

if TYPE_CHECKING:
    from collections.abc import Iterator

log = get_logger("words")


def word_generator() -> Iterator[str]:
    """Infinitely generate terms from the bundled keyword file.

    Starts reading from a random position in the file. If end of file is
    reached, close and restart. Handles file operations safely and ensures
    uniform random distribution.

    Yields:
        str: A random keyword from the file, stripped of whitespace.

    Raises:
        OSError: If there are issues accessing or reading the file.
    """
    word_data = resources.files("bing_rewards").joinpath("data", "keywords.txt")

    try:
        while True:
            with (
                resources.as_file(word_data) as p,
                p.open(mode="r", encoding="utf-8") as fh,
            ):
                # Get the file size of the keywords file
                fh.seek(0, io.SEEK_END)
                size = fh.tell()

                if size == 0:
                    raise ValueError("Keywords file is empty")

                # Start at a random position in the stream
                fh.seek(random.randint(0, size - 1), io.SEEK_SET)

                # Read and discard partial line to ensure a clean line boundary
                fh.readline()

                # Read lines until EOF
                for raw_line in fh:
                    stripped_line = raw_line.strip()
                    if stripped_line:  # Skip empty lines
                        yield stripped_line

                # Then wrap around to the beginning of the file
                fh.seek(0)
                for raw_line in fh:
                    stripped_line = raw_line.strip()
                    if stripped_line:
                        yield stripped_line
    except OSError as e:
        log.error("Error accessing keywords file: %s", e)
        raise
    except ValueError as e:
        log.error("Unexpected error in word generation: %s", e)
        raise
