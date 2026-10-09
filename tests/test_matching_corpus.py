from eil.matching import lenient_match, strict_match
from eil.models import BoundingBox
from tests.helpers import parse_corpus_file


def test_unique_mention_on_vorerinnerung_page() -> None:
    page = parse_corpus_file("1769_010", "oeg-002_1769_010_0269.txt")
    matches = strict_match("Vorerinnerung", page)

    assert matches == (BoundingBox(x=182, y=304, width=532, height=89),)


def test_multi_token_mention_uses_enclosing_box() -> None:
    page = parse_corpus_file("1769_010", "oeg-002_1769_010_0269.txt")
    matches = strict_match("wir wegen", page)

    assert matches == (BoundingBox(x=185, y=524, width=212, height=53),)


def test_repeated_token_is_ambiguous() -> None:
    page = parse_corpus_file("1769_010", "oeg-002_1769_010_0269.txt")
    matches = strict_match("wir", page)

    assert matches == (
        BoundingBox(x=185, y=524, width=65, height=42),
        BoundingBox(x=137, y=799, width=65, height=42),
    )


def test_missing_mention_on_real_page_returns_empty() -> None:
    page = parse_corpus_file("1769_010", "oeg-002_1769_010_0269.txt")
    assert strict_match("Euler", page) == ()


def test_french_page_matches_apostrophe_token() -> None:
    page = parse_corpus_file("1769_010 2", "soe-001_1769_010_0415.txt")
    matches = strict_match("qu'il doit", page)

    assert len(matches) >= 1
    assert all(box.width > 0 and box.height > 0 for box in matches)


def test_real_ocr_line_break_marker_is_rejoined() -> None:
    page = parse_corpus_file("1761_002", "oeg-001_1761_002_0004.txt")
    assert lenient_match("des täglichen Rathes", page) != ()


def test_real_ordinary_hyphen_is_not_rejoined() -> None:
    page = parse_corpus_file("1763_004 2", "soe-001_1763_004_0549.txt")
    assert lenient_match("c'eft à", page) != ()


def test_real_ordinary_line_break_hyphen_is_rejoined() -> None:
    page = parse_corpus_file("1761_002", "oeg-001_1761_002_0008.txt")
    assert lenient_match("Franz von Graffenried; Herr zu Gerzensee", page) != ()
