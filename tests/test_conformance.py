# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the Phase-G conformance corpus + badges (``hwpx.conformance``).

Deterministic and portable: the structural tiers (Open / Semantic / Form
measurement) run with no Hancom and no imaging stack, and the VisualComplete
oracle is always a fake (``visual_check`` stubbed) so these never drive Hancom.
The real-Hancom verification is the opt-in oracle run, not these tests.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.conformance import (
    CaseResult,
    ConformanceCase,
    ConformanceCorpus,
    FormSlot,
    TierVerdict,
    diff_golden,
    evaluate_badges,
    run_conformance,
)
from hwpx.conformance import runner as runner_module

GOLDEN = Path(__file__).parent / "conformance" / "golden" / "structural.json"


# --------------------------------------------------------------------------- #
# Corpus model
# --------------------------------------------------------------------------- #
def test_bundled_corpus_loads_cases() -> None:
    corpus = ConformanceCorpus.bundled()
    ids = {case.id for case in corpus.cases}
    assert {"public-notice", "public-report-table", "public-meeting-summary"} <= ids
    for case in corpus.cases:
        assert corpus.path_for(case).exists()


def test_case_applies_per_tier() -> None:
    plain = ConformanceCase(id="x", path="x.hwpx")
    assert plain.applies("open_safe") is True
    assert plain.applies("semantic_safe") is False
    assert plain.applies("form_safe") is False
    assert plain.applies("visual_complete") is True

    rich = ConformanceCase(
        id="y",
        path="y.hwpx",
        must_contain=["보고"],
        form_slots=[FormSlot(table=0, row=0, col=0, value="값")],
    )
    assert rich.applies("semantic_safe") is True
    assert rich.applies("form_safe") is True


def test_case_dict_round_trip() -> None:
    case = ConformanceCase(
        id="z",
        path="z.hwpx",
        must_contain=["A"],
        must_not_contain=["{{"],
        required_fields=["성명"],
        form_slots=[FormSlot(table=1, row=2, col=3, value="홍길동", max_lines=2)],
        note="round trip",
    )
    restored = ConformanceCase.from_dict(case.to_dict())
    assert restored == case


# --------------------------------------------------------------------------- #
# Tier evaluators
# --------------------------------------------------------------------------- #
@pytest.fixture
def corpus() -> ConformanceCorpus:
    return ConformanceCorpus.bundled()


def _bytes_for(corpus: ConformanceCorpus, case_id: str) -> bytes:
    case = next(c for c in corpus.cases if c.id == case_id)
    return corpus.path_for(case).read_bytes()


def test_open_safe_passes_for_valid_doc(corpus: ConformanceCorpus) -> None:
    case = next(c for c in corpus.cases if c.id == "public-notice")
    verdict = runner_module._eval_open_safe(_bytes_for(corpus, case.id), case)
    assert verdict.status == "pass"


def test_open_safe_fails_for_broken_package(corpus: ConformanceCorpus) -> None:
    case = next(c for c in corpus.cases if c.id == "public-notice")
    broken = _bytes_for(corpus, case.id)[:64]  # truncated -> not a readable OPC zip
    verdict = runner_module._eval_open_safe(broken, case)
    assert verdict.status == "fail"


def test_semantic_pass_and_fail(corpus: ConformanceCorpus) -> None:
    data = _bytes_for(corpus, "public-notice")
    good = ConformanceCase(id="g", path="notice.hwpx", must_contain=["운영 계획"])
    assert runner_module._eval_semantic(data, good).status == "pass"

    bad = ConformanceCase(id="b", path="notice.hwpx", must_contain=["존재하지않는문구"])
    assert runner_module._eval_semantic(data, bad).status == "fail"

    forbidden = ConformanceCase(
        id="f", path="notice.hwpx", must_not_contain=["운영 계획"]
    )
    assert runner_module._eval_semantic(data, forbidden).status == "fail"


def test_semantic_skips_without_assertions(corpus: ConformanceCorpus) -> None:
    data = _bytes_for(corpus, "public-notice")
    case = ConformanceCase(id="n", path="notice.hwpx")
    assert runner_module._eval_semantic(data, case).status == "skip"


def test_form_safe_passes_when_value_fits(corpus: ConformanceCorpus) -> None:
    data = _bytes_for(corpus, "public-report-table")
    case = next(c for c in corpus.cases if c.id == "public-report-table")
    verdict = runner_module._eval_form_safe(data, case)
    assert verdict.status == "pass"
    assert verdict.metrics["overflow_count"] == 0
    assert verdict.metrics["checked"] == 2


def test_form_safe_fails_on_high_confidence_overflow(corpus: ConformanceCorpus) -> None:
    data = _bytes_for(corpus, "public-report-table")
    # A long single-line Hangul value cannot fit a one-line cell; Hangul advance
    # is exact (high confidence), so this is a real overflow, not borderline.
    overflowing = ConformanceCase(
        id="of",
        path="report_table.hwpx",
        form_slots=[
            FormSlot(
                table=0,
                row=1,
                col=1,
                value="가" * 60,
                max_lines=1,
                label="overflow",
            )
        ],
    )
    verdict = runner_module._eval_form_safe(data, overflowing)
    assert verdict.status == "fail"
    assert verdict.metrics["overflow_count"] == 1


def test_form_safe_reports_missing_required_field(corpus: ConformanceCorpus) -> None:
    data = _bytes_for(corpus, "public-notice")  # no form fields at all
    case = ConformanceCase(
        id="rf", path="notice.hwpx", required_fields=["성명"]
    )
    verdict = runner_module._eval_form_safe(data, case)
    assert verdict.status == "fail"
    assert verdict.metrics["missing_required"] == ["성명"]


def test_form_safe_skips_without_expectations(corpus: ConformanceCorpus) -> None:
    data = _bytes_for(corpus, "public-notice")
    case = ConformanceCase(id="s", path="notice.hwpx")
    assert runner_module._eval_form_safe(data, case).status == "skip"


# --------------------------------------------------------------------------- #
# Visual tier (oracle stubbed)
# --------------------------------------------------------------------------- #
class _FakeOracle:
    def __init__(self, *, ready: bool = True) -> None:
        self._ready = ready

    def available(self) -> bool:
        return self._ready


def test_visual_unverified_without_oracle(corpus: ConformanceCorpus, tmp_path) -> None:
    case = next(c for c in corpus.cases if c.id == "public-notice")
    verdict = runner_module._eval_visual(corpus.path_for(case), case, None)
    assert verdict.status == "unverified"

    null = _FakeOracle(ready=False)
    assert runner_module._eval_visual(corpus.path_for(case), case, null).status == "unverified"


def test_visual_pass_and_fail_with_fake_oracle(
    corpus: ConformanceCorpus, monkeypatch
) -> None:
    from hwpx.visual.report import VisualReport

    case = next(c for c in corpus.cases if c.id == "public-notice")

    def _clean(*_a, **_k) -> VisualReport:
        return VisualReport(ok=True, render_checked=True)

    monkeypatch.setattr("hwpx.visual.oracle.visual_check", _clean)
    verdict = runner_module._eval_visual(corpus, case, _FakeOracle())
    assert verdict.status == "pass"

    def _defect(*_a, **_k) -> VisualReport:
        return VisualReport(ok=False, render_checked=True, overflow_detected=True)

    monkeypatch.setattr("hwpx.visual.oracle.visual_check", _defect)
    verdict = runner_module._eval_visual(corpus, case, _FakeOracle())
    assert verdict.status == "fail"
    assert verdict.metrics["overflow_count"] == 1


def _pair_corpus(tmp_path, **case_kwargs) -> tuple[ConformanceCorpus, ConformanceCase]:
    """A 2-file corpus (before+after) under tmp_path for edit-pair visual tests."""

    doc = HwpxDocument.new()
    doc.add_paragraph("edit-pair 본문")
    data = doc.to_bytes()
    (tmp_path / "before.hwpx").write_bytes(data)
    (tmp_path / "after.hwpx").write_bytes(data)
    case = ConformanceCase(
        id="pair", path="after.hwpx", before="before.hwpx", **case_kwargs
    )
    return ConformanceCorpus(root=tmp_path, cases=[case]), case


def test_visual_edit_pair_uses_diff_path(corpus, tmp_path, monkeypatch) -> None:
    from hwpx.visual.report import VisualReport

    pair_corpus, case = _pair_corpus(
        tmp_path, edit_mask={0: [[0.1, 0.1, 0.4, 0.2]]}
    )
    seen: dict = {}

    def _record(before, after, *, oracle, edit_mask=None, **_k) -> VisualReport:
        seen["before"] = before
        seen["edit_mask"] = edit_mask
        return VisualReport(ok=True, render_checked=True)

    monkeypatch.setattr("hwpx.visual.oracle.visual_check", _record)
    verdict = runner_module._eval_visual(pair_corpus, case, _FakeOracle())
    assert verdict.status == "pass"
    assert verdict.metrics["diffed"] is True
    # The before render and the declared mask reach the oracle (real teeth).
    assert seen["before"] is not None and seen["before"].endswith("before.hwpx")
    assert seen["edit_mask"] is not None
    assert seen["edit_mask"].regions[0] == [(0.1, 0.1, 0.4, 0.2)]


def test_visual_expect_defect_passes_when_caught(tmp_path, monkeypatch) -> None:
    from hwpx.visual.report import VisualReport

    pair_corpus, case = _pair_corpus(tmp_path, expect_visual_defect=True)

    def _defect(*_a, **_k) -> VisualReport:
        return VisualReport(
            ok=False, render_checked=True, unexpected_diff_outside_mask=True
        )

    monkeypatch.setattr("hwpx.visual.oracle.visual_check", _defect)
    # The planted defect is caught -> the positive control passes.
    assert runner_module._eval_visual(pair_corpus, case, _FakeOracle()).status == "pass"

    def _clean(*_a, **_k) -> VisualReport:
        return VisualReport(ok=True, render_checked=True)

    monkeypatch.setattr("hwpx.visual.oracle.visual_check", _clean)
    # No defect where one was expected -> the control FAILS (the gate went blind).
    assert runner_module._eval_visual(pair_corpus, case, _FakeOracle()).status == "fail"


def test_build_edit_mask_round_trips() -> None:
    case = ConformanceCase(
        id="m",
        path="a.hwpx",
        before="b.hwpx",
        edit_mask={0: [[0.0, 0.0, 0.5, 0.5]], 1: [[0.2, 0.2, 0.3, 0.3]]},
        expect_visual_defect=True,
    )
    restored = ConformanceCase.from_dict(case.to_dict())
    assert restored == case
    mask = case.build_edit_mask()
    assert mask.regions[0] == [(0.0, 0.0, 0.5, 0.5)]
    assert mask.regions[1] == [(0.2, 0.2, 0.3, 0.3)]


# --------------------------------------------------------------------------- #
# Badge aggregation (strict thresholds)
# --------------------------------------------------------------------------- #
def _case(verdicts: dict[str, str], *, form_metrics: dict | None = None) -> CaseResult:
    built = {}
    for tier in ("open_safe", "semantic_safe", "form_safe", "visual_complete"):
        status = verdicts.get(tier, "skip")
        metrics = form_metrics if tier == "form_safe" and form_metrics else {}
        built[tier] = TierVerdict(tier, status, metrics=metrics)
    return CaseResult(case_id="c", visibility="public", verdicts=built)


def test_badges_all_green() -> None:
    cases = [
        _case({"open_safe": "pass", "semantic_safe": "pass"}),
        _case({"open_safe": "pass", "semantic_safe": "pass"}),
    ]
    badges = {b.tier: b for b in evaluate_badges(cases)}
    assert badges["open_safe"].status == "pass"
    assert badges["open_safe"].pass_rate == 1.0
    assert badges["semantic_safe"].status == "pass"
    # No form or visual cases -> unverified, never a silent pass.
    assert badges["form_safe"].status == "unverified"
    assert badges["visual_complete"].status == "unverified"


def test_strict_threshold_fails_on_any_miss() -> None:
    cases = [
        _case({"open_safe": "pass"}),
        _case({"open_safe": "fail"}),
    ]
    badges = {b.tier: b for b in evaluate_badges(cases)}
    assert badges["open_safe"].status == "fail"
    assert badges["open_safe"].pass_rate == 0.5


def test_form_overflow_rate_gate() -> None:
    # Every form case "passes" status-wise but the set carries an overflow slot;
    # the strict overflow-rate-0 gate must still fail the badge.
    cases = [
        _case(
            {"form_safe": "pass"},
            form_metrics={"checked": 4, "overflow_count": 1},
        ),
    ]
    badges = {b.tier: b for b in evaluate_badges(cases)}
    assert badges["form_safe"].status == "fail"
    assert badges["form_safe"].extra["overflowSlots"] == 1


def test_visual_complete_threshold_is_95_percent() -> None:
    # 19/20 verified pass == 95% -> exactly meets the strict VisualComplete floor.
    cases = [_case({"visual_complete": "pass"}) for _ in range(19)]
    cases.append(_case({"visual_complete": "fail"}))
    badges = {b.tier: b for b in evaluate_badges(cases)}
    assert badges["visual_complete"].status == "pass"
    assert badges["visual_complete"].pass_rate == pytest.approx(0.95)


# --------------------------------------------------------------------------- #
# End-to-end runner + golden
# --------------------------------------------------------------------------- #
def test_run_conformance_structural_matches_golden(corpus: ConformanceCorpus) -> None:
    report = run_conformance(corpus, tier="structural")
    assert report.ok is True
    assert report.render_checked is False
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert diff_golden(golden, report) == []
    # Structural tier can never claim VisualComplete (plan §0.0).
    assert report.badge("visual_complete").status == "unverified"


def test_golden_detects_regression(corpus: ConformanceCorpus) -> None:
    report = run_conformance(corpus, tier="structural")
    poisoned = json.loads(GOLDEN.read_text(encoding="utf-8"))
    # Pretend a case used to pass open-safety and a badge used to be green.
    poisoned["cases"]["public-notice"]["open_safe"] = "pass"
    poisoned["badges"]["open_safe"] = {"status": "pass", "passRate": 1.0}
    # Force a regression by flipping the live result.
    for case in report.cases:
        if case.case_id == "public-notice":
            case.verdicts["open_safe"] = TierVerdict("open_safe", "fail")
    report.badges = evaluate_badges(report.cases)
    regressions = diff_golden(poisoned, report)
    assert any("public-notice/open_safe" in line for line in regressions)
    assert any("open_safe" in line and "fail" in line for line in regressions)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def test_cli_run_structural_exit_zero(capsys) -> None:
    code = runner_module.main(["run", "--tier", "structural"])
    assert code == 0
    out = capsys.readouterr().out
    assert "open_safe" in out
    assert "visual_complete" in out


def test_cli_check_against_golden_passes() -> None:
    code = runner_module.main(
        ["run", "--tier", "structural", "--check", str(GOLDEN)]
    )
    assert code == 0


def test_cli_check_regression_exits_nonzero(tmp_path) -> None:
    # A golden that demands a non-existent passing case -> regression -> exit 1.
    poisoned = json.loads(GOLDEN.read_text(encoding="utf-8"))
    poisoned["cases"]["public-report-table"]["form_safe"] = "pass"
    poisoned["badges"]["form_safe"] = {"status": "pass", "passRate": 1.0}
    poisoned["cases"]["ghost-case"] = {"open_safe": "pass"}
    golden_path = tmp_path / "poisoned.json"
    golden_path.write_text(json.dumps(poisoned), encoding="utf-8")
    code = runner_module.main(
        ["run", "--tier", "structural", "--check", str(golden_path)]
    )
    assert code == 1


def test_cli_writes_report_and_golden(tmp_path) -> None:
    out_dir = tmp_path / "report"
    golden_out = tmp_path / "golden.json"
    code = runner_module.main(
        [
            "run",
            "--tier",
            "structural",
            "--out",
            str(out_dir),
            "--update-golden",
            str(golden_out),
        ]
    )
    assert code == 0
    assert (out_dir / "report.json").exists()
    assert (out_dir / "report.md").exists()
    golden = json.loads(golden_out.read_text(encoding="utf-8"))
    assert "badges" in golden and "cases" in golden
