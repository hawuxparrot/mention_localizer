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

Each page is parsed once. Every mention aimed at that manifest is then matched against the parsed tokens.

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
                              IIIF FragmentSelector target
```

1. **Annotations.** `parse_annotation_page` keeps `ordiiif-vocab:MentionedPerson` items and drops every other purpose. Each kept item becomes an `EntityAnnotation`: annotation id, person id, one mention string, and the manifest URL.
2. **Manifest.** `parse_manifest` reads a IIIF Presentation 3 manifest into a `ManifestDocument`. Canvas order is the page order. Each page is a `PageImage`: image-service URL, width, and height in IIIF pixels.
3. **Grouping.** Annotations that share a manifest should be collected before any OCR file is read, so each page is parsed once and then queried many times. This stage is not written yet.
4. **OCR.** `parse_ocr_text` reads one positional text file onto a `PageImage` and returns an `OcrPage`: the page, the token sequence, and the width and height of the OCR coordinate space.
5. **Matching.** `strict_match` slides the mention's tokens across the page and returns the enclosing box of every hit.
6. **Target.** The box, the image-service URL, and the page source should be written as the fragment selector above. `targets.py` is not written yet. Statistics over hits, misses, and ambiguous mentions are not written yet.

`main.py` is a placeholder. Nothing yet runs this sequence end to end.

## Current status


| Piece                                | Module            | State       |
| ------------------------------------ | ----------------- | ----------- |
| Person annotations to mentions       | `eil/parsing.py`  | Done        |
| IIIF manifest to ordered page images | `eil/iiif.py`     | Done        |
| Positional OCR to tokens             | `eil/ocr.py`      | Done        |
| Exact mention to enclosing boxes     | `eil/matching.py` | Done        |
| Shared types                         | `eil/models.py`   | Done        |
| Group mentions by manifest           | —                 | Not started |
| Attach an OCR file to a canvas       | —                 | Not started |
| Scale OCR boxes into IIIF pixels     | —                 | Not started |
| Build the fragment-selector target   | —                 | Not started |
| Statistics                           | —                 | Not started |
| Command-line pipeline                | `main.py`         | Placeholder |


The input OCR file starts with `width,height`. Each later line is `text x,y,width,height`. The text is everything before the last space, so a token may contain spaces or commas. Blank lines and `<EOS>` / `<EOP>` are skipped. Confidence and layout ids are not in this format; those fields on `OcrToken` stay `None`.

## Layout

```text
mention_localizer/
├── pyproject.toml
├── README.md
├── main.py
├── eil/
│   ├── models.py      # BoundingBox, OcrToken, PageImage, OcrPage,
│   │                   # EntityAnnotation, ManifestDocument
│   ├── parsing.py     # AnnotationPage → EntityAnnotation
│   ├── iiif.py        # IIIF Presentation 3 → ManifestDocument
│   ├── ocr.py         # positional OCR text → OcrPage
│   └── matching.py    # mention → enclosing boxes
└── tests/
    ├── helpers.py
    ├── test_models.py
    ├── test_parsing.py
    ├── test_iiif.py
    ├── test_ocr.py
    ├── test_ocr_corpus.py
    ├── test_matching.py
    └── test_matching_corpus.py
```



## Tests

```bash
uv sync --extra dev
uv run pytest
```

Unit tests build their own pages. Corpus tests read positional OCR under `data/` next to the package or one directory above it, and they skip when that directory is absent. They check that real pages parse, that punctuation and apostrophes stay inside tokens, and that `strict_match` returns the expected boxes for a few known strings.