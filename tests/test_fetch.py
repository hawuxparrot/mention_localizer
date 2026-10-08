import io
import urllib.error

import pytest

from eil.fetch import FetchError, crop_url_is_image, fetch_json


class _Response:
    def __init__(self, status: int, content_type: str, body: bytes):
        self.status = status
        self.headers = {"Content-Type": content_type}
        self._body = body

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            return self._body
        return self._body[:size]

    def __enter__(self):
        return self

    def __exit__(self, *args) -> bool:
        return False


def test_crop_url_accepts_an_image_response() -> None:
    def opener(request, timeout):
        assert timeout == 30
        return _Response(200, "image/jpeg; charset=binary", b"\xff\xd8\xff")

    assert crop_url_is_image("https://iiif.example.org/crop.jpg", opener=opener)


def test_crop_url_rejects_a_non_image_body() -> None:
    def opener(request, timeout):
        return _Response(200, "text/html", b"<html>missing</html>")

    assert crop_url_is_image("https://iiif.example.org/crop.jpg", opener=opener) is False


def test_crop_url_rejects_an_empty_image() -> None:
    def opener(request, timeout):
        return _Response(200, "image/jpeg", b"")

    assert crop_url_is_image("https://iiif.example.org/crop.jpg", opener=opener) is False


def test_crop_url_rejects_transport_errors() -> None:
    def opener(request, timeout):
        raise urllib.error.URLError("down")

    assert crop_url_is_image("https://iiif.example.org/crop.jpg", opener=opener) is False


def test_fetch_json_returns_an_object() -> None:
    def opener(request, timeout):
        return io.BytesIO(b'{"id": "https://example.org/manifest"}')

    assert fetch_json("https://example.org/manifest", opener=opener) == {
        "id": "https://example.org/manifest"
    }


def test_fetch_json_rejects_a_non_object() -> None:
    def opener(request, timeout):
        return io.BytesIO(b"[1, 2]")

    with pytest.raises(FetchError, match="JSON object"):
        fetch_json("https://example.org/manifest", opener=opener)


def test_fetch_json_wraps_network_errors() -> None:
    def opener(request, timeout):
        raise urllib.error.URLError("refused")

    with pytest.raises(FetchError, match="Failed to fetch JSON"):
        fetch_json("https://example.org/manifest", opener=opener)


def test_fetch_json_wraps_invalid_json() -> None:
    def opener(request, timeout):
        return io.BytesIO(b"not-json")

    with pytest.raises(FetchError, match="Failed to fetch JSON"):
        fetch_json("https://example.org/manifest", opener=opener)
