"""
Resolve a PageImage to its positional OCR .txt file.
page_image_stem()
index_ocr_directory()
resolve_ocr_path()
"""
from pathlib import Path, PurePosixPath
from typing import Mapping
from urllib.parse import unquote, urlsplit

from .models import PageImage

IMAGE_SUFFIXES = frozenset({
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
    ".png",
    ".jp2",
    ".gif",
    ".webp",
})


class OcrResolutionError(ValueError):
    """Raised when a page image has no unique positional OCR file."""


def page_image_stem(page: PageImage) -> str:
    """Return the page filename stem encoded in a IIIF image-service URL.

    e-periodica service ids end in a ``!``-separated image filename, for
    example ``...!oeg-002_1765_006_0038.jpg``. The stem of that filename
    is the OCR file stem. A URL without ``!`` uses its last path segment.
    """
    raw = page.image_service_url.strip()
    if not raw:
        raise OcrResolutionError("Page image has an empty service URL")

    name = unquote(PurePosixPath(urlsplit(raw).path).name)
    if not name:
        raise OcrResolutionError(
            f"Cannot derive an image filename from {page.image_service_url!r}"
        )
    if "!" in name:
        name = name.rsplit("!", 1)[-1]
    if not name:
        raise OcrResolutionError(
            f"Cannot derive an image filename from {page.image_service_url!r}"
        )

    suffix = PurePosixPath(name).suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        return PurePosixPath(name).stem
    return name


def index_ocr_directory(data_dir: Path) -> dict[str, Path]:
    """Map each OCR filename stem to exactly one ``.txt`` path.

    Raises:
        OcrResolutionError: If ``data_dir`` is missing or two files share
            a stem. Duplicate stems are never collapsed to one path.
    """
    root = Path(data_dir)
    if not root.is_dir():
        raise OcrResolutionError(f"OCR data directory does not exist: {root}")

    grouped: dict[str, list[Path]] = {}
    for path in _ocr_files(root):
        grouped.setdefault(path.stem, []).append(path)

    duplicates = sorted(stem for stem, paths in grouped.items() if len(paths) > 1)
    if duplicates:
        details = [
            f"{stem}: {', '.join(str(path) for path in grouped[stem])}"
            for stem in duplicates
        ]
        raise OcrResolutionError(
            "Ambiguous OCR files for stem(s): " + "; ".join(details)
        )
    return {stem: paths[0] for stem, paths in grouped.items()}


def resolve_ocr_path(page: PageImage, ocr_index: Mapping[str, Path]) -> Path:
    """Return the OCR file for ``page``.

    Raises:
        OcrResolutionError: If no indexed file has the page's image stem.
    """
    stem = page_image_stem(page)
    path = ocr_index.get(stem)
    if path is None:
        raise OcrResolutionError(
            f"No OCR file for page image {stem!r} ({page.image_service_url})"
        )
    return path


def _ocr_files(root: Path) -> tuple[Path, ...]:
    files: list[Path] = []
    for path in root.rglob("*.txt"):
        if not path.is_file():
            continue
        if path.name.startswith(".") or path.name.startswith("._"):
            continue
        relative = path.relative_to(root)
        if "__MACOSX" in relative.parts:
            continue
        if path.suffix.lower() != ".txt":
            continue
        files.append(path)
    return tuple(sorted(files))
