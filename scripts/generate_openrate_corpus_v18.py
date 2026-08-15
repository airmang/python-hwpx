# SPDX-License-Identifier: Apache-2.0
"""openrate corpus v18 -- first real-Hancom batch for train 48's date/time
field + proofreading-mark field authoring (cycle 6.13, editor-menu
reverse-map priority-reorder gap closure). v18 is ADDITIVE over v17.

Two strata (deterministic -- fixed seeds, bank rotation, no wall clock)
============================================================================

* ``authored-date-field``          5  ``HwpxOxmlParagraph.add_date_field``
                                       -- v1 scope is deliberately narrow
                                       (single confirmed date_format/
                                       date_nation combination, see
                                       ``oxml/field_marks.py``'s module
                                       docstring) so this rotates what IS
                                       confirmed: cached_text values,
                                       placement (alone / mid-paragraph
                                       surrounded by text), repetition
                                       (two fields in one document), a
                                       non-default char_pr_id_ref, and
                                       composition with add_heading.
* ``authored-proofreading-marks``  5  ``HwpxOxmlParagraph.
                                       add_proofreading_mark`` -- v1 scope
                                       is narrower still (the only
                                       confirmed $RevisionSign index is
                                       mark="space"=1). Rotates placement
                                       (alone / mid-sentence, matching the
                                       real dialog's actual use case of
                                       marking a missing-space location),
                                       repetition, a non-default
                                       char_pr_id_ref, and composition
                                       with add_table.

No titleMark stratum: team-lead's 2026-08-11 GUI re-probe (3 rounds)
confirmed titleMark's real target is a TOC-page entry paragraph that this
environment cannot place a caret inside (no canvas click, no keystroke
reaches the document) -- authoring stays deferred (DEV-044). See
docs/editor-menu-reverse-map.md's "차례 숨기기 / 제목 차례 표시" row.

Generation ONLY -- no Hancom oracle here. Every produced file gets the
static ``validate_editor_open_safety`` pre-filter (necessary, not
sufficient); the real verdict comes from the macOS GUI oracle (root's Mac).
``render_jobs_v18.json`` lists a PDF export job per produced file, same
shape as v4-v17.

Field names are the render pipeline's contract (see v4-v17's own comments)
-- a bare array of ``{sourceId,stratum,src,pdf}``, not wrapped in a
``{"jobs": [...]}`` object.

``toolVersions["python-hwpx"]`` is read from ``pyproject.toml`` directly,
not ``importlib.metadata`` -- same staleness rationale v4-v17 already
established.

    cd python-hwpx
    .venv-core/bin/python scripts/generate_openrate_corpus_v18.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

PYTHON_HWPX = Path(__file__).resolve().parent.parent
# Explicit -- this worktree's src/ must win over whatever editable install the
# running venv happens to carry (v5's own comment records the exact failure
# mode this guards against).
sys.path.insert(0, str(PYTHON_HWPX / "src"))
sys.path.insert(0, str(PYTHON_HWPX / "scripts"))

from generate_openrate_corpus import (  # noqa: E402
    DEPT_BANK,
    cycle,
    record,
)
from generate_openrate_corpus_v3 import (  # noqa: E402
    BOX_NEGATIVE_CONTROLS,
    OUT_DIR_V3,
    _base_document,
)
from generate_openrate_corpus_v4 import (  # noqa: E402
    OUT_DIR_V4,
    _deterministic_object_ids,
    _frozen_reference,
    _git_commit,
    _read_pyproject_version,
)
from generate_openrate_corpus_v5 import OUT_DIR_V5  # noqa: E402
from generate_openrate_corpus_v6 import OUT_DIR_V6  # noqa: E402
from generate_openrate_corpus_v7 import OUT_DIR_V7  # noqa: E402
from generate_openrate_corpus_v8 import OUT_DIR_V8  # noqa: E402
from generate_openrate_corpus_v9 import OUT_DIR_V9  # noqa: E402
from generate_openrate_corpus_v10 import OUT_DIR_V10  # noqa: E402
from generate_openrate_corpus_v11 import OUT_DIR_V11  # noqa: E402
from generate_openrate_corpus_v12 import OUT_DIR_V12  # noqa: E402
from generate_openrate_corpus_v13 import OUT_DIR_V13  # noqa: E402
from generate_openrate_corpus_v14 import OUT_DIR_V14  # noqa: E402
from generate_openrate_corpus_v15 import OUT_DIR_V15  # noqa: E402
from generate_openrate_corpus_v16 import OUT_DIR_V16  # noqa: E402
from generate_openrate_corpus_v17 import OUT_DIR_V17  # noqa: E402


# Same discipline v4-v17 established: a moved/deprecated 5.x name firing its
# shim is a genuine 6.x-migration defect, not something to route around
# silently. Importing generate_openrate_corpus_v4 above already installs
# this filter (its own module-level statement) -- restated here so this
# module's contract is legible without reading v4's source.
import warnings  # noqa: E402

warnings.simplefilter("error", DeprecationWarning)

OUT_DIR_V18 = PYTHON_HWPX / "work" / "openrate-corpus-v18"
MANIFEST_SCHEMA = "hwpx.openrate.frozen-manifest.v18"
BOX_ROOT = "C:\\openrate\\v18"
BOX_ROOT_PDF = "C:\\openrate\\v18-pdf"


# ================================================================================
# stratum 1 -- authored-date-field
# ================================================================================
#: cached_text values -- the one confirmed date_format ("YYYY년 M월 D일")
#: does not constrain these (the module's Command preview string is fixed
#: regardless of cached_text, see field_marks.py); this rotates what a
#: caller would plausibly compute for "오늘 날짜" on different days.
_DATE_TEXT_BANK: tuple[str, ...] = (
    "2026년 8월 11일",
    "2025년 12월 25일",
    "2026년 1월 1일",
    "2026년 3월 2일",
    "2026년 8월 11일",
)


def gen_date_field(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(5):
        rec_id = f"v18-date-field-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            cached_text = _DATE_TEXT_BANK[idx]
            document = _base_document(idx, "날짜/시간 필드 저작 표본")
            if idx == 0:
                # alone in its own paragraph, matching the real gold sample.
                paragraph = document.add_paragraph("", include_run=False)
                paragraph.add_date_field(cached_text)
            elif idx == 1:
                # mid-paragraph, surrounded by real text on both sides.
                paragraph = document.add_paragraph("작성일: ", include_run=True)
                paragraph.add_date_field(cached_text)
                paragraph.add_run(" (자동 갱신 아님)")
            elif idx == 2:
                # repetition -- two independent fields in one document,
                # exercising id/fieldid uniqueness across calls.
                p1 = document.add_paragraph("", include_run=False)
                p1.add_date_field(cached_text)
                p2 = document.add_paragraph("접수일: ", include_run=True)
                p2.add_date_field(_DATE_TEXT_BANK[(idx + 1) % len(_DATE_TEXT_BANK)])
            elif idx == 3:
                # non-default char_pr_id_ref -- confirms the field's run
                # inherits the requested character format like any other
                # add_run-family call.
                cid = document.styles.ensure_run(bold=True)
                paragraph = document.add_paragraph("", include_run=False)
                paragraph.add_date_field(cached_text, char_pr_id_ref=cid)
            else:
                # composition with add_heading -- date field lands in the
                # paragraph right after a heading, not the heading itself.
                document.add_heading(f"{cycle(DEPT_BANK, idx)} 보고서", level=1)
                paragraph = document.add_paragraph("작성일 ", include_run=True)
                paragraph.add_date_field(cached_text)

            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-date-field", seed=cached_text,
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001 - withheld is the honest record
            records.append(record(
                rec_id=rec_id, bucket="authored-date-field", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


# ================================================================================
# stratum 2 -- authored-proofreading-marks
# ================================================================================


def gen_proofreading_marks(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(5):
        rec_id = f"v18-proofreading-marks-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            document = _base_document(idx, "교정 부호 저작 표본")
            if idx == 0:
                # alone in its own paragraph.
                paragraph = document.add_paragraph("", include_run=False)
                paragraph.add_proofreading_mark("space")
            elif idx == 1:
                # mid-sentence -- the real dialog's actual use case: marking
                # a missing-space location inside otherwise-typed text.
                paragraph = document.add_paragraph("이것은시험", include_run=True)
                paragraph.add_proofreading_mark("space")
                paragraph.add_run("문장입니다.")
            elif idx == 2:
                # repetition -- two independent marks in one document.
                p1 = document.add_paragraph("첫번째부분", include_run=True)
                p1.add_proofreading_mark("space")
                p1.add_run("입니다.")
                p2 = document.add_paragraph("두번째부분", include_run=True)
                p2.add_proofreading_mark("space")
                p2.add_run("입니다.")
            elif idx == 3:
                # non-default char_pr_id_ref.
                cid = document.styles.ensure_run(bold=True)
                paragraph = document.add_paragraph("", include_run=False)
                paragraph.add_proofreading_mark("space", char_pr_id_ref=cid)
            else:
                # composition with add_table -- mark lands in a paragraph
                # sharing the document with a table, not inside a cell.
                document.add_table(rows=2, cols=2, width=20000, height=6000)
                paragraph = document.add_paragraph("표아래문장", include_run=True)
                paragraph.add_proofreading_mark("space")
                paragraph.add_run("입니다.")

            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-proofreading-marks", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001 - withheld is the honest record
            records.append(record(
                rec_id=rec_id, bucket="authored-proofreading-marks", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


GENERATORS: tuple[tuple[str, Callable[[Path], list[dict[str, Any]]]], ...] = (
    ("authored-date-field", gen_date_field),
    ("authored-proofreading-marks", gen_proofreading_marks),
)


def _tool_versions() -> dict[str, str | None]:
    """python-hwpx's own version, pyproject-first (see module docstring)."""

    versions: dict[str, str | None] = {}
    versions["python-hwpx"] = _read_pyproject_version(PYTHON_HWPX / "pyproject.toml")
    if versions["python-hwpx"] is None:
        import hwpx

        versions["python-hwpx"] = str(hwpx.__version__)
    return versions


def main() -> int:
    if OUT_DIR_V18.exists() and any(OUT_DIR_V18.iterdir()):
        print(
            f"ERROR: {OUT_DIR_V18} already exists -- v18 is frozen once generated. "
            "Delete the tree explicitly to regenerate.",
            file=sys.stderr,
        )
        return 2

    all_records: list[dict[str, Any]] = []
    with _deterministic_object_ids():
        for bucket, generator in GENERATORS:
            bucket_dir = OUT_DIR_V18 / bucket
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
            "v18 is ADDITIVE over v17: 2 new strata covering train 48's "
            "GUI-probe-confirmed date/time + proofreading-mark field "
            "authoring (priority-reordered ahead of the 부분 대응 backlog "
            "by team-lead's real-Hancom GUI probes ①③) -- authored-date-"
            "field (HwpxOxmlParagraph.add_date_field, type=DATE, the one "
            "confirmed date_format/date_nation combination rotated across "
            "cached_text/placement/repetition/char_pr_id_ref/heading-"
            "composition) and authored-proofreading-marks (HwpxOxmlParagraph."
            "add_proofreading_mark, type=PROOFREADING_MARKS_SIGN -- DEV-043, "
            "the one confirmed $RevisionSign index mark=\"space\" rotated "
            "the same way plus table composition). No titleMark stratum: "
            "team-lead's GUI probe② re-probe (3 rounds) found the real "
            "target is a TOC-entry paragraph this environment cannot place "
            "a caret inside -- authoring stays deferred, DEV-044. It does "
            "not re-touch v3-v17's strata; it does not replace v1-v17, "
            "which remain published with their own measurement stack and "
            "date."
        ),
        "generatedAt": None,  # root stamps it; determinism
        "toolVersions": _tool_versions(),
        "generatingCommit": {
            "python-hwpx": _git_commit(PYTHON_HWPX),
        },
        "boxRoot": BOX_ROOT,
        "boxRootPdf": BOX_ROOT_PDF,
        "negativeControlsByReference": list(BOX_NEGATIVE_CONTROLS),
        "frozenPredecessors": {
            "v3": _frozen_reference(OUT_DIR_V3 / "manifest.json"),
            "v4": _frozen_reference(OUT_DIR_V4 / "manifest.json"),
            "v5": _frozen_reference(OUT_DIR_V5 / "manifest.json"),
            "v6": _frozen_reference(OUT_DIR_V6 / "manifest.json"),
            "v7": _frozen_reference(OUT_DIR_V7 / "manifest.json"),
            "v8": _frozen_reference(OUT_DIR_V8 / "manifest.json"),
            "v9": _frozen_reference(OUT_DIR_V9 / "manifest.json"),
            "v10": _frozen_reference(OUT_DIR_V10 / "manifest.json"),
            "v11": _frozen_reference(OUT_DIR_V11 / "manifest.json"),
            "v12": _frozen_reference(OUT_DIR_V12 / "manifest.json"),
            "v13": _frozen_reference(OUT_DIR_V13 / "manifest.json"),
            "v14": _frozen_reference(OUT_DIR_V14 / "manifest.json"),
            "v15": _frozen_reference(OUT_DIR_V15 / "manifest.json"),
            "v16": _frozen_reference(OUT_DIR_V16 / "manifest.json"),
            "v17": _frozen_reference(OUT_DIR_V17 / "manifest.json"),
        },
        "counts": counts,
        "requestedTotal": sum(slot["requested"] for slot in counts.values()),
        "producedTotal": sum(slot["produced"] for slot in counts.values()),
        "items": all_records,
    }
    manifest_path = OUT_DIR_V18 / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    filelist_path = OUT_DIR_V18 / "box_run_v18.filelist"
    lines = [
        f"{BOX_ROOT}\\{entry['bucket']}\\{entry['id']}.hwpx"
        for entry in all_records
        if entry["produced"]
    ]
    lines += list(BOX_NEGATIVE_CONTROLS)
    filelist_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Field names are the render pipeline's contract (see module docstring --
    # v5's already-corrected shape, copied verbatim: a bare array of
    # {sourceId,stratum,src,pdf}, not {id,bucket,input,output} wrapped in a
    # {"jobs": [...]} object.
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
    render_jobs_path = OUT_DIR_V18 / "render_jobs_v18.json"
    render_jobs_path.write_text(
        json.dumps(render_jobs, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"v18 corpus: {manifest['producedTotal']}/{manifest['requestedTotal']} produced")
    for bucket in sorted(counts):
        slot = counts[bucket]
        flags = ""
        if slot["withheld_ids"]:
            flags += f"  withheld={slot['withheld_ids']}"
        if slot["static_unsafe_ids"]:
            flags += f"  STATIC-UNSAFE={slot['static_unsafe_ids']}"
        print(f"  {bucket:24s} {slot['produced']:3d}/{slot['requested']:3d}{flags}")
    print(f"manifest    : {manifest_path}")
    print(f"filelist    : {filelist_path}")
    print(f"render jobs : {render_jobs_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
