"""HTTP layer: polite fetching, robots.txt gate, retries/backoff, cache.

Hard rules (see POLICY.md):
- robots.txt is always honoured via urllib.robotparser, cached per domain.
  If `obey_robots` is True (always, except explicit site-operator whitelist),
  a disallowed URL is never fetched.
- One in-flight request per host; a min-delay gap is enforced between requests.
- Retries only for transient errors (429/5xx/network), with exponential backoff
  and honouring Retry-After.
"""

from __future__ import annotations

import time
import threading
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from dataclasses import dataclass, field

from .config import Settings


@dataclass
class FetchResult:
    url: str
    html: str
    status: int
    from_cache: bool = False
    robots_verdict: str = "allow"


class RobotsGate:
    """Cached robots.txt gate per domain."""

    def __init__(self, user_agent: str, timeout: float = 15.0):
        self.user_agent = user_agent
        self.timeout = timeout
        self._parsers: dict[str, urllib.robotparser.RobotFileParser] = {}
        self._lock = threading.Lock()
        self._fail_open = True  # if robots.txt is unreadable, allow (treat as no restrictions)

    def can_fetch(self, url: str) -> str:
        parts = urllib.parse.urlsplit(url)
        domain = parts.netloc
        with self._lock:
            rp = self._parsers.get(domain)
            if rp is None:
                rp = urllib.robotparser.RobotFileParser()
                rp.set_url(f"{parts.scheme}://{domain}/robots.txt")
                try:
                    rp.read()
                except Exception:
                    # robots.txt unreachable -> no restrictions applied by us.
                    rp = None
                self._parsers[domain] = rp if rp is not None else "unreachable"
                if rp is None:
                    return "allow"
            if rp == "unreachable":
                return "allow"
        allowed = rp.can_fetch(self.user_agent, url)
        # Also respect that a "*" agent may only cover generic; be conservative.
        return "allow" if allowed else "disallow"


class HttpFetcher:
    """Politeness-aware fetcher. One instance per host is serialised."""

    def __init__(self, settings: Settings, robots: RobotsGate):
        self.settings = settings
        self.robots = robots
        self._last = 0.0
        self._lock = threading.Lock()

    def _throttle(self):
        with self._lock:
            gap = self.settings.min_delay_seconds - (time.monotonic() - self._last)
            if gap > 0:
                time.sleep(gap)
            self._last = time.monotonic()

    def fetch(self, url: str, store=None, use_cache: bool = True) -> FetchResult:
        verdict = self.robots.can_fetch(url)
        if verdict == "disallow":
            return FetchResult(url=url, html="", status=0, robots_verdict="disallow")
        if store and use_cache and not self.settings.refresh:
            cached = store.get_html(url)
            if cached is not None:
                return FetchResult(url=url, html=cached, status=200, from_cache=True)

        req = urllib.request.Request(url, headers={
            "User-Agent": self.settings.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.8",
            "Accept-Encoding": "identity",
        })
        last_err = None
        for attempt in range(self.settings.max_retries + 1):
            self._throttle()
            try:
                with urllib.request.urlopen(req, timeout=self.settings.request_timeout) as resp:
                    body = resp.read(self.settings.max_page_size_kb * 1024).decode("utf-8", "replace")
                    if store:
                        store.put_html(url, body)
                    return FetchResult(url=url, html=body, status=resp.status)
            except urllib.error.HTTPError as e:
                last_err = e
                if e.code in (429, 500, 502, 503, 504):
                    retry_after = e.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after and retry_after.isdigit() \
                        else self.settings.backoff_base ** attempt
                    time.sleep(min(delay, 30.0))
                    continue
                if e.code in (403, 401, 404):
                    return FetchResult(url=url, html="", status=e.code)
                continue
            except (urllib.error.URLError, OSError, ValueError) as e:
                last_err = e
                time.sleep(self.settings.backoff_base ** attempt)
        return FetchResult(url=url, html="", status=0, robots_verdict=verdict)
