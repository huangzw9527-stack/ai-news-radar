from datetime import datetime, timedelta, timezone
from typing import Optional


def parse_datetime(value) -> Optional[datetime]:
    if not value:
        return None

    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return None
        text = text.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            for fmt in (
                "%Y-%m-%d",
                "%Y/%m/%d",
                "%Y-%m-%d %H:%M:%S",
                "%Y/%m/%d %H:%M:%S",
                "%Y-%m-%d %H:%M",
                "%Y/%m/%d %H:%M",
            ):
                try:
                    dt = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue
            else:
                return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def get_yesterday_date_str(now: Optional[datetime] = None) -> str:
    now_utc = parse_datetime(now) if now else datetime.now(timezone.utc)
    return (now_utc - timedelta(days=1)).date().isoformat()


def is_yesterday(value, now: Optional[datetime] = None) -> bool:
    dt = parse_datetime(value)
    if dt is None:
        return False
    return dt.date().isoformat() == get_yesterday_date_str(now)


def is_within_recent_days(value, days: int = 3, now: Optional[datetime] = None) -> bool:
    """判断时间是否在最近 N 天内（含今天）。

    空值或无法解析 → True（放行，避免因缺失日期丢失新闻；dedup 会兜底重复）。
    允许 2 天未来偏差以吸收时区抖动。
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return True
    dt = parse_datetime(value)
    if dt is None:
        return True
    now_utc = parse_datetime(now) if now else datetime.now(timezone.utc)
    delta_days = (now_utc - dt).total_seconds() / 86400
    return -2 <= delta_days <= days
