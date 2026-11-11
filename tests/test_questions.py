import pytest

from krillionbot import views
from krillionbot.db import Player, Store
from krillionbot.handlers import render_questions
from krillionbot.questions import parse_today
from krillionbot.stats import daily_board


@pytest.fixture
async def store():
    s = Store(":memory:")
    await s.open()
    yield s
    await s.close()


def test_parse_today_accepts_the_feed_shape():
    prompts = [{"id": "p1", "text": " Name a tree "}, {"id": "p2", "text": "x" * 500}]
    payload = {"dayNumber": 119, "prompts": prompts}
    assert parse_today(payload) == (119, ["Name a tree", "x" * 200])


@pytest.mark.parametrize("bad", [
    None, [], {}, {"dayNumber": "119", "prompts": []}, {"dayNumber": 119, "prompts": []},
    {"dayNumber": 119, "prompts": [{"text": ""}]}, {"dayNumber": 119, "prompts": [{"text": 5}]},
    {"dayNumber": True, "prompts": [{"text": "a"}]}, {"dayNumber": 1, "prompts": [{"text": "a"}] * 50},
])
def test_parse_today_rejects_anything_else(bad):
    assert parse_today(bad) is None


async def test_questions_board(store: Store):
    for uid, name in [(1, "Mark"), (2, "Zo<ey")]:
        await store.upsert_player(-1, Player(uid, name, None))
    await store.add_result(-1, 1, 118, 415, "🦑🦑🦑🏮🦑🦑🐟")
    await store.add_result(-1, 2, 118, 355, "🌟🐟🐟🏮🦑🦑⬛")
    await store.save_prompts(118, [f"Name a <thing> {i}" for i in range(1, 8)])
    assert len(await store.prompts(118)) == 7 and await store.prompts(117) == []

    text = await render_questions(store, -1, 118)
    assert "<b>1.</b> Name a &lt;thing&gt; 1\n      Mark 🦑 · Zo&lt;ey 🌟" in text
    assert "<b>7.</b> Name a &lt;thing&gt; 7\n      Mark 🐟 · Zo&lt;ey ⬛" in text

    # No saved wording (older dives, or the feed was down): still shows the emoji.
    rs = await store.results_for_dive(-1, 118)
    bare = views.questions_board(118, rs, daily_board(rs), await store.players(-1), [])
    assert "<b>3.</b> <i>(question not saved)</i>\n      Mark 🦑 · Zo&lt;ey 🐟" in bare
    assert "Nobody dived" in views.questions_board(117, [], [], {}, [])
