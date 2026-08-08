# SPDX-License-Identifier: Apache-2.0
"""openrate corpus v15 -- closes the 3 remaining verification-debt items
train ㊳'s exhaustive 미실측 judgment table identified: form-field-create
and form-fill were plain omissions from v14's scope (no structural
blocker, see docs/editor-surface-inventory.md's 트레인㊳ judgment table),
and character-formatting's `italic` parameter was itself an omission
inside v14's own authored-charformat2 bank (found while reflowing v14 --
docs/support-matrix.md's 문자 서식 row now names it explicitly). v15 is
ADDITIVE over v14, cycle 6.11 cleanup train (after ㊳/㊴/㊵).

Why v15 exists
===============

Train ㊳'s judgment table (docs/editor-surface-inventory.md) concluded
form-field-create/form-fill were **omissions**, not intentional
deferrals -- `doc.fields.add` is a from-scratch single-call creation API
exactly like the 10 strata v14 already covered (no oracle/fixture
dependency), and form-fill's byte-splice mechanism is the same shape
already proven in v14 (authored-tablestructure/authored-editplan).
`authored-formfield` and `authored-formfill` are the first real-Hancom
batches for these two areas.

`authored-charformat-italic` targets the ONE gap v14's own
authored-charformat2 stratum left behind: `italic` was never in that
bank's rotation (a generator-design mistake, not a code gap --
`ensure_run(italic=True)` has existed since before v14). Since v14 is
already frozen/real-Hancom-measured, this couldn't be retrofitted into
that stratum -- it gets its own fresh one here instead.

Three strata (deterministic -- fixed seeds, bank rotation, no wall clock)
============================================================================

* ``authored-formfield``       5  ``doc.fields.add(name, *, prompt=,
                                     memo=, editable=, ...)`` -- rotates
                                     prompt/memo/editable presence, one
                                     record places the field inside a
                                     table cell (the docstring's own
                                     claim: "표 셀 배치 포함").
* ``authored-formfill``        5  Synthetic "form" (a 2-column table,
                                     label cells pre-filled, value cells
                                     empty) built fresh per record, then
                                     ``hwpx.table_patch.fill_cells``
                                     byte-splices values into the empty
                                     cells -- the same byte-splice shape
                                     v14's authored-tablestructure/
                                     authored-editplan already proved
                                     works as an openrate target.
* ``authored-charformat-italic`` 5  ``doc.styles.ensure_run(italic=True,
                                     ...)`` -- italic alone (2 records),
                                     italic+bold (already-verified combo,
                                     proves composability), italic+
                                     underline, italic+color -- four
                                     distinct combos across five records
                                     (one repeats a combo with different
                                     text, deterministic bank rotation).

Generation ONLY -- no Hancom oracle here. Every produced file gets the
static ``validate_editor_open_safety`` pre-filter (necessary, not
sufficient); the real verdict comes from the macOS GUI oracle (root's Mac).
``render_jobs_v15.json`` lists a PDF export job per produced file, same
shape as v4-v14.

Field names are the render pipeline's contract (see v4-v14's own comments)
-- a bare array of ``{sourceId,stratum,src,pdf}``, not wrapped in a
``{"jobs": [...]}`` object.

``toolVersions["python-hwpx"]`` is read from ``pyproject.toml`` directly,
not ``importlib.metadata`` -- same staleness rationale v4-v14 already
established.

    cd python-hwpx
    .venv-core/bin/python scripts/generate_openrate_corpus_v15.py
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

from hwpx.document import HwpxDocument  # noqa: E402
from hwpx.table_patch import fill_cells  # noqa: E402

# Same discipline v4-v14 established: a moved/deprecated 5.x name firing its
# shim is a genuine 6.x-migration defect, not something to route around
# silently. Importing generate_openrate_corpus_v4 above already installs
# this filter (its own module-level statement) -- restated here so this
# module's contract is legible without reading v4's source.
import warnings  # noqa: E402

warnings.simplefilter("error", DeprecationWarning)

OUT_DIR_V15 = PYTHON_HWPX / "work" / "openrate-corpus-v15"
MANIFEST_SCHEMA = "hwpx.openrate.frozen-manifest.v15"
BOX_ROOT = "C:\\openrate\\v15"
BOX_ROOT_PDF = "C:\\openrate\\v15-pdf"


# ================================================================================
# stratum 1 -- authored-formfield
# ================================================================================
_FORMFIELD_BANK: tuple[dict[str, Any], ...] = (
    {"prompt": "이름을 입력하세요", "memo": "성명 필드"},
    {"prompt": "", "memo": ""},
    {"prompt": "날짜를 선택하세요", "memo": "일정 안내"},
    {"prompt": "잠긴 필드입니다", "editable": False},
    {"prompt": "표 셀 안의 누름틀", "memo": "표 배치 확인"},
)


def gen_formfield(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(5):
        rec_id = f"v15-formfield-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            document = _base_document(idx, "누름틀 저작 표본")
            kwargs = dict(_FORMFIELD_BANK[idx])
            name = f"{cycle(DEPT_BANK, idx)}필드{idx}"

            if idx == 4:
                # "표 셀 배치 포함" -- place the field inside a table cell.
                table = document.add_table(rows=1, cols=2, width=42000)
                table.cell(0, 0).text = "항목"
                cell_paragraph = table.cell(0, 1).paragraphs[0]
                document.fields.add(name, paragraph=cell_paragraph, **kwargs)
            else:
                document.fields.add(name, **kwargs)

            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-formfield", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001 - withheld is the honest record
            records.append(record(
                rec_id=rec_id, bucket="authored-formfield", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


# ================================================================================
# stratum 2 -- authored-formfill (byte-splice into a synthetic form)
# ================================================================================
_FORMFILL_LABELS: tuple[str, ...] = ("성명", "부서", "직급", "연락처", "비고")


def _build_form_template(idx: int) -> HwpxDocument:
    """A minimal synthetic "form": a 2-column table, labels pre-filled,
    value cells left empty -- the shape authored-tablenavfill (v14)
    already exercises for label-matching, reused here as the fill
    target instead."""

    document = _base_document(idx, "양식 채움 대상 표본")
    table = document.add_table(rows=3, cols=2, width=42000)
    for row in range(3):
        table.cell(row, 0).text = cycle(_FORMFILL_LABELS, idx + row)
        # value column (col 1) is left empty -- fill_cells' own target.
    return document


def gen_formfill(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(5):
        rec_id = f"v15-formfill-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            document = _build_form_template(idx)
            data = document.to_bytes()

            cells = [
                {"tableIndex": 0, "row": row, "col": 1, "text": f"{cycle(DEPT_BANK, idx + row)} 값 {idx}"}
                for row in range(3)
            ]
            result = fill_cells(data, cells, output_path=out_path)
            if not result.ok:
                raise RuntimeError(f"fill_cells not ok: skipped={result.skipped}")

            records.append(record(
                rec_id=rec_id, bucket="authored-formfill", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001 - withheld is the honest record
            records.append(record(
                rec_id=rec_id, bucket="authored-formfill", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


# ================================================================================
# stratum 3 -- authored-charformat-italic (v14's own omission)
# ================================================================================
#: (kwargs, run text) -- idx0/1 italic alone (repeated with different
#: text, since there's nothing else to rotate for a single boolean);
#: idx2 italic+bold (already-verified combo, proves composability);
#: idx3 italic+underline; idx4 italic+color.
_ITALIC_BANK: tuple[dict[str, Any], ...] = (
    {"italic": True},
    {"italic": True},
    {"italic": True, "bold": True},
    {"italic": True, "underline": True},
    {"italic": True, "color": "#1F4E79"},
)


def gen_charformat_italic(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(5):
        rec_id = f"v15-charformat-italic-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            document = _base_document(idx, "기울임 표본")
            cid = document.styles.ensure_run(**_ITALIC_BANK[idx])
            document.add_paragraph(f"{cycle(DEPT_BANK, idx)} 기울임 표본 {idx}", char_pr_id_ref=cid)

            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-charformat-italic", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001 - withheld is the honest record
            records.append(record(
                rec_id=rec_id, bucket="authored-charformat-italic", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


GENERATORS: tuple[tuple[str, Callable[[Path], list[dict[str, Any]]]], ...] = (
    ("authored-formfield", gen_formfield),
    ("authored-formfill", gen_formfill),
    ("authored-charformat-italic", gen_charformat_italic),
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
    if OUT_DIR_V15.exists() and any(OUT_DIR_V15.iterdir()):
        print(
            f"ERROR: {OUT_DIR_V15} already exists -- v15 is frozen once generated. "
            "Delete the tree explicitly to regenerate.",
            file=sys.stderr,
        )
        return 2

    all_records: list[dict[str, Any]] = []
    with _deterministic_object_ids():
        for bucket, generator in GENERATORS:
            bucket_dir = OUT_DIR_V15 / bucket
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
            "v15 is ADDITIVE over v14: 3 new strata closing the "
            "verification-debt items train ㊳'s exhaustive 미실측 judgment "
            "table identified as plain omissions (not intentional "
            "deferrals) -- authored-formfield (doc.fields.add, "
            "form-field-create's first real-Hancom batch), "
            "authored-formfill (a synthetic 2-column form built fresh per "
            "record, then hwpx.table_patch.fill_cells byte-splices values "
            "into the empty value column -- form-fill's first real-Hancom "
            "batch), and authored-charformat-italic (ensure_run(italic="
            "True) alone and in combination with bold/underline/color -- "
            "the one parameter v14's own authored-charformat2 bank left "
            "out of its rotation, found while reflowing v14's results). "
            "It does not re-touch v3-v14's strata; it does not replace "
            "v1-v14, which remain published with their own measurement "
            "stack and date."
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
        },
        "counts": counts,
        "requestedTotal": sum(slot["requested"] for slot in counts.values()),
        "producedTotal": sum(slot["produced"] for slot in counts.values()),
        "items": all_records,
    }
    manifest_path = OUT_DIR_V15 / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    filelist_path = OUT_DIR_V15 / "box_run_v15.filelist"
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
    render_jobs_path = OUT_DIR_V15 / "render_jobs_v15.json"
    render_jobs_path.write_text(
        json.dumps(render_jobs, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"v15 corpus: {manifest['producedTotal']}/{manifest['requestedTotal']} produced")
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
