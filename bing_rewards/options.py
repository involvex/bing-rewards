# SPDX-FileCopyrightText: 2020 jack-mil
#
# SPDX-License-Identifier: MIT

"""Defaults and helper functions related to getting user config and command line arguments."""

import dataclasses
import json
import os
import random
import sys
from argparse import (
    ArgumentParser,
    ArgumentTypeError,
    BooleanOptionalAction,
    Namespace,
    RawDescriptionHelpFormatter,
)
from importlib import metadata
from pathlib import Path

import bing_rewards

try:
    __version = metadata.version("bing_rewards")
except metadata.PackageNotFoundError:
    __version = "unknown+local"

# Number of searches to make
DESKTOP_COUNT = 33
MOBILE_COUNT = 23

# Time to allow Chrome to load in seconds
LOAD_DELAY = 1.5

# Default WebDriver wait timeout in seconds
WEBDRIVER_TIMEOUT = 10.0

# Time between searches in seconds
# Searches may not be counted if done too quickly
SEARCH_DELAY = 6.0

# Bing Search base url, with new form= parameter (code differs per browser?)
URL = "https://www.bing.com/search?form=QBRE&q="

# Edge Browser user agents
# Makes Google Chrome look like MS Edge to Bing
MOBILE_AGENT = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 6 Build/AP2A.240605.024) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/121.0.0.0 Mobile Safari/537.36 Edge/121.0.2277.138"
)

DESKTOP_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36 Edge/126.0.0.0"
)


@dataclasses.dataclass()
class Config:
    """Default settings for file config and types."""

    desktop_count: int = DESKTOP_COUNT
    mobile_count: int = MOBILE_COUNT
    load_delay: float = LOAD_DELAY
    timeout: float = WEBDRIVER_TIMEOUT
    search_delay: float | tuple[float, float] = SEARCH_DELAY
    search_url: str = URL
    desktop_agent: str = DESKTOP_AGENT
    mobile_agent: str = MOBILE_AGENT
    browser_path: str = "chrome"
    user_data_dir: str | None = None  # None = dedicated dir next to config.json
    setup_login: bool = False  # One-time headed login for the headless profile
    bing: bool = False  # True means Bing is default search engine
    open_rewards: bool = False
    window: bool = True
    exit: bool = True
    ime: bool = False
    headless: bool = False
    profile: list[str] = dataclasses.field(default_factory=lambda: ["Default"])
    # Opt-in earn automation (rewards.bing.com/earn). Default off.
    # When True, earn activities run *instead of* searches.
    earn: bool = False
    daily_set_only: bool = False
    explore_only: bool = False
    earn_headed: bool = False
    # Delay between earn activities (seconds). None = fall back to search_delay.
    earn_delay: float | None = None
    # Search backend: 'auto' (selenium, pynput fallback), 'selenium', 'pynput', 'api'.
    backend: str = "auto"
    # Browser window size (width,height) for Selenium runs.
    window_size: str = "1280,720"
    # Only read the rewards snapshot and exit (no searches).
    points: bool = False
    # Emit the run summary as JSON on stdout.
    json: bool = False
    # Logging level: critical, error, warning, info, debug.
    log_level: str = "info"
    # Optional file to write log output to.
    log_file: str | None = None
    # Optional JSON file with session cookies (name→value) for authenticated
    # dashboard reads (--points) or the browserless API backend.
    cookies_file: str | None = None
    # Hard cap on total searches across all profiles/modes.
    max_searches: int | None = None
    # Keep exiting with code 2 when no points were earned instead of success.
    run_on_zero_points: bool = False


def parse_args() -> Namespace:
    """Parse all command line arguments and return Namespace."""
    p = ArgumentParser(
        description=bing_rewards.__doc__.format(
            DESKTOP_COUNT=DESKTOP_COUNT,
            MOBILE_COUNT=MOBILE_COUNT,
            VERSION=__version,
            CONFIG=config_location(),
        ),
        epilog="* Repository and issues: https://github.com/jack-mil/bing-search",
        formatter_class=RawDescriptionHelpFormatter,
        prog=Path(sys.argv[0]).name,
    )

    if sys.version_info >= (3, 14):
        p.suggest_on_error = True  # pyright: ignore[reportUnreachable]
        p.color = True

    p.add_argument("--version", action="version", version=f"%(prog)s v{__version}")
    p.add_argument(
        "-c",
        "--count",
        help="Override the number of searches to perform",
        type=int,
    )
    p.add_argument(
        "-b",
        "--bing",
        help="Add this flag if your default search engine is Bing",
        action=BooleanOptionalAction,
        default=None,
    )
    # Mutually exclusive options. Only one can be present
    group = p.add_mutually_exclusive_group()
    group.add_argument(
        "-d",
        "--desktop",
        help="Do only desktop searches",
        action="store_true",
    )
    group.add_argument(
        "-m",
        "--mobile",
        help="Do only mobile searches (appear as phone browser)",
        action="store_true",
    )

    # Other options
    p.add_argument(
        "--exe",
        help="The full path of the Chrome compatible browser executable",
        type=valid_file,
        dest="browser_path",
    )
    p.add_argument(
        "--load-delay",
        help="Override the time given to Chrome to load in seconds",
        metavar="SEC",
        type=int,
    )
    p.add_argument(
        "--search-delay",
        help=(
            "Override the time between searches in seconds.\t"
            "Can be a single value, or comma separated range (e.g. 10,45)"
        ),
        metavar="MIN[,MAX]",
        type=valid_range,
    )
    p.add_argument(
        "-n",
        "--dryrun",
        help="Do everything but search",
        action="store_true",
    )
    p.add_argument(
        "--open-rewards",
        help="Open the rewards page at the end of the run",
        action=BooleanOptionalAction,
        default=None,
    )
    p.add_argument(
        "--window",
        help="Open a new Chrome window (default: True)",
        action=BooleanOptionalAction,
        default=None,
    )
    p.add_argument(
        "-X",
        "--exit",
        help="Close the browser window after searching (default: True)",
        action=BooleanOptionalAction,
        default=None,
    )
    p.add_argument(
        "--ime",
        help="Triggers windows IME to switch to english by pressing SHIFT",
        action=BooleanOptionalAction,
        default=None,
    )
    p.add_argument(
        "--headless",
        help="Run browser in headless mode (no GUI)",
        action=BooleanOptionalAction,
        default=None,
    )
    p.add_argument(
        "--profile",
        help="Sets one or more chrome profiles to run sequentially (space separated)",
        type=str,
        nargs="+",
    )
    p.add_argument(
        "--user-data-dir",
        help=(
            "Path to the persistent Chrome User Data dir used for headless "
            "login. Defaults to a dedicated 'chrome-headless-profile' dir "
            "next to the config file. NOTE: do NOT point this at your real "
            "Chrome profile (it will crash); log in once via --setup-login."
        ),
        type=str,
        dest="user_data_dir",
    )
    p.add_argument(
        "--setup-login",
        help=(
            "One-time login for headless mode: opens a visible Chrome window "
            "using the headless profile so you can log into bing.com. "
            "Cookies persist for future --headless runs."
        ),
        action="store_true",
    )
    p.add_argument(
        "--earn",
        help=(
            "Discover and complete earn activities from "
            "https://rewards.bing.com/earn (daily set, explore, polls, quizzes) "
            "instead of searches. Requires selenium; uses the same persistent "
            "profile as --headless."
        ),
        action=BooleanOptionalAction,
        default=None,
    )
    p.add_argument(
        "--daily-set-only",
        help="With --earn, only complete daily-set quiz/poll items",
        action=BooleanOptionalAction,
        default=None,
    )
    p.add_argument(
        "--explore-only",
        help="With --earn, only complete explore click-through cards",
        action=BooleanOptionalAction,
        default=None,
    )
    p.add_argument(
        "--earn-headed",
        help="Run the --earn browser visibly (for debugging)",
        action=BooleanOptionalAction,
        default=None,
    )
    p.add_argument(
        "--earn-delay",
        help=(
            "Override the time between earn activities in seconds. Defaults to --search-delay."
        ),
        metavar="SEC",
        type=float,
    )
    p.add_argument(
        "--backend",
        help=(
            "Search backend: auto (selenium with pynput fallback), selenium, "
            "pynput, or api (browserless, opt-in). Default: auto."
        ),
        choices=["auto", "selenium", "pynput", "api"],
        default="auto",
    )
    p.add_argument(
        "--points",
        help=(
            "Read the rewards snapshot (points, quotas, streaks) and exit without searching."
        ),
        action="store_true",
    )
    p.add_argument(
        "--json",
        help="Emit the run summary as JSON on stdout instead of plain text.",
        action="store_true",
    )
    p.add_argument(
        "--log-level",
        help="Logging level: critical, error, warning, info, debug. Default: info.",
        choices=["critical", "error", "warning", "info", "debug"],
        default="info",
    )
    p.add_argument(
        "--log-file",
        help="Optional path to a file to also write log output to.",
        type=str,
    )
    p.add_argument(
        "--cookies-file",
        help=(
            "Optional JSON file with session cookies (name->value) for "
            "authenticated dashboard reads (--points) or --backend api."
        ),
        type=str,
    )
    p.add_argument(
        "--max-searches",
        help="Hard cap on the total number of searches across all profiles.",
        type=int,
    )
    p.add_argument(
        "--run-on-zero-points",
        help=(
            "Exit with code 0 even when no points were earned. Default: exit code 2 on zero points."
        ),
        action=BooleanOptionalAction,
        default=False,
    )
    args = p.parse_args()
    return args


def valid_range(value: str) -> float | tuple[float, float]:
    """
    Check that a string is a valid format for the --search-delay flag.
    A valid format looks like:
    --search-delay 10,45
    --search-delay 20
    """
    match value.split(","):
        case [sec] if sec.isdecimal():
            return float(sec)
        case [min, max] if min.isdecimal() and max.isdecimal():
            min_s, max_s = float(min), float(max)
            if max_s <= min_s:
                raise ArgumentTypeError("Max delay should be greater than min.")
            return min_s, max_s
        case _:
            raise ArgumentTypeError("Invalid format. Use numeric value or range.")


def resolve_delay(value: object) -> float:
    """Resolve a delay config value to a single delay in seconds.

    Accepts an int, a float, a single-element sequence ``[x]`` / ``(x,)``, or
    a two-element sequence ``[min, max]`` / ``(min, max)`` which resolves to a
    uniform random value in that range.
    """
    match value:
        case int() as x:
            return float(x)
        case float() as x:
            return float(x)
        case [x] | (x,):
            return resolve_delay(x)
        case [min_s, max_s] | (min_s, max_s):
            return random.uniform(resolve_delay(min_s), resolve_delay(max_s))
        case other:
            raise ValueError(f'Invalid configuration format: "search_delay": {other!r}')


def resolve_earn_delay(options: Namespace) -> float:
    """Resolve the earn delay for a run.

    Uses ``options.earn_delay`` when set, otherwise falls back to
    ``options.search_delay`` so earn activity pacing matches search pacing
    unless explicitly overridden.
    """
    earn_delay = getattr(options, "earn_delay", None)
    if earn_delay is not None:
        return resolve_delay(earn_delay)
    return resolve_delay(options.search_delay)


def valid_file(path: str) -> Path:
    """Check that a string is an existing file; handler for the --exe= flag."""
    exe = Path(path)
    if exe.is_file():
        return exe
    raise ArgumentTypeError(f"file not found: {path}")


def config_location() -> Path:
    r"""Check these locations in order for config.json.

    - %APPDATA%\bing-rewards\
    - $XDG_CONFIG_HOME/bing-rewards/
    - $HOME/.config/bing-rewards/
    """
    # Config file in .config or APPDATA on Windows
    config_home = Path(
        os.environ.get("APPDATA")
        or os.environ.get("XDG_CONFIG_HOME")
        or Path(os.environ["HOME"], ".config"),
        "bing-rewards",
    )

    return config_home.joinpath("config.json")


def read_config() -> Config:
    """Read a configuration file if it exists, otherwise write (and return) default settings."""
    config_file: Path = config_location()

    if not config_file.is_file():
        # Make directories and default config if it doesn't exist
        print(f"Generating config at {config_file}")
        config_file.parent.mkdir(parents=True, exist_ok=True)
        default_options = Config()
        with config_file.open("x") as f:
            json.dump(dataclasses.asdict(default_options), f, indent=2)
        return default_options

    # Otherwise, try to read the config from a file
    config = {}
    with config_file.open() as f:
        try:
            config = json.load(f)
        except json.decoder.JSONDecodeError as e:
            print(e)
            print("Config JSON format error. Reverting to default.")
    # return dataclass with values from config taking priority.
    # Ignore unknown keys so stale config files (e.g. from removed options)
    # don't crash startup; defaults apply for anything missing.
    known = {f.name for f in dataclasses.fields(Config)}
    return Config(**{k: v for k, v in config.items() if k in known})


def get_options() -> Namespace:
    """Combine the defaults, config file options, and command line arguments into one Namespace."""
    file_config = read_config()
    args = parse_args()

    # Start with config file values
    merged_dict = dataclasses.asdict(file_config)

    # Override config values with command line args if provided
    for key, value in vars(args).items():
        if value is not None:
            merged_dict[key] = value
    result = Namespace(**merged_dict)

    # Ensure all boolean options are set
    result.no_window = not result.window
    result.no_exit = not result.exit

    return result
