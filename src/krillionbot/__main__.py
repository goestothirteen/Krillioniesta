from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from .config import load_settings
from .db import Store
from .handlers import router
from .scheduler import build_scheduler, catch_up

COMMANDS = [
    BotCommand(command="board", description="The board, with buttons for every view"),
    BotCommand(command="today", description="Today's dive board"),
    BotCommand(command="week", description="This week's board (Mon–Sun)"),
    BotCommand(command="alltime", description="All-time table"),
    BotCommand(command="me", description="Your own stats"),
    BotCommand(command="forfeit", description="The forfeit jar"),
    BotCommand(command="yesterday", description="Yesterday's board"),
    BotCommand(command="questions", description="Yesterday's questions, with everyone's emoji"),
    BotCommand(command="undo", description="Remove your own last result"),
    BotCommand(command="clear", description="Admin: clear a dive or everything"),
    BotCommand(command="tiers", description="What each emoji is worth"),
    BotCommand(command="help", description="How this works"),
]


async def run() -> None:
    settings = load_settings()
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log = logging.getLogger("krillionbot")

    store = Store(settings.db_path)
    await store.open()

    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(store=store, settings=settings)
    dp.include_router(router)

    await bot.set_my_commands(COMMANDS)
    me = await bot.get_me()
    log.info("running as @%s", me.username)

    sched = build_scheduler(bot, store, settings)
    sched.start()
    await catch_up(bot, store)
    try:
        await dp.start_polling(bot, allowed_updates=["message", "callback_query", "my_chat_member"])
    finally:
        sched.shutdown(wait=False)
        await store.close()
        await bot.session.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
