"""Tests for edgelab.time.broker_time.BrokerTime (Phase 1, Module 1)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from edgelab.time.broker_time import BrokerTime


def _dt(y, mo, d, h=0, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)


class TestConstruction:
    def test_construct_with_offset(self):
        bt = BrokerTime(offset="+3")
        assert bt.offset_minutes == 180

    def test_construct_negative_offset(self):
        bt = BrokerTime(offset="-5")
        assert bt.offset_minutes == -300

    def test_construct_zero_offset(self):
        bt = BrokerTime(offset="+0")
        assert bt.offset_minutes == 0

    def test_construct_invalid_raises(self):
        with pytest.raises(ValueError):
            BrokerTime(offset="banana")


class TestNow:
    @patch("edgelab.time.broker_time.datetime")
    def test_now_returns_broker_time(self, mock_dt):
        fixed = _dt(2026, 7, 15, 12, 0)
        mock_dt.now.return_value = fixed
        bt = BrokerTime(offset="+3", dst=False)  # isolate raw offset (no DST shift)
        now = bt.now()
        assert now.hour == 15
        assert now.tzinfo is not None

    @patch("edgelab.time.broker_time.datetime")
    def test_utc_now(self, mock_dt):
        fixed = _dt(2026, 7, 15, 12, 0)
        mock_dt.now.return_value = fixed
        bt = BrokerTime(offset="+3")
        assert bt.utc_now() == fixed

    def test_to_broker_time(self):
        bt = BrokerTime(offset="+3", dst=False)
        out = bt.to_broker_time(_dt(2026, 7, 15, 12, 0))
        assert out.hour == 15

    def test_to_utc(self):
        bt = BrokerTime(offset="+3", dst=False)
        # a broker-time datetime (naive, representing +3)
        broker_dt = datetime(2026, 7, 15, 15, 0)
        out = bt.to_utc(broker_dt)
        assert out.hour == 12
        assert out.tzinfo is not None


class TestSessions:
    def test_session_names(self):
        bt = BrokerTime(offset="+3")
        assert bt.session_name(2) == "asian"
        assert bt.session_name(7) == "london"
        assert bt.session_name(10) == "london"
        assert bt.session_name(13) == "overlap"
        assert bt.session_name(15) == "overlap"

    def test_overlap_session(self):
        bt = BrokerTime(offset="+3")
        # London at +3 = 7-12 broker; NY/London overlap = 12-16 broker.
        assert bt.session_name(14) == "overlap"

    def test_session_name_out_of_range(self):
        bt = BrokerTime(offset="+3")
        assert bt.session_name(22) == "closed"


class TestDST:
    def test_dst_active_during_us_dst(self):
        # July is inside US DST window -> +1 hour shift
        bt = BrokerTime(offset="+3", dst=True)
        out = bt.to_broker_time(_dt(2026, 7, 15, 12, 0))
        # 12 UTC +3 +1(DST) = 16
        assert out.hour == 16

    def test_dst_inactive_during_us_winter(self):
        bt = BrokerTime(offset="+3", dst=True)
        out = bt.to_broker_time(_dt(2026, 1, 15, 12, 0))
        # January -> no DST -> +3 only
        assert out.hour == 15

    def test_dst_false_no_shift(self):
        bt = BrokerTime(offset="+3", dst=False)
        out = bt.to_broker_time(_dt(2026, 7, 15, 12, 0))
        assert out.hour == 15


class TestWeekend:
    def test_saturday_is_weekend(self):
        bt = BrokerTime(offset="+3")
        assert bt.is_weekend(_dt(2026, 7, 18)) is True  # Saturday

    def test_monday_not_weekend(self):
        bt = BrokerTime(offset="+3")
        assert bt.is_weekend(_dt(2026, 7, 20)) is False  # Monday

    def test_sunday_is_weekend(self):
        bt = BrokerTime(offset="+3")
        assert bt.is_weekend(_dt(2026, 7, 19)) is True


class TestArithmetic:
    def test_minutes_since(self):
        bt = BrokerTime(offset="+0")
        past = _dt(2026, 7, 15, 10, 0)
        now = _dt(2026, 7, 15, 11, 0)
        with patch.object(bt, "now", return_value=now):
            assert bt.minutes_since(past) == 60

    def test_minutes_until(self):
        bt = BrokerTime(offset="+0")
        future = _dt(2026, 7, 15, 11, 30)
        now = _dt(2026, 7, 15, 11, 0)
        with patch.object(bt, "now", return_value=now):
            assert bt.minutes_until(future) == 30


class TestOffsetValidation:
    """Phase 1.5 hotfix: BrokerTime must fail LOUDLY on impossible offsets."""

    def test_offset_plus_3_accepted(self):
        bt = BrokerTime(offset="+3")
        assert bt.offset_minutes == 180

    def test_offset_plus_0_accepted(self):
        bt = BrokerTime(offset="+0")
        assert bt.offset_minutes == 0

    def test_offset_minus_5_accepted(self):
        bt = BrokerTime(offset="-5")
        assert bt.offset_minutes == -300

    def test_offset_plus_14_accepted_at_max(self):
        bt = BrokerTime(offset="+14")
        assert bt.offset_minutes == 14 * 60

    def test_offset_plus_12_accepted_with_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger="edgelab.time.broker_time"):
            bt = BrokerTime(offset="+12")
        assert bt.offset_minutes == 12 * 60
        # a warning was logged about the unusual offset
        assert any("+12" in r.message for r in caplog.records)
        assert any("unusual" in r.message.lower() for r in caplog.records)

    def test_offset_plus_15_rejected(self):
        with pytest.raises(ValueError):
            BrokerTime(offset="+15")

    def test_offset_plus_25_rejected_garbage(self):
        with pytest.raises(ValueError):
            BrokerTime(offset="+25")

    def test_offset_minus_13_rejected(self):
        with pytest.raises(ValueError):
            BrokerTime(offset="-13")

    def test_offset_minus_10_accepted(self):
        bt = BrokerTime(offset="-10")
        assert bt.offset_minutes == -10 * 60

    def test_offset_plus_14_with_dst(self):
        bt = BrokerTime(offset="+14", dst=True)
        assert bt.offset_minutes == 14 * 60

    def test_invalid_format_raises(self):
        for bad in ("+abc", "three", "x7"):
            with pytest.raises(ValueError):
                BrokerTime(offset=bad)

    def test_error_message_contains_offset_value(self):
        with pytest.raises(ValueError) as exc:
            BrokerTime(offset="+25")
        assert "25" in str(exc.value)

    def test_warning_message_contains_offset_value(self, caplog):
        with caplog.at_level(logging.WARNING, logger="edgelab.time.broker_time"):
            BrokerTime(offset="+13")
        assert any("+13" in r.message for r in caplog.records)
