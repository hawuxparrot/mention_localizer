"""
Build a precise IIIF target from an ImageRegion.
crop_url()
precise_target()
"""
from typing import Any

from .models import ImageRegion

MEDIA_FRAGMENTS = "http://www.w3.org/TR/media-frags/"


def crop_url(region: ImageRegion) -> str:
    """IIIF Image API 2 region URL for ``region`` in IIIF pixels."""
    box = region.box
    service = region.page.image_service_url.rstrip("/")
    return (
        f"{service}/{box.x},{box.y},{box.width},{box.height}/full/0/default.jpg"
    )


def precise_target(region: ImageRegion) -> dict[str, Any]:
    """Web Annotation target for one IIIF image region.

    The shape matches the fragment-selector target in the project README.
    ``region.box`` is written through as IIIF pixels; this function does
    not interpret OCR coordinates.
    """
    box = region.box
    return {
        "rendering": [
            {
                "format": "image/jpeg",
                "type": "Image",
                "id": crop_url(region),
            }
        ],
        "rdlRegion": "main",
        "source": region.page.image_service_url,
        "selector": {
            "conformsTo": MEDIA_FRAGMENTS,
            "value": f"xywh={box.x},{box.y},{box.width},{box.height}",
            "type": "FragmentSelector",
        },
    }
