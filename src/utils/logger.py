"""Structured JSON logger for TripOrchestrator.
Produces CloudWatch-compatible log events with correlation IDs.
"""
from __future__ import annotations

import json
import logging
import sys
import uuid
from datetime import datetime
from typing import Any, Dict, Optional


class StructuredFormatter(logging.Formatter):
    """JSON structured log formatter."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Include exception info
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Include extra fields
        for key, value in record.__dict__.items():
            if key not in (
                "name", "msg", "args", "levelname", "levelno", "pathname",
                "filename", "module", "exc_info", "exc_text", "stack_info",
                "lineno", "funcName", "created", "msecs", "relativeCreated",
                "thread", "threadName", "processName", "process", "message",
                "taskName",
            ):
                log_entry[key] = value

        return json.dumps(log_entry, default=str)


def get_logger(
    name: str,
    level: str = "INFO",
    correlation_id: Optional[str] = None,
) -> logging.Logger:
    """Get a structured logger instance."""
    logger = logging.getLogger(name)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredFormatter())
        logger.addHandler(handler)
        logger.propagate = False

    try:
        from src.utils.config import settings
        logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
    except Exception:
        logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    return logger


class RequestContext:
    """Context manager for request-scoped correlation IDs."""

    _correlation_id: Optional[str] = None

    @classmethod
    def set(cls, correlation_id: Optional[str] = None) -> str:
        cls._correlation_id = correlation_id or str(uuid.uuid4())
        return cls._correlation_id

    @classmethod
    def get(cls) -> Optional[str]:
        return cls._correlation_id

    @classmethod
    def clear(cls) -> None:
        cls._correlation_id = None


def get_request_logger(name: str) -> logging.LoggerAdapter:
    """Logger adapter that automatically injects correlation ID."""
    logger = get_logger(name)

    class CorrelationAdapter(logging.LoggerAdapter):
        def process(self, msg, kwargs):
            extra = kwargs.get("extra", {})
            extra["correlation_id"] = RequestContext.get() or "no-correlation-id"
            kwargs["extra"] = extra
            return msg, kwargs

    return CorrelationAdapter(logger, {})


def setup_logger(name: str) -> logging.Logger:
    """Set up and return a logger with structured JSON formatting."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


def get_logger(name: str) -> logging.Logger:
    """Alias for setup_logger for backwards compatibility."""
    return setup_logger(name)

