# SPDX-License-Identifier: Apache-2.0
"""Acceptance: **zero write paths bypass the SavePipeline** (plan §2 Phase B / DoD #1).

Two layers of evidence:

* **Static** — the single atomic writer lives only in ``hwpx.quality.save_pipeline``;
  none of the four public write modules (``document`` / ``patch`` /
  ``template_formfit`` / ``builder``) write serialized HWPX output to a destination
  themselves, and each routes through the gate (``self._save_pipeline.run`` /
  ``SavePipeline().run`` / ``save_report``).
* **Behavioral** — exercising each public write actually invokes ``SavePipeline.run``,
  and the rich result objects carry a ``VisualCompleteReport`` (DoD #2).

The engine serializer (``opc/package``) sits *underneath* the gate by design and is
intentionally out of scope here (the plan forbids touching it).
"""
from __future__ import annotations

import io
from pathlib import Path

import hwpx
from hwpx import HwpxDocument, paragraph_patch
from hwpx.quality import VisualCompleteReport
from hwpx.quality import save_pipeline as save_pipeline_module

_SRC = Path(hwpx.__file__).parent
WRITE_MODULES = {
    "document": _SRC / "document.py",
    "patch": _SRC / "patch.py",
    "template_formfit": _SRC / "template_formfit.py",
    "builder": _SRC / "builder" / "core.py",
}


def _document_owner_sources() -> dict[str, str]:
    """The S-084 domain owners behind the facade are write-surface too."""
    return {
        f"_document/{path.name}": path.read_text(encoding="utf-8")
        for path in sorted((_SRC / "_document").glob("*.py"))
    }


# --------------------------------------------------------------------------- #
# Static: the single writer + no direct destination writes
# --------------------------------------------------------------------------- #
def test_atomic_writers_defined_only_in_save_pipeline() -> None:
    sources = {name: path.read_text(encoding="utf-8") for name, path in WRITE_MODULES.items()}
    sources.update(_document_owner_sources())
    for name, src in sources.items():
        for forbidden in (
            "def write_bytes_atomically",
            "def _write_bytes_atomically",
            "def write_stream_or_rollback",
            "def _write_stream_or_rollback",
        ):
            assert forbidden not in src, f"{name} must not define its own atomic writer"


def test_no_public_write_path_writes_serialized_output_directly() -> None:
    # document (facade + _document owners) / patch / builder never write the
    # output archive themselves.
    sources = {
        name: WRITE_MODULES[name].read_text(encoding="utf-8")
        for name in ("document", "patch", "builder")
    }
    sources.update(_document_owner_sources())
    for name, src in sources.items():
        assert "os.replace(" not in src, f"{name} writes output outside the pipeline"
        assert ".write_bytes(" not in src, f"{name} writes output outside the pipeline"
    # template_formfit publishes the *pipeline-produced* temp via exactly one
    # documented os.replace, and never writes serialized bytes itself.
    tf = WRITE_MODULES["template_formfit"].read_text(encoding="utf-8")
    assert tf.count("os.replace(") == 1
    assert ".write_bytes(" not in tf


def test_every_write_path_routes_through_the_gate() -> None:
    # S-084 moved the document savers behind the facade into the persistence
    # owner (``hwpx._document.persistence``); the gate call now reads
    # ``doc._save_pipeline.run(`` there instead of ``self._save_pipeline.run(``
    # in document.py. The document write surface still routes through the gate.
    persistence = (_SRC / "_document" / "persistence.py").read_text(encoding="utf-8")
    assert "doc._save_pipeline.run(" in persistence
    patch = WRITE_MODULES["patch"].read_text(encoding="utf-8")
    assert "SavePipeline().run(" in patch
    builder = WRITE_MODULES["builder"].read_text(encoding="utf-8")
    assert "document.save_report(" in builder  # builder routes via the document gate
    tf = WRITE_MODULES["template_formfit"].read_text(encoding="utf-8")
    assert "doc.save_report(" in tf  # template_formfit routes via the document gate


# --------------------------------------------------------------------------- #
# Behavioral: exercising the public writes invokes the gate
# --------------------------------------------------------------------------- #
def test_public_writes_invoke_save_pipeline(tmp_path, monkeypatch) -> None:
    labels: list[str | None] = []
    original_run = save_pipeline_module.SavePipeline.run

    def spy(self, data, **kwargs):
        labels.append(kwargs.get("source_label"))
        return original_run(self, data, **kwargs)

    monkeypatch.setattr(save_pipeline_module.SavePipeline, "run", spy)

    seed = tmp_path / "seed.hwpx"
    doc = HwpxDocument.new()
    doc.add_paragraph("게이트 본문")
    doc.save_to_path(seed)
    HwpxDocument.open(seed).save_to_stream(io.BytesIO())
    HwpxDocument.open(seed).save_report(tmp_path / "report.hwpx")
    paragraph_patch(seed.read_bytes(), [], output_path=tmp_path / "patched.hwpx")

    from hwpx.builder import Document, Paragraph, Section

    Document(sections=[Section(children=[Paragraph(text="hello")])]).save_to_path(
        tmp_path / "built.hwpx"
    )

    assert "document.save_to_path" in labels
    assert "document.save_to_stream" in labels
    assert "document.save_report" in labels
    assert "patch.paragraph_patch" in labels
    # builder funnels through document.save_report -> at least two such calls.
    assert labels.count("document.save_report") >= 2


# --------------------------------------------------------------------------- #
# Behavioral: the public results carry a VisualCompleteReport (DoD #2)
# --------------------------------------------------------------------------- #
def test_document_save_report_returns_visual_complete_report(tmp_path) -> None:
    report = HwpxDocument.new().save_report(tmp_path / "out.hwpx")
    assert isinstance(report, VisualCompleteReport)
    assert report.ok is True


def test_patch_result_carries_visual_complete_report(tmp_path) -> None:
    seed = tmp_path / "seed.hwpx"
    HwpxDocument.new().save_to_path(seed)
    result = paragraph_patch(seed.read_bytes(), [], output_path=tmp_path / "out.hwpx")
    assert isinstance(result.visual_complete, VisualCompleteReport)
    assert result.to_dict()["visualComplete"] is not None


def test_builder_report_carries_visual_complete_report(tmp_path) -> None:
    from hwpx.builder import Document, Paragraph, Section

    report = Document(
        sections=[Section(children=[Paragraph(text="hello")])]
    ).save_to_path(tmp_path / "out.hwpx")
    assert isinstance(report.visual_complete, VisualCompleteReport)
    assert report.to_dict()["visual_complete"] is not None
