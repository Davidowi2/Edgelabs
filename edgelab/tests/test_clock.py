"""Tests for the NY session clock."""

from __future__ import annotations

from datetime import datetime

import pytest

from edgelab.state.clock import Clock


class TestSessionDetection:
    def test_inside_first_window(self):
        clock = Clock()
        assert clock.in_session(datetime(2026, 7, 20, 10, 0)) is True

    def test_inside_second_window(self):
        clock = Clock()
        assert clock.in_session(datetime(2026, 7, 20, 14, 30)) is True

    def test_outside_both_windows(self):
        clock = Clock()
        assert clock.in_session(datetime(2026, 7, 20, 3, 0)) is False

    def test_at_window_start_boundary(self):
        clock = Clock()
        assert clock.in_session(datetime(2026, 7, 20, 8, 0)) is True

    def test_at_window_end_boundary(self):
        clock = Clock()
        assert clock.in_session(datetime(2026, 7, 20, 11, 0)) is True

    def test_just_before_window(self):
        clock = Clock()
        assert clock.in_session(datetime(2026, 7, 20, 7, 59)) is False

    def test_custom_windows(self):
        clock = Clock(session_windows=[[0, 0, 1, 0]])
        assert clock.in_session(datetime(2026, 7, 20, 0, 30)) is True
        assert clock.in_session(datetime(2026, 7, 20, 12, 0)) is False


class TestTimeConversion:
    def test_to_ny_returns_ny_aware(self):
        clock = Clock()
        dt = datetime(2026, 7, 20, 10, 0)
        converted = clock.to_ny(dt)
        assert converted.tzinfo is not None
