# SPDX-FileCopyrightText: 2020 jack-mil
#
# SPDX-License-Identifier: MIT

"""Command-line entrypoint for bing-rewards.

Wires together options, logging, search backends, earn automation and the
end-of-run report.  The console script and ``python -m bing_rewards`` both
delegate to :func:`main` here; ``bing_rewards.app`` remains a thin shim for
backwards compatibility.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from argparse import Namespace
from typing import TYPE_CHECKING

from pynput import keyboard
from pynput.keyboard import Key

from bing_rewards import earn as earn_module
from bing_rewards import options as app_options
from bing_rewards.log import get_logger, setup_logging
from bing_rewards.login import setup_login
from bing_rewards.report import (
    STATUS_FAILED,
    STATUS_NO_POINTS,
    AccountRun,
    RunReport,
    render_text_summary,
)
from bing_rewards.rewards import RewardsClient, RewardsHttp
from bing_rewards.rewards.http import load_cookies
from bing_rewards.search import SearchOutcome, perform_searches, resolve_backend
from bing_rewards.search.plan import (
    SearchBudget,
    SearchContext,
    SearchPlan,
    plan_searches,
)
from bing_rewards.words import word_generator

if TYPE_CHECKING:
    from bing_rewards.rewards.models import RewardsSnapshot

log = get_logger("cli")

EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_NO_POINTS = 2


def _profile_options(options: Namespace, profile: str) -> Namespace:
    """Return a copy of ``options`` with a single profile set (no mutation)."""
    copy = Namespace(**vars(options))
    copy.profile = profile
    return copy


def _resolve_count(options: Namespace, desktop: bool) -> int:
    """Resolve the search count for one mode, honouring --count."""
    if options.count:
        return options.count
    return app_options.DESKTOP_COUNT if desktop else app_options.MOBILE_COUNT


def _search_loop(
    mode: str,
    ctx: SearchContext,
    profile: str,
) -> int:
    """Run desktop and/or mobile searches for one profile.

    ``mode`` is one of ``'desktop'``, ``'mobile'``, or ``'both'``.

    Returns the number of searches performed.  Counts are capped by the
    quota plan (remaining searches per mode) and the --max-searches budget.
    """
    total = 0
    do_desktop = mode in ("desktop", "both")
    do_mobile = mode in ("mobile", "both")

    if do_desktop:
        requested = (
            ctx.plan.desktop_missing
            if ctx.plan.desktop_known
            else _resolve_count(ctx.options, desktop=True)
        )
        requested = ctx.budget.allocate(requested)
        if requested > 0:
            outcome: SearchOutcome = perform_searches(
                requested, ctx.words, ctx.options.desktop_agent, ctx.options, profile
            )
            total += outcome.searches
            ctx.budget.spend(outcome.searches)
            log.info("Desktop searches complete: %d", outcome.searches)

    if do_mobile:
        remaining_budget = ctx.budget.remaining()
        if remaining_budget is None or remaining_budget > 0:
            requested = (
                ctx.plan.mobile_missing
                if ctx.plan.mobile_known
                else _resolve_count(ctx.options, desktop=False)
            )
            requested = ctx.budget.allocate(requested)
            if requested > 0:
                outcome = perform_searches(
                    requested, ctx.words, ctx.options.mobile_agent, ctx.options, profile
                )
                total += outcome.searches
                ctx.budget.spend(outcome.searches)
                log.info("Mobile searches complete: %d", outcome.searches)

    return total


def _listen_for_abort(thread: threading.Thread, options: Namespace) -> bool:
    """Wait for a search thread, honouring ESC (visible) / Ctrl-C (any).

    Returns ``True`` when the thread finished naturally, ``False`` when aborted.
    """
    if not options.headless:
        print("Press ESC to quit searching")
        try:
            with keyboard.Events() as events:
                while thread.is_alive():
                    event = events.get(timeout=0.5)
                    if event and event.key == Key.esc:
                        print("ESC pressed, terminating")
                        return False
        except KeyboardInterrupt:
            print("CTRL-C pressed, terminating")
            return False
        thread.join()
    else:
        print("Running in headless mode - press CTRL-C to quit")
        try:
            thread.join()
        except KeyboardInterrupt:
            print("CTRL-C pressed, terminating")
            return False
    return True


def _run_searches_for_profile(
    ctx: SearchContext,
    profile: str,
) -> int:
    """Run the configured search mode for one profile.

    Returns the number of searches performed.
    """
    options = ctx.options
    mode = "mobile" if options.mobile else ("desktop" if options.desktop else "both")

    state = {"total": 0}

    def target() -> None:
        state["total"] = _search_loop(mode, ctx, profile)

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    _listen_for_abort(thread, options)
    thread.join(timeout=0)
    return state["total"]


def _run_searches(
    ctx: SearchContext,
    profile: str,
    report: RunReport,
) -> None:
    """Run searches for one profile and append to the report."""
    print(f'Doing searches for profile "{profile}"...')
    searches = _run_searches_for_profile(ctx, profile)
    print(f'Searches complete for profile "{profile}" ({searches}).')
    report.accounts.append(
        AccountRun(profile=profile, backend=report.backend, searches=searches)
    )


def _run_earn(options: Namespace, profile: str, report: RunReport) -> bool:
    """Run earn activities for one profile. Returns False if interrupted."""
    print(f'Running earn activities for profile "{profile}"...')
    earn_options = _profile_options(options, profile)
    try:
        earn_module.run_earn(earn_options)
    except KeyboardInterrupt:
        print("CTRL-C pressed, terminating")
        report.status = STATUS_FAILED
        report.error = "interrupted"
        return False
    print("Earn activities complete!")
    return True


def _fetch_snapshot(options: Namespace) -> RewardsSnapshot | None:
    """Fetch the Rewards dashboard snapshot (best-effort; never crashes)."""
    try:
        cookies = {}
        if options.cookies_file:
            cookies = load_cookies(options.cookies_file)
        http = RewardsHttp(cookies=cookies)
        client = RewardsClient(http=http)
        return client.fetch_snapshot()
    except Exception as e:  # noqa: BLE001 - dashboard read-out is best-effort
        log.warning("Dashboard read-out failed: %s", e)
        return None


def main() -> int:
    """Program entrypoint.

    Parses options, configures logging, then runs searches (and optionally
    earn activities) for each configured profile.  Returns a process exit
    code: 0 success, 1 error, 2 no points earned (unless --run-on-zero-points).
    """
    options = app_options.get_options()
    setup_logging(level=options.log_level, log_file=options.log_file)

    if getattr(options, "setup_login", False):
        return setup_login(options)

    report = RunReport(
        version=app_options.__version,
        backend=resolve_backend(options),
        dryrun=bool(getattr(options, "dryrun", False)),
    )
    report.started_at = time.strftime("%Y-%m-%dT%H:%M:%S")

    # --points: read-only dashboard read-out via the Rewards endpoints.
    if getattr(options, "points", False):
        cookies = {}
        if options.cookies_file:
            cookies = load_cookies(options.cookies_file)
        http = RewardsHttp(cookies=cookies)
        client = RewardsClient(http=http)
        snapshot = client.fetch_snapshot()

        if options.json:
            print(json.dumps(snapshot.to_dict(), indent=2))
        else:
            print(f"bing-rewards v{app_options.__version} · points read-out")
            print(f'  source: {snapshot.source or "none"}')
            print(f"  available points: {snapshot.available_points}")
            print(f"  level: {snapshot.level}")
            print(f"  lifetime earn: {snapshot.lifetime_earn}")
            print(f"  desktop: {snapshot.desktop.label}")
            print(f"  mobile: {snapshot.mobile.label}")
            print(f"  edge: {snapshot.edge.label}")
            if snapshot.missing_sections:
                print(f'  missing sections: {", ".join(snapshot.missing_sections)}')
            print(render_text_summary(report))
        return EXIT_SUCCESS

    words = word_generator()
    budget = SearchBudget(max_searches=getattr(options, "max_searches", None))

    # Fetch the dashboard snapshot for quota-aware searching (unless dryrun).
    snapshot = _fetch_snapshot(options) if not options.dryrun else None
    plan = plan_searches(snapshot) if snapshot else SearchPlan()

    profiles = options.profile
    if not isinstance(profiles, (list, tuple)):
        profiles = [profiles]

    ctx = SearchContext(options=options, plan=plan, budget=budget, words=words)
    _run_all_profiles(ctx, profiles, report)

    report.finish()

    if options.json:
        print(report.render_json())
    else:
        print(render_text_summary(report))

    if report.status == STATUS_NO_POINTS and not getattr(
        options, "run_on_zero_points", False
    ):
        return EXIT_NO_POINTS
    return EXIT_SUCCESS


def _run_all_profiles(
    ctx: SearchContext,
    profiles: list[str],
    report: RunReport,
) -> None:
    """Run searches and/or earn for every configured profile."""
    options = ctx.options
    do_earn = bool(getattr(options, "earn", False))
    do_search = not do_earn

    for profile in profiles:
        profile_opts = _profile_options(options, profile)
        profile_ctx = SearchContext(
            options=profile_opts,
            plan=ctx.plan,
            budget=ctx.budget,
            words=ctx.words,
        )

        if do_search:
            _run_searches(profile_ctx, profile, report)

            if ctx.budget.remaining() is not None and ctx.budget.remaining() <= 0:
                log.info('--max-searches reached, stopping after profile "%s"', profile)
                break

        if do_earn and not _run_earn(profile_opts, profile, report):
            break


if __name__ == "__main__":  # pragma: no cover - manual smoke helper
    sys.exit(main())
