# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the Phase-B single save gate (``hwpx.quality``).

Deterministic and portable: the visual oracle is always a fake (an injected
backend, with ``visual_check`` stubbed for the render branches), so these never
drive Hancom. The real-Hancom verification is the opt-in Mac smoke in
``test_save_pipeline_mac_oracle.py``.
"""
from __future__ import annotations

import io

import pytest

from hwpx import HwpxDocument
from hwpx.quality import (
    DirtyLayoutLedger,
    DirtyLayoutRange,
    QualityPolicy,
    SavePipeline,
    VisualCompleteReport,
)
from hwpx.quality import save_pipeline as save_pipeline_module
from hwpx.quality.report import (
    OPEN_SAFETY_FAILED,
    REFERENCE_INTEGRITY_FAILED,
    RENDER_ORACLE_UNAVAILABLE,
    VISUAL_COMPLETE_FAILED,
)
from hwpx.visual.report import VisualReport


@pytest.fixture
def valid_bytes() -> bytes:
    document = HwpxDocument.new()
    document.add_paragraph("SavePipeline 게이트 본문")
    return document.to_bytes()


class _FakeOracle:
    """An oracle that is reachable; rendering itself is stubbed via visual_check."""

    def __init__(self, *, ready: bool = True) -> None:
        self._ready = ready

    def available(self) -> bool:
        return self._ready

    def render_many(self, pairs):  # pragma: no cover - visual_check is stubbed
        raise AssertionError("visual_check should be stubbed in these tests")


# --------------------------------------------------------------------------- #
# Policy
# --------------------------------------------------------------------------- #
def test_transparent_policy_is_lenient() -> None:
    policy = QualityPolicy.transparent()
    assert policy.require_open_safety is True
    assert policy.require_visual_complete is False
    assert policy.render_check == "off"
    assert policy.require_reference_integrity is False
    assert policy.renders is False


def test_strict_policy_defaults_match_appendix_a() -> None:
    policy = QualityPolicy()
    assert policy.require_visual_complete is True
    assert policy.render_check == "auto"
    assert policy.renders is True


# --------------------------------------------------------------------------- #
# Transparent gate == today's behaviour (open-safety only, no render)
# --------------------------------------------------------------------------- #
def test_transparent_pass_writes_and_degrades(tmp_path, valid_bytes) -> None:
    out = tmp_path / "out.hwpx"
    report = SavePipeline().run(
        valid_bytes, output_path=out, quality=QualityPolicy.transparent()
    )
    assert isinstance(report, VisualCompleteReport)
    assert report.ok is True
    assert report.output_path == str(out)
    assert out.read_bytes() == valid_bytes
    # §0.0: no render ran -> visual_complete must NOT be a silent true.
    assert report.visual_complete is False
    assert report.visual_complete_status == "unverified"
    assert report.render_checked is False


def test_to_bytes_style_gate_without_output(valid_bytes) -> None:
    report = SavePipeline().run(valid_bytes, quality=QualityPolicy.transparent())
    assert report.ok is True
    assert report.output_path is None  # gate-only, nothing published


def test_stream_publish(valid_bytes) -> None:
    stream = io.BytesIO()
    report = SavePipeline().run(
        valid_bytes, output_stream=stream, quality=QualityPolicy.transparent()
    )
    assert report.ok is True
    assert stream.getvalue() == valid_bytes


# --------------------------------------------------------------------------- #
# Integrity floor
# --------------------------------------------------------------------------- #
def test_malformed_bytes_fail_integrity(tmp_path) -> None:
    out = tmp_path / "out.hwpx"
    report = SavePipeline().run(
        b"not a zip at all", output_path=out, quality=QualityPolicy.transparent()
    )
    assert report.ok is False
    assert REFERENCE_INTEGRITY_FAILED in report.error_codes
    assert not out.exists()  # on_pass: a failing doc is never published


# --------------------------------------------------------------------------- #
# Open-safety gate
# --------------------------------------------------------------------------- #
def test_open_safety_failure_withholds_output(tmp_path, valid_bytes, monkeypatch) -> None:
    from hwpx.tools import package_validator

    class _Fail:
        ok = False
        summary = "synthetic open-safety failure"

        def to_dict(self):
            return {"ok": False, "summary": self.summary}

    monkeypatch.setattr(package_validator, "validate_editor_open_safety", lambda src: _Fail())

    out = tmp_path / "out.hwpx"
    report = SavePipeline().run(
        valid_bytes, output_path=out, quality=QualityPolicy.transparent()
    )
    assert report.ok is False
    assert OPEN_SAFETY_FAILED in report.error_codes
    assert not out.exists()


def test_publish_always_writes_even_on_failure(tmp_path, valid_bytes, monkeypatch) -> None:
    # The byte path (patch.py) historically always writes + reports; preserve it.
    from hwpx.tools import package_validator

    class _Fail:
        ok = False
        summary = "synthetic open-safety failure"

        def to_dict(self):
            return {"ok": False, "summary": self.summary}

    monkeypatch.setattr(package_validator, "validate_editor_open_safety", lambda src: _Fail())
    out = tmp_path / "out.hwpx"
    report = SavePipeline().run(
        valid_bytes, output_path=out, quality=QualityPolicy.transparent(), publish="always"
    )
    assert report.ok is False
    assert out.exists()  # published anyway
    assert report.output_path == str(out)


def test_debug_artifact_on_failure(tmp_path, valid_bytes, monkeypatch) -> None:
    from hwpx.tools import package_validator

    class _Fail:
        ok = False
        summary = "synthetic open-safety failure"

        def to_dict(self):
            return {"ok": False, "summary": self.summary}

    monkeypatch.setattr(package_validator, "validate_editor_open_safety", lambda src: _Fail())
    out = tmp_path / "out.hwpx"
    debug = tmp_path / "debug"
    report = SavePipeline().run(
        valid_bytes,
        output_path=out,
        quality=QualityPolicy.transparent(),
        debug_dir=debug,
        source_label="unit",
    )
    assert report.ok is False
    assert not out.exists()
    assert report.debug_path is not None
    assert (debug / "unit.rejected.hwpx").exists()


# --------------------------------------------------------------------------- #
# Visual oracle branches (render stubbed; assurance tiers)
# --------------------------------------------------------------------------- #
def test_render_required_but_unavailable_fails(tmp_path, valid_bytes) -> None:
    out = tmp_path / "out.hwpx"
    policy = QualityPolicy(render_check="required", require_visual_complete=True)
    report = SavePipeline(oracle=_FakeOracle(ready=False)).run(
        valid_bytes, output_path=out, quality=policy
    )
    assert report.ok is False
    assert RENDER_ORACLE_UNAVAILABLE in report.error_codes
    assert report.visual_complete_status == "unverified"
    assert not out.exists()


def test_render_auto_unavailable_degrades_not_fails(tmp_path, valid_bytes) -> None:
    # auto + no oracle + require_visual_complete=False -> structural pass, written.
    out = tmp_path / "out.hwpx"
    policy = QualityPolicy(render_check="auto", require_visual_complete=False)
    report = SavePipeline(oracle=_FakeOracle(ready=False)).run(
        valid_bytes, output_path=out, quality=policy
    )
    assert report.ok is True
    assert report.visual_complete_status == "unverified"
    assert out.exists()


def test_render_verified_sets_visual_complete(tmp_path, valid_bytes, monkeypatch) -> None:
    monkeypatch.setattr(
        save_pipeline_module,
        "visual_check",
        lambda *a, **k: VisualReport(ok=True, render_checked=True, max_diff_ratio=0.0),
    )
    out = tmp_path / "out.hwpx"
    policy = QualityPolicy(render_check="required", require_visual_complete=True)
    report = SavePipeline(oracle=_FakeOracle(ready=True)).run(
        valid_bytes, output_path=out, quality=policy
    )
    assert report.ok is True
    assert report.visual_complete is True
    assert report.visual_complete_status == "verified"
    assert report.render_checked is True
    assert out.exists()


def test_render_defect_rolls_back(tmp_path, valid_bytes, monkeypatch) -> None:
    monkeypatch.setattr(
        save_pipeline_module,
        "visual_check",
        lambda *a, **k: VisualReport(ok=False, render_checked=True, overlap_detected=True),
    )
    out = tmp_path / "out.hwpx"
    policy = QualityPolicy(render_check="required", require_visual_complete=True)
    report = SavePipeline(oracle=_FakeOracle(ready=True)).run(
        valid_bytes, output_path=out, quality=policy
    )
    assert report.ok is False
    assert report.visual_complete is False
    assert report.visual_complete_status == "failed"
    assert VISUAL_COMPLETE_FAILED in report.error_codes
    assert not out.exists()  # rolled back: the defective doc is never published


def test_allow_expert_unsafe_waives_visual(tmp_path, valid_bytes) -> None:
    out = tmp_path / "out.hwpx"
    policy = QualityPolicy(
        render_check="required", require_visual_complete=True, allow_expert_unsafe=True
    )
    report = SavePipeline(oracle=_FakeOracle(ready=False)).run(
        valid_bytes, output_path=out, quality=policy
    )
    assert report.ok is True  # expert override
    assert report.visual_complete is False  # but never claims verified
    assert out.exists()
    assert any("allow_expert_unsafe" in w for w in report.warnings)


# --------------------------------------------------------------------------- #
# Report + ledger data models
# --------------------------------------------------------------------------- #
def test_report_to_dict_is_json_shaped(valid_bytes) -> None:
    report = SavePipeline().run(valid_bytes, quality=QualityPolicy.transparent())
    data = report.to_dict()
    for key in ("ok", "visualComplete", "visualCompleteStatus", "renderChecked", "openSafety"):
        assert key in data
    assert data["visualCompleteStatus"] == "unverified"


def test_ledger_accumulates_ranges() -> None:
    ledger = DirtyLayoutLedger()
    assert ledger.is_empty
    ledger.note("Contents/section0.xml", start_paragraph=2, end_paragraph=2, reason="text_replaced")
    ledger.note(DirtyLayoutRange(part="Contents/section1.xml", reason="builder_generated"))
    assert not ledger.is_empty
    assert ledger.parts == {"Contents/section0.xml", "Contents/section1.xml"}
    assert ledger.to_dict()["ranges"][0]["reason"] == "text_replaced"
