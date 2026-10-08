from eil.localize import find_image_regions
from eil.models import BoundingBox, ImageRegion, OcrPage, OcrToken, PageImage


def _page(url: str, width: int = 200, height: int = 100) -> PageImage:
    return PageImage(image_service_url=url, width=width, height=height)


def _ocr(page: PageImage, *tokens: tuple[str, int]) -> OcrPage:
    return OcrPage(
        page=page,
        tokens=tuple(
            OcrToken(text=text, box=BoundingBox(x=x, y=0, width=10, height=10))
            for text, x in tokens
        ),
        width=100,
        height=50,
    )


def _scaled(x: int) -> BoundingBox:
    """OCR box (x, 0, 10, 10) on a 100x50 page shown at 200x100."""
    return BoundingBox(x=x * 2, y=0, width=20, height=20)


def test_zero_matches_across_the_manifest() -> None:
    pages = (
        _ocr(_page("https://iiif.example.org/a.jpg"), ("Haller", 0)),
        _ocr(_page("https://iiif.example.org/b.jpg"), ("aus", 10), ("Bern", 20)),
    )
    assert find_image_regions("Euler", pages) == ()


def test_exactly_one_match_is_scaled_into_iiif_coordinates() -> None:
    page = _page("https://iiif.example.org/a.jpg")
    regions = find_image_regions("Haller", (_ocr(page, ("Haller", 10), ("aus", 30)),))
    assert regions == (
        ImageRegion(page=page, box=_scaled(10)),
    )


def test_multiple_matches_on_one_page_keep_token_order() -> None:
    page = _page("https://iiif.example.org/a.jpg")
    regions = find_image_regions(
        "von Haller",
        (
            _ocr(
                page,
                ("von", 0),
                ("Haller", 10),
                ("und", 20),
                ("von", 40),
                ("Haller", 50),
            ),
        ),
    )
    assert [region.box for region in regions] == [
        BoundingBox(x=0, y=0, width=40, height=20),
        BoundingBox(x=80, y=0, width=40, height=20),
    ]
    assert all(region.page is page for region in regions)


def test_matches_on_later_pages_do_not_precede_the_earliest_page() -> None:
    early = _page("https://iiif.example.org/early.jpg")
    late = _page("https://iiif.example.org/late.jpg")
    regions = find_image_regions(
        "Haller",
        (
            _ocr(_page("https://iiif.example.org/before.jpg"), ("other", 0)),
            _ocr(early, ("Haller", 10), ("Haller", 40)),
            _ocr(late, ("Haller", 5)),
        ),
    )
    assert len(regions) == 3
    assert regions[0] == ImageRegion(page=early, box=_scaled(10))
    assert regions[1] == ImageRegion(page=early, box=_scaled(40))
    assert regions[2] == ImageRegion(page=late, box=_scaled(5))
