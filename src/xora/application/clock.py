from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def now_ist() -> datetime:
    return datetime.now(IST)


def floor_slot(moment: datetime | None = None) -> datetime:
    moment = (moment or now_ist()).astimezone(IST)
    snapped = moment.replace(second=0, microsecond=0)
    return snapped.replace(minute=(snapped.minute // 15) * 15)


def next_full_slot(moment: datetime | None = None) -> tuple[datetime, datetime]:
    """If user is mid-slot (4:25), wait for 4:30-4:45. If exactly on a mark, take that slot."""
    moment = (moment or now_ist()).astimezone(IST)
    start = floor_slot(moment)
    if moment - start > timedelta(seconds=2):
        start = start + timedelta(minutes=15)
    return start, start + timedelta(minutes=15)


def slot_label(start: datetime, end: datetime) -> str:
    return f"{start.strftime('%H:%M')}–{end.strftime('%H:%M')} IST"
