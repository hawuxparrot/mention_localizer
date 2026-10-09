from pathlib import Path

from eil.ocr_index import index_ocr_directory
from eil.parsing import MENTIONED_PERSON
from eil.pipeline import localize_annotation_page

MANIFEST = "https://example.org/manifest"
OTHER_MANIFEST = "https://example.org/manifest-2"


def _service(stem: str) -> str:
    return f"https://iiif.example.org/iiif/2/book!{stem}.jpg"


def _manifest(manifest_id: str, pages: list[tuple[str, int, int]]) -> dict:
    canvases = []
    for index, (stem, width, height) in enumerate(pages):
        service = _service(stem)
        canvases.append(
            {
                "id": f"{manifest_id}/canvas/{index}",
                "type": "Canvas",
                "items": [
                    {
                        "type": "AnnotationPage",
                        "items": [
                            {
                                "type": "Annotation",
                                "motivation": "painting",
                                "body": {
                                    "id": f"{service}/full/max/0/default.jpg",
                                    "type": "Image",
                                    "format": "image/jpeg",
                                    "width": width,
                                    "height": height,
                                    "service": [
                                        {"@id": service, "@type": "ImageService2"}
                                    ],
                                },
                            }
                        ],
                    }
                ],
            }
        )
    return {"id": manifest_id, "type": "Manifest", "items": canvases}


def _person(
    annotation_id: str,
    mention: str,
    target: str = MANIFEST,
    **extra: object,
) -> dict:
    annotation = {
        "id": annotation_id,
        "motivation": "linking",
        "type": "Annotation",
        "body": {
            "purpose": {"id": MENTIONED_PERSON},
            "identifier": "https://example.org/person/1",
            "mention": [{"value": mention, "language": "de"}],
            "label": {"de": ["Kept label"]},
        },
        "target": target,
        "custom": "stay",
    }
    annotation.update(extra)
    return annotation


def _write_ocr(
    directory: Path,
    stem: str,
    width: int,
    height: int,
    lines: list[str],
) -> None:
    path = directory / f"{stem}.txt"
    path.write_text(
        "\n".join([f"{width},{height}", *lines, ""]),
        encoding="utf-8",
    )


def _run(raw: dict, data: Path, manifests: dict[str, dict], validate):
    calls = {"manifests": [], "crops": []}

    def fetch(url: str) -> dict:
        calls["manifests"].append(url)
        if url not in manifests:
            raise RuntimeError(f"no manifest for {url}")
        return manifests[url]

    def check(url: str) -> bool:
        calls["crops"].append(url)
        return validate(url)

    run = localize_annotation_page(
        raw,
        index_ocr_directory(data),
        fetch_manifest=fetch,
        validate_crop=check,
    )
    return run, calls


def test_zero_matches_preserve_the_coarse_target_and_record_count(tmp_path) -> None:
    _write_ocr(tmp_path, "page-a", 100, 50, ["Haller 10,0,8,6"])
    raw = {
        "@context": "http://www.w3.org/ns/anno.jsonld",
        "type": "AnnotationPage",
        "items": [_person("https://example.org/ann/1", "Euler")],
    }
    run, calls = _run(
        raw,
        tmp_path,
        {MANIFEST: _manifest(MANIFEST, [("page-a", 200, 100)])},
        validate=lambda url: True,
    )

    assert run.annotation_page["items"][0]["target"] == MANIFEST
    assert run.results[0].strict_match_count == 0
    assert run.results[0].lenient_match_count == 0
    assert run.results[0].precise_target_written is False
    assert run.results[0].crop_validation_succeeded is None
    assert run.results[0].error is None
    assert calls["crops"] == []
    assert raw["items"][0]["target"] == MANIFEST


def test_one_match_writes_a_scaled_precise_target(tmp_path) -> None:
    _write_ocr(tmp_path, "page-a", 100, 50, ["Haller 10,4,8,6"])
    place = {
        "id": "https://example.org/ann/place",
        "body": {"purpose": {"id": "ordiiif-vocab:MentionedPlace"}},
        "target": "https://example.org/place-manifest",
        "note": "untouched",
    }
    raw = {
        "@context": "http://www.w3.org/ns/anno.jsonld",
        "id": "https://example.org/page",
        "type": "AnnotationPage",
        "label": "volume",
        "items": [
            place,
            _person("https://example.org/ann/1", "Haller"),
        ],
    }
    run, calls = _run(
        raw,
        tmp_path,
        {MANIFEST: _manifest(MANIFEST, [("page-a", 200, 100)])},
        validate=lambda url: True,
    )

    person = run.annotation_page["items"][1]
    service = _service("page-a")
    crop = f"{service}/20,8,16,12/full/0/default.jpg"
    assert person["target"] == {
        "rendering": [
            {"format": "image/jpeg", "type": "Image", "id": crop}
        ],
        "rdlRegion": "main",
        "source": service,
        "selector": {
            "conformsTo": "http://www.w3.org/TR/media-frags/",
            "value": "xywh=20,8,16,12",
            "type": "FragmentSelector",
        },
    }
    result = run.results[0]
    assert result.annotation_id == "https://example.org/ann/1"
    assert result.mention == "Haller"
    assert result.strict_match_count == 1
    assert result.lenient_match_count == 1
    assert result.precise_target_written is True
    assert result.crop_validation_succeeded is True
    assert result.crop_url == crop
    assert result.error is None
    assert calls["crops"] == [crop]
    assert run.annotation_page["items"][0] == place
    assert raw["items"][1]["target"] == MANIFEST


def test_strict_miss_rescued_by_lenient_matching(tmp_path) -> None:
    _write_ocr(tmp_path, "page-a", 100, 50, ["Bafel 10,4,8,6"])
    raw = {"items": [_person("https://example.org/ann/1", "Basel")]}
    run, _calls = _run(
        raw,
        tmp_path,
        {MANIFEST: _manifest(MANIFEST, [("page-a", 100, 50)])},
        validate=lambda url: True,
    )

    result = run.results[0]
    assert result.strict_match_count == 0
    assert result.lenient_match_count == 1
    assert result.precise_target_written is True


def test_matcher_multiple_counts_are_recorded_independently(tmp_path) -> None:
    _write_ocr(
        tmp_path,
        "page-a",
        100,
        50,
        ["Haller 10,1,5,5", "Hallcr 30,1,5,5"],
    )
    raw = {"items": [_person("https://example.org/ann/1", "Haller")]}
    run, _calls = _run(
        raw,
        tmp_path,
        {MANIFEST: _manifest(MANIFEST, [("page-a", 100, 50)])},
        validate=lambda url: True,
    )

    result = run.results[0]
    assert result.strict_match_count == 1
    assert result.lenient_match_count == 2


def test_multiple_matches_use_the_earliest_page_and_keep_the_count(tmp_path) -> None:
    _write_ocr(
        tmp_path,
        "early",
        100,
        50,
        ["Haller 10,1,5,5", "Haller 30,1,5,5"],
    )
    _write_ocr(tmp_path, "late", 100, 50, ["Haller 7,2,5,5"])
    raw = {"items": [_person("https://example.org/ann/1", "Haller")]}
    run, _calls = _run(
        raw,
        tmp_path,
        {
            MANIFEST: _manifest(
                MANIFEST,
                [("early", 100, 50), ("late", 100, 50)],
            )
        },
        validate=lambda url: True,
    )

    target = run.annotation_page["items"][0]["target"]
    assert target["source"] == _service("early")
    assert target["selector"]["value"] == "xywh=10,1,5,5"
    assert run.results[0].strict_match_count == 3
    assert run.results[0].lenient_match_count == 3
    assert run.results[0].precise_target_written is True
    assert "late" not in target["rendering"][0]["id"]


def test_crop_validation_failure_does_not_abort_later_annotations(tmp_path) -> None:
    _write_ocr(tmp_path, "first-page", 100, 50, ["Haller 1,2,3,4"])
    _write_ocr(tmp_path, "second-page", 100, 50, ["Euler 4,5,6,7"])
    raw = {
        "items": [
            _person("https://example.org/ann/1", "Haller", target=MANIFEST),
            _person("https://example.org/ann/2", "Euler", target=OTHER_MANIFEST),
        ]
    }

    def validate(url: str) -> bool:
        if "first-page" in url:
            raise RuntimeError("crop server down")
        return "second-page" in url

    run, calls = _run(
        raw,
        tmp_path,
        {
            MANIFEST: _manifest(MANIFEST, [("first-page", 100, 50)]),
            OTHER_MANIFEST: _manifest(OTHER_MANIFEST, [("second-page", 100, 50)]),
        },
        validate=validate,
    )

    first, second = run.results
    assert first.lenient_match_count == 1
    assert first.precise_target_written is True
    assert first.crop_validation_succeeded is False
    assert first.error is None
    assert isinstance(run.annotation_page["items"][0]["target"], dict)
    assert second.lenient_match_count == 1
    assert second.precise_target_written is True
    assert second.crop_validation_succeeded is True
    assert second.error is None
    assert calls["crops"][0].endswith("/1,2,3,4/full/0/default.jpg")
    assert calls["crops"][1].endswith("/4,5,6,7/full/0/default.jpg")
    assert calls["manifests"] == [MANIFEST, OTHER_MANIFEST]


def test_unrelated_fields_survive_output_transformation(tmp_path) -> None:
    _write_ocr(tmp_path, "page-a", 80, 40, ["Bern 0,0,4,4"])
    raw = {
        "@context": ["http://www.w3.org/ns/anno.jsonld"],
        "id": "https://example.org/page/1",
        "type": "AnnotationPage",
        "extra": {"kept": True},
        "items": [
            _person("https://example.org/ann/1", "Bern"),
            {
                "id": "https://example.org/ann/other",
                "type": "Annotation",
                "body": {
                    "purpose": {"id": "ordiiif-vocab:MentionedPlace"},
                    "value": "not a person",
                },
                "target": "https://example.org/other",
            },
        ],
    }
    run, _calls = _run(
        raw,
        tmp_path,
        {MANIFEST: _manifest(MANIFEST, [("page-a", 80, 40)])},
        validate=lambda url: True,
    )
    patched = run.annotation_page
    assert patched["@context"] == ["http://www.w3.org/ns/anno.jsonld"]
    assert patched["id"] == "https://example.org/page/1"
    assert patched["extra"] == {"kept": True}
    person = patched["items"][0]
    assert person["motivation"] == "linking"
    assert person["type"] == "Annotation"
    assert person["custom"] == "stay"
    assert person["body"]["label"] == {"de": ["Kept label"]}
    assert person["body"]["mention"][0]["language"] == "de"
    assert person["target"]["selector"]["value"] == "xywh=0,0,4,4"
    assert patched["items"][1] == raw["items"][1]
    assert len(run.results) == 1


def test_missing_ocr_is_reported_and_later_annotations_continue(tmp_path) -> None:
    _write_ocr(tmp_path, "later", 100, 50, ["Haller 9,9,2,2"])
    _write_ocr(tmp_path, "present", 100, 50, ["Euler 1,1,2,2"])
    raw = {
        "items": [
            _person("https://example.org/ann/1", "Haller", target=MANIFEST),
            _person("https://example.org/ann/2", "Euler", target=OTHER_MANIFEST),
        ]
    }
    run, calls = _run(
        raw,
        tmp_path,
        {
            MANIFEST: _manifest(
                MANIFEST,
                [("absent", 100, 50), ("later", 100, 50)],
            ),
            OTHER_MANIFEST: _manifest(OTHER_MANIFEST, [("present", 100, 50)]),
        },
        validate=lambda url: True,
    )

    failed, found = run.results
    assert failed.strict_match_count is None
    assert failed.lenient_match_count is None
    assert failed.precise_target_written is False
    assert failed.crop_validation_succeeded is None
    assert failed.error is not None
    assert "absent" in failed.error
    assert run.annotation_page["items"][0]["target"] == MANIFEST
    assert found.lenient_match_count == 1
    assert found.precise_target_written is True
    assert found.error is None
    assert calls["manifests"] == [MANIFEST, OTHER_MANIFEST]
    assert len(calls["crops"]) == 1


def test_manifest_fetch_error_does_not_abort_later_annotations(tmp_path) -> None:
    _write_ocr(tmp_path, "page-b", 20, 20, ["Euler 1,1,2,2"])
    raw = {
        "items": [
            _person("https://example.org/ann/1", "Haller", target=MANIFEST),
            _person("https://example.org/ann/2", "Euler", target=OTHER_MANIFEST),
        ]
    }
    run, _calls = _run(
        raw,
        tmp_path,
        {OTHER_MANIFEST: _manifest(OTHER_MANIFEST, [("page-b", 20, 20)])},
        validate=lambda url: True,
    )
    assert run.results[0].error is not None
    assert run.results[0].precise_target_written is False
    assert run.annotation_page["items"][0]["target"] == MANIFEST
    assert run.results[1].lenient_match_count == 1
    assert run.results[1].precise_target_written is True


def test_german_mention_on_french_page_searches_the_parallel_edition(tmp_path) -> None:
    _write_ocr(tmp_path, "french-page", 100, 50, ["Docteur 1,1,2,2"])
    _write_ocr(tmp_path, "german-page", 100, 50, ["Bourgeois 10,4,8,6"])
    french = "https://example.org/soe/manifest"
    german = "https://example.org/oeg/manifest"
    raw = {
        "type": "AnnotationPage",
        "journal": {"language": "fr"},
        "parallelVersions": [{"lang": "de", "manifestUrl": german}],
        "items": [_person("https://example.org/ann/1", "Bourgeois", target=french)],
    }
    run, calls = _run(
        raw,
        tmp_path,
        {
            french: _manifest(french, [("french-page", 100, 50)]),
            german: _manifest(german, [("german-page", 100, 50)]),
        },
        validate=lambda url: True,
    )
    assert calls["manifests"] == [german]
    target = run.annotation_page["items"][0]["target"]
    assert target["source"] == _service("german-page")
    assert target["selector"]["value"] == "xywh=10,4,8,6"
    assert run.results[0].lenient_match_count == 1


def test_german_mention_miss_records_the_parallel_manifest(tmp_path) -> None:
    _write_ocr(tmp_path, "german-page", 100, 50, ["Haller 1,1,2,2"])
    french = "https://example.org/soe/manifest"
    german = "https://example.org/oeg/manifest"
    raw = {
        "journal": {"language": "fr"},
        "parallelVersions": [{"lang": "de", "manifestUrl": german}],
        "items": [_person("https://example.org/ann/1", "Bourgeois", target=french)],
    }
    run, calls = _run(
        raw,
        tmp_path,
        {german: _manifest(german, [("german-page", 100, 50)])},
        validate=lambda url: True,
    )
    assert calls["manifests"] == [german]
    assert run.annotation_page["items"][0]["target"] == german
    assert run.results[0].lenient_match_count == 0
    assert run.results[0].precise_target_written is False


def test_matching_mention_language_keeps_the_annotation_manifest(tmp_path) -> None:
    _write_ocr(tmp_path, "german-page", 100, 50, ["Bourgeois 1,1,2,2"])
    french = "https://example.org/soe/manifest"
    german = "https://example.org/oeg/manifest"
    raw = {
        "journal": {"language": "de"},
        "parallelVersions": [{"lang": "fr", "manifestUrl": french}],
        "items": [_person("https://example.org/ann/1", "Bourgeois", target=german)],
    }
    run, calls = _run(
        raw,
        tmp_path,
        {german: _manifest(german, [("german-page", 100, 50)])},
        validate=lambda url: True,
    )
    assert calls["manifests"] == [german]
    assert run.results[0].lenient_match_count == 1
    assert run.annotation_page["items"][0]["target"]["source"] == _service("german-page")
