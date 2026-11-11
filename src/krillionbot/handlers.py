from __future__ import annotations

import logging
from datetime import timedelta

from aiogram import Bot, F, Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, ChatMemberUpdated, Message, User

from . import views
from .config import Settings
from .db import Player, Store
from .dives import current_dive, dive_date, fmt_date, week_dives, week_of_dive, week_start
from .keyboards import board_views, confirm
from .parser import ParseError, looks_like_result, parse_share
from .stats import all_time, daily_board, personal_best_before, week_losers, weekly_board

log = logging.getLogger(__name__)
router = Router(name="krillion")

ACTIVE_WINDOW = 7  # someone is "active" if they posted in the last N dives


def _player(user: User) -> Player:
    return Player(user.id, user.full_name, user.username)


async def active_players(store: Store, chat_id: int, dive: int) -> set[int]:
    recent = await store.results_for_dives(chat_id, list(range(dive - ACTIVE_WINDOW, dive)))
    return {r.user_id for r in recent}


# -- view rendering -----------------------------------------------------------------


async def render_today(store: Store, chat_id: int, dive: int) -> str:
    results = await store.results_for_dive(chat_id, dive)
    players = await store.players(chat_id)
    posted = {r.user_id for r in results}
    live = dive == current_dive()
    waiting = sorted(u for u in await active_players(store, chat_id, dive) if u not in posted) if live else []
    return views.today_board(dive, results, daily_board(results), players, waiting, live)


async def render_week(store: Store, chat_id: int, monday, final: bool, announce: bool = False) -> str:
    dives = week_dives(monday)
    results = await store.results_for_dives(chat_id, dives)
    players = await store.players(chat_id)
    rows = weekly_board(results, dives)
    today = current_dive()
    dives_done = sum(1 for d in dives if d <= today)
    owed = await store.week_forfeits(chat_id, monday.isoformat()) if final else []
    return views.weekly_board(monday, rows, players, dives_done, final, owed, announce)


async def close_week(store: Store, chat_id: int, monday) -> str:
    """Sunday night: draw a forfeit, pin it on whoever finished last, and return the final board."""
    dives = week_dives(monday)
    key = monday.isoformat()
    losers = week_losers(weekly_board(await store.results_for_dives(chat_id, dives), dives))
    if losers and not await store.week_forfeits(chat_id, key):
        text = await store.draw_forfeit(chat_id, key)
        if text:
            await store.assign_forfeit(chat_id, key, losers, text)
    return await render_week(store, chat_id, monday, final=True, announce=True)


async def render_alltime(store: Store, chat_id: int) -> str:
    results = await store.all_results(chat_id)
    players = await store.players(chat_id)
    rows = all_time(results, current_dive())
    return views.alltime_board(rows, players, len({r.dive for r in results}))


async def render_me(store: Store, chat_id: int, user: User) -> str:
    results = await store.user_results(chat_id, user.id)
    rows = all_time(results, current_dive())
    return views.me_card(rows[0] if rows else None, user.full_name, results)


async def render_view(key: str, store: Store, chat_id: int, user: User) -> str:
    today = current_dive()
    monday = week_of_dive(today)
    match key:
        case "today":
            return await render_today(store, chat_id, today)
        case "yesterday":
            return await render_today(store, chat_id, today - 1)
        case "week":
            return await render_week(store, chat_id, monday, final=False)
        case "lastweek":
            return await render_week(store, chat_id, monday - timedelta(days=7), final=True)
        case "alltime":
            return await render_alltime(store, chat_id)
        case "me":
            return await render_me(store, chat_id, user)
        case "forfeits":
            owed = await store.owed_forfeits(chat_id)
            return views.forfeit_list(await store.forfeits(chat_id), owed, await store.players(chat_id))
        case "tiers":
            return "<b>Tier values</b>\n" + views.tier_legend()
    return await render_today(store, chat_id, today)


async def post_card(bot: Bot, store: Store, chat_id: int, text: str, key: str) -> Message:
    """Post a board card and take down the previous one, so only the latest card sits in the chat."""
    sent = await bot.send_message(chat_id, text, reply_markup=board_views(key))
    previous = await store.swap_board_message(chat_id, sent.message_id)
    if previous is not None:
        try:
            await bot.delete_message(chat_id, previous)
        except (TelegramBadRequest, TelegramForbiddenError):
            pass  # older than 48h without admin rights, or already gone
    return sent


async def send_board(msg: Message, store: Store, key: str) -> None:
    assert msg.from_user is not None
    text = await render_view(key, store, msg.chat.id, msg.from_user)
    await post_card(msg.bot, store, msg.chat.id, text, key)


@router.callback_query(F.data.startswith("v:"))
async def on_view_button(cb: CallbackQuery, store: Store) -> None:
    parts = (cb.data or "").split(":")
    key = parts[1] if len(parts) > 1 else "today"
    msg = cb.message
    if msg is None or not isinstance(msg, Message):
        await cb.answer()
        return
    text = await render_view(key, store, msg.chat.id, cb.from_user)
    try:
        await msg.edit_text(text, reply_markup=board_views(key))
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise
    await cb.answer()


# -- result pastes ---------------------------------------------------------------


@router.message(F.text.func(looks_like_result), ~F.text.startswith("/"))
async def on_paste(msg: Message, store: Store) -> None:
    text = msg.text or ""
    if msg.from_user is None:
        return
    try:
        res = parse_share(text)
    except ParseError as e:
        # Only answer when it was clearly an attempt at a result, not casual chat.
        if "#" in text or "∞" in text:
            await msg.reply(f"🤔 {e}")
        return

    today = current_dive()
    if res.dive > today:
        await msg.reply(f"🤔 Dive #{res.dive} hasn't opened yet — today is #{today}.")
        return

    chat_id = msg.chat.id
    player = _player(msg.from_user)
    await store.ensure_chat(chat_id, msg.chat.title or msg.chat.full_name)
    await store.upsert_player(chat_id, player)

    existing = await store.get_result(chat_id, player.user_id, res.dive)
    if existing is not None:
        await msg.reply(
            f"Already got your dive #{res.dive}: <b>{existing.score}</b> {existing.tiers}. "
            "First paste counts — /undo if that one was wrong."
        )
        return

    history = await store.user_results(chat_id, player.user_id)
    prev_best = personal_best_before(history, res.dive)
    await store.add_result(chat_id, player.user_id, res.dive, res.score, res.tiers)

    results = await store.results_for_dive(chat_id, res.dive)
    ranked = daily_board(results)
    mine = next(r for r in ranked if r.user_id == player.user_id)
    late = "" if res.dive == today else f" <i>(late entry for {fmt_date(dive_date(res.dive))})</i>"
    place = views.MEDALS.get(mine.rank, f"#{mine.rank}")
    head = f"✅ Logged <b>{res.score}</b> for dive #{res.dive}{late} — {place} of {len(ranked)} so far."
    lines = [head, *views.ack_lines(player.name, res, prev_best), ""]
    lines.append(await render_today(store, chat_id, res.dive))
    await msg.reply("\n".join(lines), reply_markup=board_views("today"))


# -- commands --------------------------------------------------------------------


@router.message(Command("start", "help"))
async def on_help(msg: Message, store: Store) -> None:
    await post_card(msg.bot, store, msg.chat.id, views.HELP, "help")


@router.message(Command("board"))
async def on_board(msg: Message, store: Store) -> None:
    await send_board(msg, store, "today")


@router.message(Command("today"))
async def on_today(msg: Message, store: Store) -> None:
    await send_board(msg, store, "today")


@router.message(Command("yesterday"))
async def on_yesterday(msg: Message, store: Store) -> None:
    await send_board(msg, store, "yesterday")


@router.message(Command("week"))
async def on_week(msg: Message, command: CommandObject, store: Store) -> None:
    arg = (command.args or "").strip().lower()
    await send_board(msg, store, "lastweek" if arg in {"last", "prev", "previous"} else "week")


@router.message(Command("alltime", "all", "season"))
async def on_alltime(msg: Message, store: Store) -> None:
    await send_board(msg, store, "alltime")


@router.message(Command("me"))
async def on_me(msg: Message, store: Store) -> None:
    await send_board(msg, store, "me")


@router.message(Command("tiers"))
async def on_tiers(msg: Message, store: Store) -> None:
    await send_board(msg, store, "tiers")


@router.message(Command("forfeit", "forfeits"))
async def on_forfeit(msg: Message, command: CommandObject, store: Store) -> None:
    chat_id = msg.chat.id
    args = (command.args or "").strip()
    if args.lower().startswith("add "):
        text = args[4:].strip()
        if not text:
            await msg.reply("Add what? e.g. /forfeit add Buy everyone bubble tea")
            return
        await store.ensure_chat(chat_id, msg.chat.title or msg.chat.full_name)
        await store.add_forfeit(chat_id, text[:200], msg.from_user.id if msg.from_user else None)
        await msg.reply(f"🎲 Added to the jar: <i>{views.escape(text[:200])}</i>")
        return
    if args.lower().startswith("remove "):
        try:
            fid = int(args.split(maxsplit=1)[1])
        except (IndexError, ValueError):
            await msg.reply("Which one? e.g. /forfeit remove 3")
            return
        ok = await store.remove_forfeit(chat_id, fid)
        await msg.reply("🗑 Removed." if ok else "No forfeit with that number.")
        return
    if args.lower() in {"done", "paid"}:
        if msg.from_user is None:
            return
        paid = await store.mark_forfeit_done(chat_id, msg.from_user.id)
        if paid is None:
            await msg.reply("You don't owe a forfeit. Lucky you.")
        else:
            name = views.escape(msg.from_user.full_name)
            await msg.reply(f"✅ {name} has paid up: <i>{views.escape(paid.text)}</i>")
        return
    await send_board(msg, store, "forfeits")


@router.message(Command("pastehelp"))
async def on_pastehelp(msg: Message) -> None:
    await msg.reply(
        "Paste exactly what Krillion copies, e.g.\n\n"
        "Krillion #118 🦐\n415\n\n🦑🦑🦑🏮🦑🦑🐟\n\n"
        "I check the emoji add up to the score, so don't tidy it."
    )


# -- fixing mistakes ---------------------------------------------------------------


@router.message(Command("undo"))
async def on_undo(msg: Message, command: CommandObject, store: Store) -> None:
    """Remove your own result: the latest one, or /undo 118 for a specific dive."""
    if msg.from_user is None:
        return
    chat_id, uid = msg.chat.id, msg.from_user.id
    arg = (command.args or "").strip().lstrip("#")
    if arg.isdigit():
        dive = int(arg)
    else:
        latest = await store.latest_result(chat_id, uid)
        if latest is None:
            await msg.reply("Nothing of yours to undo here.")
            return
        dive = latest.dive
    existing = await store.get_result(chat_id, uid, dive)
    if existing is None:
        await msg.reply(f"You have no result for dive #{dive}.")
        return
    await store.delete_result(chat_id, uid, dive)
    await msg.reply(f"↩️ Removed your dive #{dive} ({existing.score}). Paste the right one whenever.")


async def _is_admin(bot: Bot, msg: Message) -> bool:
    if msg.chat.type == ChatType.PRIVATE or msg.from_user is None:
        return True
    member = await bot.get_chat_member(msg.chat.id, msg.from_user.id)
    return member.status in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}


@router.message(Command("clear"))
async def on_clear(msg: Message, command: CommandObject, bot: Bot, store: Store) -> None:
    """Group admins only. /clear today · /clear 118 · /clear all"""
    if not await _is_admin(bot, msg):
        await msg.reply("Only a group admin can clear results. You can /undo your own.")
        return
    arg = (command.args or "").strip().lower().lstrip("#")
    if arg in {"", "help"}:
        await msg.reply(
            "What should I clear?\n"
            "/clear today — everyone's result for today's dive\n"
            "/clear 118 — everyone's result for dive #118\n"
            "/clear all — wipe this chat's whole history (results, forfeits)"
        )
        return
    if arg in {"today"}:
        dive = current_dive()
        payload = f"dive:{dive}"
        what = f"everyone's result for dive #{dive}"
    elif arg in {"yesterday"}:
        dive = current_dive() - 1
        payload = f"dive:{dive}"
        what = f"everyone's result for dive #{dive}"
    elif arg.isdigit():
        payload = f"dive:{int(arg)}"
        what = f"everyone's result for dive #{int(arg)}"
    elif arg == "all":
        payload = "all"
        what = "this chat's <b>entire</b> history — every result and every forfeit"
    else:
        await msg.reply("I didn't get that. Try /clear today, /clear 118 or /clear all.")
        return
    await msg.reply(f"⚠️ Clear {what}?", reply_markup=confirm("clr", payload))


@router.callback_query(F.data.startswith("clr:"))
async def on_clear_confirm(cb: CallbackQuery, bot: Bot, store: Store) -> None:
    msg = cb.message
    if msg is None or not isinstance(msg, Message):
        await cb.answer()
        return
    # Only the person who asked (replied-to message author) or an admin may confirm.
    asker = msg.reply_to_message.from_user if msg.reply_to_message else None
    asked_by = asker.id if asker else None
    if cb.from_user.id != asked_by:
        is_admin = msg.chat.type == ChatType.PRIVATE
        if not is_admin:
            member = await bot.get_chat_member(msg.chat.id, cb.from_user.id)
            is_admin = member.status in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}
        if not is_admin:
            await cb.answer("Not your button.", show_alert=True)
            return
    _, verdict, *rest = (cb.data or "").split(":")
    if verdict != "yes":
        await msg.edit_text("Left as is.")
        await cb.answer()
        return
    if rest and rest[0] == "dive" and len(rest) > 1:
        n = await store.clear_dive(msg.chat.id, int(rest[1]))
        await msg.edit_text(f"🧹 Cleared dive #{rest[1]} — {n} result{'s' if n != 1 else ''} removed.")
    else:
        n = await store.clear_chat(msg.chat.id)
        await msg.edit_text(f"🧹 Fresh start — {n} result{'s' if n != 1 else ''} and all forfeits removed.")
    await cb.answer()


# -- membership ------------------------------------------------------------------


@router.my_chat_member()
async def on_membership(event: ChatMemberUpdated, bot: Bot, store: Store, settings: Settings) -> None:
    new = event.new_chat_member.status
    chat = event.chat
    if new in {ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR}:
        await store.ensure_chat(chat.id, chat.title or chat.full_name)
        monday = week_start(dive_date(current_dive()))
        await post_card(
            bot,
            store,
            chat.id,
            "🦐 <b>Krillioniesta reporting for duty.</b>\n"
            "Paste your Krillion results here and I'll keep the daily, weekly and all-time boards. "
            f"This week started {fmt_date(monday)}. Type /help for the commands.",
            "today",
        )
    elif new in {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}:
        await store.forget_chat(chat.id)
        log.info("left chat %s", chat.id)
