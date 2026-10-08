import pytest

from eil.iiif import IiifParseError, parse_manifest


SERVICE_URL = "https://iiif.example.org/iiif/2/page.jpg"
MANIFEST_ID = "https://example.org/iiif/manifest"


def image_body(
    service_id: str = SERVICE_URL,
    width: int = 1286,
    height: int = 2124,
    service: object | None = None,
    **overrides: object,
) -> dict:
    body: dict = {
        "id": f"{service_id}/full/max/0/default.jpg",
        "type": "Image",
        "format": "image/jpeg",
        "width": width,
        "height": height,
        "service": service
        if service is not None
        else [{"@id": service_id, "@type": "ImageService2"}],
    }
    body.update(overrides)
    return body


def painting_annotation(body: dict | None = None) -> dict:
    return {
        "type": "Annotation",
        "motivation": "painting",
        "body": body if body is not None else image_body(),
    }


def annotation_page(*annotations: dict) -> dict:
    return {"type": "AnnotationPage", "items": list(annotations)}


def canvas(
    canvas_id: str = "https://example.org/canvas/1",
    *,
    items: object | None = None,
    body: dict | None = None,
) -> dict:
    result = {
        "id": canvas_id,
        "type": "Canvas",
        "height": 2124,
        "width": 1286,
        "items": items
        if items is not None
        else [annotation_page(painting_annotation(body))],
    }
    return result


def manifest(*canvases: object, manifest_id: object = MANIFEST_ID) -> dict:
    raw: dict = {"type": "Manifest", "items": list(canvases)}
    if manifest_id is not None:
        raw["id"] = manifest_id
    return raw


def test_single_canvas_extracts_service_url_and_source_size() -> None:
    document = parse_manifest(manifest(canvas()))

    assert document.manifest_id == MANIFEST_ID
    assert len(document.pages) == 1
    page = document.pages[0]
    assert page.image_service_url == SERVICE_URL
    assert page.width == 1286
    assert page.height == 2124


def test_multiple_canvases_preserve_order() -> None:
    first = "https://iiif.example.org/iiif/2/first.jpg"
    second = "https://iiif.example.org/iiif/2/second.jpg"
    document = parse_manifest(
        manifest(
            canvas("https://example.org/canvas/1", body=image_body(first, width=10, height=20)),
            canvas("https://example.org/canvas/2", body=image_body(second, width=30, height=40)),
        )
    )

    assert [page.image_service_url for page in document.pages] == [first, second]
    assert (document.pages[0].width, document.pages[0].height) == (10, 20)
    assert (document.pages[1].width, document.pages[1].height) == (30, 40)


def test_empty_items_returns_empty_pages() -> None:
    document = parse_manifest(manifest())
    assert document.pages == ()


def test_missing_manifest_id_raises() -> None:
    with pytest.raises(IiifParseError, match="missing required non-empty 'id'"):
        parse_manifest(manifest(canvas(), manifest_id=None))


def test_empty_manifest_id_raises() -> None:
    with pytest.raises(IiifParseError, match="missing required non-empty 'id'"):
        parse_manifest(manifest(canvas(), manifest_id="  "))


def test_missing_manifest_items_raises() -> None:
    with pytest.raises(IiifParseError, match="missing required 'items' list"):
        parse_manifest({"id": MANIFEST_ID, "type": "Manifest"})


def test_invalid_manifest_items_raises() -> None:
    with pytest.raises(IiifParseError, match="must be a list"):
        parse_manifest({"id": MANIFEST_ID, "items": {"id": "not-a-list"}})


def test_non_object_canvas_raises() -> None:
    with pytest.raises(IiifParseError, match="item 0 must be a Canvas object"):
        parse_manifest(manifest("not-a-canvas"))


def test_missing_canvas_items_raises() -> None:
    raw_canvas = {"id": "https://example.org/canvas/1", "type": "Canvas"}
    with pytest.raises(IiifParseError, match="Canvas 0 is missing required 'items'"):
        parse_manifest(manifest(raw_canvas))


def test_invalid_canvas_items_raises() -> None:
    with pytest.raises(IiifParseError, match="Canvas 0 'items' must be a list"):
        parse_manifest(manifest(canvas(items="not-a-list")))


def test_missing_painting_image_raises() -> None:
    with pytest.raises(IiifParseError, match="no painting Image annotation"):
        parse_manifest(manifest(canvas(items=[annotation_page()])))


def test_non_painting_annotation_is_not_used() -> None:
    other = {
        "type": "Annotation",
        "motivation": "commenting",
        "body": image_body(),
    }
    with pytest.raises(IiifParseError, match="no painting Image annotation"):
        parse_manifest(manifest(canvas(items=[annotation_page(other)])))


def test_ambiguous_painting_images_raise() -> None:
    page = annotation_page(painting_annotation(), painting_annotation())
    with pytest.raises(IiifParseError, match="2 painting images"):
        parse_manifest(manifest(canvas(items=[page])))


def test_missing_image_service_url_raises() -> None:
    body = image_body(service=[])
    with pytest.raises(IiifParseError, match="missing an image service URL"):
        parse_manifest(manifest(canvas(body=body)))


def test_service_without_id_raises() -> None:
    body = image_body(service=[{"@type": "ImageService2"}])
    with pytest.raises(IiifParseError, match="missing an image service URL"):
        parse_manifest(manifest(canvas(body=body)))


def test_iiif3_service_id_is_accepted() -> None:
    body = image_body(
        service=[{"id": SERVICE_URL, "type": "ImageService3"}],
    )
    document = parse_manifest(manifest(canvas(body=body)))
    assert document.pages[0].image_service_url == SERVICE_URL


def test_invalid_image_width_raises() -> None:
    with pytest.raises(IiifParseError, match="image width must be a positive integer"):
        parse_manifest(manifest(canvas(body=image_body(width=0))))


def test_missing_image_height_raises() -> None:
    body = image_body()
    del body["height"]
    with pytest.raises(IiifParseError, match="image height must be a positive integer"):
        parse_manifest(manifest(canvas(body=body)))


def test_non_integer_image_dimension_raises() -> None:
    with pytest.raises(IiifParseError, match="image width must be a positive integer"):
        parse_manifest(manifest(canvas(body=image_body(width="1286"))))
