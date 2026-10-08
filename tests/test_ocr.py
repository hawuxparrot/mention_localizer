import pytest

from eil.ocr import OcrParseError, parse_ocr_text
from tests.helpers import make_page


def test_parse_ocr_text_reads_tokens_and_skips_markers() -> None:
    raw = "\n".join(
        [
            "1062,1815",
            "Vorerinnerung 182,304,532,89",
            "<EOS>",
            "<EOP>",
            "wir 185,524,65,42",
            "",
            "wegen 281,533,116,44",
        ]
    )
    page = parse_ocr_text(raw, make_page())
    assert [token.text for token in page.tokens] == [
        "Vorerinnerung",
        "wir",
        "wegen",
    ]
    assert page.tokens[1].box.x == 185
    assert page.tokens[1].confidence is None
    assert page.tokens[1].lineId is None


def test_parse_ocr_text_preserves_ocr_dimensions_separately_from_iiif() -> None:
    page_image = make_page(width=1286, height=2124)
    ocr_page = parse_ocr_text("1062,1815\nwir 185,524,65,42\n", page_image)

    assert ocr_page.width == 1062
    assert ocr_page.height == 1815
    assert ocr_page.page.width == 1286
    assert ocr_page.page.height == 2124


def test_parse_ocr_text_empty_tokens_still_keep_dimensions() -> None:
    ocr_page = parse_ocr_text("1062,1815\n<EOS>\n", make_page())
    assert ocr_page.tokens == ()
    assert (ocr_page.width, ocr_page.height) == (1062, 1815)


def test_token_text_may_contain_commas() -> None:
    ocr_page = parse_ocr_text("100,200\n9,7 798,74,57,28\n", make_page())
    assert ocr_page.tokens[0].text == "9,7"
    assert (ocr_page.tokens[0].box.x, ocr_page.tokens[0].box.y) == (798, 74)


def test_token_text_may_contain_spaces() -> None:
    ocr_page = parse_ocr_text(
        "100,200\nJohann Caspar 182,304,532,89\n",
        make_page(),
    )
    assert ocr_page.tokens[0].text == "Johann Caspar"


def test_empty_input_raises() -> None:
    with pytest.raises(OcrParseError, match="OCR text is empty"):
        parse_ocr_text("", make_page())


def test_missing_page_dimensions_raises() -> None:
    with pytest.raises(OcrParseError, match="expected page dimensions"):
        parse_ocr_text("wir 185,524,65,42\n", make_page())


def test_zero_page_dimensions_raise() -> None:
    with pytest.raises(OcrParseError, match="must be positive"):
        parse_ocr_text("0,1815\nwir 1,2,3,4\n", make_page())


def test_token_without_bbox_raises() -> None:
    with pytest.raises(OcrParseError, match="expected 'text x,y,width,height'"):
        parse_ocr_text("100,200\nnotabox\n", make_page())


def test_zero_width_token_box_raises() -> None:
    with pytest.raises(OcrParseError, match="invalid bounding box"):
        parse_ocr_text("100,200\nwir 1,2,0,4\n", make_page())
