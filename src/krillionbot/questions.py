"""The day's seven prompts, read from the feed krillion.io's own page uses.

It is not a published API, so everything here is best-effort: any failure just means the
question view falls back to "Q1…Q7" without the wording.
"""

from __future__ import annotations

import logging

import aiohttp

from .db import Store

log = logging.getLogger(__name__)

TODAY_URL = "https://krillion.io/api/today"
MAX_PROMPTS = 12
MAX_LEN = 200


def parse_today(payload: object) -> tuple[int, list[str]] | None:
    """(dive number, prompt texts) from the feed's JSON, or None if it isn't the shape we expect."""
    if not isinstance(payload, dict):
        return None
    dive, prompts = payload.get("dayNumber"), payload.get("prompts")
    if not isinstance(dive, int) or isinstance(dive, bool) or not isinstance(prompts, list):
        return None
    texts = [p.get("text") for p in prompts if isinstance(p, dict)]
    if not texts or len(texts) > MAX_PROMPTS or not all(isinstance(t, str) and t.strip() for t in texts):
        return None
    return dive, [t.strip()[:MAX_LEN] for t in texts]


async def fetch_today() -> tuple[int, list[str]] | None:
    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout, headers={"User-Agent": "krillion-score-bot"}) as http:
        async with http.get(TODAY_URL) as resp:
            if resp.status != 200:
                return None
            return parse_today(await resp.json(content_type=None))


async def remember_today(store: Store) -> None:
    """Store today's prompts if we don't have them yet. Never raises."""
    try:
        got = await fetch_today()
        if got is None:
            log.warning("krillion feed gave nothing usable")
            return
        dive, texts = got
        if not await store.prompts(dive):
            await store.save_prompts(dive, texts)
            log.info("stored %d prompts for dive #%d", len(texts), dive)
    except Exception:  # noqa: BLE001
        log.warning("could not fetch today's prompts", exc_info=True)
