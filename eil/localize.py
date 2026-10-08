"""
Manifest-level mention matching.
find_image_regions()
"""
from typing import Sequence

from .geometry import scale_box_to_iiif
from .matching import lenient_match
from .models import ImageRegion, OcrPage


def find_image_regions(
    mention: str,
    ocr_pages: Sequence[OcrPage],
) -> tuple[ImageRegion, ...]:
    """Return every lenient hit of ``mention``, in selection order.

    Pages are searched in the order given, which is manifest canvas order.
    Within a page, hits keep the order returned by ``lenient_match``
    (OCR token order). The first region is therefore the earliest page's
    earliest token hit. Every box is in that page's IIIF coordinates.
    """
    regions: list[ImageRegion] = []
    for ocr_page in ocr_pages:
        for box in lenient_match(mention, ocr_page):
            regions.append(
                ImageRegion(
                    page=ocr_page.page,
                    box=scale_box_to_iiif(box, ocr_page),
                )
            )
    return tuple(regions)
