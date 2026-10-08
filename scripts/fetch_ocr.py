"""Download the OCR corpus zip from Polybox and extract it to data/."""

import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

URL = os.environ.get(
    "MENTION_LOCALIZER_OCR_URL",
    "https://polybox.ethz.ch/index.php/s/i7QxDaEQ698BbiB/download",
)
ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "data"


def main() -> None:
    if any(DEST.glob("*/*.txt")):
        print(f"OCR data already present at {DEST}")
        return

    DEST.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {URL}")
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        zip_path = Path(tmp.name)
    try:
        urllib.request.urlretrieve(URL, zip_path)
        if not zipfile.is_zipfile(zip_path):
            sys.exit(
                "Download is not a zip. Check that the Polybox link is a "
                "public share and that /download was appended."
            )
        with zipfile.ZipFile(zip_path) as archive:
            _extract(archive, DEST)
    finally:
        zip_path.unlink(missing_ok=True)

    print(f"Extracted to {DEST}")


def _extract(archive: zipfile.ZipFile, dest: Path) -> None:
    infos = [info for info in archive.infolist() if _is_ocr_member(info)]
    prefix = "data/" if _tops(infos) == {"data"} else ""
    root = dest.resolve()
    for info in infos:
        relative = info.filename.removeprefix(prefix)
        target = (dest / relative).resolve()
        if target != root and root not in target.parents:
            sys.exit(f"Refusing to extract unsafe path: {info.filename}")
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(info) as src, target.open("wb") as out:
            shutil.copyfileobj(src, out)


def _is_ocr_member(info: zipfile.ZipInfo) -> bool:
    if info.is_dir():
        return False
    parts = PurePosixPath(info.filename).parts
    if not parts or "__MACOSX" in parts:
        return False
    return not any(part.startswith("._") for part in parts)


def _tops(infos: list[zipfile.ZipInfo]) -> set[str]:
    return {PurePosixPath(info.filename).parts[0] for info in infos}


if __name__ == "__main__":
    main()