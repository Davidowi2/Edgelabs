"""Static news-calendar config for EdgeLab (Phase 2, Module 1).

The static JSON calendar is the PRIMARY news data source: it is always
available, never requires a network, and never fails. This module loads,
validates, and filters ``NewsEvent`` records. Only the standard library is used.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List

from edgelab.monitoring.logger import TradingLogger

VALID_IMPACTS = ("low", "medium", "high")
UTC = "UTC"

_logger = None


def _log() -> TradingLogger:
    global _logger
    if _logger is None:
        _logger = TradingLogger(name="news.static_config", log_file="logs/news_static.log")
    return _logger


@dataclass
class NewsEvent:
    id: str
    name: str
    currency: str
    datetime_utc: datetime
    impact: str
    source: str


def _parse_dt(value) -> datetime:
    if isinstance(value, datetime):
        return value
    s = str(value).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def load_events_from_json(file_path: str) -> List[NewsEvent]:
    """Load and build NewsEvent objects. Returns [] on any failure (fail open)."""
    path = Path(file_path)
    if not path.exists():
        _log().error("news calendar file missing", path=str(path))
        return []
    try:
        import json

        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - malformed JSON must not crash
        _log().error("news calendar file malformed", path=str(path), error=repr(exc))
        return []
    events: List[NewsEvent] = []
    for item in raw:
        try:
            events.append(
                NewsEvent(
                    id=item["id"],
                    name=item["name"],
                    currency=item["currency"],
                    datetime_utc=_parse_dt(item["datetime_utc"]),
                    impact=item["impact"],
                    source=item.get("source", ""),
                )
            )
        except Exception as exc:  # noqa: BLE001 - skip bad records, keep the rest
            _log().warning("skipping invalid news record", record=item, error=repr(exc))
    return events


def validate_events(events: List[NewsEvent]) -> List[str]:
    """Return a list of human-readable validation errors (empty == valid)."""
    errors: List[str] = []
    seen_ids = set()
    for e in events:
        # unique id
        if e.id in seen_ids:
            errors.append(f"duplicate event id: {e.id}")
        seen_ids.add(e.id)
        # tz-aware datetime
        if not isinstance(e.datetime_utc, datetime) or e.datetime_utc.tzinfo is None:
            errors.append(f"naive or missing timezone on event {e.id}")
        # 3-letter currency
        if not (isinstance(e.currency, str) and len(e.currency) == 3 and e.currency.isalpha()):
            errors.append(f"invalid currency code on event {e.id}: {e.currency!r}")
        # valid impact
        if e.impact not in VALID_IMPACTS:
            errors.append(f"invalid impact on event {e.id}: {e.impact!r}")
    return errors


def filter_events_by_currency(events: List[NewsEvent], currencies: List[str]) -> List[NewsEvent]:
    wanted = set(currencies)
    return [e for e in events if e.currency in wanted]
