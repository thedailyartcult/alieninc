"""Structured logging setup — stdlib only, no new dependencies.

Plain human-readable lines by default (the format the server has always used);
one-line JSON per record when ``CMB_LOG_FORMAT=json`` (``CMB_LOG_JSON=1``
is kept as an alias) so a log shipper (Loki/CloudWatch/jq) can parse without
regexes. Level via ``CMB_LOG_LEVEL`` (default INFO). Any ``extra={...}``
fields a caller attaches (e.g. the request-id middleware's
``request_id``/``duration_ms``) are included in the JSON output.

When ``CMB_LOG_FILE`` is set, a ``RotatingFileHandler`` is added alongside
the stream handler. Rotation is governed by ``CMB_LOG_MAX_BYTES`` (default
10 MiB) and ``CMB_LOG_BACKUP_COUNT`` (default 5).
"""
from __future__ import annotations

import json
import logging
import os
import time
from logging.handlers import RotatingFileHandler

from cmb.observability import redact, redact_json_value

_PLAIN_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"

# Attributes present on every LogRecord — everything else came in via ``extra=``.
_RESERVED = frozenset(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__
) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    """One JSON object per line: ts, level, logger, message, plus any extras."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
                  + ".%03dZ" % (record.msecs,),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = redact_json_value({key: value})[key]
        if record.exc_info:
            payload["exc_info"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(
    level_env: str = "CMB_LOG_LEVEL",
    format_env: str = "CMB_LOG_FORMAT",
    json_env: str = "CMB_LOG_JSON",
    file_env: str = "CMB_LOG_FILE",
    max_bytes_env: str = "CMB_LOG_MAX_BYTES",
    backup_count_env: str = "CMB_LOG_BACKUP_COUNT",
) -> None:
    """Configure root logging from env. Idempotent — safe to call more than once
    (replaces the root handler instead of stacking duplicates).

    When ``CMB_LOG_FILE`` is set, a ``RotatingFileHandler`` is added so
    logs persist across restarts and are rotated by size.
    """
    level_name = os.environ.get(level_env, "INFO").strip().upper()
    level = getattr(logging, level_name, None)
    if not isinstance(level, int):
        level = logging.INFO
    fmt = os.environ.get(format_env, "").strip().lower()
    if fmt in ("json", "text"):
        use_json = fmt == "json"
    else:
        use_json = os.environ.get(json_env, "").strip().lower() in ("1", "true", "yes", "on")

    handlers = []
    handler = logging.StreamHandler()
    if use_json:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(_PLAIN_FORMAT))
    handlers.append(handler)

    log_file = os.environ.get(file_env, "").strip()
    if log_file:
        max_bytes = int(os.environ.get(max_bytes_env, str(10 * 1024 * 1024)))
        backup_count = int(os.environ.get(backup_count_env, "5"))
        file_handler = RotatingFileHandler(
            log_file, maxBytes=max_bytes, backupCount=backup_count
        )
        if use_json:
            file_handler.setFormatter(JsonFormatter())
        else:
            file_handler.setFormatter(logging.Formatter(_PLAIN_FORMAT))
        handlers.append(file_handler)

    root = logging.getLogger()
    root.handlers[:] = handlers
    root.setLevel(level)