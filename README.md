# mention_localizer

Locate a known text mention on a scanned page and return its IIIF region.
The input is an entity mention that already points at an article manifest, plus that article's page images and positional OCR. The output is the pixel box of the mention, expressed as a Web Annotation target.

## Goal

An annotation arrives with the mention in the body and only a manifest URL as the target:

```json
{
  "body": {
    "purpose": { "id": "ordiiif-vocab:MentionedPerson" },
    "identifier": "https://example.org/person/frey",
    "mention": [{
      "value": "Frey, Hauptmann in Königl. franz. Diensten; aus Basel"
    }]
  },
  "target": "https://www.e-periodica.ch/iiif/oeg-002:1765:6::1051/manifest"
}
```

```json
"target": {
  "rendering": [{
    "format": "image/jpeg",
    "type": "Image",
    "id": "...jpg/108,1235,646,64/full/0/default.jpg"
  }],
  "rdlRegion": "main",
  "source": "...0015.jpg",
  "selector": {
    "conformsTo": "http://www.w3.org/TR/media-frags/",
    "value": "xywh=108,1235,646,64",
    "type": "FragmentSelector"
  }
}
```

Note: The query string is the mention, not the person. One person can map to multiple different mentions.

## Intended architecture

Annotations are localized one at a time. Grouping mentions that share a manifest, so each page is parsed once, is still to come.

```text
AnnotationPage ──► EntityAnnotation (mention + manifest URL)
                              │
IIIF Manifest ──► ManifestDocument ──► PageImage (service URL, IIIF size)
                              │                    │
positional OCR .txt ──────────┼──────────► OcrPage (tokens, OCR size)
                              │                    │
                              └──── strict_match ─┘
                                        │
                                        ▼
                              scale OCR box into IIIF pixels
                                        │
                                        ▼
                                   ImageRegion
                                        │
                                        ▼
                              IIIF FragmentSelector target
```

1. **Annotations.** `parse_annotation_page` keeps `ordiiif-vocab:MentionedPerson` items and drops every other purpose. Each kept item becomes an `EntityAnnotation`: annotation id, person id, one mention string, and the manifest URL.
2. **Manifest.** `parse_manifest` reads a IIIF Presentation 3 manifest into a `ManifestDocument`. Canvas order is the page order. Each page is a `PageImage`: image-service URL, width, and height in IIIF pixels.
3. **Grouping.** Annotations that share a manifest should be collected before any OCR file is read, so each page is parsed once and then queried many times. This stage is not written yet.
4. **OCR files.** `index_ocr_directory` maps a page-image filename to one positional `.txt` under `data/`. The filename is the last `!`-separated segment of the IIIF service URL. A missing file is an error. Two files with the same stem are an error; neither is chosen.
5. **OCR.** `parse_ocr_text` reads one positional text file onto a `PageImage` and returns an `OcrPage`: the page, the token sequence, and the width and height of the OCR coordinate space.
6. **Matching.** `strict_match` slides the mention's tokens across one page and returns every enclosing box, in OCR coordinates. `find_image_regions` does that for every manifest page, in canvas order, and scales each hit into IIIF pixels. The first hit is the earliest page, then the earliest token match on that page. The scaled box is an `ImageRegion`. `ImageRegion.box` is always in the page's IIIF coordinates.
7. **Target.** `precise_target` writes the fragment selector above from that `ImageRegion`. The pipeline copies the original AnnotationPage and replaces only `target` when there is at least one hit. Zero hits leave the coarse manifest URL in place. More than one hit still writes the first region, and the real match count stays on the per-annotation result. Each written crop URL is requested; a failed image response is recorded and does not stop the next annotation.

`main.py` reads an AnnotationPage JSON, writes the patched page, and prints one diagnostic line per MentionedPerson.

## Current status


| Piece                                | Module            | State       |
| ------------------------------------ | ----------------- | ----------- |
| Person annotations to mentions       | `eil/parsing.py`  | Done        |
| IIIF manifest to ordered page images | `eil/iiif.py`     | Done        |
| Positional OCR to tokens             | `eil/ocr.py`      | Done        |
| Exact mention to enclosing boxes     | `eil/matching.py` | Done        |
| Shared types                         | `eil/models.py`   | Done        |
| Attach an OCR file to a page image   | `eil/ocr_index.py` | Done        |
| Scale OCR boxes into IIIF pixels     | `eil/geometry.py` | Done        |
| Strict matches across one manifest   | `eil/localize.py` | Done        |
| Build the fragment-selector target   | `eil/targets.py`  | Done        |
| Patch the page and record each hit   | `eil/pipeline.py` | Done        |
| Command-line pipeline                | `main.py`         | Done        |
| Group mentions by manifest           | —                 | Not started |


The input OCR file starts with `width,height`. Each later line is `text x,y,width,height`. The text is everything before the last space, so a token may contain spaces or commas. Blank lines and `<EOS>` / `<EOP>` are skipped. Confidence and layout ids are not in this format; those fields on `OcrToken` stay `None`.

## Layout

```text
mention_localizer/
├── pyproject.toml
├── README.md
├── main.py
├── eil/
│   ├── models.py      # BoundingBox, OcrToken, PageImage, OcrPage,
│   │                   # EntityAnnotation, ManifestDocument, ImageRegion
│   ├── parsing.py     # AnnotationPage → EntityAnnotation
│   ├── iiif.py        # IIIF Presentation 3 → ManifestDocument
│   ├── ocr.py         # positional OCR text → OcrPage
│   ├── ocr_index.py   # page image filename → one OCR .txt
│   ├── geometry.py    # OCR box → IIIF box
│   ├── matching.py    # mention → enclosing boxes
│   ├── localize.py    # manifest pages → ImageRegion hits
│   ├── targets.py     # ImageRegion → fragment-selector target
│   ├── fetch.py       # manifest JSON and crop-image check
│   └── pipeline.py    # AnnotationPage → patched page + diagnostics
└── tests/
    ├── helpers.py
    ├── test_models.py
    ├── test_parsing.py
    ├── test_iiif.py
    ├── test_ocr.py
    ├── test_ocr_corpus.py
    ├── test_ocr_index.py
    ├── test_geometry.py
    ├── test_matching.py
    ├── test_matching_corpus.py
    ├── test_localize.py
    ├── test_targets.py
    ├── test_fetch.py
    └── test_pipeline.py
```

## Data

The positional OCR corpus is too large for GitHub, so it is not in the clone. `data/` is gitignored.
From the repository root:
```bash
make setup
```
`make setup` installs the project, then `scripts/fetch_ocr.py` downloads the corpus from Polybox and extracts it to `data/`.

## Tests

```bash
uv run pytest
```

Run `make setup` once before this. Unit tests build their own pages. Corpus tests read `data/` and skip when it is absent. They check that real pages parse, that punctuation and apostrophes stay inside tokens, and that `strict_match` returns the expected boxes for a few known strings.
