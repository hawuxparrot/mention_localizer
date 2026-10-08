import pytest

from eil.ocr import OCR_MARKERS, parse_ocr_text
from tests.helpers import data_dir, make_page, parse_corpus_file

COLLECTIONS = [
    "1761_002",
    "1761_002 2",
    "1762_003",
    "1762_003 2",
    "1763_004",
    "1763_004 2",
    "1764_005",
    "1764_005 2",
    "1765_006",
    "1765_006 2",
    "1766_007",
    "1766_007 2",
    "1767_008",
    "1767_008 2",
    "1769_010",
    "1769_010 2",
    "1770_011",
    "1771_012",
    "1779_001",
]


def test_vorerinnerung_page_parses_known_header_and_tokens() -> None:
    page = parse_corpus_file("1769_010", "oeg-002_1769_010_0269.txt")

    assert (page.width, page.height) == (1062, 1815)
    assert page.tokens[0].text == "Vorerinnerung"
    assert page.tokens[0].box.x == 182
    assert page.tokens[-1].text == "-5"
    assert all(token.text not in OCR_MARKERS for token in page.tokens)
    assert all(token.confidence is None for token in page.tokens)


def test_oeg001_page_keeps_comma_inside_token_text() -> None:
    page = parse_corpus_file("1761_002", "oeg-001_1761_002_0890.txt")

    assert (page.width, page.height) == (1034, 1780)
    comma_tokens = [token for token in page.tokens if token.text == "9,7"]
    assert len(comma_tokens) == 1
    assert comma_tokens[0].box.x == 798


def test_oeg001_page_keeps_punctuation_only_token() -> None:
    page = parse_corpus_file("1761_002", "oeg-001_1761_002_0136.txt")
    token = next(token for token in page.tokens if token.text == ",«,0")
    assert (token.box.x, token.box.y) == (609, 878)


def test_oeg003_title_page_parses() -> None:
    page = parse_corpus_file("1779_001", "oeg-003_1779_001_0218.txt")

    assert (page.width, page.height) == (987, 1684)
    assert page.tokens[0].text == "IV."
    assert "Bescheidene" in {token.text for token in page.tokens}


def test_soe_french_page_parses_apostrophe_and_punctuation_tokens() -> None:
    page = parse_corpus_file("1769_010 2", "soe-001_1769_010_0415.txt")

    assert (page.width, page.height) == (968, 1680)
    texts = [token.text for token in page.tokens]
    assert texts[:3] == ["DES", "PAQUIERS", "COMMUNS-"]
    assert "qu'il" in texts
    assert ";" in texts


def test_ocr_dimensions_are_not_replaced_by_iiif_size() -> None:
    iiif_page = make_page(width=1286, height=2124)
    page = parse_corpus_file(
        "1769_010",
        "oeg-002_1769_010_0269.txt",
        page=iiif_page,
    )
    assert (page.width, page.height) == (1062, 1815)
    assert (page.page.width, page.page.height) == (1286, 2124)


@pytest.mark.parametrize("collection", COLLECTIONS)
def test_one_file_from_each_collection_parses(collection: str) -> None:
    files = sorted((data_dir() / collection).glob("*.txt"))
    if not files:
        pytest.skip(f"no OCR files in {collection}")

    page = parse_ocr_text(files[0].read_text(encoding="utf-8"), make_page())
    assert page.width > 0
    assert page.height > 0
    assert all(token.box.width > 0 and token.box.height > 0 for token in page.tokens)


def test_all_files_in_vorerinnerung_volume_parse() -> None:
    files = sorted((data_dir() / "1769_010").glob("*.txt"))
    assert files
    for path in files:
        page = parse_ocr_text(path.read_text(encoding="utf-8"), make_page())
        assert page.width > 0
        assert page.height > 0
