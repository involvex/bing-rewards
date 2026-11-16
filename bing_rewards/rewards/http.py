# SPDX-FileCopyrightText: 2020 jack-mil
#
# SPDX-License-Identifier: MIT

"""Small HTTP client for the Microsoft Rewards endpoints.

Uses :mod:`urllib3` (a transitive dependency of :mod:`selenium`) so no new
package is introduced.  All requests carry the cookies extracted from a live
Selenium session (or a saved cookie file) so the Microsoft session is reused.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlencode

import urllib3
from urllib3.util.retry import Retry

from bing_rewards.log import get_logger

if TYPE_CHECKING:
    from collections.abc import Mapping

log = get_logger("rewards.http")

REWARDS_ORIGIN = "https://rewards.bing.com"
PLATFORM_ORIGIN = "https://prod.rewardsplatform.microsoft.com"
BING_ORIGIN = "https://www.bing.com"

# Microsoft dashboards: options=613 is the bitmask observed in the TS port.
DAPI_ME_URL = f"{PLATFORM_ORIGIN}/dapi/me?channel=&options=613"
PANELFLYOUT_URL = f"{BING_ORIGIN}/rewards/panelflyout/getuserinfo"
GETUSERINFO_URL = f"{REWARDS_ORIGIN}/api/getuserinfo"
# Browserless search-activity reporting endpoint used by --backend api.
REPORT_ACTIVITY_URL = f"{BING_ORIGIN}/rewardsapp/reportActivity"

HEADERS_JSON = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": f"{REWARDS_ORIGIN}/",
    "Origin": REWARDS_ORIGIN,
}

# Headers a browser owns; never send them from urllib3.
BROWSER_OWNED_HEADERS = frozenset(
    {
        "accept-charset",
        "accept-encoding",
        "access-control-request-headers",
        "access-control-request-method",
        "connection",
        "content-length",
        "cookie",
        "date",
        "dnt",
        "expect",
        "host",
        "keep-alive",
        "origin",
        "permissions-policy",
        "referer",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
        "user-agent",
        "via",
    }
)


class RewardsHttpError(RuntimeError):
    """Raised when a Rewards endpoint returns an error status."""


def _sanitize_headers(headers: dict[str, str]) -> dict[str, str]:
    """Drop browser-owned headers urllib3 must not set."""
    return {k: v for k, v in headers.items() if k.lower() not in BROWSER_OWNED_HEADERS}


def load_cookies(path: str | Path) -> dict[str, str]:
    """Load cookies from a JSON file written by :func:`save_cookies`.

    Cookie files are session-equivalent credentials.  On POSIX we refuse to
    read files that are group- or world-readable; on Windows we proceed and
    let the OS ACLs enforce access.
    """
    p = Path(path)
    if os.name == "posix":
        mode = stat.S_IMODE(p.stat().st_mode)
        if mode & 0o077:
            raise ValueError(
                f"cookie file {p} is readable by others ({oct(mode)}); "
                "chmod 600 it or use a more private location"
            )
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        return {str(k): str(v) for k, v in data.items()}
    # List of {name, value} dicts (Netscape-ish / Playwright shape).
    if not isinstance(data, list):
        raise TypeError(
            f"cookie file {p} must contain a JSON object or list of objects"
        )
    cookies: dict[str, str] = {}
    for item in data:
        if not isinstance(item, dict):
            raise TypeError(f"cookie file {p} contains a non-object entry")
        try:
            cookies[str(item["name"])] = str(item["value"])
        except KeyError as e:
            raise ValueError(f"cookie file {p} entry missing required key: {e}") from e
    return cookies


def save_cookies(cookies: Mapping[str, str], path: str | Path) -> None:
    """Persist cookies to a JSON file.

    The file is session-equivalent credential material: treat it like a
    password (chmod 600, never commit to git).
    """
    p = Path(path)
    data = dict(cookies)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    try:
        p.chmod(0o600)
    except OSError:
        log.debug("Could not set restrictive permissions on %s", p)


class RewardsHttp:
    """Thin wrapper around urllib3 for the Rewards endpoints."""

    def __init__(
        self,
        cookies: dict[str, str] | None = None,
        user_agent: str = "",
        timeout_s: float = 15.0,
    ) -> None:
        self._http = urllib3.PoolManager(
            timeout=urllib3.Timeout(connect=5.0, read=timeout_s),
            retries=Retry(
                total=3,
                backoff_factor=0.5,
                status_forcelist=[429, 500, 502, 503, 504],
                redirect=5,
            ),
            headers={"User-Agent": user_agent} if user_agent else None,
        )
        self.cookies = dict(cookies or {})

    @property
    def cookie_header(self) -> str:
        return (
            "; ".join(f"{k}={v}" for k, v in self.cookies.items())
            if self.cookies
            else ""
        )

    def _request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        body: bytes | str | None = None,
        query_params: dict[str, str] | None = None,
    ) -> urllib3.HTTPResponse:
        merged = dict(HEADERS_JSON)
        if self.cookie_header:
            merged["Cookie"] = self.cookie_header
        if headers:
            merged.update(_sanitize_headers(headers))
        merged = _sanitize_headers(merged)

        encoded_body: bytes | None = None
        if body is not None:
            encoded_body = body if isinstance(body, bytes) else body.encode("utf-8")
            merged.setdefault("Content-Type", "application/x-www-form-urlencoded")

        if query_params:
            url = (
                f"{url}&{urlencode(query_params)}"
                if "?" in url
                else f"{url}?{urlencode(query_params)}"
            )

        log.debug("%s %s", method, url)
        return self._http.request(method, url, headers=merged, body=encoded_body)

    def get(
        self, url: str, headers: dict[str, str] | None = None
    ) -> urllib3.HTTPResponse:
        return self._request("GET", url, headers=headers)

    def post(
        self,
        url: str,
        data: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> urllib3.HTTPResponse:
        body = None
        if data:
            body = "&".join(f"{k}={v}" for k, v in data.items())
        return self._request("POST", url, headers=headers, body=body)

    def json_get(self, url: str, headers: dict[str, str] | None = None) -> object:
        """GET and parse JSON, raising :class:`RewardsHttpError` on non-2xx."""
        resp = self.get(url, headers=headers)
        if not 200 <= resp.status < 300:  # noqa: PLR2004 - HTTP 2xx range check
            raise RewardsHttpError(f"{url} returned HTTP {resp.status}")
        try:
            return json.loads(resp.data.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            raise RewardsHttpError(f"{url} returned invalid JSON: {e}") from e
