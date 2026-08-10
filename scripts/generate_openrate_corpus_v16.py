# SPDX-License-Identifier: Apache-2.0
"""openrate corpus v16 -- first real-Hancom batch for train ㊸'s 5 new gaps
(cycle 6.12, editor-menu reverse-map found by train ㊷, authored by train 48
across 4 commits: fac1a03/c5c6968/ffe0ef8/f7e4e67). v16 is ADDITIVE over v15.

Five strata (deterministic -- fixed seeds, bank rotation, no wall clock)
============================================================================

* ``authored-document-metadata`` 5  ``doc.parts.set_document_metadata`` --
                                     rotates title/creator/subject/keyword,
                                     one record leaves them empty (real-
                                     corpus 67-fixture census: 31/67 titles
                                     were empty strings), one sets created_
                                     date/modified_date explicitly.
* ``authored-drop-cap``          5  ``doc.shapes.add_drop_cap`` -- rotates
                                     the enlarged character across 5
                                     distinct Korean characters plus a
                                     width/height variant, proving the
                                     TripleLine builder isn't hardcoded to
                                     the single real-corpus example it was
                                     reverse-engineered from.
* ``authored-text-direction``    5  ``doc.page.set_text_direction`` --
                                     VERTICAL/VERTICALALL/explicit-
                                     HORIZONTAL combined with
                                     vertical_header_footer True/False.
                                     Zero real-corpus VERTICAL examples
                                     exist (see the module's own docstring
                                     in oxml/section_format.py) -- this is
                                     v16's whole point, first real-Hancom
                                     evidence either way.
* ``authored-column-break``      5  ``doc.styles.apply_paragraph_format(
                                     column_break=True)`` on a different
                                     paragraph position in a multi-
                                     paragraph document each record,
                                     proving it's a per-instance flag, not
                                     a document-wide toggle.
* ``authored-table-split-merge`` 5  ``hwpx.table_patch.apply_table_ops``'s
                                     new 'split_table'/'merge_table' ops --
                                     3 split variants at different row
                                     counts/positions, 1 merge of two
                                     freshly-built adjacent tables, 1
                                     split-then-merge round trip inside a
                                     single record (proves the two ops
                                     compose back to the original shape).

Generation ONLY -- no Hancom oracle here. Every produced file gets the
static ``validate_editor_open_safety`` pre-filter (necessary, not
sufficient); the real verdict comes from the macOS GUI oracle (root's Mac).
``render_jobs_v16.json`` lists a PDF export job per produced file, same
shape as v4-v15.

Field names are the render pipeline's contract (see v4-v15's own comments)
-- a bare array of ``{sourceId,stratum,src,pdf}``, not wrapped in a
``{"jobs": [...]}`` object.

``toolVersions["python-hwpx"]`` is read from ``pyproject.toml`` directly,
not ``importlib.metadata`` -- same staleness rationale v4-v15 already
established.

    cd python-hwpx
    .venv-core/bin/python scripts/generate_openrate_corpus_v16.py
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

from hwpx.document import HwpxDocument  # noqa: E402
from hwpx.table_patch import apply_table_ops  # noqa: E402

# Same discipline v4-v15 established: a moved/deprecated 5.x name firing its
# shim is a genuine 6.x-migration defect, not something to route around
# silently. Importing generate_openrate_corpus_v4 above already installs
# this filter (its own module-level statement) -- restated here so this
# module's contract is legible without reading v4's source.
import warnings  # noqa: E402

warnings.simplefilter("error", DeprecationWarning)

OUT_DIR_V16 = PYTHON_HWPX / "work" / "openrate-corpus-v16"
MANIFEST_SCHEMA = "hwpx.openrate.frozen-manifest.v16"
BOX_ROOT = "C:\\openrate\\v16"
BOX_ROOT_PDF = "C:\\openrate\\v16-pdf"


# ================================================================================
# stratum 1 -- authored-document-metadata
# ================================================================================
_METADATA_BANK: tuple[dict[str, Any], ...] = (
    {"title": "행정 안내문", "creator": "기획부", "subject": "협조 요청"},
    {"title": "", "creator": "", "subject": ""},
    {"title": "보고서 초안", "creator": "운영부", "keyword": "분기보고"},
    {"title": "회의록", "creator": "지원부", "created_date": "2026-08-01T09:00:00Z", "modified_date": "2026-08-04T17:30:00Z"},
    {"title": "공지사항", "creator": "총무부", "subject": "일정 변경", "keyword": "공지"},
)


def gen_document_metadata(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(5):
        rec_id = f"v16-document-metadata-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            document = _base_document(idx, "문서 정보 저작 표본")
            document.parts.set_document_metadata(**_METADATA_BANK[idx])

            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-document-metadata", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001 - withheld is the honest record
            records.append(record(
                rec_id=rec_id, bucket="authored-document-metadata", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


# ================================================================================
# stratum 2 -- authored-drop-cap
# ================================================================================
#: (character, width, height) -- 5 distinct characters, one with a
#: different width/height ratio to prove the size isn't hardcoded.
_DROP_CAP_BANK: tuple[tuple[str, int, int], ...] = (
    ("가", 4200, 4200),
    ("나", 4200, 4200),
    ("다", 4200, 4200),
    ("라", 4200, 4200),
    ("마", 5600, 4200),
)


def gen_drop_cap(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(5):
        rec_id = f"v16-drop-cap-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            character, width, height = _DROP_CAP_BANK[idx]
            document = HwpxDocument.new()
            document.shapes.add_drop_cap(character, width=width, height=height)
            document.add_paragraph(f"{cycle(DEPT_BANK, idx)} 드롭캡 본문 표본 {idx}")

            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-drop-cap", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001 - withheld is the honest record
            records.append(record(
                rec_id=rec_id, bucket="authored-drop-cap", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


# ================================================================================
# stratum 3 -- authored-text-direction
# ================================================================================
#: (direction, vertical_header_footer) -- VERTICAL/VERTICALALL both flag
#: combos, plus an explicit HORIZONTAL set-back (round-trip toggling).
_TEXT_DIRECTION_BANK: tuple[tuple[str, bool], ...] = (
    ("VERTICAL", False),
    ("VERTICAL", True),
    ("VERTICALALL", False),
    ("VERTICALALL", True),
    ("HORIZONTAL", False),
)


def gen_text_direction(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(5):
        rec_id = f"v16-text-direction-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            direction, vertical_header_footer = _TEXT_DIRECTION_BANK[idx]
            document = _base_document(idx, "글자 방향 저작 표본")
            document.page.set_text_direction(
                direction, vertical_header_footer=vertical_header_footer, section=0,
            )

            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-text-direction", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001 - withheld is the honest record
            records.append(record(
                rec_id=rec_id, bucket="authored-text-direction", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


# ================================================================================
# stratum 4 -- authored-column-break
# ================================================================================


def gen_column_break(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(5):
        rec_id = f"v16-column-break-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            document = HwpxDocument.new()
            for p in range(5):
                document.add_paragraph(f"{cycle(DEPT_BANK, idx + p)} 단 나누기 본문 {p}")
            # the break sits on paragraph idx (0..4) -- a different physical
            # position per record, proving it's per-paragraph, not global.
            document.styles.apply_paragraph_format(paragraph_index=idx, column_break=True)

            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-column-break", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001 - withheld is the honest record
            records.append(record(
                rec_id=rec_id, bucket="authored-column-break", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


# ================================================================================
# stratum 5 -- authored-table-split-merge
# ================================================================================


def _build_labeled_table(document: HwpxDocument, row_cnt: int, prefix: str) -> None:
    table = document.add_table(rows=row_cnt, cols=1, width=20000)
    for r in range(row_cnt):
        table.cell(r, 0).text = f"{prefix}{r}"


def gen_table_split_merge(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    plans: tuple[tuple[str, Callable[[Path], None]], ...] = (
        ("split-3-at-1", lambda out: _split_variant(out, row_cnt=3, split_row=1)),
        ("split-4-at-2", lambda out: _split_variant(out, row_cnt=4, split_row=2)),
        ("split-5-at-3", lambda out: _split_variant(out, row_cnt=5, split_row=3)),
        ("merge-2plus2", _merge_variant),
        ("split-then-merge", _round_trip_variant),
    )
    for idx, (label, build) in enumerate(plans):
        rec_id = f"v16-table-split-merge-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            build(out_path)
            records.append(record(
                rec_id=rec_id, bucket="authored-table-split-merge", seed=label,
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001 - withheld is the honest record
            records.append(record(
                rec_id=rec_id, bucket="authored-table-split-merge", seed=label,
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


def _split_variant(out_path: Path, *, row_cnt: int, split_row: int) -> None:
    document = HwpxDocument.new()
    document.add_paragraph("표 나누기 저작 표본")
    _build_labeled_table(document, row_cnt, "행")
    data = document.to_bytes()
    result = apply_table_ops(
        data, [{"op": "split_table", "table_index": 0, "split_row": split_row}],
        output_path=out_path,
    )
    if not result.ok:
        raise RuntimeError(f"split_table not ok: skipped={result.skipped}")


def _merge_variant(out_path: Path) -> None:
    document = HwpxDocument.new()
    document.add_paragraph("표 붙이기 저작 표본")
    _build_labeled_table(document, 2, "위")
    _build_labeled_table(document, 2, "아래")
    data = document.to_bytes()
    result = apply_table_ops(
        data, [{"op": "merge_table", "table_index": 0}], output_path=out_path,
    )
    if not result.ok:
        raise RuntimeError(f"merge_table not ok: skipped={result.skipped}")


def _round_trip_variant(out_path: Path) -> None:
    document = HwpxDocument.new()
    document.add_paragraph("표 나누기·붙이기 왕복 표본")
    _build_labeled_table(document, 4, "칸")
    data = document.to_bytes()
    split = apply_table_ops(data, [{"op": "split_table", "table_index": 0, "split_row": 2}])
    if not split.ok:
        raise RuntimeError(f"split_table not ok: skipped={split.skipped}")
    merged = apply_table_ops(
        split.data, [{"op": "merge_table", "table_index": 0}], output_path=out_path,
    )
    if not merged.ok:
        raise RuntimeError(f"merge_table not ok: skipped={merged.skipped}")


GENERATORS: tuple[tuple[str, Callable[[Path], list[dict[str, Any]]]], ...] = (
    ("authored-document-metadata", gen_document_metadata),
    ("authored-drop-cap", gen_drop_cap),
    ("authored-text-direction", gen_text_direction),
    ("authored-column-break", gen_column_break),
    ("authored-table-split-merge", gen_table_split_merge),
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
    if OUT_DIR_V16.exists() and any(OUT_DIR_V16.iterdir()):
        print(
            f"ERROR: {OUT_DIR_V16} already exists -- v16 is frozen once generated. "
            "Delete the tree explicitly to regenerate.",
            file=sys.stderr,
        )
        return 2

    all_records: list[dict[str, Any]] = []
    with _deterministic_object_ids():
        for bucket, generator in GENERATORS:
            bucket_dir = OUT_DIR_V16 / bucket
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
            "v16 is ADDITIVE over v15: 5 new strata covering train ㊸'s "
            "editor-menu gaps (found by train ㊷'s exhaustive reverse-map, "
            "authored by train 48 across 4 commits) -- authored-document-"
            "metadata (doc.parts.set_document_metadata, opf:metadata's "
            "first real-Hancom batch), authored-drop-cap (doc.shapes."
            "add_drop_cap, TripleLine dropcapstyle reverse-engineered from "
            "the single real-corpus example that used it), authored-text-"
            "direction (doc.page.set_text_direction, zero real-corpus "
            "VERTICAL/VERTICALALL examples existed before this batch), "
            "authored-column-break (doc.styles.apply_paragraph_format("
            "column_break=True), hp:p's own instance attribute, distinct "
            "from page_break_before's shared paraPr mechanism), and "
            "authored-table-split-merge (apply_table_ops's new "
            "split_table/merge_table ops -- table flip was deliberately "
            "NOT authored this train, see docs/support-matrix.md's "
            "table-structure row). It does not re-touch v3-v15's strata; "
            "it does not replace v1-v15, which remain published with "
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
        },
        "counts": counts,
        "requestedTotal": sum(slot["requested"] for slot in counts.values()),
        "producedTotal": sum(slot["produced"] for slot in counts.values()),
        "items": all_records,
    }
    manifest_path = OUT_DIR_V16 / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    filelist_path = OUT_DIR_V16 / "box_run_v16.filelist"
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
    render_jobs_path = OUT_DIR_V16 / "render_jobs_v16.json"
    render_jobs_path.write_text(
        json.dumps(render_jobs, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"v16 corpus: {manifest['producedTotal']}/{manifest['requestedTotal']} produced")
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
