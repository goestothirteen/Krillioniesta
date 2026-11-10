# Krillioniesta — Krillion scores for a Telegram group

Everyone plays the [Krillion](https://krillion.io) Daily dive, taps **Copy
result**, and pastes it in the group. The bot logs each paste and keeps the
daily, weekly (Mon–Sun) and all-time boards. The lowest combined score of the
week draws a forfeit from the jar.

```
Krillion #118 🦐
415

🦑🦑🦑🏮🦑🦑🐟
```

Krillion has no API, so the paste *is* the data. The emoji row is recomputed
against the score, so an edited paste is rejected. Unlimited results
(`Krillion ∞`) are rejected too. One paste per person per dive; first counts.

## What it does

- Replies to every valid paste with the score, today's standings so far and
  who still hasn't dived. Calls out personal bests, 🌟 gems, 🤡 Too Clevers.
- Posts the day's wrap 10 minutes before the next dive opens (midnight New
  York = 1pm Singapore in winter, 12pm in summer). Diver of the day, Plankton
  of the day.
- Sunday's wrap also closes the week: winner, lowest combined, and a forfeit
  drawn from the jar (`/forfeit add …`). Missed days count as 0; only people
  who dived at least once that week are ranked.
- Evening nudge (21:00 SGT) tagging anyone active in the last 7 dives who
  hasn't posted today's.
- `/today` `/yesterday` `/week` `/week last` `/alltime` `/me` `/forfeit` `/tiers` `/help`

Dive #1 was 16 July 2026, so the dive number maps to a date regardless of when
someone pastes — late entries land on the right day.

## Setup

1. @BotFather → `/newbot` → name "Krillioniesta Bot", pick a free handle. Copy the token.
2. @BotFather → `/setprivacy` → pick the bot → **Disable**. Without this the bot
   cannot see pastes in a group. (If the bot is already in a group, remove and
   re-add it after changing this.)
3. `cp .env.example .env` and put the token in.
4. `docker compose up -d --build`, then `docker compose logs -f`.
5. Add the bot to the group. It says hello; paste a result.

## Develop

```bash
uv sync --extra dev
uv run pytest -q
uv run ruff check src tests
```

## Layout

```
src/krillionbot/
  parser.py     share-text → (dive, score, tiers); validates the sum
  dives.py      dive number ↔ date, weeks, reset time (New York midnight)
  db.py         SQLite store (aiosqlite): chats, players, results, forfeits
  stats.py      pure leaderboard maths: daily rank, weekly totals, all-time, streaks
  views.py      HTML message formatting (no <pre>)
  handlers.py   aiogram handlers: pastes + commands + membership
  scheduler.py  nightly wrap, Sunday weekly wrap, evening nudge, startup catch-up
```
