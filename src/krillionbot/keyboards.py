from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

VIEWS: list[tuple[str, str]] = [
    ("today", "🦐 Today"),
    ("week", "📅 Week"),
    ("alltime", "🏆 All-time"),
    ("yesterday", "📆 Yesterday"),
    ("questions", "❓ Questions"),
    ("lastweek", "📅 Last week"),
    ("me", "🤿 Me"),
    ("forfeits", "🎲 Forfeits"),
    ("tiers", "ℹ️ Tiers"),
]


def board_views(active: str) -> InlineKeyboardMarkup:
    """One board message, many views: tapping swaps the text in place instead of posting again."""
    b = InlineKeyboardBuilder()
    for key, label in VIEWS:
        text = f"• {label}" if key == active else label
        b.button(text=text, callback_data=f"v:{key}")
    b.button(text="🔄 Refresh", callback_data=f"v:{active}:r")
    b.adjust(3, 3, 3, 1)
    return b.as_markup()


def confirm(action: str, payload: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="✅ Yes, clear it", callback_data=f"{action}:yes:{payload}"),
            InlineKeyboardButton(text="✖️ No", callback_data=f"{action}:no:{payload}"),
        ]]
    )
