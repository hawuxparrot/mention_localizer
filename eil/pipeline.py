"""
Localize MentionedPerson annotations and patch their targets.
localize_annotation_page()
"""
import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .fetch import crop_url_is_image, fetch_json
from .iiif import parse_manifest
from .localize import find_image_regions
from .models import EntityAnnotation, ManifestDocument, OcrPage
from .ocr import parse_ocr_text
from .ocr_index import resolve_ocr_path
from .parsing import parse_annotation_page, parse_entity_annotation
from .targets import precise_target

ManifestFetcher = Callable[[str], Any]
CropValidator = Callable[[str], bool]


@dataclass(frozen=True)
class AnnotationResult:
    """Diagnostics for one processed MentionedPerson annotation.

    ``match_count`` is the number of strict hits across the manifest.
    It is ``None`` when localization stopped before matching finished.
    ``crop_validation_succeeded`` is ``None`` when no precise target was
    written, and otherwise whether that target's crop URL returned an image.
    ``crop_url`` is the URL that was validated, when one was written.
    """
    annotation_id: str
    mention: str
    match_count: int | None
    precise_target_written: bool
    crop_validation_succeeded: bool | None
    error: str | None
    crop_url: str | None


@dataclass(frozen=True)
class LocalizationRun:
    """Patched AnnotationPage plus one result per MentionedPerson."""
    annotation_page: dict[str, Any]
    results: tuple[AnnotationResult, ...]


def localize_annotation_page(
    annotation_page: dict[str, Any],
    ocr_index: Mapping[str, Path],
    *,
    fetch_manifest: ManifestFetcher | None = None,
    validate_crop: CropValidator | None = None,
) -> LocalizationRun:
    """Localize every MentionedPerson and patch precise targets in place.

    The input document is not mutated. Only an annotation's ``target`` is
    replaced, and only when mention matching found at least one hit. A
    failure while localizing or validating one annotation is recorded on
    that annotation and does not stop the rest of the page. If any page
    in the manifest has no OCR file, that annotation is not matched
    against the remaining pages.

    Structural problems in the AnnotationPage still raise, via
    ``parse_annotation_page``.
    """
    if not isinstance(annotation_page, dict):
        raise TypeError("annotation_page must be a JSON object")

    patched = copy.deepcopy(annotation_page)
    annotations = parse_annotation_page(patched)
    person_items = [
        item
        for item in patched["items"]
        if isinstance(item, dict) and parse_entity_annotation(item) is not None
    ]
    if len(person_items) != len(annotations):
        raise RuntimeError(
            "MentionedPerson items diverged from parse_annotation_page"
        )

    fetcher = fetch_manifest or fetch_json
    checker = validate_crop or crop_url_is_image
    results = tuple(
        _localize_one(item, annotation, ocr_index, fetcher, checker)
        for item, annotation in zip(person_items, annotations, strict=True)
    )
    return LocalizationRun(annotation_page=patched, results=results)


def _localize_one(
    item: dict[str, Any],
    annotation: EntityAnnotation,
    ocr_index: Mapping[str, Path],
    fetch_manifest: ManifestFetcher,
    validate_crop: CropValidator,
) -> AnnotationResult:
    try:
        manifest = parse_manifest(fetch_manifest(annotation.target_manifest))
        ocr_pages = _load_ocr_pages(manifest, ocr_index)
        regions = find_image_regions(annotation.mention, ocr_pages)
    except Exception as exc:
        return _result(annotation, error=_error_text(exc))

    if not regions:
        return _result(annotation, match_count=0)

    target = precise_target(regions[0])
    item["target"] = target
    crop = target["rendering"][0]["id"]
    return _result(
        annotation,
        match_count=len(regions),
        precise_target_written=True,
        crop_validation_succeeded=_crop_ok(crop, validate_crop),
        crop_url=crop,
    )


def _load_ocr_pages(
    manifest: ManifestDocument,
    ocr_index: Mapping[str, Path],
) -> tuple[OcrPage, ...]:
    pages = []
    for page in manifest.pages:
        path = resolve_ocr_path(page, ocr_index)
        pages.append(parse_ocr_text(path.read_text(encoding="utf-8"), page))
    return tuple(pages)


def _crop_ok(url: str, validate_crop: CropValidator) -> bool:
    try:
        return bool(validate_crop(url))
    except Exception:
        return False


def _result(
    annotation: EntityAnnotation,
    *,
    match_count: int | None = None,
    precise_target_written: bool = False,
    crop_validation_succeeded: bool | None = None,
    error: str | None = None,
    crop_url: str | None = None,
) -> AnnotationResult:
    return AnnotationResult(
        annotation_id=annotation.annotation_id,
        mention=annotation.mention,
        match_count=match_count,
        precise_target_written=precise_target_written,
        crop_validation_succeeded=crop_validation_succeeded,
        error=error,
        crop_url=crop_url,
    )


def _error_text(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"
