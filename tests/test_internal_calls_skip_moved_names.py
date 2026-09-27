# SPDX-License-Identifier: Apache-2.0
"""Library code must not raise its own 6.0 move warnings.

The ``HwpxDocument`` names that moved in 6.0 (``char_property``,
``list_form_fields``, ``track_changes``, ...) warn with ``DeprecationWarning``.
Internal callers used them, so a user calling only current APIs still saw the
warnings. These paths now call the current names or the OXML root.
"""
from __future__ import annotations

import io
import warnings
from pathlib import Path

from hwpx import HwpxDocument
from hwpx.form_fit.apply import fit_cell_text
from hwpx.form_fit.policy import FitPolicy
from hwpx.ingest.base import DocumentSourceInfo
from hwpx.ingest.hwpx_converter import HwpxMarkdownConverter
from hwpx.layout import lint_layout
from hwpx.tools.redline import author_demo_redline, inspect_redline_structure


class _NoMoveWarnings:
    """Record every warning and fail on a DeprecationWarning.

    Recording rather than raising: some of these paths catch ``Exception``
    around the call, which would swallow a warning raised as an error.
    """

    def __enter__(self) -> None:
        self._guard = warnings.catch_warnings(record=True)
        self._caught = self._guard.__enter__()
        warnings.simplefilter("always")

    def __exit__(self, *exc: object) -> None:
        self._guard.__exit__(*exc)
        moved = [str(w.message) for w in self._caught if issubclass(w.category, DeprecationWarning)]
        assert moved == []


def test_fit_with_a_document_uses_no_moved_names() -> None:
    doc = HwpxDocument.new()
    table = doc.add_table(1, 1, width=6000)
    with _NoMoveWarnings():
        fit_cell_text(
            table.cell(0, 0),
            "아주 긴 값을 넣어서 줄이기가 일어나게 한다 " * 3,
            FitPolicy(mode="shrink", max_lines=1),
            document=doc,
        )


def test_required_field_lint_uses_no_moved_names() -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("본문")
    data = doc.to_bytes()
    with _NoMoveWarnings():
        lint_layout(data, document=doc, required_fields={"name"})


def test_redline_helpers_use_no_moved_names(tmp_path: Path) -> None:
    doc = HwpxDocument.new()
    target = tmp_path / "redline.hwpx"
    with _NoMoveWarnings():
        author_demo_redline(doc)
        doc.save_to_path(target)
        inspect_redline_structure(target)


def test_markdown_ingest_uses_no_moved_names() -> None:
    doc = HwpxDocument.new()
    doc.add_paragraph("본문")
    data = doc.to_bytes()
    source = DocumentSourceInfo(extension=".hwpx", mimetype=None, filename="doc.hwpx")
    with _NoMoveWarnings():
        HwpxMarkdownConverter().convert(io.BytesIO(data), source)
