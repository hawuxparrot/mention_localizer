from eil.models import BoundingBox, ImageRegion, PageImage
from eil.targets import MEDIA_FRAGMENTS, crop_url, precise_target


def test_precise_target_matches_the_readme_shape() -> None:
    service = "https://iiif.example.org/iiif/2/book!oeg-003_1785_003_0015.jpg"
    region = ImageRegion(
        page=PageImage(image_service_url=service, width=1286, height=2124),
        box=BoundingBox(x=108, y=1235, width=646, height=64),
    )

    assert precise_target(region) == {
        "rendering": [
            {
                "format": "image/jpeg",
                "type": "Image",
                "id": (
                    f"{service}/108,1235,646,64/full/0/default.jpg"
                ),
            }
        ],
        "rdlRegion": "main",
        "source": service,
        "selector": {
            "conformsTo": MEDIA_FRAGMENTS,
            "value": "xywh=108,1235,646,64",
            "type": "FragmentSelector",
        },
    }
    assert crop_url(region).endswith("/108,1235,646,64/full/0/default.jpg")
