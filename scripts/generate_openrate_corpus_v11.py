# SPDX-License-Identifier: Apache-2.0
"""openrate corpus v11 -- the 6.7 cycle's hp:label (Avery-style label-sheet/
nameplate print layout) authoring surface, additive over v10.

Why v11 exists
===============

Cycle 6.7 (train 26) opened one new authoring surface -- ``HwpxOxmlTable.
set_label``/``.label``/``.remove_label`` (``src/hwpx/oxml/body.py``,
``src/hwpx/oxml/table.py``) -- reverse-engineered from the maintainer's
private real-world corpus (DEV-023, docs/owpml-deviations.md), since the
47-file vendored corpus has zero real ``hp:label`` samples. That private
corpus's path is never recorded anywhere (including here); every value
this generator uses is synthetic, reconstructed from DEV-023's aggregate
findings, not copied from any real document. None of this authoring
surface has been exposed to a real Hancom oracle yet -- this is its first
batch.

One stratum (deterministic -- fixed seeds, bank rotation, no wall clock)
============================================================================

* ``authored-label``  15  Each record builds a table sized to its own
                           labelcols x labelrows grid, fills every cell
                           with short label-appropriate text (this is a
                           label/nameplate print layout, not prose), and
                           calls ``table.set_label(...)``. Weighted toward
                           DEV-023's two observed real-corpus clusters --
                           2x9 small label sheets (325/436 real
                           occurrences) and 1x2 large square nameplates
                           (111/436, boxwidth == boxlength) -- but
                           deliberately includes a handful of
                           out-of-distribution combinations DEV-023 never
                           observed: a labelcols x labelrows grid shape
                           neither real cluster used, landscape="NARROWLY"
                           (schema-legal per the enum, 0 real precedent --
                           every real sample was "WIDELY"), and two records
                           that set only a partial attribute subset
                           (leaving the rest ``None``, matching the
                           existing partial-update test coverage) rather
                           than the full 11-attribute set every real
                           sample carried. Every record still has to clear
                           the same static open-safety pre-filter every
                           other stratum does before it is ever produced.

Generation ONLY -- no Hancom oracle here. Every produced file gets the
static ``validate_editor_open_safety`` pre-filter (necessary, not
sufficient); the real verdict comes from the macOS GUI oracle (root's Mac).
``render_jobs_v11.json`` lists a PDF export job per produced file, same
shape as v4-v10.

Field names are the render pipeline's contract (see v4-v10's own comments)
-- a bare array of ``{sourceId,stratum,src,pdf}``, not wrapped in a
``{"jobs": [...]}`` object.

``toolVersions["python-hwpx"]`` is read from ``pyproject.toml`` directly,
not ``importlib.metadata`` -- same staleness rationale v4-v10 already
established.

    cd python-hwpx
    .venv-core/bin/python scripts/generate_openrate_corpus_v11.py
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

# Same discipline v4-v10 established: a moved/deprecated 5.x name firing its
# shim is a genuine 6.x-migration defect, not something to route around
# silently. Importing generate_openrate_corpus_v4 above already installs
# this filter (its own module-level statement) -- restated here so this
# module's contract is legible without reading v4's source.
import warnings  # noqa: E402

warnings.simplefilter("error", DeprecationWarning)

OUT_DIR_V11 = PYTHON_HWPX / "work" / "openrate-corpus-v11"
MANIFEST_SCHEMA = "hwpx.openrate.frozen-manifest.v11"
BOX_ROOT = "C:\\openrate\\v11"
BOX_ROOT_PDF = "C:\\openrate\\v11-pdf"


# ================================================================================
# authored-label banks
# ================================================================================
#: DEV-023: exactly 2 observed real combinations across 436 hp:label samples --
#: 2x9 small label sheets (325/436) and 1x2 large square nameplates (111/436,
#: boxwidth == boxlength). One out-of-distribution grid shape (3x6) neither
#: cluster used is mixed in to probe the acceptance boundary. Box/margin
#: dimensions here are synthetic HWPUNIT values reconstructed from DEV-023's
#: structural findings (the square-nameplate invariant, the small-sheet
#: proportions) -- not copied from any private document.
#: (labelcols, labelrows, topmargin, leftmargin, boxwidth, boxlength,
#:  boxmarginhor, boxmarginver)
_LAYOUT_BANK: tuple[tuple[int, int, int, int, int, int, int, int], ...] = (
    (2, 9, 2500, 900, 18000, 7500, 450, 0),      # small sheet (DEV-023 majority)
    (2, 9, 2500, 900, 18000, 7500, 450, 0),
    (2, 9, 2268, 850, 17500, 7200, 400, 0),      # small sheet, second synthetic variant
    (1, 2, 5670, 5670, 28346, 28346, 850, 850),  # large square nameplate (boxwidth==boxlength)
    (1, 2, 5670, 5670, 28346, 28346, 850, 850),
    (3, 6, 3200, 1200, 15000, 6000, 500, 0),      # out-of-distribution: unobserved grid shape
)

#: DEV-023: landscape="WIDELY" is the only value ever observed (100%, though
#: "NARROWLY" is schema-legal). One out-of-distribution entry mixed in.
_LANDSCAPE_BANK: tuple[str, ...] = ("WIDELY", "WIDELY", "WIDELY", "WIDELY", "WIDELY", "NARROWLY")

#: Page dimensions are independent of the label-sheet layout itself; two
#: plausible HWPUNIT page sizes (A4-ish portrait/landscape), no real-corpus
#: claim attached (DEV-023 did not report a page-size distribution).
_PAGE_SIZE_BANK: tuple[tuple[int, int], ...] = (
    (59528, 84188),
    (84188, 59528),
)

#: Records that only set a partial attribute subset (labelcols/labelrows/
#: landscape only, leaving margins/box/page dimensions None) -- DEV-023's own
#: test coverage already established set_label supports this, but every real
#: sample DEV-023 observed carried the full 11-attribute set. One-indexed
#: record numbers (within this stratum) that get the partial treatment.
_PARTIAL_ATTRIBUTE_RECORD_INDEXES: frozenset[int] = frozenset({4, 11})

#: Short, label-appropriate cell text -- this is a print layout for
#: individually-cut labels/nameplates, not prose. Synthetic placeholders only.
_CELL_TEXT_BANK: tuple[str, ...] = ("라벨", "명패", "구역", "번호표", "안내", "표시")


def _tool_versions() -> dict[str, str | None]:
    """python-hwpx's own version, pyproject-first (see module docstring)."""

    versions: dict[str, str | None] = {}
    versions["python-hwpx"] = _read_pyproject_version(PYTHON_HWPX / "pyproject.toml")
    if versions["python-hwpx"] is None:
        import hwpx

        versions["python-hwpx"] = str(hwpx.__version__)
    return versions


def _fill_label_grid(table: Any, cols: int, rows: int, idx: int) -> None:
    for row in range(rows):
        for col in range(cols):
            text = f"{_CELL_TEXT_BANK[(idx + row + col) % len(_CELL_TEXT_BANK)]} {row + 1}-{col + 1}"
            table.set_cell_text(row, col, text)


# ================================================================================
# stratum
# ================================================================================
def gen_label(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(15):
        rec_id = f"v11-label-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            cols, rows, topmargin, leftmargin, boxwidth, boxlength, marginhor, marginver = (
                _LAYOUT_BANK[idx % len(_LAYOUT_BANK)]
            )
            landscape = _LANDSCAPE_BANK[(idx + 1) % len(_LANDSCAPE_BANK)]
            pagewidth, pageheight = _PAGE_SIZE_BANK[(idx + 2) % len(_PAGE_SIZE_BANK)]
            partial = idx in _PARTIAL_ATTRIBUTE_RECORD_INDEXES

            document = _base_document(idx, "라벨 인쇄 레이아웃(hp:label) 저작 표본")
            paragraph = document.add_paragraph(
                f"표본 {idx}: labelcols={cols}, labelrows={rows}, "
                f"landscape={landscape}, partial={partial}"
            )
            table = paragraph.add_table(rows, cols)
            _fill_label_grid(table, cols, rows, idx)

            if partial:
                # Deliberately mirrors DEV-023's own
                # test_label_partial_update_only_sets_the_given_field
                # coverage on a real, saved document -- every real sample
                # DEV-023 observed carried the full attribute set, so this
                # combination has 0 real precedent.
                table.set_label(labelcols=cols, labelrows=rows, landscape=landscape)
            else:
                table.set_label(
                    topmargin=topmargin,
                    leftmargin=leftmargin,
                    boxwidth=boxwidth,
                    boxlength=boxlength,
                    boxmarginhor=marginhor,
                    boxmarginver=marginver,
                    labelcols=cols,
                    labelrows=rows,
                    landscape=landscape,
                    pagewidth=pagewidth,
                    pageheight=pageheight,
                )

            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-label", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001 - withheld is the honest record
            records.append(record(
                rec_id=rec_id, bucket="authored-label", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


GENERATORS: tuple[tuple[str, Callable[[Path], list[dict[str, Any]]]], ...] = (
    ("authored-label", gen_label),
)


def main() -> int:
    if OUT_DIR_V11.exists() and any(OUT_DIR_V11.iterdir()):
        print(
            f"ERROR: {OUT_DIR_V11} already exists -- v11 is frozen once generated. "
            "Delete the tree explicitly to regenerate.",
            file=sys.stderr,
        )
        return 2

    all_records: list[dict[str, Any]] = []
    with _deterministic_object_ids():
        for bucket, generator in GENERATORS:
            bucket_dir = OUT_DIR_V11 / bucket
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
            "v11 is ADDITIVE over v10: 1 new stratum exercising the sole "
            "authoring surface the 6.7 cycle opened (train 26) -- "
            "HwpxOxmlTable.set_label (hp:label, Avery-style label-sheet/"
            "nameplate print layout). This is 15 records, not a padded 30 "
            "or 45 -- the rotation space (6 layout combos x 6 landscape "
            "values x 2 page sizes, each bank offset by its own stride) "
            "already produces 15 genuinely different combinations without "
            "needing the full cartesian product. Deliberately mixes in a "
            "handful of combinations DEV-023's private-corpus reverse "
            "engineering never observed (a 3x6 label grid shape, "
            "landscape=NARROWLY, and 2 records with only labelcols/"
            "labelrows/landscape set rather than the full 11-attribute set "
            "every real sample carried) -- each is schema-legal and passes "
            "this repo's own static validators, so the real oracle batch "
            "is what actually tells us whether Hancom accepts, silently "
            "ignores, or rejects them. It does not re-touch v3-v10's "
            "strata; it does not replace v1-v10, which remain published "
            "with their own measurement stack and date."
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
        },
        "counts": counts,
        "requestedTotal": sum(slot["requested"] for slot in counts.values()),
        "producedTotal": sum(slot["produced"] for slot in counts.values()),
        "items": all_records,
    }
    manifest_path = OUT_DIR_V11 / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    filelist_path = OUT_DIR_V11 / "box_run_v11.filelist"
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
    render_jobs_path = OUT_DIR_V11 / "render_jobs_v11.json"
    render_jobs_path.write_text(
        json.dumps(render_jobs, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"v11 corpus: {manifest['producedTotal']}/{manifest['requestedTotal']} produced")
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
