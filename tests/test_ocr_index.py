import pytest

from eil.models import PageImage
from eil.ocr_index import (
    OcrResolutionError,
    index_ocr_directory,
    page_image_stem,
    resolve_ocr_path,
)


def _page(url: str) -> PageImage:
    return PageImage(image_service_url=url, width=10, height=20)


def test_page_image_stem_uses_eperiodica_filename() -> None:
    page = _page(
        "https://iiif.library.ethz.ch/iiif/2/"
        "e-periodica!oeg!1765_006!oeg-002_1765_006_0038.jpg"
    )
    assert page_image_stem(page) == "oeg-002_1765_006_0038"


def test_page_image_stem_keeps_hyphenated_plate_names() -> None:
    page = _page(
        "https://iiif.example.org/iiif/2/book!oeg-001_1761_002_0589-09.jpg"
    )
    assert page_image_stem(page) == "oeg-001_1761_002_0589-09"


def test_page_image_stem_decodes_percent_encoded_separator() -> None:
    page = _page(
        "https://iiif.example.org/iiif/2/"
        "e-periodica%21oeg%211765_006%21oeg-002_1765_006_0039.jpg"
    )
    assert page_image_stem(page) == "oeg-002_1765_006_0039"


def test_index_resolves_nested_file_by_stem(tmp_path) -> None:
    target = tmp_path / "1765_006" / "oeg-002_1765_006_0039.txt"
    target.parent.mkdir()
    target.write_text("10,20\nHaller 1,2,3,4\n", encoding="utf-8")
    other = tmp_path / "1765_006" / "oeg-002_1765_006_0038.txt"
    other.write_text("10,20\n", encoding="utf-8")

    index = index_ocr_directory(tmp_path)
    page = _page(
        "https://iiif.example.org/iiif/2/book!oeg-002_1765_006_0039.jpg"
    )
    assert resolve_ocr_path(page, index) == target


def test_missing_ocr_file_is_reported(tmp_path) -> None:
    present = tmp_path / "other.txt"
    present.write_text("10,20\n", encoding="utf-8")
    index = index_ocr_directory(tmp_path)
    page = _page("https://iiif.example.org/iiif/2/book!missing-page.jpg")

    with pytest.raises(OcrResolutionError, match="missing-page"):
        resolve_ocr_path(page, index)


def test_duplicate_stems_are_not_collapsed(tmp_path) -> None:
    first = tmp_path / "a" / "page.txt"
    second = tmp_path / "b" / "page.txt"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_text("1,1\n", encoding="utf-8")
    second.write_text("2,2\n", encoding="utf-8")

    with pytest.raises(OcrResolutionError, match="Ambiguous OCR files") as caught:
        index_ocr_directory(tmp_path)
    message = str(caught.value)
    assert "page:" in message
    assert str(first) in message
    assert str(second) in message


def test_macos_metadata_does_not_make_a_stem_ambiguous(tmp_path) -> None:
    real = tmp_path / "1765_006" / "oeg-002_1765_006_0038.txt"
    junk = tmp_path / "__MACOSX" / "oeg-002_1765_006_0038.txt"
    real.parent.mkdir()
    junk.parent.mkdir()
    real.write_text("10,20\n", encoding="utf-8")
    junk.write_text("10,20\n", encoding="utf-8")

    index = index_ocr_directory(tmp_path)
    page = _page("https://iiif.example.org/iiif/2/book!oeg-002_1765_006_0038.jpg")
    assert resolve_ocr_path(page, index) == real


def test_missing_data_directory_is_reported(tmp_path) -> None:
    missing = tmp_path / "nope"
    with pytest.raises(OcrResolutionError, match="does not exist"):
        index_ocr_directory(missing)
