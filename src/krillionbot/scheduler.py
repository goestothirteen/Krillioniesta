"""Timed posts: the nightly wrap (and Sunday's weekly result), and the evening nudge."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from . import views
from .config import Settings
from .db import Store
from .dives import NY, SG, current_dive, dive_date, week_of_dive
from .handlers import active_players, close_week
from .stats import daily_board

log = logging.getLogger(__name__)


async def _send(bot: Bot, store: Store, chat_id: int, text: str) -> None:
    try:
        await bot.send_message(chat_id, text)
    except TelegramForbiddenError:
        log.warning("bot no longer in chat %s — forgetting it", chat_id)
        await store.forget_chat(chat_id)
    except Exception:  # noqa: BLE001
        log.exception("send to %s failed", chat_id)


async def wrap_dive(bot: Bot, store: Store, chat_id: int, dive: int) -> None:
    """Post the daily wrap for ``dive`` once; add the weekly wrap if it was a Sunday."""
    results = await store.results_for_dive(chat_id, dive)
    if not results:
        return
    if await store.mark_posted(chat_id, "daily", str(dive)):
        players = await store.players(chat_id)
        await _send(bot, store, chat_id, views.daily_wrap(dive, results, daily_board(results), players))

    if dive_date(dive).weekday() == 6:  # Sunday closes the week
        monday = week_of_dive(dive)
        key = monday.isoformat()
        if await store.mark_posted(chat_id, "weekly", key):
            await _send(bot, store, chat_id, await close_week(store, chat_id, monday))


async def daily_job(bot: Bot, store: Store) -> None:
    dive = current_dive()  # runs minutes before reset, so this is the closing dive
    for chat_id in await store.chat_ids():
        await wrap_dive(bot, store, chat_id, dive)


async def nudge_job(bot: Bot, store: Store) -> None:
    dive = current_dive()
    for chat_id in await store.chat_ids():
        posted = {r.user_id for r in await store.results_for_dive(chat_id, dive)}
        missing = sorted(u for u in await active_players(store, chat_id, dive) if u not in posted)
        if not missing or not await store.mark_posted(chat_id, "nudge", str(dive)):
            continue
        players = await store.players(chat_id)
        names = ", ".join(views.mention(players, u) for u in missing)
        await _send(bot, store, chat_id, f"🤿 Dive #{dive} closes soon — {names}, you haven't dived yet!")


async def catch_up(bot: Bot, store: Store, days: int = 3) -> None:
    """On startup, post any wraps that were missed while the bot was down."""
    today = current_dive()
    for chat_id in await store.chat_ids():
        for dive in range(today - days, today):
            await wrap_dive(bot, store, chat_id, dive)


def build_scheduler(bot: Bot, store: Store, settings: Settings) -> AsyncIOScheduler:
    sched = AsyncIOScheduler()
    wrap_at = datetime(2000, 1, 2, tzinfo=NY) - timedelta(minutes=settings.wrap_minutes_before_reset)
    sched.add_job(
        daily_job,
        CronTrigger(hour=wrap_at.hour, minute=wrap_at.minute, timezone=NY),
        args=[bot, store],
        id="daily_wrap",
        misfire_grace_time=3600,
        coalesce=True,
    )
    if settings.nudge_hour_sgt:
        sched.add_job(
            nudge_job,
            CronTrigger(hour=settings.nudge_hour_sgt, minute=0, timezone=SG),
            args=[bot, store],
            id="nudge",
            misfire_grace_time=1800,
            coalesce=True,
        )
    return sched
