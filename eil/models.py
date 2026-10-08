"""
Contains domain types shared across the Entity Image Localization tool:
- BoundingBox
- OcrToken
- PageImage
- OcrPage
- EntityAnnotation
- ManifestDocument
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class BoundingBox:
    """Axis-aligned rectangle in pixel coordinates: x, y, width, height."""
    x: int
    y: int
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.x < 0:
            raise ValueError("x must be non-negative")
        if self.y < 0:
            raise ValueError("y must be non-negative")
        if self.width <= 0:
            raise ValueError("width must be positive")
        if self.height <= 0:
            raise ValueError("height must be positive")

    @classmethod
    def enclosing(cls, boxes: tuple["BoundingBox", ...]) -> "BoundingBox":
        """Return the smallest box containing all given boxes."""
        if not boxes:
            raise ValueError("Cannot enclose zero bounding boxes")

        min_x = min(box.x for box in boxes)
        min_y = min(box.y for box in boxes)
        max_x = max(box.x + box.width for box in boxes)
        max_y = max(box.y + box.height for box in boxes)

        return cls(
            x=min_x,
            y=min_y,
            width=max_x - min_x,
            height=max_y - min_y,
        )


@dataclass(frozen=True)
class OcrToken:
    """One positional OCR token. confidence and layout ids are optional."""
    text: str
    box: BoundingBox
    confidence: float | None = None
    blockId: int | None = None
    paragraphId: int | None = None
    lineId: int | None = None


@dataclass(frozen=True)
class PageImage:
    """One IIIF source image. width and height are IIIF pixel size, not OCR-file size."""
    image_service_url: str
    width: int
    height: int


@dataclass(frozen=True)
class OcrPage:
    """OCR tokens for one page, in reading order.

    width and height are the OCR-file coordinate space (first line of the
    .txt). They are not assumed equal to page.width / page.height.
    """
    page: PageImage
    tokens: tuple[OcrToken, ...]
    width: int
    height: int


@dataclass(frozen=True)
class EntityAnnotation:
    """Entity mention plus the coarse IIIF manifest it targets."""
    annotation_id: str
    entity_id: str
    mention: str
    target_manifest: str


@dataclass(frozen=True)
class ManifestDocument:
    """Ordered page images from one IIIF Manifest."""
    manifest_id: str
    pages: tuple[PageImage, ...]
