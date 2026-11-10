import pytest

from krillionbot.parser import ParseError, looks_like_result, parse_share

SAMPLE = "Krillion #118 🦐\n415\n\n🦑🦑🦑🏮🦑🦑🐟"


def test_sample_parses():
    r = parse_share(SAMPLE)
    assert (r.dive, r.score, r.tiers) == (118, 415, "🦑🦑🦑🏮🦑🦑🐟")
    assert r.gems == 0 and r.clowns == 0 and r.misses == 0


def test_counts_glyphs():
    r = parse_share("Krillion #5 🦐\n235\n🌟🤡🤡⬛🫧🏮🫧")
    assert r.score == 100 + 15 + 15 + 0 + 10 + 85 + 10 == 235
    assert (r.gems, r.clowns, r.misses) == (1, 2, 1)


def test_tolerates_variation_selectors_and_spaces():
    r = parse_share("Krillion #7 🦐\n60\n\n⬛️ ⬛️ ⬛ 🐟 🐟 ⬛ ⬛")
    assert r.score == 60 and r.tiers == "⬛⬛⬛🐟🐟⬛⬛"


def test_text_around_paste_is_fine():
    r = parse_share("lol finally\nKrillion #118 🦐\n415\n\n🦑🦑🦑🏮🦑🦑🐟\nbeat that")
    assert r.score == 415


def test_rejects_unlimited():
    with pytest.raises(ParseError, match="Unlimited"):
        parse_share("Krillion ∞ 🦐\n415\n🦑🦑🦑🏮🦑🦑🐟")


def test_rejects_edited_score():
    with pytest.raises(ParseError, match="add up to 415"):
        parse_share("Krillion #118 🦐\n700\n🦑🦑🦑🏮🦑🦑🐟")


def test_rejects_wrong_prompt_count():
    with pytest.raises(ParseError, match="Expected 7"):
        parse_share("Krillion #118 🦐\n120\n🦑🦑")


def test_rejects_missing_rows():
    with pytest.raises(ParseError):
        parse_share("Krillion #118 🦐")
    with pytest.raises(ParseError):
        parse_share("Krillion #118 🦐\n415")


def test_precheck():
    assert looks_like_result("krillion time?")
    assert not looks_like_result("hello")
    assert not looks_like_result(None)
