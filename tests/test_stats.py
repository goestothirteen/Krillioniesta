from datetime import UTC, datetime

from krillionbot.db import Result
from krillionbot.stats import all_time, daily_board, personal_best_before, rank, streaks, weekly_board

T = datetime(2026, 11, 10, tzinfo=UTC)


def R(uid, dive, score, tiers="🦑🦑🦑🦑🦑🦑🦑"):
    return Result(uid, dive, score, tiers, T)


def test_rank_shares_ties():
    r = rank([(1, 400), (2, 400), (3, 300)])
    assert [(x.user_id, x.rank) for x in r] == [(1, 1), (2, 1), (3, 3)]


def test_daily_board_keeps_post_order_within_tie():
    # store returns score desc, posted asc — the earlier poster stays first
    ranked = daily_board([R(2, 118, 415), R(1, 118, 415), R(3, 118, 100)])
    assert [x.user_id for x in ranked] == [2, 1, 3]


def test_weekly_missed_days_count_zero_and_only_participants_ranked():
    dives = [117, 118, 119, 120, 121, 122, 123]
    results = [R(1, 117, 300), R(1, 118, 400), R(2, 118, 500), R(3, 90, 700)]
    rows = weekly_board(results, dives)
    assert [(w.user_id, w.total, w.played) for w in rows] == [(1, 700, 2), (2, 500, 1)]
    assert rows[0].average == 350


def test_streaks():
    assert streaks([115, 116, 117, 118], current_dive=118) == (4, 4)
    assert streaks([110, 111, 115, 116, 117], current_dive=118) == (3, 3)  # yesterday still counts
    assert streaks([110, 111, 112], current_dive=118) == (0, 3)
    assert streaks([], 118) == (0, 0)


def test_all_time_sorted_by_average_with_wins_and_gems():
    results = [
        R(1, 117, 300), R(1, 118, 500, "🌟🌟🌟🌟🌟🤡🫧"),
        R(2, 117, 350), R(2, 118, 350),
    ]
    rows = all_time(results, current_dive=118)
    assert [a.user_id for a in rows] == [1, 2]
    a1 = rows[0]
    assert (a1.total, a1.dives, a1.best, a1.best_dive, a1.worst) == (800, 2, 500, 118, 300)
    assert (a1.gems, a1.clowns, a1.wins) == (5, 1, 1)
    assert rows[1].wins == 1  # won dive 117


def test_personal_best_before():
    hist = [R(1, 110, 200), R(1, 111, 350), R(1, 118, 400)]
    assert personal_best_before(hist, 118) == 350
    assert personal_best_before([R(1, 118, 400)], 118) is None
