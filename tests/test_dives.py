from datetime import date, datetime
from zoneinfo import ZoneInfo

from krillionbot.dives import NY, current_dive, dive_date, dive_number, next_reset, week_dives, week_start

SG = ZoneInfo("Asia/Singapore")


def test_dive_118_is_10_nov_2026():
    assert dive_date(118) == date(2026, 11, 10)
    assert dive_number(date(2026, 11, 10)) == 118
    assert dive_date(1) == date(2026, 7, 16)


def test_current_dive_follows_new_york_midnight():
    # 12:30 SGT on 10 Nov = 23:30 NY on 9 Nov -> dive 117 still open
    assert current_dive(datetime(2026, 11, 10, 12, 30, tzinfo=SG)) == 117
    # 13:30 SGT on 10 Nov = 00:30 NY on 10 Nov -> dive 118
    assert current_dive(datetime(2026, 11, 10, 13, 30, tzinfo=SG)) == 118


def test_week_runs_monday_to_sunday():
    assert week_start(date(2026, 11, 10)) == date(2026, 11, 9)  # Tue -> Mon
    assert week_start(date(2026, 11, 15)) == date(2026, 11, 9)  # Sun -> same Mon
    assert week_dives(date(2026, 11, 9)) == [117, 118, 119, 120, 121, 122, 123]


def test_next_reset():
    now = datetime(2026, 11, 10, 13, 30, tzinfo=SG)
    r = next_reset(now)
    assert r == datetime(2026, 11, 11, 0, 0, tzinfo=NY)
