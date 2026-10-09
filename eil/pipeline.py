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
from .matching import strict_match
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

    Match counts are ``None`` when localization stopped before matching.
    ``crop_validation_succeeded`` is ``None`` when no precise target was
    written, and otherwise whether that target's crop URL returned an image.
    ``crop_url`` is the URL that was validated, when one was written.
    """
    annotation_id: str
    mention: str
    strict_match_count: int | None
    lenient_match_count: int | None
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

    The input document is not mutated. An annotation's ``target`` is
    replaced when a hit is written. A mention whose language differs from
    the journal is searched on the parallel edition, and a miss then
    leaves that edition's manifest URL. A failure while localizing or
    validating one annotation is recorded on that annotation and does not
    stop the rest of the page. If any page in the manifest has no OCR
    file, that annotation is not matched against the remaining pages.

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
        _localize_one(item, annotation, patched, ocr_index, fetcher, checker)
        for item, annotation in zip(person_items, annotations, strict=True)
    )
    return LocalizationRun(annotation_page=patched, results=results)


def _localize_one(
    item: dict[str, Any],
    annotation: EntityAnnotation,
    annotation_page: dict[str, Any],
    ocr_index: Mapping[str, Path],
    fetch_manifest: ManifestFetcher,
    validate_crop: CropValidator,
) -> AnnotationResult:
    search_manifest = resolve_search_manifest(annotation_page, annotation)
    try:
        manifest = parse_manifest(fetch_manifest(search_manifest))
        ocr_pages = _load_ocr_pages(manifest, ocr_index)
        strict_count = sum(
            len(strict_match(annotation.mention, page))
            for page in ocr_pages
        )
        regions = find_image_regions(annotation.mention, ocr_pages)
    except Exception as exc:
        return _result(annotation, error=_error_text(exc))

    if not regions:
        if isinstance(item.get("target"), str):
            item["target"] = search_manifest
        return _result(
            annotation,
            strict_match_count=strict_count,
            lenient_match_count=0,
        )

    target = precise_target(regions[0])
    item["target"] = target
    crop = target["rendering"][0]["id"]
    return _result(
        annotation,
        strict_match_count=strict_count,
        lenient_match_count=len(regions),
        precise_target_written=True,
        crop_validation_succeeded=_crop_ok(crop, validate_crop),
        crop_url=crop,
    )


def resolve_search_manifest(
    annotation_page: Mapping[str, Any],
    annotation: EntityAnnotation,
) -> str:
    """Return the IIIF manifest whose pages should be searched.

    A mention in another language than the journal is searched on the
    parallel edition of that language. ``parallelVersions`` carries that
    manifest. Otherwise the annotation's own target manifest is used.
    """
    mention_language = _language_tag(annotation.mention_language)
    journal_language = _language_tag(_journal_language(annotation_page))
    if mention_language and journal_language and mention_language != journal_language:
        parallel = _parallel_manifest(annotation_page, mention_language)
        if parallel:
            return parallel
    return annotation.target_manifest


def _journal_language(annotation_page: Mapping[str, Any]) -> str | None:
    journal = annotation_page.get("journal")
    if not isinstance(journal, dict):
        return None
    return journal.get("language") if isinstance(journal.get("language"), str) else None


def _parallel_manifest(annotation_page: Mapping[str, Any], language: str) -> str | None:
    versions = annotation_page.get("parallelVersions")
    if not isinstance(versions, list):
        return None
    for entry in versions:
        if not isinstance(entry, dict):
            continue
        if _language_tag(entry.get("lang")) != language:
            continue
        url = entry.get("manifestUrl")
        if isinstance(url, str) and url.strip():
            return url.strip()
    return None


def _language_tag(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    tag = value.strip().lower()
    return tag or None


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
    strict_match_count: int | None = None,
    lenient_match_count: int | None = None,
    precise_target_written: bool = False,
    crop_validation_succeeded: bool | None = None,
    error: str | None = None,
    crop_url: str | None = None,
) -> AnnotationResult:
    return AnnotationResult(
        annotation_id=annotation.annotation_id,
        mention=annotation.mention,
        strict_match_count=strict_match_count,
        lenient_match_count=lenient_match_count,
        precise_target_written=precise_target_written,
        crop_validation_succeeded=crop_validation_succeeded,
        error=error,
        crop_url=crop_url,
    )


def _error_text(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"
