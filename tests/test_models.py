from dataclasses import FrozenInstanceError

import pytest

from eil.models import BoundingBox, ImageRegion, ManifestDocument, PageImage


def test_bounding_box_rejects_zero_width() -> None:
    with pytest.raises(ValueError, match="width must be positive"):
        BoundingBox(x=0, y=0, width=0, height=10)


def test_bounding_box_rejects_zero_height() -> None:
    with pytest.raises(ValueError, match="height must be positive"):
        BoundingBox(x=0, y=0, width=10, height=0)


def test_bounding_box_rejects_negative_width() -> None:
    with pytest.raises(ValueError, match="width must be positive"):
        BoundingBox(x=0, y=0, width=-1, height=10)


def test_bounding_box_rejects_negative_height() -> None:
    with pytest.raises(ValueError, match="height must be positive"):
        BoundingBox(x=0, y=0, width=10, height=-4)


def test_bounding_box_rejects_negative_x() -> None:
    with pytest.raises(ValueError, match="x must be non-negative"):
        BoundingBox(x=-1, y=0, width=10, height=10)


def test_bounding_box_rejects_negative_y() -> None:
    with pytest.raises(ValueError, match="y must be non-negative"):
        BoundingBox(x=0, y=-1, width=10, height=10)


def test_bounding_box_accepts_origin_with_positive_size() -> None:
    box = BoundingBox(x=0, y=0, width=1, height=1)
    assert (box.x, box.y, box.width, box.height) == (0, 0, 1, 1)


def test_enclosing_single_box_is_itself() -> None:
    box = BoundingBox(x=4, y=8, width=10, height=6)
    assert BoundingBox.enclosing((box,)) == box


def test_enclosing_union_of_two_boxes() -> None:
    left = BoundingBox(x=10, y=20, width=5, height=5)
    right = BoundingBox(x=30, y=15, width=10, height=20)
    assert BoundingBox.enclosing((left, right)) == BoundingBox(
        x=10, y=15, width=30, height=20
    )


def test_enclosing_empty_raises() -> None:
    with pytest.raises(ValueError, match="Cannot enclose zero bounding boxes"):
        BoundingBox.enclosing(())


def test_page_image_does_not_carry_ocr_tokens() -> None:
    page = PageImage(
        image_service_url="https://iiif.example.org/image",
        width=1286,
        height=2124,
    )
    assert not hasattr(page, "ocr_tokens")
    assert not hasattr(page, "label")


def test_image_region_stores_page_and_iiif_box() -> None:
    page = PageImage("https://iiif.example.org/image", 10, 20)
    box = BoundingBox(1, 2, 3, 4)
    region = ImageRegion(page=page, box=box)
    assert region.page is page
    assert region.box == box
    with pytest.raises(FrozenInstanceError):
        region.box = BoundingBox(0, 0, 1, 1)  # type: ignore[misc]


def test_manifest_document_preserves_page_order() -> None:
    first = PageImage("https://iiif.example.org/a", 1, 2)
    second = PageImage("https://iiif.example.org/b", 3, 4)
    document = ManifestDocument("https://example.org/manifest", (first, second))
    assert document.pages == (first, second)
    assert not hasattr(document, "label")
