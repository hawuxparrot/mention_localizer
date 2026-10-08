import math

import pytest

from eil.geometry import scale_box_to_iiif
from eil.models import BoundingBox, OcrPage, OcrToken
from tests.helpers import make_page


def _page(box: BoundingBox, *, ocr_size: tuple[int, int], iiif_size: tuple[int, int]):
    width, height = iiif_size
    ocr_width, ocr_height = ocr_size
    page = make_page(width=width, height=height)
    token = OcrToken(text="Haller", box=box)
    return OcrPage(page=page, tokens=(token,), width=ocr_width, height=ocr_height)


def test_scale_box_uses_independent_axis_factors() -> None:
    ocr_page = _page(
        BoundingBox(x=3, y=40, width=4, height=10),
        ocr_size=(10, 100),
        iiif_size=(20, 100),
    )
    assert scale_box_to_iiif(ocr_page.tokens[0].box, ocr_page) == BoundingBox(
        x=6, y=40, width=8, height=10
    )


def test_scale_box_rounds_each_component_half_up() -> None:
    # 1 * 3/2 = 1.5, which rounds half up to 2. Scaling width on its own
    # stays 2; rounding the far corner instead would leave a width of 1.
    ocr_page = _page(
        BoundingBox(x=1, y=0, width=1, height=1),
        ocr_size=(2, 1),
        iiif_size=(3, 1),
    )
    assert scale_box_to_iiif(ocr_page.tokens[0].box, ocr_page) == BoundingBox(
        x=2, y=0, width=2, height=1
    )


def test_scale_box_maps_a_real_ocr_size_onto_iiif_pixels() -> None:
    ocr_page = _page(
        BoundingBox(x=182, y=304, width=532, height=89),
        ocr_size=(1062, 1815),
        iiif_size=(1286, 2124),
    )
    assert scale_box_to_iiif(ocr_page.tokens[0].box, ocr_page) == BoundingBox(
        x=220, y=356, width=644, height=104
    )


def test_scaled_width_and_height_stay_positive() -> None:
    ocr_page = _page(
        BoundingBox(x=4, y=4, width=4, height=4),
        ocr_size=(100, 100),
        iiif_size=(10, 10),
    )
    scaled = scale_box_to_iiif(ocr_page.tokens[0].box, ocr_page)
    assert scaled == BoundingBox(x=0, y=0, width=1, height=1)
    assert scaled.width > 0 and scaled.height > 0


def test_identical_coordinate_spaces_are_unchanged() -> None:
    box = BoundingBox(x=8, y=9, width=10, height=11)
    ocr_page = _page(box, ocr_size=(1286, 2124), iiif_size=(1286, 2124))
    assert scale_box_to_iiif(box, ocr_page) == box


def test_half_up_matches_floor_of_value_plus_one_half() -> None:
    ocr_page = _page(
        BoundingBox(x=182, y=304, width=532, height=89),
        ocr_size=(1062, 1815),
        iiif_size=(1286, 2124),
    )
    scaled = scale_box_to_iiif(ocr_page.tokens[0].box, ocr_page)
    scale_x = 1286 / 1062
    scale_y = 2124 / 1815
    assert scaled.x == int(math.floor(182 * scale_x + 0.5))
    assert scaled.y == int(math.floor(304 * scale_y + 0.5))


def test_non_positive_ocr_dimensions_raise() -> None:
    ocr_page = OcrPage(page=make_page(), tokens=(), width=0, height=10)
    with pytest.raises(ValueError, match="OCR page dimensions must be positive"):
        scale_box_to_iiif(BoundingBox(0, 0, 1, 1), ocr_page)
