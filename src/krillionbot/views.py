"""Chat formatting. Proportional HTML text — never <pre> blocks (they look like code on phones)."""

from __future__ import annotations

from datetime import date, timedelta
from html import escape

from .db import Player, Result
from .dives import dive_date, fmt_date
from .parser import MAX_SCORE, TIERS, ShareResult
from .stats import AllTime, Ranked, WeekRow

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


def today_board(dive: int, results: list[Result], ranked: list[Ranked], players: dict[int, Player],
                waiting: list[int], live: bool) -> str:
    d = dive_date(dive)
    title = f"🦐 <b>Dive #{dive} · {fmt_date(d)}</b>"
    if live:
        title += " <i>(so far)</i>"
    by_user = {r.user_id: r for r in results}
    lines = [title]
    for r in ranked:
        res = by_user[r.user_id]
        lines.append(f"{_place(r)} {name_of(players, r.user_id)} — <b>{res.score}</b>  {res.tiers}")
    if not ranked:
        lines.append("<i>No dives logged yet.</i>")
    if waiting:
        lines.append("")
        lines.append("⏳ Still to dive: " + ", ".join(name_of(players, u) for u in waiting))
    return "\n".join(lines)


def daily_wrap(dive: int, results: list[Result], ranked: list[Ranked], players: dict[int, Player]) -> str:
    d = dive_date(dive)
    lines = [f"🌙 <b>Dive #{dive} wrap · {fmt_date(d)}</b>"]
    by_user = {r.user_id: r for r in results}
    for r in ranked:
        res = by_user[r.user_id]
        lines.append(f"{_place(r)} {name_of(players, r.user_id)} — <b>{res.score}</b>  {res.tiers}")
    if len(ranked) >= 2:
        top = [r for r in ranked if r.rank == 1]
        bottom_score = ranked[-1].score
        bottom = [r for r in ranked if r.score == bottom_score]
        lines.append("")
        if len(top) == 1:
            lines.append(f"👑 Diver of the day: {name_of(players, top[0].user_id)}")
        else:
            lines.append("👑 Shared top spot: " + " & ".join(name_of(players, t.user_id) for t in top))
        if bottom_score != ranked[0].score:
            lines.append("🫧 Plankton of the day: " + " & ".join(name_of(players, b.user_id) for b in bottom))
    gems = [(r.user_id, r.tiers.count("🌟")) for r in results if "🌟" in r.tiers]
    if gems:
        lines.append("🌟 Gems: " + ", ".join(f"{name_of(players, u)} ×{n}" for u, n in gems))
    return "\n".join(lines)


# -- weekly ------------------------------------------------------------------


def weekly_board(monday: date, rows: list[WeekRow], players: dict[int, Player], dives_done: int,
                 final: bool, forfeit: str | None = None) -> str:
    sunday = monday + timedelta(days=6)
    head = f"📅 <b>Week {fmt_date(monday)} – {fmt_date(sunday)}</b>"
    if not final:
        head += f" <i>({dives_done} of 7 dives in)</i>"
    lines = [head]
    if not rows:
        lines.append("<i>Nobody has dived this week yet.</i>")
        return "\n".join(lines)
    ranked = {r.user_id: r for r in _rank_rows([(w.user_id, w.total) for w in rows])}
    for w in rows:
        r = ranked[w.user_id]
        extras = f"{w.played}/7 dives · avg {_n(w.average)} · best {w.best}"
        if w.gems:
            extras += f" · 🌟{w.gems}"
        if w.clowns:
            extras += f" · 🤡{w.clowns}"
        lines.append(f"{_place(r)} {name_of(players, w.user_id)} — <b>{_n(w.total)}</b>")
        lines.append(f"      <i>{extras}</i>")
    if len(rows) >= 2:
        lines.append("")
        loser = rows[-1]
        if final:
            lines.append(f"🏆 Week winner: {name_of(players, rows[0].user_id)}")
            lines.append(f"💀 Lowest combined: {mention(players, loser.user_id)}")
            if forfeit:
                lines.append(f"🎲 Forfeit: <b>{escape(forfeit)}</b>")
            else:
                lines.append("🎲 No forfeits in the jar — add some with /forfeit add …")
        else:
            lines.append(f"💀 Currently in the forfeit zone: {name_of(players, loser.user_id)}")
    return "\n".join(lines)


def _rank_rows(scores: list[tuple[int, int]]) -> list[Ranked]:
    from .stats import rank

    return rank(scores)


# -- all time ------------------------------------------------------------------


def alltime_board(rows: list[AllTime], players: dict[int, Player], total_dives_logged: int) -> str:
    lines = [f"🏆 <b>All-time · {total_dives_logged} dives logged</b>"]
    if not rows:
        lines.append("<i>Nothing logged yet. Paste a Krillion result to start.</i>")
        return "\n".join(lines)
    for i, a in enumerate(rows, start=1):
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
        lines.append(f"{place} {name_of(players, a.user_id)} — avg <b>{_n(a.average)}</b>")
        lines.append(f"      <i>{' · '.join(bits)}</i>")
    lines.append("")
    lines.append("<i>Ranked by average. 👑 daily wins · 🌟 gems · 🤡 Too Clevers · 🔥 current streak</i>")
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


def forfeit_list(items: list[tuple[int, str, str | None]]) -> str:
    if not items:
        return "🎲 The forfeit jar is empty. Add one with:\n/forfeit add Buy everyone bubble tea"
    lines = ["🎲 <b>Forfeit jar</b>"]
    for fid, text, used in items:
        flag = " <i>(used)</i>" if used else ""
        lines.append(f"{fid}. {escape(text)}{flag}")
    lines.append("")
    lines.append("<i>/forfeit add … to add · /forfeit remove N to drop one</i>")
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
    "/forfeit — the forfeit jar (add / remove). Lowest weekly total draws one.\n"
    "/undo — remove your own last paste if it was wrong\n"
    "/clear — admins: clear a dive, or everything\n"
    "/tiers — what each emoji is worth\n\n"
    "Every board has buttons underneath — tap to switch views without posting again.\n"
    "Every night before the next dive opens I post the day's wrap, and on Sundays the week's result. "
    "I'll nudge whoever hasn't dived yet in the evening."
)
