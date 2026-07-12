# SPDX-License-Identifier: Apache-2.0
"""Frozen-corpus metrics for deterministic visual QA."""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from .fixture_corpus import FixtureCorpus
from .page_qa import inspect_fixture_case
from .qa_contracts import DefectCategory, FindingSeverity, VerdictStatus


def _wilson(successes: int, total: int, z: float = 1.959963984540054) -> list[float] | None:
    if total <= 0:
        return None
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denominator
    return [max(0.0, center - margin), min(1.0, center + margin)]


def measure_fixture_corpus(corpus: FixtureCorpus) -> dict[str, Any]:
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
        category_report[category.value] = {
            **counts,
            "recall": counts["tp"] / expected_total if expected_total else None,
            "recall95CI": _wilson(counts["tp"], expected_total),
            "precision": counts["tp"] / predicted_total if predicted_total else None,
            "precision95CI": _wilson(counts["tp"], predicted_total),
            "sampleSufficient": expected_total > 0,
        }

    return {
        "schema": "hwpx.visual-qa-metrics/v1",
        "assurance": "fixture",
        "renderChecked": False,
        "counts": {
            "cases": len(corpus.cases), "expectedCritical": len(expected),
            "predictedCritical": len(predicted), "truePositive": len(true_positive),
            "falsePositive": len(false_positive), "falseNegative": len(false_negative),
        },
        "criticalRecall": recall,
        "criticalRecall95CI": _wilson(len(true_positive), len(expected)),
        "criticalPrecision": precision,
        "criticalPrecision95CI": _wilson(len(true_positive), len(predicted)),
        "defectFalseAcceptanceRate": defect_false_acceptance,
        "defectFalseAcceptance95CI": _wilson(defect_accepted, defect_total),
        "cleanFalseRejectionRate": clean_false_rejection,
        "cleanFalseRejection95CI": _wilson(clean_rejected, clean_total),
        "thresholds": {
            "criticalRecall": 0.95, "criticalPrecision": 0.90,
            "defectFalseAcceptanceRate": 0.01, "cleanFalseRejectionRate": 0.01,
        },
        "gatePassed": bool(
            recall is not None and recall >= 0.95
            and precision is not None and precision >= 0.90
            and defect_false_acceptance is not None and defect_false_acceptance <= 0.01
            and clean_false_rejection is not None and clean_false_rejection <= 0.01
        ),
        "perCategory": category_report,
        "cases": case_rows,
    }


__all__ = ["measure_fixture_corpus"]
