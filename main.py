"""Read an AnnotationPage, localize mentions, and write the patched page."""

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from eil.ocr_index import OcrResolutionError, index_ocr_directory
from eil.parsing import AnnotationParseError
from eil.pipeline import LocalizationRun, localize_annotation_page


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Localize MentionedPerson annotations onto IIIF image regions."
        )
    )
    parser.add_argument("annotation_page", type=Path)
    parser.add_argument(
        "--data",
        type=Path,
        default=None,
        help="positional OCR directory (default: discovered data/)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="patched AnnotationPage JSON (default: stdout)",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="per-annotation JSON report (default: a text summary on stderr)",
    )
    args = parser.parse_args(argv)

    data_dir = args.data if args.data is not None else default_data_dir()
    try:
        ocr_index = index_ocr_directory(data_dir)
        raw = json.loads(args.annotation_page.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise AnnotationParseError("AnnotationPage must be a JSON object")
        run = localize_annotation_page(raw, ocr_index)
    except (OSError, json.JSONDecodeError, AnnotationParseError, OcrResolutionError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    _write_json(run.annotation_page, args.output)
    _write_report(run, args.report)
    return 0


def default_data_dir() -> Path:
    """Return the first data directory that already holds OCR text files."""
    here = Path(__file__).resolve().parent
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


def _write_json(payload: object, path: Path | None) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if path is None:
        sys.stdout.write(text)
        return
    path.write_text(text, encoding="utf-8")


def _write_report(run: LocalizationRun, path: Path | None) -> None:
    rows = [asdict(result) for result in run.results]
    if path is not None:
        _write_json(rows, path)
        return
    for result in run.results:
        strict = (
            "n/a"
            if result.strict_match_count is None
            else str(result.strict_match_count)
        )
        lenient = (
            "n/a"
            if result.lenient_match_count is None
            else str(result.lenient_match_count)
        )
        fuzzy = (
            "n/a"
            if result.fuzzy_match_count is None
            else str(result.fuzzy_match_count)
        )
        if result.crop_validation_succeeded is None:
            crop = "n/a"
        else:
            crop = str(result.crop_validation_succeeded).lower()
        error = f" error={result.error}" if result.error else ""
        print(
            f"{result.annotation_id} mention={result.mention!r} "
            f"strict={strict} lenient={lenient} fuzzy={fuzzy} "
            f"precise={str(result.precise_target_written).lower()} "
            f"crop_ok={crop}{error}",
            file=sys.stderr,
        )
    print(
        f"{len(run.results)} annotations, "
        f"{sum(result.precise_target_written for result in run.results)} precise targets, "
        f"{sum(result.error is not None for result in run.results)} errors",
        file=sys.stderr,
    )


if __name__ == "__main__":
    raise SystemExit(main())
