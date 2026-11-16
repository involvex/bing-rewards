# SPDX-FileCopyrightText: 2020 jack-mil
#
# SPDX-License-Identifier: MIT

"""Run reporting: the summary printed at the end of a run and `--json`."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

STATUS_COMPLETED = "completed"
STATUS_PARTIAL = "partial"
STATUS_NO_POINTS = "no-points"
STATUS_INTERRUPTED = "interrupted"
STATUS_FAILED = "failed"
STATUS_DRYRUN = "dryrun"


@dataclass(slots=True)
class QuotaStats:
    """Points earned and available for one search counter."""

    earned: int = 0
    maximum: int = 0
    remaining: int = 0
    known: bool = False

    @property
    def label(self) -> str:
        return f"{self.earned}/{self.maximum}" if self.known else "unknown"

    def to_dict(self) -> dict[str, object]:
        return {
            "earned": self.earned,
            "maximum": self.maximum,
            "remaining": self.remaining,
            "known": self.known,
        }


@dataclass(slots=True)
class AccountRun:
    """Outcome of one profile/account run."""

    profile: str
    backend: str = ""
    desktop: QuotaStats = field(default_factory=QuotaStats)
    mobile: QuotaStats = field(default_factory=QuotaStats)
    points_before: int | None = None
    points_after: int | None = None
    searches: int = 0
    earn_completed: list[str] = field(default_factory=list)
    earn_skipped: list[str] = field(default_factory=list)
    earn_failed: list[str] = field(default_factory=list)
    duration_s: float = 0.0
    status: str = STATUS_COMPLETED
    error: str | None = None

    @property
    def points_gained(self) -> int | None:
        if self.points_before is None or self.points_after is None:
            return None
        return self.points_after - self.points_before

    def to_dict(self) -> dict[str, object]:
        return {
            "profile": self.profile,
            "backend": self.backend,
            "desktop": self.desktop.to_dict(),
            "mobile": self.mobile.to_dict(),
            "points_before": self.points_before,
            "points_after": self.points_after,
            "points_gained": self.points_gained,
            "searches": self.searches,
            "earn": {
                "completed": list(self.earn_completed),
                "skipped": list(self.earn_skipped),
                "failed": list(self.earn_failed),
            },
            "duration_s": round(self.duration_s, 1),
            "status": self.status,
            "error": self.error,
        }


@dataclass(slots=True)
class RunReport:
    """Aggregate of all accounts in one invocation."""

    version: str
    backend: str = ""
    dryrun: bool = False
    accounts: list[AccountRun] = field(default_factory=list)
    started_at: str = ""
    duration_s: float = 0.0
    status: str = STATUS_COMPLETED
    started_monotonic: float = field(default_factory=time.monotonic, repr=False)

    @property
    def points_gained(self) -> int | None:
        values = [account.points_gained for account in self.accounts]
        if not values or any(value is None for value in values):
            return None
        return sum(value for value in values if value is not None)

    def finish(self, status: str | None = None) -> None:
        """Stamp the duration and derive the overall status."""
        self.duration_s = time.monotonic() - self.started_monotonic
        self.status = status or self._derive_status()

    def _derive_status(self) -> str:
        if self.dryrun:
            return STATUS_DRYRUN
        if self.status in (STATUS_INTERRUPTED, STATUS_FAILED):
            return self.status
        if not self.accounts:
            return STATUS_FAILED
        if any(account.status == STATUS_FAILED for account in self.accounts):
            return STATUS_FAILED
        if any(account.status == STATUS_PARTIAL for account in self.accounts):
            return STATUS_PARTIAL
        gained = self.points_gained
        return (
            STATUS_NO_POINTS
            if (gained is not None and gained <= 0)
            else STATUS_COMPLETED
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "backend": self.backend,
            "dryrun": self.dryrun,
            "started_at": self.started_at,
            "duration_s": round(self.duration_s, 1),
            "points_gained": self.points_gained,
            "status": self.status,
            "accounts": [account.to_dict() for account in self.accounts],
        }

    def render_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=False)


def _format_duration(seconds: float) -> str:
    total = round(seconds)
    minutes, secs = divmod(total, 60)
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def render_text_summary(report: RunReport) -> str:
    """Render the human-readable end-of-run summary."""
    lines: list[str] = []
    header = f'bing-rewards v{report.version} · backend={report.backend or "unknown"}'
    if report.dryrun:
        header += " · dryrun"
    lines.append(header)

    for account in report.accounts:
        gained = account.points_gained
        gained_text = f"+{gained}" if gained is not None else "unknown"
        balance = (
            f"{account.points_before} -> {account.points_after}"
            if account.points_before is not None and account.points_after is not None
            else "unknown"
        )
        lines.append(
            f'  profile "{account.profile}" [{account.status}]'
            f" · desktop {account.desktop.label}"
            f" · mobile {account.mobile.label}"
            f" · points {gained_text} ({balance})"
            f" · searches {account.searches}"
            f" · {_format_duration(account.duration_s)}"
        )
        if account.earn_completed or account.earn_skipped or account.earn_failed:
            lines.append(
                f"    earn: {len(account.earn_completed)} completed,"
                f" {len(account.earn_skipped)} skipped,"
                f" {len(account.earn_failed)} failed"
            )
        if account.error:
            lines.append(f"    error: {account.error}")

    total_points = report.points_gained
    total_text = f"+{total_points}" if total_points is not None else "unknown"
    lines.append(
        f"  total: {total_text} points · {len(report.accounts)} account(s)"
        f" · {_format_duration(report.duration_s)} · status={report.status}"
    )
    return "\n".join(lines)
