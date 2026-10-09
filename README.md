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
                              └──── lenient_match ─┘
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
6. **Matching.** `strict_match` finds exact token sequences. Localization uses `lenient_match`, while both counts are retained for diagnostics. Lenient matching drops only known RdL editorial additions (`u.[s.w.]` and terminal membership notes), preserves other parentheses and brackets, rejoins OCR words split with `¬`, and rejoins ordinary `-` only when token coordinates show a line break. It also ignores punctuation stuck to a token and allows a small per-token edit distance for OCR substitutions. `v.` is not expanded to `von`. `find_image_regions` runs lenient matching on every manifest page, in canvas order, and scales each hit into IIIF pixels. The first hit is the earliest page, then the earliest token match on that page. The scaled box is an `ImageRegion`. `ImageRegion.box` is always in the page's IIIF coordinates.
7. **Target.** `precise_target` writes the fragment selector above from that `ImageRegion`. The pipeline copies the original AnnotationPage and replaces `target` when there is at least one hit. A mention whose language differs from `journal.language` is searched on the `parallelVersions` edition of the mention's language, so a German mention on a French page uses the German manifest. Zero hits on the annotation's own manifest leave that coarse URL in place. A miss on a parallel edition leaves that edition's manifest URL. More than one hit still writes the first region, and the real match count stays on the per-annotation result. Each written crop URL is requested; a failed image response is recorded and does not stop the next annotation.

`main.py` reads one AnnotationPage JSON, writes the patched page, and prints one diagnostic line per MentionedPerson. `scripts/localize_corpus.py` does that for every RdL AnnotationPage whose volume is in the local OCR corpus, and writes `examples/statistics.json`.

## Current status


| Piece                                | Module            | State       |
| ------------------------------------ | ----------------- | ----------- |
| Person annotations to mentions       | `eil/parsing.py`  | Done        |
| IIIF manifest to ordered page images | `eil/iiif.py`     | Done        |
| Positional OCR to tokens             | `eil/ocr.py`      | Done        |
| Exact and lenient mention matching   | `eil/matching.py` | Done        |
| Shared types                         | `eil/models.py`   | Done        |
| Attach an OCR file to a page image   | `eil/ocr_index.py` | Done        |
| Scale OCR boxes into IIIF pixels     | `eil/geometry.py` | Done        |
| Mention matches across one manifest  | `eil/localize.py` | Done        |
| Build the fragment-selector target   | `eil/targets.py`  | Done        |
| Patch the page and record each hit   | `eil/pipeline.py` | Done        |
| Command-line pipeline                | `main.py`         | Done        |
| Corpus run and dataset statistics    | `scripts/localize_corpus.py` | Done |
| Group mentions by manifest           | —                 | Not started |


The input OCR file starts with `width,height`. Each later line is `text x,y,width,height`. The text is everything before the last space, so a token may contain spaces or commas. Blank lines and `<EOS>` / `<EOP>` are skipped. Confidence and layout ids are not in this format; those fields on `OcrToken` stay `None`.

## Corpus results

<!-- corpus-statistics:start -->
`scripts/localize_corpus.py` was run on the OCR in `data/` (15,163 page files) and the RdL annotation pages for those volumes. Published person targets are already precise, so each one was set back to a manifest URL before matching. A mention whose language differs from the journal is searched on the parallel edition of that language: a German mention on a French page is matched against the German manifest, and the box is on the German image. Both matchers search the same parsed OCR pages; `lenient_match` supplies the production target.

560 annotation pages fall in the corpus. 30 of them contain a `MentionedPerson`. The other 530 do not. A missing `body.identifier` is allowed: that field is a GND URI, and many local persons have only a Haller record. 5 annotations are still unreadable for another reason.

| Matcher | Queries | Zero | Exactly one | Multiple | Unique recall | Found rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Strict | 1092 | 1084 | 8 | 0 | 0.7% | 0.7% |
| Lenient | 1092 | 507 | 577 | 8 | 52.8% | 53.6% |

Lenient matching uniquely rescued 569 strict misses. 8 strict misses became multiple lenient matches; 0 queries were multiple under both matchers.

The production lenient matcher wrote 585 precise targets. All 585 crop URLs returned an image. The French-page hits are the same kind of result as the German edition they were redirected to, not boxes on the French scan. The published French boxes were not used as ground truth.

| Volume | Queries | Strict one | Lenient one | Lenient zero | Lenient multiple |
| --- | ---: | ---: | ---: | ---: | ---: |
| `oeg-001` 1761/2 | 79 | 0 | 49 | 29 | 1 |
| `oeg-002` 1762/3 | 163 | 1 | 74 | 89 | 0 |
| `oeg-002` 1763/4 | 19 | 0 | 17 | 2 | 0 |
| `oeg-002` 1764/5 | 184 | 3 | 93 | 89 | 2 |
| `oeg-002` 1765/6 | 41 | 0 | 23 | 18 | 0 |
| `oeg-002` 1766/7 | 27 | 0 | 16 | 11 | 0 |
| `oeg-002` 1767/8 | 9 | 0 | 3 | 6 | 0 |
| `oeg-002` 1769/10 | 23 | 0 | 7 | 16 | 0 |
| `oeg-002` 1770/11 | 10 | 0 | 3 | 5 | 2 |
| `oeg-002` 1771/12 | 2 | 0 | 0 | 2 | 0 |
| `oeg-003` 1779/1 | 48 | 0 | 31 | 17 | 0 |
| `soe-001` 1761/2 | 79 | 0 | 49 | 29 | 1 |
| `soe-001` 1762/3 | 105 | 1 | 53 | 52 | 0 |
| `soe-001` 1763/4 | 19 | 0 | 17 | 2 | 0 |
| `soe-001` 1764/5 | 184 | 3 | 93 | 89 | 2 |
| `soe-001` 1765/6 | 41 | 0 | 23 | 18 | 0 |
| `soe-001` 1766/7 | 27 | 0 | 16 | 11 | 0 |
| `soe-001` 1767/8 | 9 | 0 | 3 | 6 | 0 |
| `soe-001` 1769/10 | 23 | 0 | 7 | 16 | 0 |

Per-page counts, crop URLs, and the patched AnnotationPages are under `examples/`. `examples/statistics.json` is the full aggregate.
<!-- corpus-statistics:end -->

## Layout

```text
mention_localizer/
├── pyproject.toml
├── README.md
├── main.py
├── scripts/
│   ├── fetch_ocr.py       # download the OCR corpus into data/
│   └── localize_corpus.py # every covered AnnotationPage → examples/
├── examples/              # generated pages, reports, statistics.json
├── eil/
│   ├── models.py      # BoundingBox, OcrToken, PageImage, OcrPage,
│   │                   # EntityAnnotation, ManifestDocument, ImageRegion
│   ├── parsing.py     # AnnotationPage → EntityAnnotation
│   ├── iiif.py        # IIIF Presentation 3 → ManifestDocument
│   ├── ocr.py         # positional OCR text → OcrPage
│   ├── ocr_index.py   # page image filename → one OCR .txt
│   ├── geometry.py    # OCR box → IIIF box
│   ├── matching.py    # strict and lenient mention matching
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
