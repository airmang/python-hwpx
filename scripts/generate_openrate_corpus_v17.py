# SPDX-License-Identifier: Apache-2.0
"""openrate corpus v17 -- first real-Hancom batch for train ㊻'s 3
"Create(experimental)" authoring surfaces (cycle 6.13, editor-menu
reverse-map gap closure). v17 is ADDITIVE over v16.

Three strata (deterministic -- fixed seeds, bank rotation, no wall clock)
============================================================================

* ``authored-cell-equalize``   5  ``HwpxOxmlTable.equalize_column_widths``/
                                   ``.equalize_row_heights`` -- rotates
                                   equalize-columns-only, equalize-rows-
                                   only, both together, and two records
                                   with a merged cell present (colSpan/
                                   rowSpan) to exercise the span-sum
                                   logic that differs from a plain
                                   uniform-weight case.
* ``authored-outline-numbering`` 5  ``doc.styles.apply_list_format(
                                   kind="outline", ...)`` -- the one
                                   genuinely new surface train ㊻ opened
                                   (개요 적용/해제·수준 증감 themselves
                                   needed no new code, already covered by
                                   add_heading elsewhere). Rotates level
                                   1/2/3, numFormat DIGIT/HANGUL/
                                   KOREAN_DIGIT, and one record combining
                                   a custom outline number with
                                   apply_paragraph_format's level-increase
                                   to prove the two mechanisms compose.
* ``authored-master-page``     5  ``doc.parts.add_master_page`` +
                                   ``doc.page.set_master_page`` --
                                   rotates page_type (OPTIONAL_PAGE/EVEN/
                                   ODD)/page_number/page_duplicate/
                                   page_front, one record with 2
                                   paragraphs of body text, one record
                                   creating a second master page to
                                   prove the part-index auto-increment
                                   produces a document Hancom still
                                   accepts.

Generation ONLY -- no Hancom oracle here. Every produced file gets the
static ``validate_editor_open_safety`` pre-filter (necessary, not
sufficient); the real verdict comes from the macOS GUI oracle (root's Mac).
``render_jobs_v17.json`` lists a PDF export job per produced file, same
shape as v4-v16.

Field names are the render pipeline's contract (see v4-v16's own comments)
-- a bare array of ``{sourceId,stratum,src,pdf}``, not wrapped in a
``{"jobs": [...]}`` object.

``toolVersions["python-hwpx"]`` is read from ``pyproject.toml`` directly,
not ``importlib.metadata`` -- same staleness rationale v4-v16 already
established.

    cd python-hwpx
    .venv-core/bin/python scripts/generate_openrate_corpus_v17.py
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

from hwpx.document import HwpxDocument  # noqa: E402

# Same discipline v4-v16 established: a moved/deprecated 5.x name firing its
# shim is a genuine 6.x-migration defect, not something to route around
# silently. Importing generate_openrate_corpus_v4 above already installs
# this filter (its own module-level statement) -- restated here so this
# module's contract is legible without reading v4's source.
import warnings  # noqa: E402

warnings.simplefilter("error", DeprecationWarning)

OUT_DIR_V17 = PYTHON_HWPX / "work" / "openrate-corpus-v17"
MANIFEST_SCHEMA = "hwpx.openrate.frozen-manifest.v17"
BOX_ROOT = "C:\\openrate\\v17"
BOX_ROOT_PDF = "C:\\openrate\\v17-pdf"


# ================================================================================
# stratum 1 -- authored-cell-equalize
# ================================================================================


def gen_cell_equalize(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    plans: tuple[tuple[str, Callable[[Any], None]], ...] = (
        ("columns-only", lambda t: t.equalize_column_widths()),
        ("rows-only", lambda t: t.equalize_row_heights()),
        ("both", lambda t: (t.equalize_column_widths(), t.equalize_row_heights())),
        ("both-with-col-merge", _equalize_with_column_merge),
        ("both-with-row-merge", _equalize_with_row_merge),
    )
    for idx, (label, apply_plan) in enumerate(plans):
        rec_id = f"v17-cell-equalize-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            document = _base_document(idx, "표 균등화 저작 표본")
            table = document.add_table(rows=3, cols=3, width=30000, height=9000)
            for row in range(3):
                for col in range(3):
                    table.cell(row, col).text = f"{cycle(DEPT_BANK, idx + row + col)}"
            table.set_column_widths([1, 5, 2])
            apply_plan(table)

            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-cell-equalize", seed=label,
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001 - withheld is the honest record
            records.append(record(
                rec_id=rec_id, bucket="authored-cell-equalize", seed=label,
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


def _equalize_with_column_merge(table: Any) -> None:
    table.merge_cells("A1:B1")
    table.equalize_column_widths()
    table.equalize_row_heights()


def _equalize_with_row_merge(table: Any) -> None:
    table.merge_cells("A1:A2")
    table.equalize_column_widths()
    table.equalize_row_heights()


# ================================================================================
# stratum 2 -- authored-outline-numbering
# ================================================================================
#: (level, number_format, start) -- rotates the customization axes
#: ensure_numbering(kind="outline") newly opened.
_OUTLINE_BANK: tuple[tuple[int, str, int], ...] = (
    (1, "DIGIT", 1),
    (2, "HANGUL", 1),
    (3, "KOREAN_DIGIT", 1),
    (1, "DIGIT", 5),
    (2, "HANGUL", 1),
)


def gen_outline_numbering(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(5):
        rec_id = f"v17-outline-numbering-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            level, number_format, start = _OUTLINE_BANK[idx]
            document = _base_document(idx, "개요 번호 모양 저작 표본")
            document.add_paragraph(f"{cycle(DEPT_BANK, idx)} 개요 대상 문단 {idx}")
            document.styles.apply_list_format(
                paragraph_index=len(document.paragraphs) - 1,
                kind="outline", level=level, number_format=number_format, start=start,
            )
            if idx == 4:
                # proves the two mechanisms (custom outline number +
                # existing level-increase) compose without conflict.
                document.styles.apply_paragraph_format(
                    paragraph_index=len(document.paragraphs) - 1, outline_level=level + 1,
                )

            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-outline-numbering", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001 - withheld is the honest record
            records.append(record(
                rec_id=rec_id, bucket="authored-outline-numbering", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


# ================================================================================
# stratum 3 -- authored-master-page
# ================================================================================
#: (page_type, page_number, page_duplicate, page_front) -- rotates the
#: schema-declared axes add_master_page exposes.
_MASTER_PAGE_BANK: tuple[tuple[str, int, bool, bool], ...] = (
    ("OPTIONAL_PAGE", 1, False, False),
    ("EVEN", 1, True, False),
    ("ODD", 2, False, True),
    ("OPTIONAL_PAGE", 3, True, True),
    ("BOTH", 1, False, False),
)


def gen_master_page(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(5):
        rec_id = f"v17-master-page-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            page_type, page_number, page_duplicate, page_front = _MASTER_PAGE_BANK[idx]
            document = _base_document(idx, "바탕쪽 저작 표본")

            if idx == 4:
                paragraphs = [f"{cycle(DEPT_BANK, idx)} 회사명", "기밀문서"]
                master_page_id = document.parts.add_master_page(
                    paragraphs=paragraphs, page_type=page_type,
                    page_number=page_number, page_duplicate=page_duplicate,
                    page_front=page_front,
                )
                # a second master page to prove the part-index
                # auto-increment produces a document Hancom still accepts.
                document.parts.add_master_page(text="둘째 바탕쪽")
            else:
                master_page_id = document.parts.add_master_page(
                    text=f"{cycle(DEPT_BANK, idx)} 회사명", page_type=page_type,
                    page_number=page_number, page_duplicate=page_duplicate,
                    page_front=page_front,
                )
            document.page.set_master_page(master_page_id, section=0)

            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-master-page", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001 - withheld is the honest record
            records.append(record(
                rec_id=rec_id, bucket="authored-master-page", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


GENERATORS: tuple[tuple[str, Callable[[Path], list[dict[str, Any]]]], ...] = (
    ("authored-cell-equalize", gen_cell_equalize),
    ("authored-outline-numbering", gen_outline_numbering),
    ("authored-master-page", gen_master_page),
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
    if OUT_DIR_V17.exists() and any(OUT_DIR_V17.iterdir()):
        print(
            f"ERROR: {OUT_DIR_V17} already exists -- v17 is frozen once generated. "
            "Delete the tree explicitly to regenerate.",
            file=sys.stderr,
        )
        return 2

    all_records: list[dict[str, Any]] = []
    with _deterministic_object_ids():
        for bucket, generator in GENERATORS:
            bucket_dir = OUT_DIR_V17 / bucket
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
            "v17 is ADDITIVE over v16: 3 new strata covering train ㊻'s "
            "editor-menu 부분 대응 closures (found by train ㊷'s exhaustive "
            "reverse-map, authored by train 48) -- authored-cell-equalize "
            "(HwpxOxmlTable.equalize_column_widths/equalize_row_heights, "
            "pure convenience wrappers over the already-verified "
            "set_column_widths mechanism, no new XML vocabulary), "
            "authored-outline-numbering (doc.styles.apply_list_format("
            "kind=\"outline\"), the one genuinely new surface -- "
            "개요 적용/해제·수준 증감 needed no new code, already covered "
            "by add_heading elsewhere), and authored-master-page ("
            "doc.parts.add_master_page + doc.page.set_master_page, opening "
            "the write side the read-only HwpxOxmlMasterPage explicitly "
            "deferred in cycle 6.4). It does not re-touch v3-v16's strata; "
            "it does not replace v1-v16, which remain published with "
            "their own measurement stack and date."
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
        },
        "counts": counts,
        "requestedTotal": sum(slot["requested"] for slot in counts.values()),
        "producedTotal": sum(slot["produced"] for slot in counts.values()),
        "items": all_records,
    }
    manifest_path = OUT_DIR_V17 / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    filelist_path = OUT_DIR_V17 / "box_run_v17.filelist"
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
    render_jobs_path = OUT_DIR_V17 / "render_jobs_v17.json"
    render_jobs_path.write_text(
        json.dumps(render_jobs, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"v17 corpus: {manifest['producedTotal']}/{manifest['requestedTotal']} produced")
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
