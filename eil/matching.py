"""
Contains matching logic for the Entity Image Localization tool.
normalize_text()
strict_match()
"""
import unicodedata

from rdl_linking.models import BoundingBox, OcrPage


def normalize_text(text: str) -> str:
    """Apply conservative normalization for strict matching."""
    text = unicodedata.normalize("NFKC", text)
    text = text.casefold()
    return " ".join(text.split())


def strict_match(
    query: str,
    ocr_page: OcrPage,
) -> tuple[BoundingBox, ...]:
    """Return enclosing boxes for every exact consecutive token match of `query`.

    Zero matches yield an empty tuple. Multiple matches are all returned.
    """
    query_tokens = tuple(
        normalize_text(token)
        for token in query.split()
    )

    if not query_tokens:
        raise ValueError("Query must contain text")

    ocr_tokens = tuple(
        normalize_text(token.text)
        for token in ocr_page.tokens
    )

    window_size = len(query_tokens)
    matches: list[BoundingBox] = []

    for start in range(len(ocr_tokens) - window_size + 1):
        end = start + window_size

        if ocr_tokens[start:end] != query_tokens:
            continue

        matched_tokens = ocr_page.tokens[start:end]

        box = BoundingBox.enclosing(
            tuple(token.box for token in matched_tokens)
        )
        matches.append(box)

    return tuple(matches)