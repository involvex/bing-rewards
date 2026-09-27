# SPDX-FileCopyrightText: 2020 jack-mil
#
# SPDX-License-Identifier: MIT

"""Automatic discovery and completion of Bing Rewards earn activities.

Covers https://rewards.bing.com/earn cards: Daily Set, Streaks (informational),
Explore on Bing / More Promotions click-throughs, polls and quizzes.

Search automation in app.py is untouched; this module is opt-in via --earn
and always uses Selenium (pynput cannot parse/complete dashboard cards).
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from argparse import Namespace

EARN_URL = 'https://rewards.bing.com/earn'
REWARDS_URL = 'https://rewards.bing.com/'

# Locale-insensitive markers (German + English, see screenshot in issue).
COMPLETED_MARKERS = (
    'abgeschlossen',
    'completed',
    'done',
    'erledigt',
    '✓',
)
LOCKED_MARKERS = (
    'wird morgen freigeschaltet',
    'coming soon',
    'locked',
    'gesperrt',
    'freigeschaltet',
)
# Cards we can never complete automatically (need real Edge/App usage).
SKIP_TITLE_MARKERS = (
    'edge-browsing',
    'edge browsing',
    'edge herunter',
    'download edge',
    'microsoft edge',
    'bing-app',
    'bing app',
)

# Points badge like +10 / +30 / ★ 100 / 40/40
_POINTS_RE = re.compile(r'\+?\s*(\d+)\s*(?:pts|points|punkte)?', re.IGNORECASE)


@dataclass()
class Offer:
    """Single earn activity discovered on the dashboard."""

    title: str
    url: str
    points: int = 0
    kind: str = 'explore'  # explore | poll | quiz | checkin | streak | generic
    state: str = 'incomplete'  # incomplete | complete | locked | skipped
    section: str = ''


@dataclass()
class EarnReport:
    """Outcome of one run_earn() pass."""

    completed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.completed) + len(self.skipped) + len(self.failed)


def _earn_delay(options: Namespace) -> float:
    """Delay between earn activities; reuses search_delay unless earn_delay set."""
    from bing_rewards.app import _get_search_delay

    custom = getattr(options, 'earn_delay', None)
    if custom is not None:
        return float(custom)
    try:
        return _get_search_delay(options)
    except Exception:
        return 3.0


def is_rewards_logged_in(driver) -> bool:
    """Heuristic: rewards header shows account name when logged in."""
    try:
        # bing.com header (shared session) ...
        name = driver.find_element('id', 'id_n').text.strip().lower()
        if name and name not in ('sign in', 'log in', 'anmelden'):
            return True
    except Exception:
        pass
    try:
        # ... or rewards medal / profile on rewards.bing.com
        for selector in ('#id_n', '#reward_p_JSwa', '.rewards-card'):
            try:
                el = driver.find_element('css selector', selector)
                if el and el.text.strip():
                    return True
            except Exception:
                continue
    except Exception:
        pass
    # If we reached the earn page without redirect to login, assume ok.
    return 'login' not in driver.current_url.lower()


def _classify_kind(title: str, url: str) -> str:
    t = f'{title} {url}'.lower()
    if 'poll' in t or 'abstimmung' in t or 'umfrage' in t:
        return 'poll'
    if 'quiz' in t or 'trivia' in t or 'test' in t or 'wer hat gewonnen' in t:
        return 'quiz'
    if 'check-in' in t or 'checkin' in t or 'einchecken' in t or 'streak' in t:
        return 'checkin'
    return 'explore'


def _card_state(card_text: str) -> str:
    low = card_text.lower()
    if any(m in low for m in LOCKED_MARKERS):
        # "Abgeschlossen" cards also contain no "+N" badge; locked cards say
        # "Wird morgen freigeschaltet" — check locked first.
        # Note: locked cards can also show "+10", so order matters.
        if 'abgeschlossen' in low or 'completed' in low:
            # Completed cards in screenshot read "Abgeschlossen" + external icon;
            # locked cards read "Wird morgen freigeschaltet". Disambiguate:
            if 'morgen' in low or 'soon' in low:
                return 'locked'
            return 'complete'
        return 'locked'
    if any(m in low for m in COMPLETED_MARKERS):
        return 'complete'
    return 'incomplete'


def discover_offers(driver, timeout: int = 15) -> list[Offer]:
    """Load the earn dashboard and return incomplete offers.

    Locale-insensitive: never matches on German/English titles, only on
    state markers (+N vs Abgeschlossen/Completed vs Wird morgen/...).
    Resilient to DOM changes: tries card containers first, falls back to links.
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    driver.get(EARN_URL)
    wait = WebDriverWait(driver, timeout)
    try:
        wait.until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
    except Exception:
        pass
    time.sleep(2)  # dashboard loads cards async

    offers: list[Offer] = []
    seen_urls: set[str] = set()

    # Strategy 1: card-like containers (rewards cards render as links/cards
    # with a points badge nearby).
    card_selectors = [
        'a[href*="bing.com/search"]',
        'a[href*="rewards.bing.com"]',
        'a[href*="aka.ms"]',
        '[data-bi-id] a',
        '.rewards-card a',
        'mee-rewards-card a',
    ]
    candidates = []
    for sel in card_selectors:
        try:
            candidates.extend(driver.find_elements(By.CSS_SELECTOR, sel))
        except Exception:
            continue

    # Strategy 2 (fallback): every link on the page.
    if not candidates:
        try:
            candidates = driver.find_elements(By.TAG_NAME, 'a')
        except Exception:
            return []

    for el in candidates:
        try:
            href = (el.get_attribute('href') or '').strip()
            text = (el.text or '').strip()
            # Include parent card text so state badges (+10 / Abgeschlossen)
            # are visible even when the link itself has little text.
            try:
                parent = el.find_element(By.XPATH, './ancestor::*[3]')
                card_text = (parent.text or text).strip()
            except Exception:
                card_text = text
            if not href or href in seen_urls:
                continue
            # Only rewards-relevant destinations.
            low_href = href.lower()
            if not any(
                k in low_href
                for k in (
                    'bing.com',
                    'rewards.bing',
                    'microsoft.com',
                    'aka.ms',
                    'quiz',
                    'poll',
                )
            ):
                continue
            state = _card_state(card_text)
            title = text.split('\n')[0][:120] if text else href[:120]
            if any(m in title.lower() for m in SKIP_TITLE_MARKERS):
                state = 'skipped'
            points = 0
            m = _POINTS_RE.search(card_text)
            if m:
                try:
                    points = int(m.group(1))
                except ValueError:
                    points = 0
            kind = _classify_kind(title, href)
            offers.append(
                Offer(
                    title=title or href,
                    url=href,
                    points=points,
                    kind=kind,
                    state=state,
                )
            )
            seen_urls.add(href)
        except Exception:
            continue

    return [o for o in offers if o.state == 'incomplete']


def _click_first(driver, selectors: list[str], timeout: int = 8) -> bool:
    """Click the first matching visible element; return True on success."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    for sel in selectors:
        try:
            el = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, sel))
            )
            el.click()
            return True
        except Exception:
            continue
    return False


def complete_offer(driver, offer: Offer, options: Namespace) -> bool:
    """Complete one offer; returns True if it looks successful."""
    delay = _earn_delay(options)
    dryrun = bool(getattr(options, 'dryrun', False))
    print(f'Earn [{offer.kind}/{offer.points}pts]: {offer.title}')
    if dryrun:
        print(f'  (dryrun) would open {offer.url}')
        return True

    try:
        driver.get(offer.url)
    except Exception as e:
        print(f'  failed to open: {e}')
        return False
    time.sleep(getattr(options, 'load_delay', 2) + 1)

    try:
        if offer.kind == 'explore':
            # Click-through search cards award points on page view.
            time.sleep(delay)
            return True
        if offer.kind in ('checkin', 'streak', 'generic'):
            time.sleep(delay)
            return True
        if offer.kind == 'poll':
            clicked = _click_first(
                driver,
                [
                    '.pollOption',
                    '.poll-option',
                    'input[type="radio"]',
                    '#poll_Option1',
                    'button[id*="poll" i]',
                    '.bt_pollvote',
                ],
            )
            time.sleep(delay)
            return clicked
        if offer.kind == 'quiz':
            # Multi-question quizzes: answer up to 10 rounds, then Next/Submit.
            for _ in range(10):
                answered = _click_first(
                    driver,
                    [
                        '.quiz-answer',
                        '.c-quiz answer',
                        '[id^="rqAnswerOption"]',
                        '.rqOption',
                        '.trivia-option',
                        'button[class*="answer" i]',
                    ],
                    timeout=5,
                )
                time.sleep(2)
                # Advance if a Next/Start button appears.
                _click_first(
                    driver,
                    [
                        '#rqStartQuiz',
                        '#rqNextQuestion',
                        'button[id*="next" i]',
                        'button[class*="next" i]',
                        '#quizCompleteContainer a',
                    ],
                    timeout=3,
                )
                time.sleep(1)
                if not answered:
                    break
            time.sleep(delay)
            return True
    except Exception as e:
        print(f'  error completing: {e}')
        return False
    time.sleep(delay)
    return True


def run_earn(options: Namespace, driver=None) -> EarnReport:
    """Discover and complete earn activities. Creates a driver if none given.

    Always uses Selenium with the persistent profile (same login as
    --headless / --setup-login). Honors dryrun, daily_set_only, explore_only.
    Owns the driver it creates (quits unless no_exit); never quits a passed-in
    driver.
    """
    try:
        import selenium  # noqa: F401 (import check only)
    except ImportError:
        print(
            'Selenium is required for --earn. '
            'Install with: pip install bing-rewards[headless] '
            'or (uv): uv sync --extra headless / uv pip install selenium'
        )
        return EarnReport(failed=['selenium missing'])

    from bing_rewards import app as app_module

    own_driver = driver is None
    report = EarnReport()
    if own_driver:
        headed = bool(getattr(options, 'earn_headed', False))
        agent = getattr(options, 'desktop_agent', '')
        try:
            driver = app_module._create_chrome_driver(options, agent, headed=headed)
        except Exception as e:
            print(f'Could not start browser for --earn: {e}')
            report.failed.append(f'driver: {e}')
            return report

    try:
        if not bool(getattr(options, 'dryrun', False)):
            driver.get('https://www.bing.com')
            time.sleep(getattr(options, 'load_delay', 1.5))
            if not is_rewards_logged_in(driver):
                print(
                    'Warning: Bing does not appear logged in. '
                    'Earn points will NOT count. Run: bing-rewards --setup-login'
                )

        offers = discover_offers(driver)
        print(f'Found {len(offers)} incomplete earn offer(s).')

        daily_only = bool(getattr(options, 'daily_set_only', False))
        explore_only = bool(getattr(options, 'explore_only', False))
        filtered: list[Offer] = []
        for o in offers:
            low = f'{o.title} {o.url}'.lower()
            if explore_only and o.kind != 'explore':
                report.skipped.append(f'{o.title} (not explore)')
                continue
            if daily_only and 'daily' not in low and 'set' not in low and o.kind == 'explore':
                # Daily Set cards link to quiz/poll/search; keep quiz/poll,
                # skip pure explore promos when --daily-set-only.
                report.skipped.append(f'{o.title} (not daily set)')
                continue
            filtered.append(o)

        for offer in filtered:
            try:
                ok = complete_offer(driver, offer, options)
                (report.completed if ok else report.failed).append(offer.title)
            except Exception as e:
                print(f'  failed {offer.title}: {e}')
                report.failed.append(offer.title)
            time.sleep(1)

        print(
            f'Earn done: {len(report.completed)} completed, '
            f'{len(report.skipped)} skipped, {len(report.failed)} failed.'
        )
        return report
    finally:
        if own_driver and driver is not None:
            try:
                if not bool(getattr(options, 'no_exit', False)):
                    driver.quit()
            except Exception:
                pass
