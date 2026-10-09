"""
Contains matching logic for the Entity Image Localization tool.
normalize_text()
prepare_mention()
strict_match()
lenient_match()
"""
import re
import unicodedata

from .models import BoundingBox, OcrPage, OcrToken

_ETC = re.compile(r"u\s*\.\s*\[\s*s\s*\.\s*w\s*\.\s*\]", re.IGNORECASE)
_BRACKETS = re.compile(r"\[[^\]]*\]")
_PARENTHESES = re.compile(r"\([^)]*\)")
_LEADING_MARKUP = re.compile(r"^[\s*.…]+")


def normalize_text(text: str) -> str:
    """Apply conservative normalization for strict matching."""
    text = unicodedata.normalize("NFKC", text)
    text = text.casefold()
    return " ".join(text.split())


def prepare_mention(mention: str) -> str:
    """Drop editorial markup that is not printed on the page.

    Removes a leading ``*``, ``...``, or ``..``, bracketed notes such as
    ``[frz.: ...]``, ``[?]``, and ``u.[s.w.]``, and parenthetical notes
    such as ``(*=Mitglied der engern Gesellschaft)``. Printed
    abbreviations such as ``v.`` are left as written.
    """
    text = _ETC.sub(" ", mention)
    text = _BRACKETS.sub(" ", text)
    text = _PARENTHESES.sub(" ", text)
    previous = None
    while previous != text:
        previous = text
        text = _LEADING_MARKUP.sub("", text)
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


_HYPHENATION_END = re.compile(r"[-‐‑‒–—―\u00ad¬]+$")


def lenient_match(
    query: str,
    ocr_page: OcrPage,
) -> tuple[BoundingBox, ...]:
    """Return enclosing boxes for mentions that survive OCR noise.

    The query is the mention after ``prepare_mention``. Clinging
    punctuation is ignored, and punctuation-only OCR tokens are skipped,
    so ``1761`` matches ``1761.`` A token that ends in a line-break
    hyphen is rejoined with the next token before comparison. Tokens of
    one or two characters, and ``v.`` against ``von``, must still match
    exactly. A longer token may differ by one edit when it has at most
    five characters, or by two edits when it is longer, and the lengths
    may differ by at most one.
    """
    query_keys = tuple(
        key
        for key in (_comparison_key(token) for token in prepare_mention(query).split())
        if key
    )
    if not query_keys:
        raise ValueError("Query must contain text")

    ocr_tokens = tuple(
        token
        for token in ocr_page.tokens
        if _comparison_key(token.text)
    )
    ocr_groups = _rejoin_hyphenated(ocr_tokens)
    ocr_keys = tuple(_group_key(group) for group in ocr_groups)

    window_size = len(query_keys)
    matches: list[BoundingBox] = []
    for start in range(len(ocr_keys) - window_size + 1):
        end = start + window_size
        if not _window_matches(query_keys, ocr_keys[start:end]):
            continue
        matched = tuple(
            token
            for group in ocr_groups[start:end]
            for token in group
        )
        matches.append(_enclose(matched))
    return tuple(matches)


def _rejoin_hyphenated(
    tokens: tuple[OcrToken, ...],
) -> tuple[tuple[OcrToken, ...], ...]:
    """Join an end-of-line hyphen token with the token that continues it."""
    groups: list[tuple[OcrToken, ...]] = []
    index = 0
    while index < len(tokens):
        if index + 1 < len(tokens) and _HYPHENATION_END.search(tokens[index].text):
            groups.append((tokens[index], tokens[index + 1]))
            index += 2
        else:
            groups.append((tokens[index],))
            index += 1
    return tuple(groups)


def _group_key(group: tuple[OcrToken, ...]) -> str:
    if len(group) == 1:
        return _comparison_key(group[0].text)
    first, second = group
    return _comparison_key(_HYPHENATION_END.sub("", first.text) + second.text)


def _window_matches(query_keys: tuple[str, ...], ocr_keys: tuple[str, ...]) -> bool:
    return all(
        _tokens_close(query_key, ocr_key)
        for query_key, ocr_key in zip(query_keys, ocr_keys, strict=True)
    )


def _enclose(tokens: tuple[OcrToken, ...]) -> BoundingBox:
    return BoundingBox.enclosing(tuple(token.box for token in tokens))


def _comparison_key(token: str) -> str:
    text = normalize_text(token)
    start = 0
    end = len(text)
    while start < end and _is_punctuation(text[start]):
        start += 1
    while end > start and _is_punctuation(text[end - 1]):
        end -= 1
    return text[start:end]


def _is_punctuation(char: str) -> bool:
    return unicodedata.category(char).startswith("P")


def _tokens_close(query_key: str, ocr_key: str) -> bool:
    if query_key == ocr_key:
        return True
    if min(len(query_key), len(ocr_key)) <= 2:
        return False
    if abs(len(query_key) - len(ocr_key)) > 1:
        return False
    limit = 1 if max(len(query_key), len(ocr_key)) <= 5 else 2
    return _within_edit_distance(query_key, ocr_key, limit)


def _within_edit_distance(left: str, right: str, limit: int) -> bool:
    if abs(len(left) - len(right)) > limit:
        return False
    previous = list(range(len(right) + 1))
    for index, left_char in enumerate(left, start=1):
        current = [index]
        row_min = index
        for column, right_char in enumerate(right, start=1):
            cost = 0 if left_char == right_char else 1
            value = min(
                previous[column] + 1,
                current[column - 1] + 1,
                previous[column - 1] + cost,
            )
            current.append(value)
            row_min = min(row_min, value)
        if row_min > limit:
            return False
        previous = current
    return previous[-1] <= limit