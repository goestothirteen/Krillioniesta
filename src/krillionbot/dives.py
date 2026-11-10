"""The Krillion calendar.

Dive #1 was 16 July 2026 and a new dive opens at midnight New York time, so the
dive number in a share paste maps to one calendar date (in New York) no matter
when or where it was pasted. Weeks run Monday–Sunday over dive dates.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
SG = ZoneInfo("Asia/Singapore")
DIVE_ONE = date(2026, 7, 16)


def dive_date(dive: int) -> date:
    return DIVE_ONE + timedelta(days=dive - 1)


def dive_number(d: date) -> int:
    return (d - DIVE_ONE).days + 1


def current_dive(now: datetime | None = None) -> int:
    """The dive that is open right now (New York 'today')."""
    now = now or datetime.now(tz=NY)
    return dive_number(now.astimezone(NY).date())


def week_start(d: date) -> date:
    """Monday of the week containing ``d``."""
    return d - timedelta(days=d.weekday())


def week_dives(monday: date) -> list[int]:
    """The seven dive numbers in the week starting on ``monday``."""
    return [dive_number(monday + timedelta(days=i)) for i in range(7)]


def week_of_dive(dive: int) -> date:
    return week_start(dive_date(dive))


def next_reset(now: datetime | None = None) -> datetime:
    """When the next dive opens, as an aware datetime in New York."""
    now = (now or datetime.now(tz=NY)).astimezone(NY)
    tomorrow = now.date() + timedelta(days=1)
    return datetime(tomorrow.year, tomorrow.month, tomorrow.day, tzinfo=NY)


def fmt_date(d: date) -> str:
    return d.strftime("%a %d %b")
