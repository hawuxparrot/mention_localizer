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
    volume_totals: dict[str, dict[str, Any]] = defaultdict(_empty_counts)
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
    strict = statistics["matching"]["strict"]
    lenient = statistics["matching"]["lenient"]
    fuzzy = statistics["matching"]["fuzzy"]
    print(
        f"persons={statistics['persons']} precise={statistics['precise_targets']} "
        f"strict=0:{strict['zero_matches']}/1:{strict['exactly_one_match']}"
        f"/multi:{strict['multiple_matches']} "
        f"lenient=0:{lenient['zero_matches']}/1:{lenient['exactly_one_match']}"
        f"/multi:{lenient['multiple_matches']} "
        f"fuzzy=0:{fuzzy['zero_matches']}/1:{fuzzy['exactly_one_match']}"
        f"/multi:{fuzzy['multiple_matches']} "
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
        "matching": _empty_matching_counts(),
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
        _record_match(
            stats["matching"]["strict"],
            result.strict_match_count,
        )
        _record_match(
            stats["matching"]["lenient"],
            result.lenient_match_count,
        )
        _record_match(
            stats["matching"]["fuzzy"],
            result.fuzzy_match_count,
        )
        _record_comparison(
            stats["matching"],
            result.strict_match_count,
            result.lenient_match_count,
            result.fuzzy_match_count,
        )
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


def _empty_match_counts() -> dict[str, int]:
    return {
        "total_queries": 0,
        "zero_matches": 0,
        "exactly_one_match": 0,
        "multiple_matches": 0,
    }


def _empty_matching_counts() -> dict[str, Any]:
    return {
        "strict": _empty_match_counts(),
        "lenient": _empty_match_counts(),
        "fuzzy": _empty_match_counts(),
        "strict_zero_lenient_one": 0,
        "strict_zero_lenient_multiple": 0,
        "strict_multiple_lenient_multiple": 0,
        "lenient_zero_fuzzy_one": 0,
        "lenient_zero_fuzzy_multiple": 0,
        "lenient_multiple_fuzzy_multiple": 0,
    }


def _empty_counts() -> dict[str, Any]:
    return {
        "pages": 0,
        "pages_with_persons": 0,
        "persons": 0,
        "precise_targets": 0,
        "matching": _empty_matching_counts(),
        "crop_validated": 0,
        "crop_failed": 0,
        "annotation_errors": 0,
        "unreadable_items": 0,
    }


def _record_match(counts: dict[str, int], match_count: int | None) -> None:
    if match_count is None:
        return
    counts["total_queries"] += 1
    if match_count == 0:
        counts["zero_matches"] += 1
    elif match_count == 1:
        counts["exactly_one_match"] += 1
    else:
        counts["multiple_matches"] += 1


def _record_comparison(
    counts: dict[str, Any],
    strict_count: int | None,
    lenient_count: int | None,
    fuzzy_count: int | None,
) -> None:
    if strict_count == 0 and lenient_count == 1:
        counts["strict_zero_lenient_one"] += 1
    elif strict_count == 0 and (lenient_count or 0) > 1:
        counts["strict_zero_lenient_multiple"] += 1
    elif (strict_count or 0) > 1 and (lenient_count or 0) > 1:
        counts["strict_multiple_lenient_multiple"] += 1
    if lenient_count == 0 and fuzzy_count == 1:
        counts["lenient_zero_fuzzy_one"] += 1
    elif lenient_count == 0 and (fuzzy_count or 0) > 1:
        counts["lenient_zero_fuzzy_multiple"] += 1
    elif (lenient_count or 0) > 1 and (fuzzy_count or 0) > 1:
        counts["lenient_multiple_fuzzy_multiple"] += 1


def _add_counts(total: dict[str, Any], page: dict[str, Any]) -> None:
    total["pages"] += 1
    if page["persons"]:
        total["pages_with_persons"] += 1
    for key in (
        "persons",
        "precise_targets",
        "crop_validated",
        "crop_failed",
        "annotation_errors",
        "unreadable_items",
    ):
        total[key] += page[key]
    for matcher in ("strict", "lenient", "fuzzy"):
        for key, value in page["matching"][matcher].items():
            total["matching"][matcher][key] += value
    for key in (
        "strict_zero_lenient_one",
        "strict_zero_lenient_multiple",
        "strict_multiple_lenient_multiple",
        "lenient_zero_fuzzy_one",
        "lenient_zero_fuzzy_multiple",
        "lenient_multiple_fuzzy_multiple",
    ):
        total["matching"][key] += page["matching"][key]


def _statistics(
    ocr_files: int,
    annotation_pages: int,
    pages: list[dict[str, Any]],
    volume_totals: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    totals = _empty_counts()
    for page in pages:
        _add_counts(totals, page)
    return {
        "ocr_files": ocr_files,
        "annotation_pages": annotation_pages,
        "pages_with_persons": totals["pages_with_persons"],
        "pages_without_persons": annotation_pages - totals["pages_with_persons"],
        "persons": totals["persons"],
        "precise_targets": totals["precise_targets"],
        "matching": _matching_statistics(totals["matching"]),
        "crop_validated": totals["crop_validated"],
        "crop_failed": totals["crop_failed"],
        "annotation_errors": totals["annotation_errors"],
        "unreadable_items": totals["unreadable_items"],
        "by_volume": {
            volume: {
                **counts,
                "matching": _matching_statistics(counts["matching"]),
            }
            for volume, counts in sorted(volume_totals.items())
        },
        "pages": pages,
    }


def _matching_statistics(counts: dict[str, Any]) -> dict[str, Any]:
    return {
        "strict": _match_statistics(counts["strict"]),
        "lenient": _match_statistics(counts["lenient"]),
        "fuzzy": _match_statistics(counts["fuzzy"]),
        "strict_zero_lenient_one": counts["strict_zero_lenient_one"],
        "strict_zero_lenient_multiple": counts["strict_zero_lenient_multiple"],
        "strict_multiple_lenient_multiple": counts[
            "strict_multiple_lenient_multiple"
        ],
        "lenient_zero_fuzzy_one": counts["lenient_zero_fuzzy_one"],
        "lenient_zero_fuzzy_multiple": counts["lenient_zero_fuzzy_multiple"],
        "lenient_multiple_fuzzy_multiple": counts[
            "lenient_multiple_fuzzy_multiple"
        ],
    }


def _match_statistics(counts: dict[str, int]) -> dict[str, int | float | None]:
    total = counts["total_queries"]
    unique = counts["exactly_one_match"]
    found = unique + counts["multiple_matches"]
    return {
        **counts,
        "unique_recall": unique / total if total else None,
        "found_rate": found / total if total else None,
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
    matching = statistics["matching"]
    strict = matching["strict"]
    lenient = matching["lenient"]
    fuzzy = matching["fuzzy"]
    unreadable = statistics["unreadable_items"]
    lines = [
        (
            f"`scripts/localize_corpus.py` was run on the OCR in `data/` "
            f"({statistics['ocr_files']:,} page files) and the RdL annotation "
            f"pages for those volumes. Published person targets are already "
            f"precise, so each one was set back to a manifest URL before "
            f"matching. Each AnnotationPage is one statistics unit: German "
            f"(`oeg-*`) and French (`soe-*`) editions are counted separately "
            f"even when a French mention is redirected to the German "
            f"manifest. In that case the hit is on the German image, not the "
            f"French scan. All three matchers search the same parsed OCR pages; "
            f"only `fuzzy_match` writes the production target. `strict_match` "
            f"and `lenient_match` are recorded for comparison. There is no "
            f"ground-truth set; the "
            f"rates below are matcher outcome rates, not retrieval recall "
            f"against published boxes."
        ),
        "",
        (
            f"{statistics['annotation_pages']} annotation pages fall in the "
            f"corpus. {statistics['pages_with_persons']} of them contain at "
            f"least one `MentionedPerson` ({statistics['persons']} person "
            f"queries in total). The other "
            f"{statistics['pages_without_persons']} do not. A missing "
            f"`body.identifier` is allowed and is not counted as an error. "
            f"{unreadable} "
            f"{'annotation is' if unreadable == 1 else 'annotations are'} "
            f"unreadable for another reason and are dropped before matching."
        ),
        "",
        (
            "| Matcher | Queries | Zero | Exactly one | Multiple | "
            "Unique hit rate | Any-hit rate |"
        ),
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        _match_summary_row("Strict", strict),
        _match_summary_row("Lenient", lenient),
        _match_summary_row("Fuzzy", fuzzy),
        "",
        (
            f"Lenient matching turned "
            f"{matching['strict_zero_lenient_one']} strict misses into "
            f"exactly one hit. "
            f"{matching['strict_zero_lenient_multiple']} strict misses became "
            f"multiple lenient matches; "
            f"{matching['strict_multiple_lenient_multiple']} queries were "
            f"multiple under both matchers."
        ),
        "",
        (
            f"Fuzzy matching turned "
            f"{matching['lenient_zero_fuzzy_one']} lenient misses into "
            f"exactly one hit. "
            f"{matching['lenient_zero_fuzzy_multiple']} lenient misses became "
            f"multiple fuzzy matches; "
            f"{matching['lenient_multiple_fuzzy_multiple']} queries were "
            f"multiple under both matchers."
        ),
        "",
        (
            f"The production fuzzy matcher wrote "
            f"{statistics['precise_targets']} precise targets "
            f"(exactly one plus multiple). All "
            f"{statistics['crop_validated']} crop URLs returned an image."
            if statistics["crop_failed"] == 0
            else (
                f"The production fuzzy matcher wrote "
                f"{statistics['precise_targets']} precise targets "
                f"(exactly one plus multiple). "
                f"{statistics['crop_validated']} crop URLs returned an image; "
                f"{statistics['crop_failed']} failed."
            )
        ),
        "",
        "| Volume | Queries | Strict one | Lenient one | Fuzzy one | Fuzzy zero | Fuzzy multiple |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for volume, counts in statistics["by_volume"].items():
        if counts["persons"] == 0:
            continue
        strict = counts["matching"]["strict"]
        lenient = counts["matching"]["lenient"]
        fuzzy = counts["matching"]["fuzzy"]
        lines.append(
            f"| {_volume_label(volume)} | {fuzzy['total_queries']} | "
            f"{strict['exactly_one_match']} | {lenient['exactly_one_match']} | "
            f"{fuzzy['exactly_one_match']} | {fuzzy['zero_matches']} | "
            f"{fuzzy['multiple_matches']} |"
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


def _match_summary_row(
    label: str,
    counts: dict[str, int | float | None],
) -> str:
    return (
        f"| {label} | {counts['total_queries']} | {counts['zero_matches']} | "
        f"{counts['exactly_one_match']} | {counts['multiple_matches']} | "
        f"{counts['unique_recall']:.1%} | {counts['found_rate']:.1%} |"
    )


def _volume_label(volume: str) -> str:
    journal, year, piece = volume.split("_", 2)
    return f"`{journal}` {year}/{piece}"


if __name__ == "__main__":
    raise SystemExit(main())
