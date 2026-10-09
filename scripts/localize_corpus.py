"""Localize every RdL AnnotationPage covered by the local OCR corpus.

Writes one patched AnnotationPage and one per-person report for each page
that contains a MentionedPerson, plus examples/statistics.json for the set.
"""

import argparse
import copy
import json
import sys
import time
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eil.fetch import fetch_json
from eil.ocr_index import index_ocr_directory
from eil.parsing import AnnotationParseError, parse_entity_annotation
from eil.pipeline import localize_annotation_page

INDEX_URL = "https://manifests.republique-des-lettres.ch/index.json"
MENTIONED = "ordiiif-vocab:MentionedPerson"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data",
        type=Path,
        default=None,
        help="positional OCR directory (default: discovered data/)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="directory for localized pages, reports, and statistics.json",
    )
    args = parser.parse_args(argv)
    data_dir = args.data if args.data is not None else default_data_dir()
    output_dir = args.output if args.output is not None else Path(__file__).resolve().parents[1] / "examples"
    output_dir.mkdir(parents=True, exist_ok=True)

    ocr_index = index_ocr_directory(data_dir)
    prefixes = _annotation_prefixes(ocr_index)
    catalog = fetch_json(INDEX_URL)
    elements = [
        element
        for section in catalog["sections"]
        for element in section.get("elements", [])
        if _covered(element.get("id") or "", prefixes)
    ]
    elements.sort(key=lambda element: element.get("id") or "")
    print(f"ocr files: {len(ocr_index)}", file=sys.stderr)
    print(f"annotation pages in corpus: {len(elements)}", file=sys.stderr)

    manifest_cache: dict[str, dict[str, Any]] = {}

    def fetch_manifest(url: str) -> dict[str, Any]:
        if url not in manifest_cache:
            manifest_cache[url] = fetch_json(url)
        return manifest_cache[url]

    pages: list[dict[str, Any]] = []
    volume_totals: dict[str, dict[str, int]] = defaultdict(_empty_counts)
    for number, element in enumerate(elements, start=1):
        page_stats = _localize_element(
            element,
            ocr_index,
            fetch_manifest,
            output_dir,
        )
        pages.append(page_stats)
        _add_counts(volume_totals[_volume_id(element.get("id") or "")], page_stats)
        if number % 25 == 0 or page_stats["persons"]:
            print(
                f"[{number}/{len(elements)}] {page_stats['id']} "
                f"persons={page_stats['persons']} "
                f"precise={page_stats['precise_targets']}",
                file=sys.stderr,
            )
        if number % 25 == 0:
            _write_json(
                _statistics(len(ocr_index), len(elements), pages, volume_totals),
                output_dir / "statistics.json",
            )

    statistics = _statistics(len(ocr_index), len(elements), pages, volume_totals)
    stats_path = output_dir / "statistics.json"
    _write_json(statistics, stats_path)
    readme_path = ROOT / "README.md"
    _update_readme_statistics(readme_path, statistics)
    print(
        f"persons={statistics['persons']} precise={statistics['precise_targets']} "
        f"unmatched={statistics['unmatched']} multi={statistics['multiple_matches']} "
        f"crop_ok={statistics['crop_validated']} crop_failed={statistics['crop_failed']} "
        f"errors={statistics['annotation_errors']}",
        file=sys.stderr,
    )
    print(stats_path)
    print(readme_path)
    return 0


def default_data_dir() -> Path:
    here = Path(__file__).resolve().parents[1]
    candidates = (
        here / "data",
        here.parent / "data",
        Path.cwd() / "data",
        Path.cwd().parent / "data",
    )
    for candidate in candidates:
        if candidate.is_dir() and any(candidate.glob("*/*.txt")):
            return candidate
    return here / "data"


def _annotation_prefixes(ocr_index: dict[str, Path]) -> set[str]:
    prefixes: set[str] = set()
    for stem in ocr_index:
        parts = stem.split("_")
        if len(parts) < 4 or not parts[2].isdigit():
            continue
        prefixes.add(f"{parts[0]}_{parts[1]}_{int(parts[2])}__")
    return prefixes


def _covered(annotation_id: str, prefixes: set[str]) -> bool:
    head, separator, _rest = annotation_id.partition("__")
    return bool(separator) and f"{head}__" in prefixes


def _volume_id(annotation_id: str) -> str:
    head, separator, _rest = annotation_id.partition("__")
    return head if separator else annotation_id


def _fetch_with_retry(url: str, attempts: int = 4) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return fetch_json(url)
        except Exception as exc:
            last_error = exc
            if attempt + 1 == attempts:
                break
            time.sleep(1.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


def _localize_element(
    element: dict[str, Any],
    ocr_index: dict[str, Path],
    fetch_manifest,
    output_dir: Path,
) -> dict[str, Any]:
    annotation_id = element.get("id") or ""
    stats = {
        "id": annotation_id,
        "label": element.get("label"),
        "source": element.get("annotations"),
        "manifest": element.get("manifest"),
        "persons": 0,
        "precise_targets": 0,
        "unmatched": 0,
        "multiple_matches": 0,
        "crop_validated": 0,
        "crop_failed": 0,
        "annotation_errors": 0,
        "unreadable_items": 0,
        "error": None,
        "localized": None,
        "report": None,
    }
    try:
        raw = _fetch_with_retry(element["annotations"])
        manifest_url = element.get("manifest")
        if not isinstance(manifest_url, str) or not manifest_url:
            manifest_url = _manifest_url(raw)
        prepared, failures = _prepare_page(raw, manifest_url)
    except Exception as exc:
        stats["error"] = f"{type(exc).__name__}: {exc}"
        stats["annotation_errors"] = 1
        return stats

    stats["unreadable_items"] = len(failures)
    if not _has_person(prepared):
        stats["annotation_errors"] = len(failures)
        return stats

    try:
        run = localize_annotation_page(
            prepared,
            ocr_index,
            fetch_manifest=fetch_manifest,
        )
    except Exception as exc:
        stats["error"] = f"{type(exc).__name__}: {exc}"
        stats["annotation_errors"] = 1 + len(failures)
        return stats

    for result in run.results:
        stats["persons"] += 1
        if result.error:
            stats["annotation_errors"] += 1
            continue
        if result.precise_target_written:
            stats["precise_targets"] += 1
        if result.match_count == 0:
            stats["unmatched"] += 1
        if (result.match_count or 0) > 1:
            stats["multiple_matches"] += 1
        if result.crop_validation_succeeded is True:
            stats["crop_validated"] += 1
        elif result.crop_validation_succeeded is False:
            stats["crop_failed"] += 1
    stats["annotation_errors"] += len(failures)

    localized_path = output_dir / f"{annotation_id}.localized.json"
    report_path = output_dir / f"{annotation_id}.report.json"
    _write_json(run.annotation_page, localized_path)
    _write_json([asdict(result) for result in run.results], report_path)
    stats["localized"] = localized_path.name
    stats["report"] = report_path.name
    return stats


def _prepare_page(
    page: dict[str, Any],
    manifest_url: str | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return a page the pipeline can parse, and items that could not be read.

    Published MentionedPerson targets are often already precise objects.
    Those are set back to the manifest URL, which is the pipeline input.
    One unreadable item is dropped so the rest of the page can still run.
    """
    prepared = copy.deepcopy(page)
    failures: list[dict[str, Any]] = []
    kept: list[Any] = []
    for index, item in enumerate(prepared.get("items") or []):
        if not isinstance(item, dict):
            failures.append({"index": index, "error": "item is not an object"})
            continue
        if _is_mentioned_person(item) and not isinstance(item.get("target"), str):
            if not manifest_url:
                failures.append(
                    {
                        "index": index,
                        "annotation_id": item.get("id"),
                        "error": "missing manifest URL for a precise target",
                    }
                )
                continue
            item["target"] = manifest_url
        try:
            parse_entity_annotation(item)
        except AnnotationParseError as exc:
            failures.append(
                {
                    "index": index,
                    "annotation_id": item.get("id"),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue
        kept.append(item)
    prepared["items"] = kept
    return prepared, failures


def _manifest_url(page: dict[str, Any]) -> str | None:
    for meta in page.get("metadata") or []:
        if not isinstance(meta, dict):
            continue
        labels = (meta.get("label") or {}).get("de") or []
        if "Manifest" not in labels:
            continue
        values = (meta.get("value") or {}).get("de") or []
        if values and isinstance(values[0], str):
            return values[0]
    return None


def _is_mentioned_person(item: dict[str, Any]) -> bool:
    body = item.get("body")
    if not isinstance(body, dict):
        return False
    purpose = body.get("purpose") or {}
    return isinstance(purpose, dict) and purpose.get("id") == MENTIONED


def _has_person(page: dict[str, Any]) -> bool:
    for item in page.get("items") or []:
        if not isinstance(item, dict):
            continue
        body = item.get("body")
        if not isinstance(body, dict):
            continue
        purpose = body.get("purpose") or {}
        if isinstance(purpose, dict) and purpose.get("id") == MENTIONED:
            return True
    return False


def _empty_counts() -> dict[str, int]:
    return {
        "pages": 0,
        "pages_with_persons": 0,
        "persons": 0,
        "precise_targets": 0,
        "unmatched": 0,
        "multiple_matches": 0,
        "crop_validated": 0,
        "crop_failed": 0,
        "annotation_errors": 0,
        "unreadable_items": 0,
    }


def _add_counts(total: dict[str, int], page: dict[str, Any]) -> None:
    total["pages"] += 1
    if page["persons"]:
        total["pages_with_persons"] += 1
    for key in (
        "persons",
        "precise_targets",
        "unmatched",
        "multiple_matches",
        "crop_validated",
        "crop_failed",
        "annotation_errors",
        "unreadable_items",
    ):
        total[key] += page[key]


def _statistics(
    ocr_files: int,
    annotation_pages: int,
    pages: list[dict[str, Any]],
    volume_totals: dict[str, dict[str, int]],
) -> dict[str, Any]:
    totals = _empty_counts()
    for page in pages:
        _add_counts(totals, page)
    persons = totals["persons"]
    precise = totals["precise_targets"]
    return {
        "ocr_files": ocr_files,
        "annotation_pages": annotation_pages,
        "pages_with_persons": totals["pages_with_persons"],
        "pages_without_persons": annotation_pages - totals["pages_with_persons"],
        "persons": persons,
        "precise_targets": precise,
        "unmatched": totals["unmatched"],
        "multiple_matches": totals["multiple_matches"],
        "crop_validated": totals["crop_validated"],
        "crop_failed": totals["crop_failed"],
        "annotation_errors": totals["annotation_errors"],
        "unreadable_items": totals["unreadable_items"],
        "recall": (precise / persons) if persons else None,
        "by_volume": {
            volume: counts
            for volume, counts in sorted(volume_totals.items())
        },
        "pages": pages,
    }


def _write_json(payload: object, path: Path) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


_README_STATS_START = "<!-- corpus-statistics:start -->"
_README_STATS_END = "<!-- corpus-statistics:end -->"


def _update_readme_statistics(readme_path: Path, statistics: dict[str, Any]) -> None:
    """Replace the marked Corpus results block in README.md."""
    text = readme_path.read_text(encoding="utf-8")
    start = text.find(_README_STATS_START)
    end = text.find(_README_STATS_END)
    if start < 0 or end < 0 or end < start:
        raise ValueError(
            f"{readme_path} is missing {_README_STATS_START!r} / {_README_STATS_END!r}"
        )
    block = (
        f"{_README_STATS_START}\n"
        f"{_format_readme_statistics(statistics).rstrip()}\n"
        f"{_README_STATS_END}"
    )
    readme_path.write_text(
        text[:start] + block + text[end + len(_README_STATS_END) :],
        encoding="utf-8",
    )


def _format_readme_statistics(statistics: dict[str, Any]) -> str:
    persons = statistics["persons"]
    precise = statistics["precise_targets"]
    unmatched = statistics["unmatched"]
    multi = statistics["multiple_matches"]
    by_lang = _language_totals(statistics["by_volume"])
    unreadable = statistics["unreadable_items"]
    lines = [
        (
            f"`scripts/localize_corpus.py` was run on the OCR in `data/` "
            f"({statistics['ocr_files']:,} page files) and the RdL annotation "
            f"pages for those volumes. Published person targets are already "
            f"precise, so each one was set back to a manifest URL before "
            f"matching. A mention whose language differs from the journal is "
            f"searched on the parallel edition of that language: a German "
            f"mention on a French page is matched against the German manifest, "
            f"and the box is on the German image. `lenient_match` then searches "
            f"every page of the chosen manifest."
        ),
        "",
        (
            f"{statistics['annotation_pages']} annotation pages fall in the "
            f"corpus. {statistics['pages_with_persons']} of them contain a "
            f"`MentionedPerson`. The other {statistics['pages_without_persons']} "
            f"do not. A missing `body.identifier` is allowed: that field is a "
            f"GND URI, and many local persons have only a Haller record. "
            f"{_count_words(unreadable)} "
            f"{'annotation is' if unreadable == 1 else 'annotations are'} "
            f"still unreadable for another reason."
        ),
        "",
        "| | Persons | Localized | Unmatched | More than one match |",
        "| --- | ---: | ---: | ---: | ---: |",
        _summary_row("Whole corpus", persons, precise, unmatched, multi),
        _summary_row(
            "German (`oeg`)",
            by_lang["oeg"]["persons"],
            by_lang["oeg"]["precise_targets"],
            by_lang["oeg"]["unmatched"],
            by_lang["oeg"]["multiple_matches"],
        ),
        _summary_row(
            "French (`soe`)",
            by_lang["soe"]["persons"],
            by_lang["soe"]["precise_targets"],
            by_lang["soe"]["unmatched"],
            by_lang["soe"]["multiple_matches"],
        ),
        "",
        (
            f"All {statistics['crop_validated']} crop URLs returned an image."
            if statistics["crop_failed"] == 0
            else (
                f"{statistics['crop_validated']} crop URLs returned an image; "
                f"{statistics['crop_failed']} failed."
            )
        )
        + (
            " The French-page hits are the same kind of result as the German "
            "edition they were redirected to, not boxes on the French scan. "
            "The published French boxes were not used as ground truth."
        ),
        "",
        "| Volume | Persons | Localized | Unmatched |",
        "| --- | ---: | ---: | ---: |",
    ]
    for volume, counts in statistics["by_volume"].items():
        if counts["persons"] == 0:
            continue
        lines.append(
            f"| {_volume_label(volume)} | {counts['persons']} | "
            f"{counts['precise_targets']} | {counts['unmatched']} |"
        )
    lines.extend(
        [
            "",
            (
                "Per-page counts, crop URLs, and the patched AnnotationPages "
                "are under `examples/`. `examples/statistics.json` is the full "
                "aggregate."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def _language_totals(by_volume: dict[str, dict[str, int]]) -> dict[str, dict[str, int]]:
    totals = {
        "oeg": {
            "persons": 0,
            "precise_targets": 0,
            "unmatched": 0,
            "multiple_matches": 0,
        },
        "soe": {
            "persons": 0,
            "precise_targets": 0,
            "unmatched": 0,
            "multiple_matches": 0,
        },
    }
    for volume, counts in by_volume.items():
        key = volume.split("-", 1)[0]
        if key not in totals:
            continue
        for field in totals[key]:
            totals[key][field] += counts[field]
    return totals


def _summary_row(
    label: str,
    persons: int,
    precise: int,
    unmatched: int,
    multi: int,
) -> str:
    pct = f"{100 * precise / persons:.1f}%" if persons else "—"
    return (
        f"| {label} | {persons} | {precise} ({pct}) | {unmatched} | {multi} |"
    )


def _volume_label(volume: str) -> str:
    journal, year, piece = volume.split("_", 2)
    return f"`{journal}` {year}/{piece}"


def _count_words(n: int) -> str:
    words = {
        0: "Zero",
        1: "One",
        2: "Two",
        3: "Three",
        4: "Four",
        5: "Five",
        6: "Six",
        7: "Seven",
        8: "Eight",
        9: "Nine",
        10: "Ten",
    }
    return words.get(n, str(n))


if __name__ == "__main__":
    raise SystemExit(main())
