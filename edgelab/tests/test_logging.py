"""Minimal import test for the logging utility (closes coverage gap)."""

from __future__ import annotations

from edgelab.utils.logging import logger


class TestLoggingImport:
    def test_logger_is_exported(self):
        assert logger is not None
