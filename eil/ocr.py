"""
Contains parsing logic for supplied positional OCR .txt files.
parse_ocr_text()
"""
from .models import BoundingBox, OcrPage, OcrToken, PageImage

OCR_MARKERS = frozenset({"<EOS>", "<EOP>"})


class OcrParseError(ValueError):
    """Raised when an OCR .txt file does not match the expected format."""


def parse_ocr_text(raw: str, page: PageImage) -> OcrPage:
    """Parse positional OCR text into ordered tokens for `page`.

    Skips blank lines and `<EOS>`/`<EOP>` markers. A valid file with no
    tokens returns an empty tuple. This format does not supply confidence
    or layout ids, so those fields are left as None.

    Stored width/height are the OCR-file coordinate space. They are not
    compared to or scaled into `page.width` / `page.height`.

    Raises:
        OcrParseError: If the input is empty or a line is malformed.
    """
    lines = raw.splitlines()
    if not lines:
        raise OcrParseError("OCR text is empty")

    width, height = _parse_page_dimensions(lines[0].strip(), line_number=1)

    tokens: list[OcrToken] = []
    for line_number, line in enumerate(lines[1:], start=2):
        stripped = line.strip()
        if not stripped or stripped in OCR_MARKERS:
            continue
        tokens.append(_parse_ocr_token_line(stripped, line_number))

    return OcrPage(page=page, tokens=tuple(tokens), width=width, height=height)


def _parse_page_dimensions(line: str, line_number: int) -> tuple[int, int]:
    """Parse a first-line page size of the form `width,height`."""
    parts = line.split(",")
    if " " in line or len(parts) != 2:
        raise OcrParseError(
            f"OCR line {line_number}: expected page dimensions 'width,height', "
            f"got {line!r}"
        )
    try:
        width, height = int(parts[0]), int(parts[1])
    except ValueError:
        raise OcrParseError(
            f"OCR line {line_number}: expected page dimensions 'width,height', "
            f"got {line!r}"
        ) from None
    if width <= 0 or height <= 0:
        raise OcrParseError(
            f"OCR line {line_number}: page dimensions must be positive, "
            f"got {width},{height}"
        )
    return width, height


def _parse_ocr_token_line(line: str, line_number: int) -> OcrToken:
    """Parse `text x,y,width,height`. Text is everything before the last space."""
    text, separator, coords = line.rpartition(" ")
    if not separator:
        raise OcrParseError(
            f"OCR line {line_number}: expected 'text x,y,width,height', "
            f"got {line!r}"
        )
    if not text:
        raise OcrParseError(
            f"OCR line {line_number}: missing token text before bounding box"
        )

    parts = coords.split(",")
    if len(parts) != 4:
        raise OcrParseError(
            f"OCR line {line_number}: bounding box must be four integers, "
            f"got {coords!r}"
        )
    try:
        x, y, width, height = (int(part) for part in parts)
    except ValueError:
        raise OcrParseError(
            f"OCR line {line_number}: bounding box must be four integers, "
            f"got {coords!r}"
        ) from None

    try:
        box = BoundingBox(x=x, y=y, width=width, height=height)
    except ValueError as exc:
        raise OcrParseError(
            f"OCR line {line_number}: invalid bounding box "
            f"({x},{y},{width},{height})"
        ) from exc

    return OcrToken(
        text=text,
        box=box,
        confidence=None,
        blockId=None,
        paragraphId=None,
        lineId=None,
    )
