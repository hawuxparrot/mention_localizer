"""
Contains parsing logic for the Entity Image Localization tool.
parse_annotation_page()
parse_entity_annotation()
"""
from typing import Any

from .models import EntityAnnotation

MENTIONED_PERSON = "ordiiif-vocab:MentionedPerson"

class AnnotationParseError(ValueError):
    """Raised when an AnnotationPage or annotation object is malformed."""

def parse_annotation_page(raw: dict[str, Any]) -> tuple[EntityAnnotation, ...]:
    """Parse an AnnotationPage into MentionedPerson annotations.

    Irrelevant annotations are omitted. A valid page with none of them
    returns an empty tuple.

    Raises:
        AnnotationParseError: If `items` is missing, not a list, an item
            is not an object, or a person annotation is malformed.
    """
    if "items" not in raw:
        raise AnnotationParseError(
            "AnnotationPage is missing required 'items' list"
        )

    items = raw["items"]
    if not isinstance(items, list):
        raise AnnotationParseError(
            f"AnnotationPage 'items' must be a list, "
            f"got {type(items).__name__}"
        )

    annotations: list[EntityAnnotation] = []

    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise AnnotationParseError(
                f"AnnotationPage item {index} must be an object, "
                f"got {type(item).__name__}"
            )

        annotation = parse_entity_annotation(item)
        if annotation is not None:
            annotations.append(annotation)

    return tuple(annotations)

def parse_entity_annotation(raw: dict[str, Any]) -> EntityAnnotation | None:
    """Parse one annotation object. Returns None if it is not a MentionedPerson.

    ``body.identifier`` is a GND URI when RdL has one. People with only a
    Haller record omit it. Localization uses the mention, so a missing
    identifier is left as ``None`` and the annotation is still returned.

    Raises:
        AnnotationParseError: If a required field is missing or malformed.
    """
    body = raw.get("body")
    if not isinstance(body, dict):
        raise AnnotationParseError("Annotation JSON is missing valid body object")
    
    purpose = body.get("purpose")
    if not isinstance(purpose, dict) or purpose.get("id") != MENTIONED_PERSON: # we care only about Persons at this stage
        return None
    
    annotation_id = raw.get("id")
    if not isinstance(annotation_id, str):
        raise AnnotationParseError("Missing or invalid annotation id")

    identifier = body.get("identifier")
    if identifier is None:
        entity_id = None
    elif isinstance(identifier, str) and identifier.strip():
        entity_id = identifier.strip()
    else:
        raise AnnotationParseError(
            f"{annotation_id}: body.identifier must be a non-empty string when present"
        )

    target_manifest = raw.get("target")
    if not isinstance(target_manifest, str):
        raise AnnotationParseError(f"{target_manifest}: missing or invalid target (must be manifest URL string)")
    
    mentions = body.get("mention")
    if not isinstance(mentions, list) or len(mentions) != 1:
        raise AnnotationParseError(
            f"{annotation_id}: expected exactly one mention"
        )

    raw_mention = mentions[0]
    if not isinstance(raw_mention, dict):
        raise AnnotationParseError(
            f"{annotation_id}: mention must be an object"
        )

    mention = raw_mention.get("value")
    if not isinstance(mention, str) or not mention.strip():
        raise AnnotationParseError(
            f"{annotation_id}: invalid mention.value"
        )

    language = raw_mention.get("language")
    if not isinstance(language, str) or not language.strip():
        language = None

    return EntityAnnotation(
        annotation_id=annotation_id,
        entity_id=entity_id,
        mention=mention,
        target_manifest=target_manifest,
        mention_language=language.strip() if language else None,
    )


