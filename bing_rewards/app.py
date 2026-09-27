# SPDX-FileCopyrightText: 2020 jack-mil
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

import io
import os
import random
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from argparse import Namespace
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import quote_plus

if TYPE_CHECKING:
    from collections.abc import Iterator

if os.name == "posix":
    import signal


from pynput import keyboard
from pynput.keyboard import Key

from bing_rewards import options as app_options


def _get_search_delay(options: Namespace) -> float:
    """Extract search delay from options."""
    match options.search_delay:
        case int() as x:
            return float(x)
        case float() as x:
            return float(x)
        case [float() as x]:
            return float(x)
        case [float() as min_s, float() as max_s]:
            return random.uniform(min_s, max_s)
        case [int() as min_s, int() as max_s]:
            return random.uniform(min_s, max_s)
        case other:
            raise ValueError(f'Invalid configuration format: "search_delay": {other!r}')


def _headless_profile_dir(options: Namespace) -> Path:
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


def _resolve_profile(options: Namespace) -> str:
    """Normalize options.profile (str or list[str]) to a single name."""
    profile = getattr(options, "profile", "Default")
    if isinstance(profile, (list, tuple)):
        return profile[0] if profile else "Default"
    return profile or "Default"


def _create_chrome_driver(options: Namespace, agent: str, headed: bool = False):
    """Create and return a Chrome WebDriver using the persistent profile.

    Always uses the dedicated `--user-data-dir` so the Microsoft login
    (saved via `--setup-login`) is present. Without persistence Selenium
    gets a fresh anonymous profile and Bing awards no points.
    """
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options as ChromeOptions

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
    chrome_options.add_argument("--window-size=1280,720")

    profile = _resolve_profile(options)
    if profile:
        chrome_options.add_argument(f"--profile-directory={profile}")
    chrome_options.add_argument(f"--user-data-dir={_headless_profile_dir(options)}")

    # Respect custom browser binary (--exe / browser_path) if provided
    browser_path = getattr(options, "browser_path", None)
    if browser_path and str(browser_path) not in ("chrome", "chrome.exe"):
        chrome_options.binary_location = str(browser_path)

    try:
        return webdriver.Chrome(options=chrome_options)
    except Exception as e:
        msg = str(e).lower()
        if "already in use" in msg or "user data directory" in msg:
            print(
                "Headless Chrome profile is locked. "
                "Close any other bing-rewards headless run, then retry."
            )
        raise


def search_headless(
    count: int,
    words_gen: Iterator[str],
    agent: str,
    options: Namespace,
) -> None:
    """Perform searches in headless mode using Selenium WebDriver."""
    try:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
    except ImportError:
        print(
            "Selenium is required for headless mode. "
            "Install with: pip install bing-rewards[headless] "
            "or (uv): uv sync --extra headless / uv pip install selenium"
        )
        sys.exit(1)

    profile = _resolve_profile(options)
    print(
        f'Headless using persistent profile "{profile}" in {_headless_profile_dir(options)}'
    )

    driver = _create_chrome_driver(options, agent)
    wait = WebDriverWait(driver, 10)
    login_warned = False
    try:
        for i in range(count):
            query = next(words_gen)
            print(f"Search {i + 1}: {query}")

            if not options.dryrun:
                driver.get("https://www.bing.com")
                time.sleep(options.load_delay)

                if not login_warned and i == 0:
                    login_warned = True
                    if not _headless_logged_in(driver):
                        print(
                            "Warning: Bing does not appear logged in "
                            f'(profile "{profile}"). Points will NOT count. '
                            "Run once: bing-rewards --setup-login "
                            "(a browser window opens; log into bing.com, "
                            "then press Enter here)."
                        )

                search_box = wait.until(
                    EC.presence_of_element_located((By.ID, "sb_form_q"))
                )
                search_box.clear()
                search_box.send_keys(query)
                search_box.send_keys(Keys.RETURN)

                time.sleep(_get_search_delay(options))
            else:
                time.sleep(_get_search_delay(options))

        if not options.no_exit:
            driver.quit()

    except Exception as e:
        print(f"Headless search error: {e}")
        driver.quit()
        sys.exit(1)


def _headless_logged_in(driver) -> bool:
    """Heuristic: is Bing logged in? Checks the account name header.

    Logged in: <span id="id_n">Lukas</span> (any non-sign-in text).
    Logged out: same element reads "Sign in"/"Anmelden" (or is missing).
    """
    try:
        name = driver.find_element("id", "id_n").text.strip().lower()
        return bool(name) and name not in ("sign in", "log in", "anmelden")
    except Exception:
        return False


def setup_headless_login(options: Namespace) -> None:
    """One-time login for the persistent headless profile.

    Opens a VISIBLE Chrome window using the same dedicated profile dir
    that headless runs use. The user logs into bing.com manually; on
    Enter the window closes and cookies persist for future headless runs.
    """
    try:
        import selenium  # noqa: F401 (import check only)
    except ImportError:
        print(
            "Selenium is required for headless mode. "
            "Install with: pip install bing-rewards[headless] "
            "or (uv): uv sync --extra headless / uv pip install selenium"
        )
        sys.exit(1)

    print(
        f"Opening a visible Chrome window (profile dir: {_headless_profile_dir(options)})."
    )
    print("Log into https://www.bing.com with your Microsoft account there.")
    driver = _create_chrome_driver(options, options.desktop_agent, headed=True)
    try:
        driver.get("https://www.bing.com")
        time.sleep(options.load_delay)
        try:
            input(
                "Press Enter HERE after you are logged in (rewards medal visible)... "
            )
        except (KeyboardInterrupt, EOFError):
            print("Login setup cancelled.")
            return
        if _headless_logged_in(driver):
            print("Login looks good! Future `--headless` runs will earn points.")
        else:
            print(
                "Warning: still looks logged out. Re-run "
                "`bing-rewards --setup-login` and complete the login."
            )
    finally:
        driver.quit()


def word_generator() -> Iterator[str]:
    """Infinitely generate terms from the word file.

    Starts reading from a random position in the file.
    If end of file is reached, close and restart.
    Handles file operations safely and ensures uniform random distribution.

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
                # Get the file size of the Keywords file
                fh.seek(0, io.SEEK_END)
                size = fh.tell()

                if size == 0:
                    raise ValueError("Keywords file is empty")

                # Start at a random position in the stream
                fh.seek(random.randint(0, size - 1), io.SEEK_SET)

                # Read and discard partial line to ensure we start at a clean line boundary
                fh.readline()

                # Read lines until EOF
                for raw_line in fh:
                    stripped_line = raw_line.strip()
                    if stripped_line:  # Skip empty lines
                        yield stripped_line

                # If we hit EOF, seek back to start and continue until we've yielded enough words
                fh.seek(0)
                for raw_line in fh:
                    stripped_line = raw_line.strip()
                    if stripped_line:
                        yield stripped_line
    except OSError as e:
        print(f"Error accessing keywords file: {e}")
        raise
    except Exception as e:
        print(f"Unexpected error in word generation: {e}")
        raise


def browser_cmd(
    exe: Path, agent: str, profile: str = "", headless: bool = False
) -> list[str]:
    """Validate command to open Google Chrome with user-agent `agent`."""
    exe = Path(exe)
    if exe.is_file() and exe.exists():
        cmd = [str(exe.resolve())]
    elif pth := shutil.which(exe):
        cmd = [str(pth)]
    else:
        print(
            f'Command "{exe}" could not be found.\n'
            "Make sure it is available on PATH, "
            "or use the --exe flag to give an absolute path."
        )
        sys.exit(1)

    cmd.extend(["--new-window", f'--user-agent="{agent}"'])
    # Switch to non default profile if supplied with valid string
    # NO CHECKING IS DONE if the profile exists
    if profile:
        cmd.extend([f"--profile-directory={profile}"])
    if os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
        cmd.append("--ozone-platform=x11")
    # Add headless flag if requested
    if headless:
        # Use --headless=new for newer Chrome versions, fallback to --headless for older
        cmd.append("--headless=new")
        # Additional flags for better headless compatibility
        cmd.extend(["--disable-gpu", "--no-sandbox"])
    return cmd


def open_browser(cmd: list[str]) -> subprocess.Popen:
    """Try to open a browser, and exit if the command cannot be found.

    Returns the subprocess.Popen object to handle the browser process.
    """
    try:
        # Open browser as a subprocess
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
        print("Unexpected error:", e)
        print(f"Running command: '{' '.join(cmd)}'")
        sys.exit(1)

    print(f"Opening browser [{chrome.pid}]")
    return chrome


def close_browser(chrome: subprocess.Popen | None):
    """Close the browser process if it exists and is still running.

    Args:
        chrome: The subprocess.Popen object representing the browser process, or None.
    """
    if chrome is None:
        return

    if chrome.poll() is not None:  # Check if the process has already terminated
        print(f"Browser [{chrome.pid}] has already terminated.")
        return

    print(f"Closing browser [{chrome.pid}]")
    try:
        if os.name == "posix":
            os.killpg(chrome.pid, signal.SIGTERM)
            # Optionally wait for process termination to avoid zombies
            chrome.wait(timeout=5)  # Wait for up to 5 seconds
        else:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(chrome.pid)],
                capture_output=True,
                check=True,  # raise exception if taskkill fails
                timeout=5,
            )
    except ProcessLookupError:
        print(f"Browser process [{chrome.pid}] not found (already closed).")
    except subprocess.CalledProcessError as e:
        print(f"Error closing browser [{chrome.pid}]: {e}")
        print(f"Stderr: {e.stderr.decode()}")
    except subprocess.TimeoutExpired:
        print(f"Timeout while closing browser [{chrome.pid}].")
    except Exception as e:
        print(f"Unexpected error while closing browser [{chrome.pid}]: {e}")


def search(count: int, words_gen: Iterator[str], agent: str, options: Namespace):
    """Perform the actual searches in a browser.

    Open a chromium browser window with specified `agent` string, complete `count`
    searches from list `words`, finally terminate browser process on completion.
    """
    if getattr(options, "headless", False):
        return search_headless(count, words_gen, agent, options)

    chrome = None
    if not options.no_window:
        headless_flag = getattr(options, "headless", False)
        cmd = browser_cmd(options.browser_path, agent, options.profile, headless_flag)
        if not options.dryrun:
            chrome = open_browser(cmd)

    # Wait for Chrome to load
    time.sleep(options.load_delay)

    # keyboard controller from pynput
    key_controller = keyboard.Controller()

    # Ctrl + E to open address bar with the default search engine
    # Alt + D focuses address bar without using search engine
    key_mod, key = (Key.ctrl, "e") if options.bing else (Key.alt, "d")

    for i in range(count):
        # Get a random query from set of words
        query = next(words_gen)

        # If user's default search engine is Bing, type the query to the address bar directly
        # Otherwise, form the bing.com search url
        search_url = query if options.bing else options.search_url + quote_plus(query)

        # Use pynput to trigger keyboard events and type search queries
        if not options.dryrun:
            with key_controller.pressed(key_mod):
                key_controller.press(key)
                key_controller.release(key)

            if options.ime:
                # Incase users use a Windows IME, change the language to English
                # Issue #35
                key_controller.tap(Key.shift)
            time.sleep(0.08)

            # Type the url into the address bar
            # with a 30ms delay between keystrokes
            for char in search_url + "\n":
                key_controller.tap(char)
                time.sleep(0.03)
            key_controller.tap(Key.enter)

        print(f"Search {i + 1}: {query}")

        # Delay to let page load
        match options.search_delay:
            case int(x) | float(x) | [float(x)]:
                delay = x
            case [float(min_s), float(max_s)] | [int(min_s), int(max_s)]:
                delay = random.uniform(min_s, max_s)
            case other:
                # catastrophic failure
                raise ValueError(
                    f'Invalid configuration format: "search_delay": {other!r}'
                )

        time.sleep(delay)

    # Skip killing the window if exit flag set
    if options.no_exit:
        return

    close_browser(chrome)


def main():
    """Program entrypoint.

    Loads keywords from a file, interprets command line arguments
    and executes search function in separate thread.
    Setup listener callback for ESC key.
    """
    options = app_options.get_options()

    if getattr(options, "setup_login", False):
        setup_headless_login(options)
        return

    do_earn = bool(getattr(options, "earn", False))
    # --earn runs earn activities *instead of* searches.
    do_search = not do_earn

    words_gen = word_generator()

    def desktop(profile=""):
        # Complete search with desktop settings
        count = options.count if "count" in options else options.desktop_count
        print(f'Doing {count} desktop searches using "{profile}"')

        temp_options = options
        temp_options.profile = profile
        search(count, words_gen, options.desktop_agent, temp_options)
        print("Desktop Search complete!\n")

    def mobile(profile=""):
        # Complete search with mobile settings
        count = options.count if "count" in options else options.mobile_count
        print(f'Doing {count} mobile searches using "{profile}"')

        temp_options = options
        temp_options.profile = profile
        search(count, words_gen, options.mobile_agent, temp_options)
        print("Mobile Search complete!\n")

    def both(profile=""):
        desktop(profile)
        mobile(profile)

    # Execute main method in a separate thread
    if options.desktop:
        target_func = desktop
    elif options.mobile:
        target_func = mobile
    else:
        # If neither mode is specified, complete both modes
        target_func = both

    # Run for each specified profile (defaults to ['Default'])
    for profile in options.profile:
        if do_search:
            # Start the searching in separate thread
            search_thread = threading.Thread(
                target=target_func, args=(profile,), daemon=True
            )
            search_thread.start()

            if getattr(options, "headless", False):
                print("Running in headless mode - press CTRL-C to quit")
            else:
                print("Press ESC to quit searching")

            try:
                # Listen for keyboard events and exit if ESC pressed
                # Skip in headless mode since we use Selenium instead of pynput
                if not getattr(options, "headless", False):
                    while search_thread.is_alive():
                        with keyboard.Events() as events:
                            event = events.get(timeout=0.5)  # block for 0.5 seconds
                            # Exit if ESC key pressed
                            if event and event.key == Key.esc:
                                print("ESC pressed, terminating")
                                return  # Exit the entire function if ESC is pressed
                else:
                    # In headless mode, just wait for the thread
                    search_thread.join()
            except KeyboardInterrupt:
                print("CTRL-C pressed, terminating")
                return  # Exit the entire function if CTRL-C is pressed

            # Wait for the current profile's searches to complete
            if not getattr(options, "headless", False):
                search_thread.join()

        if do_earn:
            from bing_rewards import earn as earn_module

            print(f'Running earn activities for profile "{profile}"...')
            # run_earn resolves the profile via options.profile; pass a
            # single-profile namespace so multi-profile runs stay isolated.
            earn_options = Namespace(**vars(options))
            earn_options.profile = profile
            try:
                earn_module.run_earn(earn_options)
            except KeyboardInterrupt:
                print("CTRL-C pressed, terminating")
                return
            print("Earn activities complete!\n")

    # Open rewards dashboard
    if options.open_rewards and not options.dryrun:
        webbrowser.open_new("https://account.microsoft.com/rewards")
