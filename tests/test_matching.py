import pytest

from eil.matching import normalize_text, strict_match
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
