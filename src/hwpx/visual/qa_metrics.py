# SPDX-License-Identifier: Apache-2.0
"""Frozen-corpus metrics for deterministic visual QA."""
from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

from .fixture_corpus import FixtureCorpus
from .page_qa import inspect_fixture_case
from .qa_contracts import TAXONOMY_VERSION, DefectCategory, FindingSeverity, VerdictStatus


DEFAULT_MINIMUM_CATEGORY_SAMPLES = 5
GATE_THRESHOLDS = {
    "criticalRecall": 0.95,
    "criticalPrecision": 0.90,
    "defectFalseAcceptanceRate": 0.01,
    "cleanFalseRejectionRate": 0.01,
}


def _wilson(successes: int, total: int, z: float = 1.959963984540054) -> list[float] | None:
    if total <= 0:
        return None
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denominator
    return [max(0.0, center - margin), min(1.0, center + margin)]


def _required_category_contract(
    required_categories: Iterable[DefectCategory | str] | None,
    provenance: Mapping[str, Any] | None,
) -> tuple[tuple[str, ...], dict[str, Any]]:
    taxonomy = tuple(category.value for category in DefectCategory)
    if required_categories is None:
        return taxonomy, {
            "mode": "full_taxonomy",
            "taxonomyVersion": TAXONOMY_VERSION,
        }

    normalized: list[str] = []
    for category in required_categories:
        value = category.value if isinstance(category, DefectCategory) else str(category)
        if value not in taxonomy:
            raise ValueError(f"unsupported required visual-QA category: {value!r}")
        if value not in normalized:
            normalized.append(value)
    if not normalized:
        raise ValueError("required visual-QA categories cannot be empty")

    narrowed = set(normalized) != set(taxonomy)
    provenance_copy = dict(provenance or {})
    if narrowed:
        missing = [key for key in ("reason", "source") if not provenance_copy.get(key)]
        if missing:
            raise ValueError(
                "narrowed required visual-QA categories require provenance fields: "
                + ", ".join(missing)
            )
        provenance_copy["mode"] = "explicitly_narrowed"
    else:
        provenance_copy.setdefault("mode", "explicit_full_taxonomy")
    provenance_copy.setdefault("taxonomyVersion", TAXONOMY_VERSION)
    return tuple(normalized), provenance_copy


def measure_fixture_corpus(
    corpus: FixtureCorpus,
    *,
    required_categories: Iterable[DefectCategory | str] | None = None,
    minimum_category_samples: int = DEFAULT_MINIMUM_CATEGORY_SAMPLES,
    required_categories_provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if minimum_category_samples < 1:
        raise ValueError("minimum_category_samples must be at least 1")
    required, scope_provenance = _required_category_contract(
        required_categories,
        required_categories_provenance,
    )
    expected: set[tuple[str, int, str]] = set()
    predicted: set[tuple[str, int, str]] = set()
    per_category: dict[str, dict[str, int]] = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    clean_total = clean_rejected = defect_total = defect_accepted = 0
    case_rows: list[dict[str, Any]] = []

    for case in corpus.cases:
        if any(annotation.label_status != "adjudicated" for annotation in case.annotations):
            raise ValueError(f"case {case.case_id} has non-adjudicated annotations")
        verdict = inspect_fixture_case(case)
        expected_case = {
            (case.case_id, item.page, item.category.value)
            for item in case.annotations
            if item.severity is FindingSeverity.CRITICAL
        }
        predicted_case = {
            (case.case_id, item.page, item.category.value)
            for item in verdict.findings
            if item.severity is FindingSeverity.CRITICAL
        }
        expected.update(expected_case)
        predicted.update(predicted_case)
        if case.classification == "clean":
            clean_total += 1
            clean_rejected += int(verdict.status is not VerdictStatus.PASS)
        else:
            defect_total += 1
            defect_accepted += int(verdict.status is VerdictStatus.PASS)
        case_rows.append({
            "caseId": case.case_id,
            "classification": case.classification,
            "status": verdict.status.value,
            "renderChecked": verdict.render_checked,
            "expectedCritical": len(expected_case),
            "predictedCritical": len(predicted_case),
        })

    true_positive = expected & predicted
    false_positive = predicted - expected
    false_negative = expected - predicted
    for _case, _page, category in true_positive:
        per_category[category]["tp"] += 1
    for _case, _page, category in false_positive:
        per_category[category]["fp"] += 1
    for _case, _page, category in false_negative:
        per_category[category]["fn"] += 1

    recall = len(true_positive) / len(expected) if expected else None
    precision = len(true_positive) / len(predicted) if predicted else None
    defect_false_acceptance = defect_accepted / defect_total if defect_total else None
    clean_false_rejection = clean_rejected / clean_total if clean_total else None
    category_report: dict[str, dict[str, Any]] = {}
    for category in DefectCategory:
        counts = per_category[category.value]
        expected_total = counts["tp"] + counts["fn"]
        predicted_total = counts["tp"] + counts["fp"]
        recall_ci = _wilson(counts["tp"], expected_total)
        precision_ci = _wilson(counts["tp"], predicted_total)
        is_required = category.value in required
        category_report[category.value] = {
            **counts,
            "recall": counts["tp"] / expected_total if expected_total else None,
            "recall95CI": recall_ci,
            "precision": counts["tp"] / predicted_total if predicted_total else None,
            "precision95CI": precision_ci,
            "required": is_required,
            "minimumSamples": minimum_category_samples if is_required else None,
            "sampleSufficient": bool(
                not is_required or expected_total >= minimum_category_samples
            ),
            "recallLowerBoundPassed": bool(
                not is_required
                or (recall_ci is not None and recall_ci[0] >= GATE_THRESHOLDS["criticalRecall"])
            ),
        }

    recall_ci = _wilson(len(true_positive), len(expected))
    precision_ci = _wilson(len(true_positive), len(predicted))
    defect_false_acceptance_ci = _wilson(defect_accepted, defect_total)
    clean_false_rejection_ci = _wilson(clean_rejected, clean_total)
    required_coverage_passed = all(
        category_report[category]["sampleSufficient"] for category in required
    )
    required_recall_bounds_passed = all(
        category_report[category]["recallLowerBoundPassed"] for category in required
    )
    aggregate_bounds = {
        "criticalRecallLower": bool(
            recall_ci is not None and recall_ci[0] >= GATE_THRESHOLDS["criticalRecall"]
        ),
        "criticalPrecisionLower": bool(
            precision_ci is not None
            and precision_ci[0] >= GATE_THRESHOLDS["criticalPrecision"]
        ),
        "defectFalseAcceptanceUpper": bool(
            defect_false_acceptance_ci is not None
            and defect_false_acceptance_ci[1]
            <= GATE_THRESHOLDS["defectFalseAcceptanceRate"]
        ),
        "cleanFalseRejectionUpper": bool(
            clean_false_rejection_ci is not None
            and clean_false_rejection_ci[1]
            <= GATE_THRESHOLDS["cleanFalseRejectionRate"]
        ),
    }
    failed_requirements: list[str] = []
    for category in required:
        if not category_report[category]["sampleSufficient"]:
            failed_requirements.append(f"category:{category}:minimum_samples")
        elif not category_report[category]["recallLowerBoundPassed"]:
            failed_requirements.append(f"category:{category}:recall_lower_bound")
    failed_requirements.extend(
        f"aggregate:{name}" for name, passed in aggregate_bounds.items() if not passed
    )

    return {
        "schema": "hwpx.visual-qa-metrics/v2",
        "assurance": "fixture",
        "renderChecked": False,
        "counts": {
            "cases": len(corpus.cases), "expectedCritical": len(expected),
            "predictedCritical": len(predicted), "truePositive": len(true_positive),
            "falsePositive": len(false_positive), "falseNegative": len(false_negative),
        },
        "criticalRecall": recall,
        "criticalRecall95CI": recall_ci,
        "criticalPrecision": precision,
        "criticalPrecision95CI": precision_ci,
        "defectFalseAcceptanceRate": defect_false_acceptance,
        "defectFalseAcceptance95CI": defect_false_acceptance_ci,
        "cleanFalseRejectionRate": clean_false_rejection,
        "cleanFalseRejection95CI": clean_false_rejection_ci,
        "gateContract": {
            "requiredCategories": list(required),
            "minimumCategorySamples": minimum_category_samples,
            "scopeProvenance": scope_provenance,
            "requiredCoveragePassed": required_coverage_passed,
            "requiredRecallBoundsPassed": required_recall_bounds_passed,
            "aggregateBounds": aggregate_bounds,
            "failedRequirements": failed_requirements,
        },
        "thresholds": dict(GATE_THRESHOLDS),
        "gatePassed": not failed_requirements,
        "perCategory": category_report,
        "cases": case_rows,
    }


__all__ = [
    "DEFAULT_MINIMUM_CATEGORY_SAMPLES",
    "GATE_THRESHOLDS",
    "measure_fixture_corpus",
]
