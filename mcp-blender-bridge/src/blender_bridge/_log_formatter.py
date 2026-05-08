"""Structured JSON log formatter for pipeline / log-aggregator integration."""

from __future__ import annotations

import json as _json
import logging


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per log record.

    Activate with: BLENDER_BRIDGE_LOG_FORMAT=json
    """

    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        obj: dict = {
            "ts": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            obj["exc"] = self.formatException(record.exc_info)
        if record.stack_info:
            obj["stack"] = self.formatStack(record.stack_info)
        return _json.dumps(obj)
