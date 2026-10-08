"""
Network boundary for IIIF manifests and crop URLs.
fetch_json()
crop_url_is_image()
"""
import json
import urllib.error
import urllib.request
from typing import Any, Callable

USER_AGENT = "mention_localizer/0.1"
Opener = Callable[..., Any]


class FetchError(RuntimeError):
    """Raised when a remote JSON document cannot be retrieved."""


def fetch_json(
    url: str,
    *,
    timeout: float = 60,
    opener: Opener | None = None,
) -> dict[str, Any]:
    """GET ``url`` and decode a JSON object."""
    open_url = opener or urllib.request.urlopen
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with open_url(request, timeout=timeout) as response:
            payload = json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError, UnicodeError) as exc:
        raise FetchError(f"Failed to fetch JSON from {url}: {exc}") from exc
    if not isinstance(payload, dict):
        raise FetchError(f"Expected a JSON object from {url}")
    return payload


def crop_url_is_image(
    url: str,
    *,
    timeout: float = 30,
    opener: Opener | None = None,
) -> bool:
    """Return whether ``url`` responds with a non-empty image body.

    A syntactically valid URL that returns an error, a non-image content
    type, or an empty body is a failed check. Network errors are failures
    too; they are not raised.
    """
    open_url = opener or urllib.request.urlopen
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with open_url(request, timeout=timeout) as response:
            status = getattr(response, "status", None)
            if status is None:
                status = response.getcode()
            if status != 200:
                return False
            content_type = ""
            headers = getattr(response, "headers", None)
            if headers is not None:
                content_type = headers.get("Content-Type", "") or ""
            if not _is_image_type(content_type):
                return False
            return bool(response.read(32))
    except Exception:
        return False


def _is_image_type(content_type: str) -> bool:
    media = content_type.split(";", 1)[0].strip().lower()
    return media.startswith("image/")
