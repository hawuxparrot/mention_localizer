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
AnnotationPage ──► EntityAnnotation (mention, language, manifest URL)
                              │
                    search manifest URL
                    (own target or parallelVersions)
                              │
                              ▼
IIIF Manifest ──► ManifestDocument ──► PageImage (service URL, IIIF size)
                                                 │
                                    OCR index (image stem → .txt)
                                                 │
                                                 ▼
                                      positional OCR .txt
                                                 │
                                                 ▼
                                       OcrPage (tokens, OCR size)
                              │                    │
                              ├── strict_match ───────────► diagnostic count only
                              │
                              ├──── lenient_match ───────► diagnostic count
                              │
                              └───── fuzzy_match ─┘
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

1. **Annotations.** `parse_annotation_page` keeps `ordiiif-vocab:MentionedPerson` items and drops every other purpose. Each kept item becomes an `EntityAnnotation`: annotation id, optional person id (`body.identifier`, often a GND URI; many local persons have only a Haller record), one mention string, optional mention language, and the manifest URL.
2. **Manifest.** `parse_manifest` reads a IIIF Presentation 3 manifest into a `ManifestDocument`. Canvas order is the page order. Each page is a `PageImage`: image-service URL, width, and height in IIIF pixels.
3. **Grouping.** Annotations that share a manifest should be collected before any OCR file is read, so each page is parsed once and then queried many times. This stage is not written yet.
4. **OCR files.** `index_ocr_directory` maps a page-image filename to one positional `.txt` under `data/`. The filename is the last `!`-separated segment of the IIIF service URL. A missing file is an error. Two files with the same stem are an error; neither is chosen.
5. **OCR.** `parse_ocr_text` reads one positional text file onto a `PageImage` and returns an `OcrPage`: the page, the token sequence, and the width and height of the OCR coordinate space.
6. **Matching.** `strict_match` finds exact token sequences. `lenient_match` adds conservative OCR normalization and remains a diagnostic baseline. Localization uses `fuzzy_match`, which preserves every lenient hit and falls back to RapidFuzz-based, variable-length token alignment for misses. The fallback understands common titles, abbreviations, and initials, requires the first distinctive name token to match strongly, and keeps semicolon/comma clauses in the alignment and returned box instead of generating name-only query variants. It does not use phonetic encoding. All three counts are retained for comparison. `find_image_regions` runs fuzzy matching on every manifest page, in canvas order, and scales each hit into IIIF pixels. The first hit is the earliest page, then the earliest token match on that page. The scaled box is an `ImageRegion`. `ImageRegion.box` is always in the page's IIIF coordinates.
7. **Target.** `precise_target` writes the fragment selector above from that `ImageRegion`. The pipeline copies the original AnnotationPage and replaces `target` when there is at least one hit. A mention whose language differs from `journal.language` is searched on the `parallelVersions` edition of the mention's language, so a German mention on a French page uses the German manifest. Zero hits on the annotation's own manifest leave that coarse URL in place. A miss on a parallel edition leaves that edition's manifest URL. More than one hit still writes the first region, and the real match count stays on the per-annotation result. Each written crop URL is requested; a failed image response is recorded and does not stop the next annotation.

`main.py` reads one AnnotationPage JSON, writes the patched page, and prints one diagnostic line per MentionedPerson. `scripts/localize_corpus.py` does that for every RdL AnnotationPage whose volume is in the local OCR corpus, and writes `examples/statistics.json`.

## Current status


| Piece                                | Module                       | State       |
| ------------------------------------ | ---------------------------- | ----------- |
| Person annotations to mentions       | `eil/parsing.py`             | Done        |
| IIIF manifest to ordered page images | `eil/iiif.py`                | Done        |
| Positional OCR to tokens             | `eil/ocr.py`                 | Done        |
| Exact, lenient, and fuzzy matching   | `eil/matching.py`            | Done        |
| Shared types                         | `eil/models.py`              | Done        |
| Attach an OCR file to a page image   | `eil/ocr_index.py`           | Done        |
| Scale OCR boxes into IIIF pixels     | `eil/geometry.py`            | Done        |
| Mention matches across one manifest  | `eil/localize.py`            | Done        |
| Build the fragment-selector target   | `eil/targets.py`             | Done        |
| Patch the page and record each hit   | `eil/pipeline.py`            | Done        |
| Command-line pipeline                | `main.py`                    | Done        |
| Corpus run and dataset statistics    | `scripts/localize_corpus.py` | Done        |
| Group mentions by manifest ???       | —                            | Not started |


The input OCR file starts with `width,height`. Each later line is `text x,y,width,height`. The text is everything before the last space, so a token may contain spaces or commas. Blank lines and `<EOS>` / `<EOP>` are skipped. Confidence and layout ids are not in this format; those fields on `OcrToken` stay `None`.

## Corpus results

<!-- corpus-statistics:start -->
`scripts/localize_corpus.py` was run on the OCR in `data/` (15,163 page files) and the RdL annotation pages for those volumes. Published person targets are already precise, so each one was set back to a manifest URL before matching. Each AnnotationPage is one statistics unit: German (`oeg-*`) and French (`soe-*`) editions are counted separately even when a French mention is redirected to the German manifest. In that case the hit is on the German image, not the French scan. All three matchers search the same parsed OCR pages; only `fuzzy_match` writes the production target. `strict_match` and `lenient_match` are recorded for comparison. There is no ground-truth set; the rates below are matcher outcome rates, not retrieval recall against published boxes.

560 annotation pages fall in the corpus. 30 of them contain at least one `MentionedPerson` (1092 person queries in total). The other 530 do not. A missing `body.identifier` is allowed and is not counted as an error. 5 annotations are unreadable for another reason and are dropped before matching.

| Matcher | Queries | Zero | Exactly one | Multiple | Unique hit rate | Any-hit rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Strict | 1092 | 1084 | 8 | 0 | 0.7% | 0.7% |
| Lenient | 1092 | 507 | 577 | 8 | 52.8% | 53.6% |
| Fuzzy | 1092 | 163 | 901 | 28 | 82.5% | 85.1% |

Lenient matching turned 569 strict misses into exactly one hit. 8 strict misses became multiple lenient matches; 0 queries were multiple under both matchers.

Fuzzy matching turned 330 lenient misses into exactly one hit. 14 lenient misses became multiple fuzzy matches; 8 queries were multiple under both matchers.

The production fuzzy matcher wrote 929 precise targets (exactly one plus multiple). All 929 crop URLs returned an image.

| Volume | Queries | Strict one | Lenient one | Fuzzy one | Fuzzy zero | Fuzzy multiple |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `oeg-001` 1761/2 | 79 | 0 | 49 | 68 | 7 | 4 |
| `oeg-002` 1762/3 | 163 | 1 | 74 | 133 | 29 | 1 |
| `oeg-002` 1763/4 | 19 | 0 | 17 | 18 | 1 | 0 |
| `oeg-002` 1764/5 | 184 | 3 | 93 | 146 | 34 | 4 |
| `oeg-002` 1765/6 | 41 | 0 | 23 | 36 | 5 | 0 |
| `oeg-002` 1766/7 | 27 | 0 | 16 | 24 | 3 | 0 |
| `oeg-002` 1767/8 | 9 | 0 | 3 | 6 | 3 | 0 |
| `oeg-002` 1769/10 | 23 | 0 | 7 | 19 | 1 | 3 |
| `oeg-002` 1770/11 | 10 | 0 | 3 | 5 | 1 | 4 |
| `oeg-002` 1771/12 | 2 | 0 | 0 | 0 | 1 | 1 |
| `oeg-003` 1779/1 | 48 | 0 | 31 | 43 | 5 | 0 |
| `soe-001` 1761/2 | 79 | 0 | 49 | 68 | 7 | 4 |
| `soe-001` 1762/3 | 105 | 1 | 53 | 86 | 19 | 0 |
| `soe-001` 1763/4 | 19 | 0 | 17 | 18 | 1 | 0 |
| `soe-001` 1764/5 | 184 | 3 | 93 | 146 | 34 | 4 |
| `soe-001` 1765/6 | 41 | 0 | 23 | 36 | 5 | 0 |
| `soe-001` 1766/7 | 27 | 0 | 16 | 24 | 3 | 0 |
| `soe-001` 1767/8 | 9 | 0 | 3 | 6 | 3 | 0 |
| `soe-001` 1769/10 | 23 | 0 | 7 | 19 | 1 | 3 |

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
│   ├── matching.py    # strict, lenient, and fuzzy mention matching
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
    ├── test_pipeline.py
    └── test_corpus_statistics.py
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

Run `make setup` once before this. Unit tests build their own pages. Corpus tests read `data/` and skip when it is absent. They check that real pages parse, that punctuation and apostrophes stay inside tokens, and that all three matchers return the expected boxes for representative strings. `tests/test_corpus_statistics.py` checks the aggregate counters behind `examples/statistics.json` and the Corpus results block above.