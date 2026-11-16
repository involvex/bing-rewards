# SPDX-FileCopyrightText: 2020 jack-mil
#
# SPDX-License-Identifier: MIT

"""Chrome process and WebDriver lifecycle helpers."""

from __future__ import annotations

import atexit
import contextlib
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions

from bing_rewards import options as app_options
from bing_rewards.log import get_logger

if TYPE_CHECKING:
    from argparse import Namespace

if os.name == "posix":
    import signal

log = get_logger("browser")

# Drivers that must be quit if the process exits unexpectedly (Ctrl-C, ESC,
# an exception in the worker thread). Without this, Chrome stays behind.
_ACTIVE_DRIVERS: set[Any] = set()


def register_driver(driver: Any) -> None:
    _ACTIVE_DRIVERS.add(driver)


def unregister_driver(driver: Any) -> None:
    _ACTIVE_DRIVERS.discard(driver)


def cleanup_drivers() -> None:
    """Best-effort quit of every driver still registered."""
    for driver in list(_ACTIVE_DRIVERS):
        with contextlib.suppress(Exception):
            driver.quit()
    _ACTIVE_DRIVERS.clear()


atexit.register(cleanup_drivers)


def headless_profile_dir(options: Namespace) -> Path:
    """Resolve the persistent User Data dir used for headless runs.

    This is a DEDICATED dir (next to config.json), NOT your real Chrome
    profile. Your real profile cannot be reused: chromedriver crashes on
    it (DevToolsActivePort), copies of it lose the login to app-bound
    encryption, and remote-debugging attach is blocked by Chrome for the
    default data directory. A dedicated dir + one-time `--setup-login`
    is the reliable path.
    """
    custom = getattr(options, "user_data_dir", None)
    if custom:
        p = Path(custom)
        p.mkdir(parents=True, exist_ok=True)
        return p
    if env_dir := os.environ.get("CHROME_USER_DATA_DIR"):
        p = Path(env_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p
    p = app_options.config_location().parent / "chrome-headless-profile"
    p.mkdir(parents=True, exist_ok=True)
    return p


def resolve_profile(options: Namespace) -> str:
    """Return the current Chrome profile name as a single string."""
    profile = getattr(options, "profile", "Default")
    if isinstance(profile, (list, tuple)):
        return profile[0] if profile else "Default"
    return profile or "Default"


def create_chrome_driver(options: Namespace, agent: str, headed: bool = False):
    """Create and return a Chrome WebDriver using the persistent profile.

    Always uses the dedicated `--user-data-dir` so the Microsoft login
    (saved via `--setup-login`) is present. Without persistence Selenium
    gets a fresh anonymous profile and Bing awards no points.
    """
    chrome_options = ChromeOptions()
    chrome_options.add_argument(f"--user-agent={agent}")
    if not headed:
        # NOTE: `chrome_options.headless = True` was removed in Selenium 4.x.
        # It silently did nothing, so Chrome launched headed. The flag must
        # be passed explicitly. (Do NOT add excludeSwitches/useAutomation
        # tweaks here: they break networking when a profile is attached.)
        chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument(f"--window-size={options.window_size}")

    profile = resolve_profile(options)
    if profile:
        chrome_options.add_argument(f"--profile-directory={profile}")
    chrome_options.add_argument(f"--user-data-dir={headless_profile_dir(options)}")

    # Respect custom browser binary (--exe / browser_path) if provided
    browser_path = getattr(options, "browser_path", None)
    if browser_path and str(browser_path) not in ("chrome", "chrome.exe"):
        chrome_options.binary_location = str(browser_path)

    try:
        driver = webdriver.Chrome(options=chrome_options)
    except Exception as e:
        if (
            "already in use" in str(e).lower()
            or "user data directory" in str(e).lower()
        ):
            log.error(
                "Headless Chrome profile is locked. "
                "Close any other bing-rewards headless run, then retry."
            )
        raise
    register_driver(driver)
    return driver


@contextlib.contextmanager
def chrome_driver(options: Namespace, agent: str, headed: bool = False):
    """Yield a Chrome driver and always quit it afterwards."""
    driver = create_chrome_driver(options, agent, headed=headed)
    try:
        yield driver
    finally:
        with contextlib.suppress(Exception):
            driver.quit()
        unregister_driver(driver)


def browser_cmd(
    exe: Path | str, agent: str, profile: str = "", headless: bool = False
) -> list[str]:
    """Validate command to open a Chrome-compatible browser with user-agent `agent`."""
    exe = Path(exe)
    if exe.is_file():
        cmd = [str(exe.resolve())]
    elif pth := shutil.which(str(exe)):
        cmd = [str(pth)]
    else:
        log.error(
            'Command "%s" could not be found. '
            "Make sure it is available on PATH, "
            "or use the --exe flag to give an absolute path.",
            exe,
        )
        raise SystemExit(1)

    # NOTE: no shell is involved, so quotes must not be embedded in the
    # argument - otherwise they become part of the user agent string.
    cmd.extend(["--new-window", f"--user-agent={agent}"])
    # Switch to non default profile if supplied with valid string
    # NO CHECKING IS DONE if the profile exists
    if profile:
        cmd.append(f"--profile-directory={profile}")
    if os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
        cmd.append("--ozone-platform=x11")
    if headless:
        # --headless=new is the current headless mode in Chrome
        cmd.append("--headless=new")
        cmd.extend(["--disable-gpu", "--no-sandbox"])
    return cmd


def open_browser(cmd: list[str]) -> subprocess.Popen:
    """Open a browser, returning the process handle.

    Exits if the command cannot be started.
    """
    try:
        # Only if a new window should be opened
        if os.name == "posix":
            chrome = subprocess.Popen(
                cmd,
                stderr=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                start_new_session=True,
            )
        else:
            chrome = subprocess.Popen(cmd)
    except OSError as e:
        log.error("Unexpected error: %s", e)
        log.error("Running command: '%s'", " ".join(cmd))
        raise SystemExit(1) from e

    log.info("Opening browser [%s]", chrome.pid)
    return chrome


def close_browser(chrome: subprocess.Popen | None) -> None:
    """Close the browser process if it exists and is still running."""
    if chrome is None:
        return

    if chrome.poll() is not None:  # Check if the process has already terminated
        log.debug("Browser [%s] has already terminated.", chrome.pid)
        return

    log.info("Closing browser [%s]", chrome.pid)
    try:
        if os.name == "posix":
            os.killpg(chrome.pid, signal.SIGTERM)
            # Wait for process termination to avoid zombies
            chrome.wait(timeout=5)
        else:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(chrome.pid)],
                capture_output=True,
                check=True,  # raise exception if taskkill fails
                timeout=5,
            )
    except ProcessLookupError:
        log.debug("Browser process [%s] not found (already closed).", chrome.pid)
    except subprocess.CalledProcessError as e:
        log.warning("Error closing browser [%s]: %s", chrome.pid, e)
        if e.stderr:
            log.debug("Stderr: %s", e.stderr.decode(errors="replace"))
    except subprocess.TimeoutExpired:
        log.warning("Timeout while closing browser [%s].", chrome.pid)
    except OSError as e:
        log.warning("Error closing browser [%s]: %s", chrome.pid, e)


def driver_quit(driver: Any) -> None:
    """Quit a Selenium driver, ignoring teardown errors."""
    if driver is None:
        return
    with contextlib.suppress(Exception):
        driver.quit()
    unregister_driver(driver)


def driver_cookies(driver: Any) -> dict[str, str]:
    """Extract name→value cookies from a Selenium driver.

    The result is suitable for :func:`bing_rewards.rewards.http.save_cookies`
    so a session cookie file can be produced for ``--backend api`` or
    ``--points`` after a one-time ``--setup-login`` Selenium run.
    """
    cookies: dict[str, str] = {}
    try:
        for cookie in driver.get_cookies():
            name = cookie.get("name")
            value = cookie.get("value")
            if name and value is not None:
                cookies[str(name)] = str(value)
    except Exception:  # noqa: BLE001 - cookie extraction is best-effort
        log.debug("Could not extract cookies from driver")
    return cookies


if __name__ == "__main__":  # pragma: no cover - manual smoke helper
    sys.exit("This module is not a script.")
