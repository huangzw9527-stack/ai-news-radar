import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.date_filters import (
    get_yesterday_date_str,
    is_within_recent_days,
    is_yesterday,
    parse_datetime,
)


def test_parse_datetime_supports_iso_and_date_only():
    assert parse_datetime("2026-03-19T08:00:00Z").isoformat() == "2026-03-19T08:00:00+00:00"
    assert parse_datetime("2026-03-19").isoformat() == "2026-03-19T00:00:00+00:00"


def test_is_yesterday_uses_natural_day():
    now = datetime(2026, 3, 20, 12, 0, 0, tzinfo=timezone.utc)
    assert is_yesterday("2026-03-19T23:59:59+00:00", now=now) is True
    assert is_yesterday("2026-03-20T00:00:00+00:00", now=now) is False
    assert is_yesterday("2026-03-18T23:59:59+00:00", now=now) is False


def test_get_yesterday_date_str():
    now = datetime(2026, 3, 20, 12, 0, 0, tzinfo=timezone.utc)
    assert get_yesterday_date_str(now=now) == "2026-03-19"


def test_is_within_recent_days_accepts_recent():
    now = datetime(2026, 3, 20, 12, 0, 0, tzinfo=timezone.utc)
    assert is_within_recent_days("2026-03-20T10:00:00+00:00", days=3, now=now) is True
    assert is_within_recent_days("2026-03-18T00:00:00+00:00", days=3, now=now) is True
    assert is_within_recent_days("2026-03-17T12:00:00+00:00", days=3, now=now) is True


def test_is_within_recent_days_rejects_old():
    now = datetime(2026, 3, 20, 12, 0, 0, tzinfo=timezone.utc)
    # 10 天前
    assert is_within_recent_days("2026-03-10T12:00:00+00:00", days=3, now=now) is False


def test_is_within_recent_days_allows_small_future_drift():
    now = datetime(2026, 3, 20, 12, 0, 0, tzinfo=timezone.utc)
    # 时区抖动：发布时间被误读成未来 12 小时 → 仍放行
    assert is_within_recent_days("2026-03-21T00:00:00+00:00", days=3, now=now) is True


def test_is_within_recent_days_rejects_far_future():
    now = datetime(2026, 3, 20, 12, 0, 0, tzinfo=timezone.utc)
    # 未来 5 天 → 必然是解析错误，拒绝
    assert is_within_recent_days("2026-03-25T12:00:00+00:00", days=3, now=now) is False


def test_is_within_recent_days_passes_missing_or_unparseable():
    now = datetime(2026, 3, 20, 12, 0, 0, tzinfo=timezone.utc)
    # 无日期字段 → 放行（避免误丢采集到的有效内容）
    assert is_within_recent_days("", days=3, now=now) is True
    assert is_within_recent_days(None, days=3, now=now) is True
    assert is_within_recent_days("昨天", days=3, now=now) is True
    assert is_within_recent_days("not-a-date", days=3, now=now) is True
