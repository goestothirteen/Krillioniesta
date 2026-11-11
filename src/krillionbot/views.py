"""Chat formatting. Proportional HTML text — never <pre> blocks (they look like code on phones)."""

from __future__ import annotations

from datetime import date, timedelta
from html import escape

from .db import Owed, Player, Result
from .dives import dive_date, fmt_date
from .parser import MAX_SCORE, TIERS, ShareResult
from .stats import AllTime, Ranked, WeekRow, rank, week_losers

MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}


def name_of(players: dict[int, Player], user_id: int) -> str:
    p = players.get(user_id)
    return escape(p.name) if p else f"player {user_id}"


def mention(players: dict[int, Player], user_id: int) -> str:
    p = players.get(user_id)
    label = escape(p.name) if p else f"player {user_id}"
    return f'<a href="tg://user?id={user_id}">{label}</a>'


def _place(r: Ranked) -> str:
    return MEDALS.get(r.rank, f"{r.rank}.")


def _n(n: int | float) -> str:
    return f"{n:,.0f}"


# -- paste acknowledgement ------------------------------------------------


def ack_lines(name: str, res: ShareResult, prev_best: int | None) -> list[str]:
    """The flavour lines under a fresh paste."""
    lines: list[str] = []
    if res.score == MAX_SCORE:
        lines.append("💯 A PERFECT 700. Seven One-in-a-Krillions. Frame it.")
    elif res.gems:
        lines.append(f"🌟 {res.gems} One in a Krillion{'s' if res.gems > 1 else ''}!")
    if prev_best is not None and res.score > prev_best:
        lines.append(f"📈 New personal best (was {prev_best}).")
    if res.clowns:
        lines.append(f"🤡 {res.clowns} Too Clever — the clown wall grows.")
    if res.misses:
        lines.append(f"⬛ {res.misses} blank{'s' if res.misses > 1 else ''}.")
    if res.tiers.count("🫧") >= 4:
        lines.append("🫧 Plankton soup today.")
    return lines


def _details(title: str, lines: list[str]) -> str:
    """The small print, folded away under the standings (tap to expand)."""
    return f"<blockquote expandable><b>{title}</b>\n" + "\n".join(lines) + "</blockquote>"


def _and(names: list[str]) -> str:
    return " & ".join(names)


def _dive_lines(results: list[Result], ranked: list[Ranked], players: dict[int, Player]) -> list[str]:
    by_user = {r.user_id: r for r in results}
    return [f"{_place(r)} {name_of(players, r.user_id)}  <b>{by_user[r.user_id].score}</b>" for r in ranked]


def _strips(results: list[Result], ranked: list[Ranked], players: dict[int, Player]) -> str:
    """Emoji strip first: the strips are all the same width, so the names line up."""
    by_user = {r.user_id: r for r in results}
    return _details("Answer by answer",
                    [f"{by_user[r.user_id].tiers}  {name_of(players, r.user_id)}" for r in ranked])


def today_board(dive: int, results: list[Result], ranked: list[Ranked], players: dict[int, Player],
                waiting: list[int], live: bool) -> str:
    d = dive_date(dive)
    title = f"🦐 <b>Dive #{dive} · {fmt_date(d)}</b>"
    if live:
        title += " <i>(so far)</i>"
    lines = [title, ""]
    if not ranked:
        lines.append("<i>No dives logged yet.</i>")
    lines += _dive_lines(results, ranked, players)
    if waiting:
        lines.append("")
        lines.append("⏳ Still to dive: " + ", ".join(name_of(players, u) for u in waiting))
    if ranked:
        lines.append(_strips(results, ranked, players))
    return "\n".join(lines)


def daily_wrap(dive: int, results: list[Result], ranked: list[Ranked], players: dict[int, Player]) -> str:
    d = dive_date(dive)
    lines = [f"🌙 <b>Dive #{dive} wrap · {fmt_date(d)}</b>", ""]
    lines += _dive_lines(results, ranked, players)
    if len(ranked) >= 2:
        top = [r for r in ranked if r.rank == 1]
        bottom_score = ranked[-1].score
        bottom = [r for r in ranked if r.score == bottom_score]
        lines.append("")
        if len(top) == 1:
            lines.append(f"👑 Diver of the day: {name_of(players, top[0].user_id)}")
        else:
            lines.append("👑 Shared top spot: " + _and([name_of(players, t.user_id) for t in top]))
        if bottom_score != ranked[0].score:
            lines.append("🫧 Plankton of the day: " + _and([name_of(players, b.user_id) for b in bottom]))
    if ranked:
        lines.append(_strips(results, ranked, players))
    return "\n".join(lines)


# -- weekly ------------------------------------------------------------------


def weekly_board(monday: date, rows: list[WeekRow], players: dict[int, Player], dives_done: int,
                 final: bool, owed: list[Owed] | None = None, announce: bool = False) -> str:
    """``owed`` is the forfeit recorded for this week (one entry per person who finished last).

    ``announce`` is the Sunday post itself: only then do we complain about an empty jar.
    """
    sunday = monday + timedelta(days=6)
    head = f"📅 <b>Week {fmt_date(monday)} – {fmt_date(sunday)}</b>"
    if not final:
        head += f" <i>({dives_done} of 7 dives in)</i>"
    lines = [head, ""]
    if not rows:
        lines.append("<i>Nobody has dived this week yet.</i>")
        return "\n".join(lines)
    ranked = {r.user_id: r for r in rank([(w.user_id, w.total) for w in rows])}
    for i, w in enumerate(rows):
        if i:
            lines.append("")  # breathing room between people
        lines.append(f"{_place(ranked[w.user_id])} {name_of(players, w.user_id)}  <b>{_n(w.total)}</b>")
        lines.append(f"      <i>{w.played}/7 dives · avg {_n(w.average)} · best {w.best}</i>")

    owed = owed or []
    losers = [o.user_id for o in owed] or week_losers(rows)
    if len(rows) >= 2:
        lines.append("")
        if final:
            winners = [w.user_id for w in rows if w.total == rows[0].total]
            lines.append("🏆 Week winner: " + _and([name_of(players, u) for u in winners]))
            if losers:
                lines.append("💀 Lowest combined: " + _and([mention(players, u) for u in losers]))
            else:
                lines.append("🤝 Dead level at the bottom — nobody takes the forfeit.")
            if owed:
                left = [o.user_id for o in owed if not o.done]
                if not left:
                    status = " ✅ done"
                elif len(owed) > 1:
                    status = " ⏳ still owed by " + _and([name_of(players, u) for u in left])
                else:
                    status = " ⏳ still owed"
                lines.append(f"🎲 Forfeit: <b>{escape(owed[0].text)}</b>{status}")
            elif announce and losers:
                lines.append("🎲 No forfeits in the jar — add some with /forfeit add …")
        elif losers:
            lines.append("💀 Forfeit zone: " + _and([name_of(players, u) for u in losers]))
    return "\n".join(lines)


# -- all time ------------------------------------------------------------------


def alltime_board(rows: list[AllTime], players: dict[int, Player], total_dives_logged: int) -> str:
    lines = [f"🏆 <b>All-time · average per dive</b> <i>({total_dives_logged} dives logged)</i>", ""]
    if not rows:
        lines.append("<i>Nothing logged yet. Paste a Krillion result to start.</i>")
        return "\n".join(lines)
    for i, a in enumerate(rows, start=1):
        if i > 1:
            lines.append("")
        place = MEDALS.get(i, f"{i}.")
        bits = [f"{a.dives} dives", f"total {_n(a.total)}", f"best {a.best}"]
        if a.wins:
            bits.append(f"👑{a.wins}")
        if a.gems:
            bits.append(f"🌟{a.gems}")
        if a.clowns:
            bits.append(f"🤡{a.clowns}")
        if a.current_streak >= 2:
            bits.append(f"🔥{a.current_streak}")
        lines.append(f"{place} {name_of(players, a.user_id)}  <b>{_n(a.average)}</b>")
        lines.append(f"      <i>{' · '.join(bits)}</i>")
    lines.append("")
    lines.append("<i>👑 daily wins · 🌟 gems · 🤡 Too Clevers · 🔥 current streak</i>")
    return "\n".join(lines)


def me_card(a: AllTime | None, name: str, recent: list[Result]) -> str:
    if a is None or a.dives == 0:
        return f"<b>{escape(name)}</b> — no dives logged yet. Paste your Krillion result here."
    lines = [
        f"🤿 <b>{escape(name)}</b>",
        f"Average <b>{_n(a.average)}</b> over {a.dives} dives · total {_n(a.total)}",
        f"Best {a.best} (dive #{a.best_dive}) · worst {a.worst}",
        f"👑 {a.wins} daily wins · 🌟 {a.gems} gems · 🤡 {a.clowns} · ⬛ {a.misses}",
        f"🔥 Streak {a.current_streak} (longest {a.longest_streak})",
    ]
    if recent:
        lines.append("")
        lines.append("Last dives: " + "  ".join(f"#{r.dive} {r.score}" for r in recent[-5:]))
    return "\n".join(lines)


def forfeit_list(items: list[tuple[int, str, str | None]], owed: list[Owed] | None = None,
                 players: dict[int, Player] | None = None) -> str:
    lines: list[str] = []
    if items:
        lines.append("🎲 <b>Forfeit jar</b>")
        for fid, text, used in items:
            flag = " <i>(used)</i>" if used else ""
            lines.append(f"{fid}. {escape(text)}{flag}")
    else:
        lines.append("🎲 The forfeit jar is empty. Add one with:\n/forfeit add Buy everyone bubble tea")
    if owed:
        lines.append("")
        lines.append("⏳ <b>Still owed</b>")
        for o in owed:
            week = fmt_date(date.fromisoformat(o.week))
            lines.append(f"{name_of(players or {}, o.user_id)} — {escape(o.text)} <i>(week of {week})</i>")
    lines.append("")
    lines.append("<i>/forfeit add … · /forfeit remove N · /forfeit done once you've paid up</i>")
    return "\n".join(lines)


def tier_legend() -> str:
    return "\n".join(f"{g} {name} — {pts}" for g, (name, pts) in TIERS.items())


HELP = (
    "🦐 <b>Krillioniesta</b>\n"
    "Play the Daily dive at krillion.io, tap <b>Copy result</b>, paste it here. "
    "I log it and show the standings.\n\n"
    "/today — today's board\n"
    "/week — this week's board (Mon–Sun). /week last for last week\n"
    "/alltime — lifetime table\n"
    "/me — your own stats\n"
    "/forfeit — the forfeit jar (add / remove). Lowest weekly total draws one; "
    "/forfeit done ticks yours off.\n"
    "/undo — remove your own last paste if it was wrong\n"
    "/clear — admins: clear a dive, or everything\n"
    "/tiers — what each emoji is worth\n\n"
    "Every board has buttons underneath — tap to switch views without posting again.\n"
    "Every night before the next dive opens I post the day's wrap, and on Sundays the week's result. "
    "I'll nudge whoever hasn't dived yet in the evening."
)
