"""
Contains domain types shared across the Entity Image Localization tool:
- BoundingBox
- OcrToken
- OcrPage
- PageImage
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
        if self.width < 0:
            raise ValueError("width must be non-negative")
        if self.height < 0:
            raise ValueError("height must be non-negative")

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
    """
    Represents a page image in a IIIF manifest. Contains information needed to identify the image and its OCR tokens.
    """
    image_id: str
    label: str
    ocr_tokens: tuple[OcrToken, ...]

@dataclass(frozen=True)
class OcrPage:
    """OCR tokens for one page, in reading order."""
    page: PageImage
    tokens: tuple[OcrToken, ...]


@dataclass(frozen=True)
class EntityAnnotation:
    """
    Represents an entity annotation. Contains information needed to identify entity mention and query OCR.
    """
    annotation_id: str
    entity_id: str
    mention: str
    target_manifest: str

@dataclass(frozen=True)
class ManifestDocument:
    """
    Represents a IIIF manifest document. Contains information needed to identify the manifest and its images.
    """
    manifest_id: str
    label: str
    pages: tuple[PageImage]



    