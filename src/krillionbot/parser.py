"""Parse the text Krillion copies to the clipboard when you share a result.

The share text looks like::

    Krillion #118 🦐
    415

    🦑🦑🦑🏮🦑🦑🐟

Line 1 carries the dive number, line 2 the score, and the emoji row has one
glyph per prompt. The glyph row lets us recompute the score, so a paste whose
numbers don't add up is rejected rather than stored.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Tier glyph -> (name, points). Keep in sync with the krillion.io client.
TIERS: dict[str, tuple[str, int]] = {
    "🫧": ("Plankton", 10),
    "🤡": ("Too Clever", 15),
    "🐟": ("Schooler", 30),
    "🦑": ("Rare", 60),
    "🏮": ("Deep Cut", 85),
    "🌟": ("One in a Krillion", 100),
    "⬛": ("Miss", 0),
}
GEM = "🌟"
CLOWN = "🤡"
MISS = "⬛"
PROMPTS_PER_DIVE = 7
MAX_SCORE = 700

_HEADER_RE = re.compile(r"Krillion\s*#\s*(\d{1,5})", re.IGNORECASE)
_UNLIMITED_RE = re.compile(r"Krillion\s*(∞|infinity)", re.IGNORECASE)
_SCORE_RE = re.compile(r"^\s*(\d{1,3})\s*(?:/\s*700)?\s*(?:pts?)?\s*$", re.IGNORECASE)
_STRIP = str.maketrans("", "", "️‍​ \t")


class ParseError(ValueError):
    """The text looked like a Krillion result but couldn't be trusted."""


@dataclass(frozen=True, slots=True)
class ShareResult:
    dive: int
    score: int
    tiers: str  # the emoji row, one glyph per prompt, no spaces

    @property
    def gems(self) -> int:
        return self.tiers.count(GEM)

    @property
    def clowns(self) -> int:
        return self.tiers.count(CLOWN)

    @property
    def misses(self) -> int:
        return self.tiers.count(MISS)


def looks_like_result(text: str | None) -> bool:
    """Cheap pre-check so we only try to parse messages that mention Krillion."""
    return bool(text) and "krillion" in text.lower()


def tier_points(tiers: str) -> int:
    return sum(TIERS[g][1] for g in tiers)


def parse_share(text: str) -> ShareResult:
    """Parse a share paste. Raises ParseError with a friendly reason on failure."""
    if _UNLIMITED_RE.search(text):
        raise ParseError("That's an Unlimited result (Krillion ∞) — only the Daily dive counts here.")

    header = _HEADER_RE.search(text)
    if not header:
        raise ParseError("I couldn't find the dive number (the “Krillion #123” line).")
    dive = int(header.group(1))

    lines = [ln for ln in text[header.end():].splitlines()]
    score: int | None = None
    tiers: str | None = None
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if score is None:
            m = _SCORE_RE.match(line)
            if m:
                score = int(m.group(1))
                continue
        glyphs = line.translate(_STRIP)
        if glyphs and all(g in TIERS for g in glyphs):
            tiers = glyphs
            break

    if score is None:
        raise ParseError("I couldn't find the score line.")
    if tiers is None:
        raise ParseError("I couldn't find the row of tier emoji under the score.")
    if len(tiers) != PROMPTS_PER_DIVE:
        raise ParseError(
            f"Expected {PROMPTS_PER_DIVE} tier emoji for a Daily dive but found {len(tiers)}."
        )
    expected = tier_points(tiers)
    if expected != score:
        raise ParseError(
            f"Those emoji add up to {expected}, not {score} — was the paste edited?"
        )
    return ShareResult(dive=dive, score=score, tiers=tiers)
