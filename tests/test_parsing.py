import pytest

from eil.parsing import AnnotationParseError, parse_annotation_page, parse_entity_annotation

MENTIONED_PERSON = "ordiiif-vocab:MentionedPerson"


def person_annotation(
    annotation_id: str = "https://example.org/ann/1",
    mention: str = "Haller",
    identifier: str = "https://example.org/person/1",
    target: str = "https://example.org/manifest",
) -> dict:
    return {
        "id": annotation_id,
        "body": {
            "purpose": {"id": MENTIONED_PERSON},
            "identifier": identifier,
            "mention": [{"value": mention}],
        },
        "target": target,
    }


def test_parse_entity_annotation_returns_mentioned_person() -> None:
    annotation = parse_entity_annotation(person_annotation())
    assert annotation is not None
    assert annotation.annotation_id == "https://example.org/ann/1"
    assert annotation.entity_id == "https://example.org/person/1"
    assert annotation.mention == "Haller"
    assert annotation.mention_language is None
    assert annotation.target_manifest == "https://example.org/manifest"


def test_parse_entity_annotation_keeps_mention_language() -> None:
    raw = person_annotation()
    raw["body"]["mention"][0]["language"] = "de"
    annotation = parse_entity_annotation(raw)
    assert annotation is not None
    assert annotation.mention_language == "de"


def test_parse_entity_annotation_allows_missing_identifier() -> None:
    raw = person_annotation(mention="Hunziger, Pfarrhr. zu Beltheim")
    del raw["body"]["identifier"]
    annotation = parse_entity_annotation(raw)
    assert annotation is not None
    assert annotation.entity_id is None
    assert annotation.mention == "Hunziger, Pfarrhr. zu Beltheim"


def test_parse_entity_annotation_rejects_blank_identifier() -> None:
    raw = person_annotation()
    raw["body"]["identifier"] = "  "
    with pytest.raises(AnnotationParseError, match="body.identifier"):
        parse_entity_annotation(raw)


def test_parse_entity_annotation_ignores_non_person() -> None:
    raw = person_annotation()
    raw["body"]["purpose"] = {"id": "ordiiif-vocab:MentionedPlace"}
    assert parse_entity_annotation(raw) is None


def test_parse_entity_annotation_missing_body_raises() -> None:
    with pytest.raises(AnnotationParseError, match="missing valid body object"):
        parse_entity_annotation({"id": "https://example.org/ann/1"})


def test_parse_entity_annotation_missing_id_raises() -> None:
    raw = person_annotation()
    del raw["id"]
    with pytest.raises(AnnotationParseError, match="Missing or invalid annotation id"):
        parse_entity_annotation(raw)


def test_parse_entity_annotation_requires_exactly_one_mention() -> None:
    raw = person_annotation()
    raw["body"]["mention"] = []
    with pytest.raises(AnnotationParseError, match="expected exactly one mention"):
        parse_entity_annotation(raw)


def test_parse_annotation_page_collects_only_mentioned_persons() -> None:
    place = person_annotation(annotation_id="https://example.org/ann/place")
    place["body"]["purpose"] = {"id": "ordiiif-vocab:MentionedPlace"}
    result = parse_annotation_page(
        {"items": [place, person_annotation(mention="Euler")]}
    )
    assert len(result) == 1
    assert result[0].mention == "Euler"


def test_parse_annotation_page_empty_items_returns_empty_tuple() -> None:
    assert parse_annotation_page({"items": []}) == ()


def test_parse_annotation_page_missing_items_raises() -> None:
    with pytest.raises(AnnotationParseError, match="missing required 'items' list"):
        parse_annotation_page({})


def test_parse_annotation_page_invalid_items_raises() -> None:
    with pytest.raises(AnnotationParseError, match="must be a list"):
        parse_annotation_page({"items": {"id": "not-a-list"}})


def test_parse_annotation_page_non_dict_item_raises() -> None:
    with pytest.raises(AnnotationParseError, match="item 1 must be an object"):
        parse_annotation_page({"items": [person_annotation(), 42]})
