"""Pure leaderboard maths over stored results. No I/O, fully unit-testable."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .db import Result
from .parser import CLOWN, GEM, MISS


@dataclass(slots=True)
class Ranked:
    user_id: int
    score: int
    rank: int  # 1-based; ties share a rank


def rank(scores: list[tuple[int, int]]) -> list[Ranked]:
    """Rank (user_id, score) pairs high-to-low. Input order breaks ties within a rank."""
    ordered = sorted(scores, key=lambda s: -s[1])
    out: list[Ranked] = []
    last_score: int | None = None
    for i, (uid, score) in enumerate(ordered, start=1):
        r = out[-1].rank if (out and score == last_score) else i
        out.append(Ranked(uid, score, r))
        last_score = score
    return out


def daily_board(results: list[Result]) -> list[Ranked]:
    """Results are already ordered score desc, posted asc — earlier post wins the tiebreak order."""
    return rank([(r.user_id, r.score) for r in results])


@dataclass(slots=True)
class WeekRow:
    user_id: int
    total: int = 0
    played: int = 0
    best: int = 0
    gems: int = 0
    clowns: int = 0
    per_dive: dict[int, int] = field(default_factory=dict)

    @property
    def average(self) -> float:
        return self.total / self.played if self.played else 0.0


def weekly_board(results: list[Result], dives: list[int]) -> list[WeekRow]:
    """Sum each player's scores over ``dives``; missed days count 0. Sorted best-first.

    Only people with at least one result in the week appear.
    """
    rows: dict[int, WeekRow] = {}
    dive_set = set(dives)
    for r in results:
        if r.dive not in dive_set:
            continue
        row = rows.setdefault(r.user_id, WeekRow(r.user_id))
        row.total += r.score
        row.played += 1
        row.best = max(row.best, r.score)
        row.gems += r.tiers.count(GEM)
        row.clowns += r.tiers.count(CLOWN)
        row.per_dive[r.dive] = r.score
    return sorted(rows.values(), key=lambda w: (-w.total, -w.played, w.user_id))


def week_losers(rows: list[WeekRow]) -> list[int]:
    """Everyone tied on the lowest weekly total. Empty when alone or when the whole table is level."""
    if len(rows) < 2:
        return []
    low = min(w.total for w in rows)
    if low == max(w.total for w in rows):
        return []
    return [w.user_id for w in rows if w.total == low]


@dataclass(slots=True)
class AllTime:
    user_id: int
    total: int = 0
    dives: int = 0
    best: int = 0
    best_dive: int = 0
    worst: int = 701
    gems: int = 0
    clowns: int = 0
    misses: int = 0
    current_streak: int = 0
    longest_streak: int = 0
    wins: int = 0  # daily wins (shared wins count)

    @property
    def average(self) -> float:
        return self.total / self.dives if self.dives else 0.0


def all_time(results: list[Result], current_dive: int) -> list[AllTime]:
    """Lifetime stats per player, sorted by average (min 1 dive) then total."""
    by_user: dict[int, list[Result]] = defaultdict(list)
    by_dive: dict[int, list[Result]] = defaultdict(list)
    for r in results:
        by_user[r.user_id].append(r)
        by_dive[r.dive].append(r)

    wins: dict[int, int] = defaultdict(int)
    for dive_results in by_dive.values():
        top = max(r.score for r in dive_results)
        for r in dive_results:
            if r.score == top:
                wins[r.user_id] += 1

    out: list[AllTime] = []
    for uid, rs in by_user.items():
        rs.sort(key=lambda r: r.dive)
        a = AllTime(uid)
        for r in rs:
            a.total += r.score
            a.dives += 1
            if r.score > a.best:
                a.best, a.best_dive = r.score, r.dive
            a.worst = min(a.worst, r.score)
            a.gems += r.tiers.count(GEM)
            a.clowns += r.tiers.count(CLOWN)
            a.misses += r.tiers.count(MISS)
        a.current_streak, a.longest_streak = streaks([r.dive for r in rs], current_dive)
        a.wins = wins[uid]
        out.append(a)
    return sorted(out, key=lambda a: (-a.average, -a.total, a.user_id))


def streaks(dives: list[int], current_dive: int) -> tuple[int, int]:
    """(current, longest) runs of consecutive dives. Current counts if it reaches today or yesterday."""
    if not dives:
        return 0, 0
    ds = sorted(set(dives))
    longest = run = 1
    for prev, cur in zip(ds, ds[1:], strict=False):
        run = run + 1 if cur == prev + 1 else 1
        longest = max(longest, run)
    # ``run`` is the length of the final consecutive block.
    current = run if ds[-1] >= current_dive - 1 else 0
    return current, longest


def personal_best_before(results: list[Result], dive: int) -> int | None:
    """Highest score this player had before ``dive`` (None if this is their first)."""
    prior = [r.score for r in results if r.dive != dive]
    return max(prior) if prior else None


def prompt_breakdown(results: list[Result]) -> list[list[tuple[int, str]]]:
    """For each of the 7 prompts, the (user_id, glyph) pairs — used for head-to-head views."""
    n = max((len(r.tiers) for r in results), default=0)
    cols: list[list[tuple[int, str]]] = [[] for _ in range(n)]
    for r in results:
        for i, g in enumerate(r.tiers):
            cols[i].append((r.user_id, g))
    return cols
