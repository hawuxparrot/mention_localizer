"""
Contains parsing logic for IIIF Presentation 3 manifests.
parse_manifest()
"""
from typing import Any

from .models import ManifestDocument, PageImage

IMAGE_SERVICE_TYPES = frozenset({"ImageService2", "ImageService3"})


class IiifParseError(ValueError):
    """Raised when a IIIF Manifest does not match the expected structure."""


def parse_manifest(raw: dict[str, Any]) -> ManifestDocument:
    """Parse a IIIF Presentation 3 Manifest into ordered PageImage objects.

    A valid Manifest with no Canvases returns an empty pages tuple.

    Raises:
        IiifParseError: If required Manifest, Canvas, painting image, or
            image-service data is missing, invalid, or ambiguous.
    """
    manifest_id = raw.get("id")
    if not isinstance(manifest_id, str) or not manifest_id.strip():
        raise IiifParseError("Manifest is missing required non-empty 'id'")

    if "items" not in raw:
        raise IiifParseError("Manifest is missing required 'items' list")
    items = raw["items"]
    if not isinstance(items, list):
        raise IiifParseError(
            f"Manifest 'items' must be a list, got {type(items).__name__}"
        )

    pages: list[PageImage] = []
    for index, canvas in enumerate(items):
        pages.append(_parse_canvas(canvas, index))

    return ManifestDocument(
        manifest_id=manifest_id.strip(),
        pages=tuple(pages),
    )


def _parse_canvas(canvas: object, index: int) -> PageImage:
    if not isinstance(canvas, dict):
        raise IiifParseError(
            f"Manifest item {index} must be a Canvas object, "
            f"got {type(canvas).__name__}"
        )

    canvas_type = canvas.get("type")
    if canvas_type != "Canvas":
        raise IiifParseError(
            f"Manifest item {index} must have type 'Canvas', got {canvas_type!r}"
        )

    if "items" not in canvas:
        raise IiifParseError(
            f"Canvas {index} is missing required 'items' list"
        )
    annotation_pages = canvas["items"]
    if not isinstance(annotation_pages, list):
        raise IiifParseError(
            f"Canvas {index} 'items' must be a list, "
            f"got {type(annotation_pages).__name__}"
        )

    image_bodies = _painting_image_bodies(annotation_pages, index)
    if not image_bodies:
        raise IiifParseError(
            f"Canvas {index} has no painting Image annotation"
        )
    if len(image_bodies) > 1:
        raise IiifParseError(
            f"Canvas {index} has {len(image_bodies)} painting images; "
            f"expected exactly one"
        )

    body = image_bodies[0]
    return PageImage(
        image_service_url=_image_service_url(body, index),
        width=_positive_int(body.get("width"), f"Canvas {index} image width"),
        height=_positive_int(body.get("height"), f"Canvas {index} image height"),
    )


def _painting_image_bodies(
    annotation_pages: list[object],
    canvas_index: int,
) -> list[dict[str, Any]]:
    bodies: list[dict[str, Any]] = []
    for page_index, annotation_page in enumerate(annotation_pages):
        if not isinstance(annotation_page, dict):
            raise IiifParseError(
                f"Canvas {canvas_index} item {page_index} must be an object, "
                f"got {type(annotation_page).__name__}"
            )
        if annotation_page.get("type") != "AnnotationPage":
            raise IiifParseError(
                f"Canvas {canvas_index} item {page_index} must be an "
                f"AnnotationPage, got {annotation_page.get('type')!r}"
            )

        annotations = annotation_page.get("items")
        if not isinstance(annotations, list):
            raise IiifParseError(
                f"Canvas {canvas_index} AnnotationPage {page_index} "
                f"'items' must be a list, got {type(annotations).__name__}"
            )

        for annotation in annotations:
            if not isinstance(annotation, dict):
                raise IiifParseError(
                    f"Canvas {canvas_index} AnnotationPage {page_index} "
                    f"contains a non-object annotation"
                )
            if not _is_painting(annotation):
                continue
            body = annotation.get("body")
            if not _is_image_body(body):
                raise IiifParseError(
                    f"Canvas {canvas_index} painting annotation is missing "
                    f"an Image body"
                )
            bodies.append(body)
    return bodies


def _is_painting(annotation: dict[str, Any]) -> bool:
    motivation = annotation.get("motivation")
    if motivation == "painting":
        return True
    return isinstance(motivation, list) and "painting" in motivation


def _is_image_body(body: object) -> bool:
    if not isinstance(body, dict):
        return False
    return (body.get("type") or body.get("@type")) == "Image"


def _image_service_url(body: dict[str, Any], canvas_index: int) -> str:
    service = body.get("service")
    if isinstance(service, dict):
        service = [service]
    if not isinstance(service, list):
        raise IiifParseError(
            f"Canvas {canvas_index} image is missing an image service URL"
        )

    urls: list[str] = []
    for entry in service:
        if not isinstance(entry, dict):
            continue
        service_type = entry.get("type") or entry.get("@type")
        if service_type not in IMAGE_SERVICE_TYPES:
            continue
        url = entry.get("id") or entry.get("@id")
        if isinstance(url, str) and url.strip():
            urls.append(url.strip())

    if not urls:
        raise IiifParseError(
            f"Canvas {canvas_index} image is missing an image service URL"
        )
    if len(urls) > 1:
        raise IiifParseError(
            f"Canvas {canvas_index} image has {len(urls)} image services; "
            f"expected exactly one"
        )
    return urls[0]


def _positive_int(value: object, what: str) -> int:
    if type(value) is not int or value <= 0:
        raise IiifParseError(
            f"{what} must be a positive integer, got {value!r}"
        )
    return value
