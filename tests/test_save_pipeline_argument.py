# SPDX-License-Identifier: Apache-2.0
"""``doc.save(..., pipeline=SavePipeline(...))`` runs the save's gate through the given pipeline (7.0).

It is how a caller gives the gate a renderer (python-hwpx-automation's Hancom backend) without touching the
document's internals: the pipeline's ``oracle_factory`` is called only when the quality policy renders, and
everything else about the save stays as it is without the argument."""

from __future__ import annotations

import io
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from hwpx import HwpxDocument, QualityPolicy, SavePipeline
from hwpx.errors import HwpxTypeError, SaveError
from hwpx.tools import package_validator

HANCOM = Path(__file__).parent / "fixtures" / "hancom_saved"


class _Factory:
    """An ``oracle_factory`` that records its calls and offers no renderer (Hancom is not reachable)."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **options: Any) -> None:
        self.calls.append(options)
        return None


def _edited() -> HwpxDocument:
    doc = HwpxDocument.open(HANCOM / "form_field_line_break.hwpx", seed=7, now=datetime(2026, 11, 16, tzinfo=timezone.utc))
    doc.add_paragraph("파이프라인으로 저장")
    return doc


def _policy(render_check: str) -> QualityPolicy:
    """A gate that passes on these documents when no renderer answers (visual completeness not required)."""

    return QualityPolicy(render_check=render_check, require_visual_complete=False, layout_lint="off", xsd_mode="off")


def _count_validations(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []
    real = package_validator.validate_editor_open_safety

    def counting(source: Any) -> Any:
        calls.append(type(source).__name__)
        return real(source)

    monkeypatch.setattr(package_validator, "validate_editor_open_safety", counting)
    return calls


@pytest.mark.parametrize("quality", [None, QualityPolicy.transparent(), _policy("off")])
def test_a_pipeline_writes_the_same_bytes_and_renders_nothing_when_the_policy_does_not(
    tmp_path: Path, quality: QualityPolicy | None
) -> None:
    plain, piped = tmp_path / "plain.hwpx", tmp_path / "piped.hwpx"
    _edited().save(plain, quality=quality)
    factory = _Factory()
    report = _edited().save(piped, quality=quality, pipeline=SavePipeline(oracle_factory=factory))
    assert piped.read_bytes() == plain.read_bytes()
    assert factory.calls == []
    assert report.path == str(piped)
    assert (report.quality is None) == (quality is None)


def test_the_factory_is_called_when_the_policy_renders(tmp_path: Path) -> None:
    factory = _Factory()
    policy = QualityPolicy(render_check="auto", dpi=96, require_visual_complete=False, layout_lint="off", xsd_mode="off")
    report = _edited().save(tmp_path / "out.hwpx", quality=policy, pipeline=SavePipeline(oracle_factory=factory))
    assert factory.calls == [{"dpi": 96}]
    assert report.quality is not None and report.quality.ok
    # without the argument the plain gate is used: the factory is never asked
    _edited().save(tmp_path / "plain.hwpx", quality=policy)
    assert factory.calls == [{"dpi": 96}]


def test_a_refused_save_writes_nothing_and_leaves_the_document_unsaved(tmp_path: Path) -> None:
    target = tmp_path / "out.hwpx"
    target.write_bytes(b"what was there")
    doc = _edited()
    factory = _Factory()
    policy = QualityPolicy(render_check="required", layout_lint="off", xsd_mode="off")
    with pytest.raises(SaveError) as caught:
        doc.save(target, quality=policy, pipeline=SavePipeline(oracle_factory=factory))
    assert caught.value.code == "quality-gate-failed"
    assert caught.value.report is not None and not caught.value.report.ok
    assert factory.calls == [{"dpi": policy.dpi}]
    assert target.read_bytes() == b"what was there"
    assert doc.sections[0].dirty
    # the same document still saves through the plain gate afterwards
    doc.save(target)
    assert "파이프라인으로 저장" in HwpxDocument.open(target).text.plain()


@pytest.mark.parametrize("quality", [None, _policy("auto")])
@pytest.mark.parametrize("how", ["path", "stream"])
def test_a_save_through_a_pipeline_checks_open_safety_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, how: str, quality: QualityPolicy | None
) -> None:
    doc = _edited()
    calls = _count_validations(monkeypatch)
    pipeline = SavePipeline(oracle_factory=_Factory())
    target: Any = tmp_path / "out.hwpx" if how == "path" else io.BytesIO()
    report = doc.save(target, quality=quality, pipeline=pipeline)
    assert len(calls) == 1
    assert report.editor_open_safety is not None and report.editor_open_safety.ok


def test_a_hwp_target_is_written_as_hwp_through_a_pipeline(tmp_path: Path) -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("한/글 5.0")
    factory = _Factory()
    with warnings.catch_warnings():  # the experimental-writer warning comes once per process
        warnings.simplefilter("ignore", UserWarning)
        report = doc.save(tmp_path / "out.hwp", pipeline=SavePipeline(oracle_factory=factory))
    assert (tmp_path / "out.hwp").read_bytes()[:8] == bytes.fromhex("d0cf11e0a1b11ae1")
    assert report.path == str(tmp_path / "out.hwp")
    assert factory.calls == []


@pytest.mark.parametrize("wrong", [object(), "pipeline", QualityPolicy.transparent()])
def test_something_else_than_a_pipeline_is_refused_before_anything_is_written(tmp_path: Path, wrong: Any) -> None:
    doc = _edited()
    with pytest.raises(HwpxTypeError) as caught:
        doc.save(tmp_path / "out.hwpx", pipeline=wrong)
    assert caught.value.code == "save-pipeline-invalid-type"
    assert isinstance(caught.value, TypeError)
    assert not (tmp_path / "out.hwpx").exists()
