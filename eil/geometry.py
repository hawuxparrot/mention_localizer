"""
Scale OCR bounding boxes into IIIF page coordinates.
scale_box_to_iiif()
"""
import math

from .models import BoundingBox, OcrPage


def scale_box_to_iiif(box: BoundingBox, ocr_page: OcrPage) -> BoundingBox:
    """Map an OCR-coordinate box into the IIIF pixel space of ``ocr_page.page``.

    The two axes are scaled independently:
    ``scale_x = page.width / ocr_page.width``
    ``scale_y = page.height / ocr_page.height``

    Each of ``x``, ``y``, ``width``, and ``height`` is multiplied by its
    axis scale and rounded half up. Width and height are kept at least 1
    so the result is a valid ``BoundingBox``.
    """
    if ocr_page.width <= 0 or ocr_page.height <= 0:
        raise ValueError("OCR page dimensions must be positive")
    page = ocr_page.page
    if page.width <= 0 or page.height <= 0:
        raise ValueError("IIIF page dimensions must be positive")

    scale_x = page.width / ocr_page.width
    scale_y = page.height / ocr_page.height
    return BoundingBox(
        x=_round_half_up(box.x * scale_x),
        y=_round_half_up(box.y * scale_y),
        width=max(1, _round_half_up(box.width * scale_x)),
        height=max(1, _round_half_up(box.height * scale_y)),
    )


def _round_half_up(value: float) -> int:
    if value < 0:
        raise ValueError(f"scaled coordinate must be non-negative, got {value}")
    return int(math.floor(value + 0.5))
