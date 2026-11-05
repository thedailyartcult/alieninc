"""
Per-feed daily quota tracker.

Tracks request counts per feed name with a rolling daily window.
Resets at midnight UTC. In-memory only (no persistence across restarts).
Intended to be called before each external API pull to enforce quotas.
"""

import threading
import time
from datetime import datetime, timezone
from typing import Dict, Optional


class FeedBudget:
    def __init__(self):
        self._lock = threading.Lock()
        self._feeds: Dict[str, dict] = {}

    def _today(self) -> str:
        return datetime.now(timezone.utc).strftime('%Y-%m-%d')

    def _ensure(self, feed: str) -> dict:
        today = self._today()
        if feed not in self._feeds or self._feeds[feed]['date'] != today:
            self._feeds[feed] = {'date': today, 'count': 0}
        return self._feeds[feed]

    def check_and_consume(self, feed: str, max_per_day: int = 10) -> dict:
        """Check quota and consume one slot if available.
        Returns {ok, used, max, remaining, resets_at}."""
        with self._lock:
            entry = self._ensure(feed)
            if entry['count'] >= max_per_day:
                return {
                    'ok': False,
                    'used': entry['count'],
                    'max': max_per_day,
                    'remaining': 0,
                    'resets_at': self._next_midnight(),
                }
            entry['count'] += 1
            return {
                'ok': True,
                'used': entry['count'],
                'max': max_per_day,
                'remaining': max_per_day - entry['count'],
                'resets_at': self._next_midnight(),
            }

    def status(self, feed: str, max_per_day: int = 10) -> dict:
        """Read-only check: {used, max, remaining}."""
        with self._lock:
            entry = self._ensure(feed)
            return {
                'used': entry['count'],
                'max': max_per_day,
                'remaining': max(0, max_per_day - entry['count']),
            }

    def _next_midnight(self) -> str:
        now = datetime.now(timezone.utc)
        from datetime import timedelta
        next_day = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return next_day.isoformat()


# Singleton instance
feed_budget = FeedBudget()
