# SPDX-License-Identifier: Apache-2.0
"""openrate corpus v4 — the 6.0 authoring surface, additive over v3.

Why v4 exists
=============

v3 measured the authoring surfaces added in 4.x/5.x with the stack of the
day. Since then the engine went through a major surface rewrite: 79 root
``HwpxDocument`` names moved into domain namespaces (``doc.notes``,
``doc.fields``, ``doc.shapes``, ``doc.styles``, ``doc.page``, ...) behind a
deprecation shim, and Q3b opened four OWPML elements that real Hancom output
always carried but 5.x code could not write (``pageBorderFill``, footnote/
endnote shape blocks, named ``hh:style`` creation). v4 answers two questions
at once: does the CURRENT stack still produce openable files, and does the
6.0-native call surface actually work end to end (not just import-clean)?

Two rules make v4 different from a v3 re-run
==============================================

1. **Every inherited stratum is rewritten to the namespaced 6.0 path.**
   ``document.add_paragraph``/``document.add_table`` are untouched (they
   never moved); everything else routes through ``doc.notes``/``doc.fields``/
   ``doc.shapes``/``doc.styles`` instead of the deprecated root shim.
2. **A ``DeprecationWarning`` is a generation failure, not a nuisance.**
   ``warnings.simplefilter("error", DeprecationWarning)`` is installed before
   any document is touched, so calling a moved 5.x name raises instead of
   quietly working — the generator doubles as a regression test for the 6.0
   migration itself. A withheld record with a ``DeprecationWarning`` reason
   is a genuine finding (a real 6.0-path defect), not something to route
   around silently.

Strata (all deterministic — fixed seeds, bank rotation, no wall clock)
=======================================================================

Inherited from v3, rewritten to the 6.0 surface:

* ``baseline-regen``          30  (unchanged shape of v3; add_rectangle/
                                    add_line/add_ellipse now via doc.shapes)
* ``authored-footnote``       15  doc.notes.add_footnote / add_endnote
* ``authored-formfield``      15  doc.fields.add / doc.fields.fill
* ``authored-equation``       15  doc.shapes.add_equation
* ``authored-chart``          15  doc.shapes.add_chart (ChartML still
                                    composed by hwpx_automation.office.
                                    charting — core does not own composition)
* ``authored-checkbox``       15  doc.fields.add_check_box / set_check_box
* ``edit-plan``               15  hwpx.plan.apply_edit_plan (unchanged —
                                    never touched HwpxDocument root methods)

New in v4, exercising surface opened by S-120c Q3b/6.0:

* ``authored-heading``        15  add_heading level 1..10 rotation, plus an
                                    in-generator round trip: resolving
                                    "개요 {level}" by name must land on the
                                    exact style id the heading paragraph got
* ``authored-named-style``    10  doc.oxml.headers[0].ensure_style(...) +
                                    add_paragraph(..., style="name") — no
                                    ns/ wrapper exists yet for style creation,
                                    so this one intentionally reaches into
                                    doc.oxml directly (Q3b's own layer)
* ``authored-page-structure`` 15  pageBorderFill(BOTH/EVEN/ODD) [also
                                    oxml-direct, no ns/ wrapper yet] +
                                    doc.page.set_visibility/set_line_numbers/
                                    set_grid (ns/ wrappers built on top of
                                    Q3b's first 3/7 batch)
* ``authored-note-shape``     10  all 5 footnote + 5 endnote shape blocks
                                    (oxml-direct, Q3b's second batch) plus
                                    real footnote/endnote body text via
                                    doc.notes.add_footnote/add_endnote

Generation ONLY — no Hancom oracle here. Every produced file gets the static
``validate_editor_open_safety`` pre-filter (necessary, not sufficient); the
real verdict comes from the Windows box run. ``render_jobs_v4.json`` lists a
PDF export job per produced file (page-structure/note-shape/named-style are
visual claims a mere "does it open" check cannot confirm) — box-side PDF
export is a separate step from the open-rate filelist.

hwpx_automation lives in the sibling ``hwpx-mcp-server-s120c`` checkout now
(not a standalone ``python-hwpx-automation`` repo/venv as when v3 was
written) — this script inserts its ``src/`` onto ``sys.path`` directly
instead of requiring a separate "automation environment", so a single
``python-hwpx`` venv is sufficient:

    cd python-hwpx
    .venv-core/bin/python scripts/generate_openrate_corpus_v4.py
"""
from __future__ import annotations

import itertools
import json
import re
import subprocess
import sys
import uuid
import warnings
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

PYTHON_HWPX = Path(__file__).resolve().parent.parent
HWPX_ROOT = PYTHON_HWPX.parent
AUTOMATION_REPO = HWPX_ROOT / "hwpx-mcp-server-s120"
sys.path.insert(0, str(PYTHON_HWPX / "scripts"))
sys.path.insert(0, str(AUTOMATION_REPO / "src"))

from generate_openrate_corpus import (  # noqa: E402
    DEPT_BANK,
    ORG_BANK,
    OUT_DIR,
    OUT_DIR_V2,
    SUBJECT_BANK,
    cycle,
    record,
    sha256_file,
)
from generate_openrate_corpus_v3 import (  # noqa: E402
    BOX_NEGATIVE_CONTROLS,
    EQUATION_LATEX_BANK,
    OUT_DIR_V3,
    _base_document,
)

from hwpx import HwpxDocument  # noqa: E402,F401 (imported for readers of this module)

# The whole point of v4 is proving the 6.0-native call surface works — a
# moved 5.x name firing its shim IS a failure, recorded as withheld with the
# warning text as the reason, not silently absorbed.
warnings.simplefilter("error", DeprecationWarning)

OUT_DIR_V4 = PYTHON_HWPX / "work" / "openrate-corpus-v4"
MANIFEST_SCHEMA = "hwpx.openrate.frozen-manifest.v4"
BOX_ROOT = "C:\\openrate\\v4"
BOX_ROOT_PDF = "C:\\openrate\\v4-pdf"


# ================================================================================
# new-stratum banks (rotation only — no wall clock, no randomness)
# ================================================================================
NOTE_NUMBER_TYPE_BANK = (
    "DIGIT", "CIRCLED_DIGIT", "ROMAN_CAPITAL", "HANGUL_JAMO", "HANGUL_SYLLABLE",
)
FOOTNOTE_NUMBERING_TYPE_BANK = ("CONTINUOUS", "ON_SECTION", "ON_PAGE")
ENDNOTE_NUMBERING_TYPE_BANK = ("CONTINUOUS", "ON_SECTION")  # no ON_PAGE — schema
FOOTNOTE_PLACEMENT_BANK = ("EACH_COLUMN", "MERGED_COLUMN", "RIGHT_MOST_COLUMN")
ENDNOTE_PLACEMENT_BANK = ("END_OF_DOCUMENT", "END_OF_SECTION")  # distinct vocab
NOTE_LINE_COLOR_BANK = ("#0000FF", "#AA0000", "#007700", "#555555")
PAGE_BORDER_TYPE_BANK = ("BOTH", "EVEN", "ODD")


def _tool_versions() -> dict[str, str | None]:
    from importlib.metadata import PackageNotFoundError, version

    versions: dict[str, str | None] = {}
    import hwpx

    versions["python-hwpx"] = str(hwpx.__version__)
    # hwpx_automation is imported from AUTOMATION_REPO/src via the sys.path
    # insert above, regardless of what this venv has pip-installed — so that
    # checkout's pyproject.toml is the truth about the code that actually ran.
    # Asking importlib.metadata first labelled the run with whatever stale
    # version the venv happened to carry (observed: 6.7.1 while executing
    # 6.8.1 sources), which is exactly the coordinate lie S-119 exists to kill.
    versions["python-hwpx-automation"] = _read_pyproject_version(
        AUTOMATION_REPO / "pyproject.toml"
    )
    if versions["python-hwpx-automation"] is None:
        try:
            versions["python-hwpx-automation"] = version("python-hwpx-automation")
        except PackageNotFoundError:
            pass
    return versions


def _read_pyproject_version(pyproject_path: Path) -> str | None:
    if not pyproject_path.exists():
        return None
    match = re.search(
        r'^version\s*=\s*"([^"]+)"', pyproject_path.read_text(encoding="utf-8"), re.MULTILINE
    )
    return match.group(1) if match else None


def _git_commit(repo_dir: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_dir), capture_output=True, text=True, timeout=10, check=True,
        )
    except Exception:  # noqa: BLE001 - provenance-only, never fatal
        return None
    return out.stdout.strip() or None


def _frozen_reference(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return {"path": str(path.relative_to(PYTHON_HWPX)), "sha256": sha256_file(path)}


@contextmanager
def _deterministic_object_ids() -> Iterator[None]:
    """Reseed core's paragraph/object/memo id source for this run only.

    ``hwpx.oxml._document_primitives._paragraph_id``/``_object_id``/
    ``_memo_id`` all draw from ``uuid.uuid4()`` (``os.urandom``-backed,
    unseedable by design — that is what "random" means). This was already
    true in v1/v2/v3: none of them ever claimed or verified file-byte
    determinism across separate runs, only record id/order/bank-content
    determinism (confirmed: no seed hook exists anywhere in the library, no
    test in this repo asserts cross-run byte identity). v4's gate asks for
    file-sha determinism too, so this reseeds the entropy SOURCE the three
    id functions share (``_document_primitives.uuid4``) with a fixed
    counter, scoped to generation only — no core library file is touched.
    Generation is single-threaded and fully deterministic in call order
    (same strata, same idx loops, same branches every run), so the same
    counter sequence lands on the same ids run after run.
    """

    import hwpx.oxml._document_primitives as _prim

    counter = itertools.count(1)
    original_uuid4 = _prim.uuid4

    def _seeded_uuid4() -> uuid.UUID:
        return uuid.UUID(int=next(counter))

    _prim.uuid4 = _seeded_uuid4
    try:
        yield
    finally:
        _prim.uuid4 = original_uuid4


# ================================================================================
# inherited strata (v3 shape, rewritten to the 6.0 namespaced surface)
# ================================================================================
def gen_baseline_regen(bucket_dir: Path) -> list[dict[str, Any]]:
    """v1's authored shapes, re-emitted by the current core serializer."""

    records: list[dict[str, Any]] = []
    for idx in range(30):
        rec_id = f"v4-baseline-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            document = _base_document(idx, "일반 안내")
            if idx % 3 == 1:
                table = document.add_table(3, 3, width=42000)
                for column, value in enumerate(("구분", "내용", "비고")):
                    table.cell(0, column).text = value
                for row in (1, 2):
                    for column in range(3):
                        table.cell(row, column).text = f"항목 {row}-{column}"
            if idx % 3 == 2:
                variant = (idx // 3) % 3
                if variant == 0:
                    document.shapes.add_rectangle(14400, 7200, fill_color="#CCE5FF")
                elif variant == 1:
                    document.shapes.add_line(0, 0, 14400, 0)
                else:
                    document.shapes.add_ellipse(10000, 6000, fill_color="#FFD9CC")
            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="baseline-regen", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001 - withheld is the honest record
            records.append(record(
                rec_id=rec_id, bucket="baseline-regen", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


def gen_footnote(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(15):
        rec_id = f"v4-footnote-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            document = _base_document(idx, "각주 표본")
            paragraph = document.add_paragraph(f"본문 문단 {idx} — 각주가 달린 문장입니다.")
            for note_index in range(1 + idx % 3):
                document.notes.add_footnote(
                    f"각주 {note_index + 1}: {cycle(SUBJECT_BANK, idx + note_index)}",
                    paragraph=paragraph,
                )
            if idx % 3 == 0:
                document.notes.add_endnote(f"미주: {cycle(DEPT_BANK, idx)} 참고", paragraph=paragraph)
            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-footnote", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001
            records.append(record(
                rec_id=rec_id, bucket="authored-footnote", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


def gen_formfield(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(15):
        rec_id = f"v4-formfield-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            document = _base_document(idx, "누름틀 표본")
            field_count = 1 + idx % 3
            for field_index in range(field_count):
                document.fields.add(
                    f"field_{idx}_{field_index}",
                    prompt=f"{cycle(DEPT_BANK, idx + field_index)} 입력",
                )
            # fill half the documents so both authored and filled shapes are judged
            if idx % 2 == 0:
                document.fields.fill(cycle(ORG_BANK, idx), name=f"field_{idx}_0")
            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-formfield", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001
            records.append(record(
                rec_id=rec_id, bucket="authored-formfield", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


def gen_equation(bucket_dir: Path) -> list[dict[str, Any]]:
    from hwpx.equation import latex_to_eqedit

    records: list[dict[str, Any]] = []
    for idx in range(15):
        rec_id = f"v4-equation-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        latex = EQUATION_LATEX_BANK[idx % len(EQUATION_LATEX_BANK)]
        try:
            script = latex_to_eqedit(latex)
            document = _base_document(idx, "수식 표본")
            document.add_paragraph(f"수식 {idx}:")
            document.shapes.add_equation(script)
            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-equation", seed=latex,
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001
            records.append(record(
                rec_id=rec_id, bucket="authored-equation", seed=latex,
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


def gen_chart(bucket_dir: Path) -> list[dict[str, Any]]:
    from hwpx_automation.office.charting import ChartSeries, build_chart_ml

    records: list[dict[str, Any]] = []
    chart_types = ("bar", "line", "pie")
    for idx in range(15):
        rec_id = f"v4-chart-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        chart_type = chart_types[idx % len(chart_types)]
        try:
            categories = [cycle(DEPT_BANK, idx + offset) for offset in range(3)]
            series = [
                ChartSeries(
                    name=f"{cycle(ORG_BANK, idx)} 지표",
                    values=[float(10 + idx), float(20 + idx % 7), float(15 + idx % 5)],
                )
            ]
            if chart_type != "pie":
                series.append(ChartSeries(
                    name="전년 동기",
                    values=[float(8 + idx % 4), float(18 + idx % 3), float(12 + idx % 6)],
                ))
            chart_xml = build_chart_ml(
                chart_type, categories, series, title=f"{chart_type} 표본 {idx}",
            )
            document = _base_document(idx, "차트 표본")
            document.shapes.add_chart(chart_xml, size=(60000, 40000))
            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-chart", seed=f"{chart_type}:{idx}",
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001
            records.append(record(
                rec_id=rec_id, bucket="authored-chart", seed=f"{chart_type}:{idx}",
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


def gen_checkbox(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(15):
        rec_id = f"v4-checkbox-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            document = _base_document(idx, "체크박스 표본")
            box_count = 1 + idx % 3
            for box_index in range(box_count):
                document.fields.add_check_box(
                    f"{cycle(SUBJECT_BANK, idx + box_index)} 여부",
                    checked=(idx + box_index) % 2 == 0,
                    name=f"chk_{idx}_{box_index}",
                )
            if idx % 3 == 0:
                # exercise the SET path on an authored box, not only CREATE
                document.fields.set_check_box(True, name=f"chk_{idx}_0")
            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-checkbox", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001
            records.append(record(
                rec_id=rec_id, bucket="authored-checkbox", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


def gen_edit_plan(bucket_dir: Path) -> list[dict[str, Any]]:
    """The atomic plan executor's OUTPUT documents are the corpus items."""

    from hwpx.plan import apply_edit_plan

    records: list[dict[str, Any]] = []
    base_dir = bucket_dir / "_bases"
    base_dir.mkdir(parents=True, exist_ok=True)
    for idx in range(15):
        rec_id = f"v4-editplan-{idx:03d}"
        base_path = base_dir / f"{rec_id}-base.hwpx"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            document = _base_document(idx, "계획 실행 표본")
            document.add_paragraph("치환 대상 문단입니다.")
            table = document.add_table(2, 2, width=42000)
            table.cell(0, 0).text = "라벨"
            document.save_to_path(str(base_path))

            plan = {
                "schemaVersion": "hwpx.edit-plan/v1",
                "source": str(base_path),
                "output": str(out_path),
                "steps": [
                    {
                        "id": "s1",
                        "op": "paragraph_patch",
                        "args": {"patches": [{
                            "paragraphIndex": 3,
                            "text": f"계획으로 치환된 문단 {idx}",
                        }]},
                    },
                    {
                        "id": "s2",
                        "op": "fill_cells",
                        "args": {"cells": [{
                            "tableIndex": 0, "row": 0, "col": 1,
                            "text": cycle(DEPT_BANK, idx),
                        }]},
                    },
                ],
            }
            report = apply_edit_plan(plan)
            if not report.ok:
                raise RuntimeError(f"edit plan failed: {report.to_dict().get('failedStepId')}")
            records.append(record(
                rec_id=rec_id, bucket="edit-plan", seed=str(idx),
                output_path=out_path, produced=True, input_path=base_path,
            ))
        except Exception as exc:  # noqa: BLE001
            records.append(record(
                rec_id=rec_id, bucket="edit-plan", seed=str(idx),
                output_path=None, produced=False, input_path=base_path,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


# ================================================================================
# new strata (6.0-only surface — Q3b/S-120c)
# ================================================================================
def gen_authored_heading(bucket_dir: Path) -> list[dict[str, Any]]:
    """``add_heading`` level 1..10 rotation, plus a style-name round trip.

    ``add_heading`` resolves *level* to a style internally; this generator
    independently re-resolves the implied style NAME ("개요 {level}") and
    checks it lands on the exact id the heading paragraph actually got. A
    mismatch here is a real defect, not a generation nuisance — it is raised
    so it shows up as a withheld record with a precise reason.
    """

    records: list[dict[str, Any]] = []
    for idx in range(15):
        rec_id = f"v4-heading-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        level = 1 + idx % 10
        try:
            document = _base_document(idx, "제목 표본")
            heading = document.add_heading(f"{level}수준 제목 {idx}", level=level)
            document.add_paragraph(f"{cycle(SUBJECT_BANK, idx)} 본문 문단입니다.")

            expected_name = f"개요 {level}"
            resolved = document.styles.resolve(expected_name)
            actual_id = str(heading.style_id_ref)
            if str(resolved.id) != actual_id:
                raise RuntimeError(
                    f"heading level={level} wrote styleIDRef={actual_id!r} but "
                    f"{expected_name!r} resolves to id={resolved.id!r} — "
                    "style-name round trip broken"
                )

            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-heading", seed=f"level:{level}",
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001
            records.append(record(
                rec_id=rec_id, bucket="authored-heading", seed=f"level:{level}",
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


def gen_authored_named_style(bucket_dir: Path) -> list[dict[str, Any]]:
    """``ensure_style`` (Q3b) creation + ``style=`` name-based authoring.

    No ``ns/`` wrapper exists yet for style CREATION (only lookup/apply do:
    ``doc.styles.resolve``/``apply_paragraph_format``), so this reaches into
    ``doc.oxml.headers[0].ensure_style`` directly — the oxml layer Q3b built.
    ``doc.styles.ensure_run`` (the namespaced char-property twin) is used for
    the style's charPr so this generator itself fires no DeprecationWarning.
    """

    records: list[dict[str, Any]] = []
    for idx in range(10):
        rec_id = f"v4-namedstyle-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        style_name = f"강조단락{idx}"
        try:
            document = _base_document(idx, "사용자 스타일 표본")
            char_id = document.styles.ensure_run(
                bold=(idx % 2 == 0), color="#1F4E79", size=13,
            )
            document.oxml.headers[0].ensure_style(
                style_name,
                eng_name=f"Emphasis{idx}",
                char_pr_id_ref=char_id,
                next_style_id_ref="1",
            )
            document.add_paragraph(
                f"{cycle(DEPT_BANK, idx)} 사용자 스타일 문단입니다.", style=style_name,
            )
            document.add_paragraph("이어지는 평문 문단입니다 — 스타일이 새어나가면 안 됩니다.")
            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-named-style", seed=style_name,
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001
            records.append(record(
                rec_id=rec_id, bucket="authored-named-style", seed=style_name,
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


def gen_authored_page_structure(bucket_dir: Path) -> list[dict[str, Any]]:
    """pageBorderFill (oxml-direct) + visibility/lineNumberShape/grid (ns/).

    ``pageBorderFill`` has no ``ns/`` wrapper yet (Q3b's second batch), so it
    goes through ``doc.sections[0].properties.set_page_border_fill`` exactly
    like the Q3b demo fixtures. ``visibility``/``lineNumberShape``/``grid``
    DO have ``doc.page.*`` wrappers (built over Q3b's first batch), so those
    route through the namespace.
    """

    records: list[dict[str, Any]] = []
    for idx in range(15):
        rec_id = f"v4-pagestructure-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        page_type = PAGE_BORDER_TYPE_BANK[idx % len(PAGE_BORDER_TYPE_BANK)]
        show_line_number = idx % 2 == 0
        hide_first_header = idx % 3 == 0
        try:
            document = _base_document(idx, "쪽 구조 표본")
            border_id = document.styles.ensure_border_fill(
                border_color=NOTE_LINE_COLOR_BANK[idx % len(NOTE_LINE_COLOR_BANK)],
                border_width="0.4 mm",
            )
            document.sections[0].properties.set_page_border_fill(
                page_type=page_type,
                border_fill_id_ref=border_id,
                text_border="PAPER" if idx % 2 == 0 else "CONTENT",
                fill_area="PAGE",
                offset_left=850 + idx * 10,
                offset_right=850 + idx * 10,
                offset_top=850,
                offset_bottom=850,
            )
            document.page.set_visibility(
                show_line_number=show_line_number,
                hide_first_header=hide_first_header,
            )
            document.page.set_line_numbers(
                restart_type=idx % 3,
                count_by=1 + idx % 5,
                distance=2000 + idx * 50,
                start_number=1 + idx % 10,
            )
            document.page.set_grid(
                line_grid=idx % 4,
                char_grid=idx % 4,
                wonggoji_format=(idx % 5 == 0),
            )
            for i in range(1, 4):
                document.add_paragraph(f"{i}쪽에 해당하는 본문 문단 {idx}-{i}입니다.")
            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-page-structure",
                seed=f"{page_type}:{idx}", output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001
            records.append(record(
                rec_id=rec_id, bucket="authored-page-structure",
                seed=f"{page_type}:{idx}", output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


def gen_authored_note_shape(bucket_dir: Path) -> list[dict[str, Any]]:
    """All 5 footnote + 5 endnote shape blocks (Q3b's second batch), plus
    real footnote/endnote body text so the shapes have something to render.

    Footnote and endnote do NOT share a numbering/placement vocabulary —
    endnote has no ``ON_PAGE`` numbering and no per-column placement — so the
    rotation banks are kept separate (``ENDNOTE_NUMBERING_TYPE_BANK`` /
    ``ENDNOTE_PLACEMENT_BANK``) rather than reusing the footnote ones.
    """

    records: list[dict[str, Any]] = []
    for idx in range(10):
        rec_id = f"v4-noteshape-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            document = _base_document(idx, "각주/미주 서식 표본")
            paragraph = document.add_paragraph(f"본문 문단 {idx} — 각주·미주가 달립니다.")

            document.sections[0].properties.set_footnote_auto_num_format(
                type=NOTE_NUMBER_TYPE_BANK[idx % len(NOTE_NUMBER_TYPE_BANK)],
                suffix_char=")",
            )
            document.sections[0].properties.set_footnote_note_line(
                color=NOTE_LINE_COLOR_BANK[idx % len(NOTE_LINE_COLOR_BANK)],
                width=f"{0.2 + 0.1 * (idx % 3):.1f} mm",
                length=-2,
            )
            document.sections[0].properties.set_footnote_note_spacing(
                between_notes=100 + idx * 5, below_line=200, above_line=150,
            )
            document.sections[0].properties.set_footnote_numbering(
                type=FOOTNOTE_NUMBERING_TYPE_BANK[idx % len(FOOTNOTE_NUMBERING_TYPE_BANK)],
                new_num=1 + idx,
            )
            document.sections[0].properties.set_footnote_placement(
                place=FOOTNOTE_PLACEMENT_BANK[idx % len(FOOTNOTE_PLACEMENT_BANK)],
                beneath_text=(idx % 2 == 0),
            )

            document.sections[0].properties.set_endnote_auto_num_format(
                type=NOTE_NUMBER_TYPE_BANK[(idx + 1) % len(NOTE_NUMBER_TYPE_BANK)],
                suffix_char=".",
            )
            document.sections[0].properties.set_endnote_note_line(
                color=NOTE_LINE_COLOR_BANK[(idx + 1) % len(NOTE_LINE_COLOR_BANK)],
                width="0.3 mm",
            )
            document.sections[0].properties.set_endnote_note_spacing(
                between_notes=120, below_line=180 + idx * 5, above_line=140,
            )
            document.sections[0].properties.set_endnote_numbering(
                type=ENDNOTE_NUMBERING_TYPE_BANK[idx % len(ENDNOTE_NUMBERING_TYPE_BANK)],
                new_num=1,
            )
            document.sections[0].properties.set_endnote_placement(
                place=ENDNOTE_PLACEMENT_BANK[idx % len(ENDNOTE_PLACEMENT_BANK)],
                beneath_text=(idx % 2 == 1),
            )

            document.notes.add_footnote(
                f"각주 {idx}: {cycle(SUBJECT_BANK, idx)}", paragraph=paragraph,
            )
            document.notes.add_endnote(
                f"미주 {idx}: {cycle(DEPT_BANK, idx)} 참고", paragraph=paragraph,
            )

            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-note-shape", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001
            records.append(record(
                rec_id=rec_id, bucket="authored-note-shape", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


GENERATORS: tuple[tuple[str, Callable[[Path], list[dict[str, Any]]]], ...] = (
    ("baseline-regen", gen_baseline_regen),
    ("authored-footnote", gen_footnote),
    ("authored-formfield", gen_formfield),
    ("authored-equation", gen_equation),
    ("authored-chart", gen_chart),
    ("authored-checkbox", gen_checkbox),
    ("edit-plan", gen_edit_plan),
    ("authored-heading", gen_authored_heading),
    ("authored-named-style", gen_authored_named_style),
    ("authored-page-structure", gen_authored_page_structure),
    ("authored-note-shape", gen_authored_note_shape),
)


def main() -> int:
    try:
        import hwpx_automation  # noqa: F401
    except ModuleNotFoundError:
        print(
            "ERROR: v4 needs hwpx_automation importable (the chart stratum "
            f"composes ChartML through it). Expected it under "
            f"{AUTOMATION_REPO / 'src'} — checkout missing or moved.",
            file=sys.stderr,
        )
        return 2

    if OUT_DIR_V4.exists() and any(OUT_DIR_V4.iterdir()):
        print(
            f"ERROR: {OUT_DIR_V4} already exists — v4 is frozen once generated. "
            "Delete the tree explicitly to regenerate.",
            file=sys.stderr,
        )
        return 2

    all_records: list[dict[str, Any]] = []
    with _deterministic_object_ids():
        for bucket, generator in GENERATORS:
            bucket_dir = OUT_DIR_V4 / bucket
            bucket_dir.mkdir(parents=True, exist_ok=True)
            all_records += generator(bucket_dir)

    all_records.sort(key=lambda item: (item["bucket"], item["id"]))

    counts: dict[str, dict[str, Any]] = {}
    for entry in all_records:
        slot = counts.setdefault(
            entry["bucket"],
            {"requested": 0, "produced": 0, "withheld_ids": [], "static_unsafe_ids": []},
        )
        slot["requested"] += 1
        if entry["produced"]:
            slot["produced"] += 1
            if entry["static_open_safety_ok"] is False:
                slot["static_unsafe_ids"].append(entry["id"])
        else:
            slot["withheld_ids"].append(entry["id"])

    manifest = {
        "schemaVersion": MANIFEST_SCHEMA,
        "scopeNote": (
            "v4 is ADDITIVE over v3: the same 7 strata, rewritten to the 6.0 "
            "namespaced call surface (doc.notes/doc.fields/doc.shapes/"
            "doc.styles) with any DeprecationWarning treated as a generation "
            "failure, plus 4 new strata exercising the OWPML elements Q3b "
            "opened (pageBorderFill, footnote/endnote shape blocks, named "
            "hh:style creation) and the add_heading convenience API. It does "
            "not replace v1/v2/v3, which remain published with their own "
            "measurement stack and date."
        ),
        "generatedAt": None,  # root stamps it; determinism
        "toolVersions": _tool_versions(),
        "generatingCommit": {
            "python-hwpx": _git_commit(PYTHON_HWPX),
            "python-hwpx-automation": _git_commit(AUTOMATION_REPO),
        },
        "boxRoot": BOX_ROOT,
        "boxRootPdf": BOX_ROOT_PDF,
        "negativeControlsByReference": list(BOX_NEGATIVE_CONTROLS),
        "frozenPredecessors": {
            "v1": _frozen_reference(OUT_DIR / "manifest.json"),
            "v2": _frozen_reference(OUT_DIR_V2 / "manifest.json"),
            "v3": _frozen_reference(OUT_DIR_V3 / "manifest.json"),
        },
        "counts": counts,
        "requestedTotal": sum(slot["requested"] for slot in counts.values()),
        "producedTotal": sum(slot["produced"] for slot in counts.values()),
        "items": all_records,
    }
    manifest_path = OUT_DIR_V4 / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    filelist_path = OUT_DIR_V4 / "box_run_v4.filelist"
    lines = [
        f"{BOX_ROOT}\\{entry['bucket']}\\{entry['id']}.hwpx"
        for entry in all_records
        if entry["produced"]
    ]
    lines += list(BOX_NEGATIVE_CONTROLS)
    filelist_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Field names are the render pipeline's contract
    # (hancom_render_batch.ps1 reads $Job.sourceId/.stratum/.src/.pdf and it
    # expects a BARE ARRAY, not a wrapper object). The first v4 box run failed
    # on exactly this: {id,bucket,input,output} inside {"jobs": [...]} bound an
    # empty string into the renderer's Path parameters.
    render_jobs = [
        {
            "sourceId": entry["id"],
            "stratum": entry["bucket"],
            "src": f"{BOX_ROOT}\\{entry['bucket']}\\{entry['id']}.hwpx",
            "pdf": f"{BOX_ROOT_PDF}\\{entry['bucket']}\\{entry['id']}.pdf",
        }
        for entry in all_records
        if entry["produced"]
    ]
    render_jobs_path = OUT_DIR_V4 / "render_jobs_v4.json"
    render_jobs_path.write_text(
        json.dumps(render_jobs, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"v4 corpus: {manifest['producedTotal']}/{manifest['requestedTotal']} produced")
    for bucket in sorted(counts):
        slot = counts[bucket]
        flags = ""
        if slot["withheld_ids"]:
            flags += f"  withheld={len(slot['withheld_ids'])}"
        if slot["static_unsafe_ids"]:
            flags += f"  STATIC-UNSAFE={slot['static_unsafe_ids']}"
        print(f"  {bucket:24s} {slot['produced']:3d}/{slot['requested']:3d}{flags}")
    print(f"manifest    : {manifest_path}")
    print(f"filelist    : {filelist_path}")
    print(f"render jobs : {render_jobs_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
