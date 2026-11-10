from datetime import date

import pytest

from krillionbot import views
from krillionbot.db import Player, Store
from krillionbot.parser import parse_share
from krillionbot.stats import all_time, daily_board, weekly_board


@pytest.fixture
async def store():
    s = Store(":memory:")
    await s.open()
    yield s
    await s.close()


async def test_round_trip_and_duplicate(store: Store):
    await store.ensure_chat(-1, "Seering")
    await store.upsert_player(-1, Player(1, "Mark", "mark"))
    assert await store.add_result(-1, 1, 118, 415, "🦑🦑🦑🏮🦑🦑🐟")
    assert not await store.add_result(-1, 1, 118, 700, "🌟🌟🌟🌟🌟🌟🌟")  # first paste counts
    got = await store.get_result(-1, 1, 118)
    assert got and got.score == 415
    assert await store.chat_ids() == [-1]
    assert (await store.players(-1))[1].name == "Mark"


async def test_results_for_dives_and_week(store: Store):
    for uid, dive, score in [(1, 117, 300), (1, 118, 400), (2, 118, 500)]:
        await store.add_result(-1, uid, dive, score, "🦑🦑🦑🦑🦑🦑🦑")
    rs = await store.results_for_dives(-1, [117, 118, 119])
    assert len(rs) == 3
    rows = weekly_board(rs, [117, 118, 119, 120, 121, 122, 123])
    assert rows[0].user_id == 1 and rows[0].total == 700


async def test_forfeit_draw_marks_used_and_recycles(store: Store):
    await store.add_forfeit(-1, "Buy bubble tea", 1)
    first = await store.draw_forfeit(-1, "2026-11-09")
    assert first == "Buy bubble tea"
    assert (await store.forfeits(-1))[0][2] == "2026-11-09"
    second = await store.draw_forfeit(-1, "2026-11-16")  # only one in the jar → recycled
    assert second == "Buy bubble tea"
    assert await store.draw_forfeit(-2, "x") is None


async def test_undo_and_clear(store: Store):
    await store.ensure_chat(-1, "t")
    await store.add_result(-1, 1, 117, 300, "🦑🦑🦑🦑🦑🫧🫧")
    await store.add_result(-1, 1, 118, 415, "🦑🦑🦑🏮🦑🦑🐟")
    await store.add_result(-1, 2, 118, 355, "🦑🐟🐟🏮🦑🦑🐟")
    latest = await store.latest_result(-1, 1)
    assert latest and latest.dive == 118
    assert await store.delete_result(-1, 1, 118)
    assert not await store.delete_result(-1, 1, 118)
    assert await store.mark_posted(-1, "daily", "118")
    assert await store.clear_dive(-1, 118) == 1
    assert await store.mark_posted(-1, "daily", "118")  # marker was reset
    await store.add_forfeit(-1, "x", None)
    assert await store.clear_chat(-1) == 1
    assert await store.forfeits(-1) == []
    assert await store.all_results(-1) == []
    assert (await store.players(-1)) == {}  # no players were registered via upsert here


async def test_swap_board_message_returns_previous(store: Store):
    assert await store.swap_board_message(-1, 10) is None
    assert await store.swap_board_message(-1, 11) == 10
    assert await store.swap_board_message(-1, 11) is None  # same card again → nothing to delete
    assert await store.swap_board_message(-2, 5) is None  # per chat


async def test_mark_posted_is_idempotent(store: Store):
    assert await store.mark_posted(-1, "daily", "118")
    assert not await store.mark_posted(-1, "daily", "118")


async def test_views_render(store: Store):
    players = {1: Player(1, "Mark <3", None), 2: Player(2, "Zoey", None)}
    await store.add_result(-1, 1, 118, 415, "🦑🦑🦑🏮🦑🦑🐟")
    await store.add_result(-1, 2, 118, 355, "🦑🐟🐟🏮🦑🦑🐟")
    rs = await store.results_for_dive(-1, 118)
    ranked = daily_board(rs)

    today = views.today_board(118, rs, ranked, players, waiting=[], live=True)
    assert "🥇 Mark &lt;3 — <b>415</b>" in today and "Tue 10 Nov" in today

    wrap = views.daily_wrap(118, rs, ranked, players)
    assert "Diver of the day: Mark &lt;3" in wrap and "Plankton of the day: Zoey" in wrap

    week = views.weekly_board(date(2026, 11, 9), weekly_board(rs, [117, 118, 119, 120, 121, 122, 123]),
                              players, dives_done=2, final=True, forfeit="Sing a song")
    assert "Week winner: Mark &lt;3" in week and "Sing a song" in week and 'tg://user?id=2' in week

    at = views.alltime_board(all_time(rs, 118), players, 1)
    assert "avg <b>415</b>" in at

    res = parse_share("Krillion #118 🦐\n415\n\n🦑🦑🦑🏮🦑🦑🐟")
    assert views.ack_lines("Mark", res, prev_best=400) == ["📈 New personal best (was 400)."]
    assert views.me_card(None, "Mark", []).startswith("<b>Mark</b>")
