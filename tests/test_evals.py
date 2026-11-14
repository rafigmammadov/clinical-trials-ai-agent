"""Benchmark harness contracts; these tests do not claim live AI accuracy."""

from evals.run import balanced_sample, load_cases, matches


def test_benchmark_contains_fifty_independently_validated_cases():
    cases = load_cases()
    assert len(cases) == 50
    assert len({case["id"] for case in cases}) == 50
    assert {c["category"] for c in cases} == {
        "straightforward", "multi_filter", "network", "numeric", "adversarial",
    }


def test_short_live_benchmark_samples_all_families():
    selected = balanced_sample(load_cases(), 10)
    assert len(selected) == 10
    assert len({c["category"] for c in selected}) == 5


def test_drug_comparison_evaluation_is_case_and_order_insensitive():
    assert matches("drugs", ["LUMACAFTOR", "ivacaftor"], ["ivacaftor", "lumacaftor"])
