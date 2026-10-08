from pathlib import Path

import pytest

from eil.models import OcrPage, PageImage
from eil.ocr import parse_ocr_text

DATA_CANDIDATES = (
    Path(__file__).resolve().parents[2] / "data",
    Path(__file__).resolve().parents[1] / "data",
    Path.cwd().parent / "data",
    Path.cwd() / "data",
)


def make_page(
    image_service_url: str = "https://iiif.example.org/image",
    width: int = 1286,
    height: int = 2124,
) -> PageImage:
    return PageImage(
        image_service_url=image_service_url,
        width=width,
        height=height,
    )


def data_dir() -> Path:
    """Return the provided OCR `data/` directory, or skip if it is absent."""
    for path in DATA_CANDIDATES:
        if path.is_dir() and any(path.glob("*/*.txt")):
            return path
    pytest.skip("provided OCR data/ directory not found")


def corpus_path(*parts: str) -> Path:
    path = data_dir().joinpath(*parts)
    if not path.is_file():
        pytest.skip(f"OCR file not found: {path}")
    return path


def parse_corpus_file(*parts: str, page: PageImage | None = None) -> OcrPage:
    path = corpus_path(*parts)
    return parse_ocr_text(path.read_text(encoding="utf-8"), page or make_page())

