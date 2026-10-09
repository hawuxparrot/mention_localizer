from scripts.localize_corpus import (
    _empty_counts,
    _format_readme_statistics,
    _record_comparison,
    _record_match,
    _statistics,
)


def test_corpus_statistics_separate_strict_and_lenient_matches() -> None:
    page = _empty_counts()
    page["persons"] = 3
    page["precise_targets"] = 2
    for strict, lenient in ((0, 1), (2, 2), (0, 0)):
        _record_match(page["matching"]["strict"], strict)
        _record_match(page["matching"]["lenient"], lenient)
        _record_comparison(page["matching"], strict, lenient)

    statistics = _statistics(10, 1, [page], {"oeg-001_1761_2": page})

    assert statistics["matching"]["strict"] == {
        "total_queries": 3,
        "zero_matches": 2,
        "exactly_one_match": 0,
        "multiple_matches": 1,
        "unique_recall": 0.0,
        "found_rate": 1 / 3,
    }
    assert statistics["matching"]["lenient"] == {
        "total_queries": 3,
        "zero_matches": 1,
        "exactly_one_match": 1,
        "multiple_matches": 1,
        "unique_recall": 1 / 3,
        "found_rate": 2 / 3,
    }
    assert statistics["matching"]["strict_zero_lenient_one"] == 1
    assert statistics["matching"]["strict_multiple_lenient_multiple"] == 1
    readme = _format_readme_statistics(statistics)
    assert "| Strict | 3 | 2 | 0 | 1 | 0.0% | 33.3% |" in readme
    assert "| Lenient | 3 | 1 | 1 | 1 | 33.3% | 66.7% |" in readme
