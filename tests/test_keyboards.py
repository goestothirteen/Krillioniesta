from krillionbot.keyboards import VIEWS, board_views, confirm


def test_board_views_marks_active_and_has_refresh():
    kb = board_views("week")
    buttons = [b for row in kb.inline_keyboard for b in row]
    assert len(buttons) == len(VIEWS) + 1
    active = [b for b in buttons if b.text.startswith("• ")]
    assert len(active) == 1 and active[0].callback_data == "v:week"
    assert buttons[-1].callback_data == "v:week:r"
    assert all(len(b.callback_data.encode()) <= 64 for b in buttons)


def test_confirm():
    kb = confirm("clr", "dive:118")
    assert [b.callback_data for b in kb.inline_keyboard[0]] == ["clr:yes:dive:118", "clr:no:dive:118"]
