"""
Contains matching logic for the Entity Image Localization tool.
normalize_text()
prepare_mention()
strict_match()
lenient_match()
"""
import re
import unicodedata

from rapidfuzz.distance import JaroWinkler, Levenshtein

from .models import BoundingBox, OcrPage, OcrToken

_ETC = re.compile(r"u\s*\.\s*\[\s*s\s*\.\s*w\s*\.\s*\]", re.IGNORECASE)
_MEMBERSHIP_NOTE = re.compile(
    r"\s+\((?:\*=?[^)]*Mitglied[^)]*|=Mitglied der engern Gesellschaft)\)$",
    re.IGNORECASE,
)
_ABBREVIATIONS = {
    "v": "von",
    "hr": "herr",
    "hn": "herr",
    "pf": "pfarrer",
    "pfr": "pfarrer",
    "oberpfr": "pfarrer",
    "ab": "abt",
    "frhr": "freyherr",
    "freih": "freyherr",
    "pr": "praesident",
    "prof": "professor",
    "sek": "sekretaer",
}
_LOW_INFORMATION = {
    "am",
    "an",
    "auf",
    "aus",
    "bei",
    "de",
    "der",
    "des",
    "die",
    "du",
    "en",
    "et",
    "im",
    "in",
    "la",
    "le",
    "und",
    "von",
    "zu",
    "zur",
}
_TITLES = {
    "abt",
    "baron",
    "doktor",
    "frau",
    "freyherr",
    "fürst",
    "graf",
    "hauptmann",
    "herr",
    "marchese",
    "pastor",
    "pfarrer",
    "praesident",
    "professor",
    "sekretaer",
}


def normalize_text(text: str) -> str:
    """Apply conservative normalization for strict matching."""
    text = unicodedata.normalize("NFKC", text)
    text = text.casefold()
    return " ".join(text.split())


def prepare_mention(mention: str) -> str:
    """Drop known RdL editorial additions that are not printed on the page.

    Removes ``u.[s.w.]`` and terminal membership notes such as
    ``(*=Mitglied der engern Gesellschaft)``. Other bracketed and
    parenthesized text is preserved.
    """
    text = _ETC.sub(" ", mention)
    text = _MEMBERSHIP_NOTE.sub("", text)
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


def lenient_match(
    query: str,
    ocr_page: OcrPage,
) -> tuple[BoundingBox, ...]:
    """Return enclosing boxes for mentions that survive OCR noise.

    The query is the mention after ``prepare_mention``. Clinging
    punctuation is ignored, and punctuation-only OCR tokens are skipped,
    so ``1761`` matches ``1761.`` The OCR line-break marker ``¬`` is
    rejoined; ordinary ``-`` is rejoined only when coordinates show that
    the next token starts leftward on a lower line. Tokens of
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


def fuzzy_match(
    query: str,
    ocr_page: OcrPage,
) -> tuple[BoundingBox, ...]:
    """Return conservative name-aware fuzzy matches for ``query``.

    Existing lenient hits are returned unchanged. For a lenient miss, this
    matcher aligns variable-length token sequences using RapidFuzz
    similarities. Known title abbreviations and initials receive explicit
    treatment, while short function words are never matched fuzzily. At least
    one distinctive token must match strongly, which avoids accepting a span
    based only on titles and words such as ``von`` or ``zu``.
    """
    lenient = lenient_match(query, ocr_page)
    if lenient:
        return lenient

    ocr_tokens = tuple(
        token
        for token in ocr_page.tokens
        if _comparison_key(token.text)
    )
    ocr_groups = _rejoin_hyphenated(ocr_tokens)
    ocr_keys = tuple(_group_key(group) for group in ocr_groups)
    if not ocr_keys:
        return ()

    candidates: list[tuple[float, int, int]] = []
    for query_keys in _fuzzy_query_variants(query):
        strong_indexes = tuple(
            index
            for index, key in enumerate(query_keys)
            if _is_distinctive(key)
        )
        if not strong_indexes:
            continue

        # The first distinctive token is the name core in RdL entries (after
        # optional initials/titles). Requiring it prevents a wrong person from
        # matching merely because a later place or office is identical.
        for query_index in strong_indexes[:1]:
            query_key = query_keys[query_index]
            for ocr_index, ocr_key in enumerate(ocr_keys):
                anchor_score = _token_similarity(query_key, ocr_key)
                if anchor_score < 0.88:
                    continue
                for start, end in _candidate_windows(
                    len(query_keys),
                    query_index,
                    ocr_index,
                    len(ocr_keys),
                ):
                    window = ocr_keys[start:end]
                    score = _alignment_score(query_keys, window)
                    threshold = 0.93 if len(query_keys) == 1 else 0.80
                    if score >= threshold:
                        candidates.append((score, start, end))

    selected: list[tuple[float, int, int]] = []
    for candidate in sorted(candidates, reverse=True):
        _score, start, end = candidate
        if any(start < kept_end and kept_start < end for _, kept_start, kept_end in selected):
            continue
        selected.append(candidate)

    boxes = []
    for _score, start, end in sorted(selected, key=lambda item: item[1]):
        matched = tuple(
            token
            for group in ocr_groups[start:end]
            for token in group
        )
        boxes.append(_enclose(matched))
    return tuple(boxes)


def _fuzzy_query_variants(query: str) -> tuple[tuple[str, ...], ...]:
    prepared = prepare_mention(query)
    keys = tuple(
        key
        for key in (_comparison_key(token) for token in prepared.split())
        if key
    )
    return (keys,) if keys else ()


def _candidate_windows(
    query_length: int,
    query_anchor: int,
    ocr_anchor: int,
    ocr_length: int,
) -> tuple[tuple[int, int], ...]:
    slack = min(3, max(1, query_length // 4))
    windows = set()
    expected_start = ocr_anchor - query_anchor
    minimum = max(1, query_length - slack)
    maximum = query_length + slack
    for start in range(expected_start - slack, expected_start + slack + 1):
        if start < 0 or start >= ocr_length:
            continue
        for length in range(minimum, maximum + 1):
            end = min(start + length, ocr_length)
            if start <= ocr_anchor < end:
                windows.add((start, end))
    return tuple(windows)


def _alignment_score(
    query_keys: tuple[str, ...],
    ocr_keys: tuple[str, ...],
) -> float:
    weights = tuple(_token_weight(key) for key in query_keys)
    previous = [sum(0.35 for _ in ocr_keys[:column]) for column in range(len(ocr_keys) + 1)]
    for query_index, query_key in enumerate(query_keys, start=1):
        weight = weights[query_index - 1]
        current = [previous[0] + 0.55 * weight]
        for ocr_index, ocr_key in enumerate(ocr_keys, start=1):
            similarity = _token_similarity(query_key, ocr_key)
            current.append(
                min(
                    previous[ocr_index] + 0.55 * weight,
                    current[ocr_index - 1] + 0.35,
                    previous[ocr_index - 1] + (1.0 - similarity) * weight,
                )
            )
        previous = current
    denominator = sum(weights) + 0.35 * max(0, len(ocr_keys) - len(query_keys))
    return max(0.0, 1.0 - previous[-1] / denominator)


def _token_weight(key: str) -> float:
    canonical = _canonical_token(key)
    if canonical in _LOW_INFORMATION:
        return 0.45
    if (
        key in _ABBREVIATIONS
        or canonical in _TITLES
        or _is_initial(key)
    ):
        return 0.65
    return min(2.0, max(1.0, len(key) / 4))


def _is_distinctive(key: str) -> bool:
    canonical = _canonical_token(key)
    return (
        len(key) >= 4
        and canonical not in _LOW_INFORMATION
        and canonical not in _TITLES
        and not _is_initial(key)
    )


def _canonical_token(key: str) -> str:
    canonical = _ABBREVIATIONS.get(key, key)
    return (
        canonical.replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("ß", "ss")
    )


def _is_initial(key: str) -> bool:
    letters = "".join(char for char in key if char.isalpha())
    return bool(letters) and len(letters) <= 3 and "." in key


def _token_similarity(left: str, right: str) -> float:
    if left == right:
        return 1.0
    left_canonical = _canonical_token(left)
    right_canonical = _canonical_token(right)
    if left_canonical == right_canonical:
        return 0.98
    if _is_initial(left) or _is_initial(right):
        left_letters = "".join(char for char in left if char.isalpha())
        right_letters = "".join(char for char in right if char.isalpha())
        if left_letters and right_letters and left_letters[0] == right_letters[0]:
            return 0.90
        return 0.0
    if min(len(left_canonical), len(right_canonical)) <= 2:
        return 0.0
    if left_canonical in _LOW_INFORMATION or right_canonical in _LOW_INFORMATION:
        return 0.0
    return max(
        JaroWinkler.normalized_similarity(left_canonical, right_canonical),
        Levenshtein.normalized_similarity(left_canonical, right_canonical),
    )


def _rejoin_hyphenated(
    tokens: tuple[OcrToken, ...],
) -> tuple[tuple[OcrToken, ...], ...]:
    """Join OCR tokens that continue on the next line."""
    groups: list[tuple[OcrToken, ...]] = []
    index = 0
    while index < len(tokens):
        if index + 1 < len(tokens) and _continues_on_next_line(
            tokens[index],
            tokens[index + 1],
        ):
            groups.append((tokens[index], tokens[index + 1]))
            index += 2
        else:
            groups.append((tokens[index],))
            index += 1
    return tuple(groups)


def _continues_on_next_line(first: OcrToken, second: OcrToken) -> bool:
    if first.text.endswith("¬"):
        return True
    return (
        first.text.endswith("-")
        and second.box.x < first.box.x
        and second.box.y > first.box.y
    )


def _group_key(group: tuple[OcrToken, ...]) -> str:
    if len(group) == 1:
        return _comparison_key(group[0].text)
    first, second = group
    return _comparison_key(first.text.rstrip("-¬") + second.text)


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