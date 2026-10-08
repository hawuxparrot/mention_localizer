import pytest

from eil.matching import lenient_match, normalize_text, prepare_mention, strict_match
from eil.models import BoundingBox, OcrPage, OcrToken
from tests.helpers import make_page


def ocr_page(*texts: str) -> OcrPage:
    tokens = tuple(
        OcrToken(
            text=text,
            box=BoundingBox(x=i * 10, y=0, width=8, height=6),
        )
        for i, text in enumerate(texts)
    )
    return OcrPage(page=make_page(), tokens=tokens, width=100, height=50)


def test_normalize_text_casefolds_and_collapses_whitespace() -> None:
    assert normalize_text("  Haller\t") == "haller"
    assert normalize_text("Johann  Caspar") == "johann caspar"


def test_strict_match_no_match_returns_empty_tuple() -> None:
    assert strict_match("Euler", ocr_page("Haller", "aus", "Bern")) == ()


def test_strict_match_unique_match_returns_enclosing_box() -> None:
    page = ocr_page("Haller", "aus", "Bern")
    matches = strict_match("Haller aus", page)
    assert matches == (
        BoundingBox.enclosing((page.tokens[0].box, page.tokens[1].box)),
    )


def test_strict_match_multiple_matches_are_all_returned() -> None:
    page = ocr_page("von", "Haller", "und", "von", "Haller")
    matches = strict_match("von Haller", page)
    assert matches == (
        BoundingBox.enclosing((page.tokens[0].box, page.tokens[1].box)),
        BoundingBox.enclosing((page.tokens[3].box, page.tokens[4].box)),
    )


def test_strict_match_is_case_insensitive() -> None:
    page = ocr_page("HALLER")
    assert strict_match("haller", page) == (page.tokens[0].box,)


def test_strict_match_empty_query_raises() -> None:
    with pytest.raises(ValueError, match="Query must contain text"):
        strict_match("   ", ocr_page("Haller"))


def test_prepare_mention_drops_editorial_markup() -> None:
    assert prepare_mention("... Herrenschwand v. Grain, der Arz. Dr.") == (
        "Herrenschwand v. Grain, der Arz. Dr."
    )
    assert prepare_mention(
        "*V. B. Tscharner von Bellevue (=Mitglied der engern Gesellschaft)"
    ) == "V. B. Tscharner von Bellevue"
    assert prepare_mention("Bourgelaz in Lyon u.[s.w.]") == "Bourgelaz in Lyon"
    assert prepare_mention(
        "Walomont in Geldern [frz.: de Malomont, en Gueldres]"
    ) == "Walomont in Geldern"
    assert prepare_mention("Matthey in Tuerin[?]") == "Matthey in Tuerin"


def test_lenient_match_ignores_a_trailing_period() -> None:
    page = ocr_page("C.", "Em.", "von", "Bonstetten,", "in", "1761.")
    matches = lenient_match("C. Em. von Bonstetten, in 1761", page)
    assert matches == (BoundingBox.enclosing(tuple(token.box for token in page.tokens)),)


def test_lenient_match_skips_punctuation_only_tokens() -> None:
    page = ocr_page("Sam.", "Gruner", "v.", "Worlauffcn", "/", "des", "gr.", "R.")
    matches = lenient_match("Sam. Gruner v. Worlauffen, des gr. R.", page)
    assert len(matches) == 1
    assert matches[0] == BoundingBox.enclosing(
        tuple(token.box for token in page.tokens if token.text != "/")
    )


def test_lenient_match_allows_a_small_ocr_substitution() -> None:
    page = ocr_page("Dan.", "Bernoulli,", "zu", "Bafel.")
    assert lenient_match("Dan. Bernoulli, zu Basel", page) != ()
    page = ocr_page("Em.", "von", "Grassenried,", "zu", "Word.")
    assert lenient_match("Em. von Graffenried, zu Worb", page) != ()


def test_lenient_match_does_not_expand_v_to_von() -> None:
    assert lenient_match("Gruner v. Worlauffen", ocr_page("Gruner", "von", "Worlauffen")) == ()
    assert lenient_match("Gruner von Worlauffen", ocr_page("Gruner", "v.", "Worlauffen")) == ()


def test_lenient_match_does_not_fuzzy_match_short_tokens() -> None:
    assert lenient_match("in Bern", ocr_page("im", "Bern")) == ()


def test_lenient_match_rejects_a_large_edit() -> None:
    assert lenient_match("zu Losane", ocr_page("zu", "Losimc")) == ()


def test_lenient_match_empty_after_markup_raises() -> None:
    with pytest.raises(ValueError, match="Query must contain text"):
        lenient_match("... (*=Mitglied der engern Gesellschaft)", ocr_page("Haller"))
