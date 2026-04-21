"""Tests for structured logging helpers."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_json_formatter_outputs_json_payload():
    from gateway.logging_utils import JsonFormatter

    record = logging.LogRecord(
        name="gateway.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    record.session_id = "abc123"

    data = json.loads(JsonFormatter().format(record))
    assert data["level"] == "INFO"
    assert data["logger"] == "gateway.test"
    assert data["message"] == "hello world"
    assert data["session_id"] == "abc123"
    assert "timestamp" in data


def test_configure_logging_json_mode_sets_json_formatter():
    from gateway.logging_utils import JsonFormatter, configure_logging

    configure_logging("INFO", json_logs=True)
    root = logging.getLogger()

    assert root.handlers
    assert isinstance(root.handlers[0].formatter, JsonFormatter)


def test_configure_logging_plain_mode_sets_default_formatter():
    from gateway.logging_utils import JsonFormatter, configure_logging

    configure_logging("INFO", json_logs=False)
    root = logging.getLogger()

    assert root.handlers
    assert not isinstance(root.handlers[0].formatter, JsonFormatter)


def test_json_formatter_serializes_exception_and_extra_fields():
    from gateway.logging_utils import JsonFormatter

    try:
        raise ValueError("boom")
    except ValueError:
        record = logging.LogRecord(
            name="gateway.test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=99,
            msg="failed",
            args=(),
            exc_info=sys.exc_info(),
        )
    record.db_name = "ERP"
    record.tool = "execute_query"
    record.request_id = "req-1"

    data = json.loads(JsonFormatter().format(record))
    assert data["db_name"] == "ERP"
    assert data["tool"] == "execute_query"
    assert data["request_id"] == "req-1"
    assert "exception" in data


def test_configure_logging_falls_back_to_info_for_unknown_level():
    from gateway.logging_utils import configure_logging

    configure_logging("not-a-real-level", json_logs=False)
    root = logging.getLogger()

    assert root.level == logging.INFO
