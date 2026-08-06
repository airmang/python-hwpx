# SPDX-License-Identifier: Apache-2.0
"""openrate corpus v8 — the 6.4 cycle's authored-only strata, additive over v7.

Why v8 exists
=============

Cycle 6.4 closed audit gap #7 (arc·polygon·curve·connectLine — "Parse·
Unsupported-but-preserved") for two of its four elements. Of the four, only
**two** produced a new authoring surface:

* ``hp:polygon`` — ``doc.shapes.add_polygon(points_mm=...)`` (train 13).
* ``hp:arc`` — ``doc.shapes.add_arc(width, height, corner=, arc_type=)``
  (train 14).

``hp:curve`` and ``hp:connectLine`` stayed honestly deferred (train 13/14's
own commits and ``docs/support-matrix.md`` carry the evidence: curve's one
real example has an ``orgSz`` measurably larger than its anchor-point
bounding box — spline overshoot with no derivable fit algorithm; connectLine
turned out to be a shape-to-shape "smart connector" with a negative offset,
a non-identity ``scaMatrix``, and no way to reverse the relationship from a
single sample). Nothing new to author for either means nothing new for an
openrate corpus to measure — **v8 has no authored-curve or
authored-connectline stratum**, the same "additive means additive" discipline
v7 already established for compose/container and comboBox.

Two strata (all deterministic — fixed seeds, bank rotation, no wall clock)
=============================================================================

* ``authored-polygon``  15  ``doc.shapes.add_polygon`` — rotates through 4
                              vertex-count shapes (triangle/pentagon/
                              hexagon/5-point star, via the same regular-
                              polygon and star point-generation used in
                              ``tests/test_polygon_authoring.py``) and a
                              5-color fill bank. Every record's points are
                              generated fresh from ``idx``, not copy-pasted
                              literals, so vertex count and geometry genuinely
                              differ record to record.
* ``authored-arc``       15  ``doc.shapes.add_arc`` — rotates through all
                              12 ``corner`` x ``arc_type`` combinations
                              (4 corners x NORMAL/PIE/CHORD) plus a
                              width/height size bank, so every corner
                              (only ``TOP_LEFT`` is corpus-verified
                              point-for-point; the other three mirror it via
                              ``hp:flip`` — see ``_create_arc_element``'s own
                              docstring) gets real Hancom exposure across
                              this corpus, not just the default.

That is 30 records total (15+15) — the same shape v7 settled on for its own
two-surface cycle, for the same reason: padding either stratum past what the
rotation banks actually vary would repeat rather than add coverage.

Generation ONLY — no Hancom oracle here. Every produced file gets the static
``validate_editor_open_safety`` pre-filter (necessary, not sufficient); the
real verdict comes from the macOS GUI oracle (osascript-driven, this Mac).
``render_jobs_v8.json`` lists a PDF export job per produced file, same shape
as v4-v7.

Field names are the render pipeline's contract (see v4-v7's own comments) —
a bare array of ``{sourceId,stratum,src,pdf}``, not wrapped in a
``{"jobs": [...]}`` object.

``toolVersions["python-hwpx"]`` is read from ``pyproject.toml`` directly, not
``importlib.metadata`` — same staleness rationale v4-v7 already established.

    cd python-hwpx
    .venv-core/bin/python scripts/generate_openrate_corpus_v8.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any, Callable

PYTHON_HWPX = Path(__file__).resolve().parent.parent
# Explicit — this worktree's src/ must win over whatever editable install the
# running venv happens to carry (v5's own comment records the exact failure
# mode this guards against).
sys.path.insert(0, str(PYTHON_HWPX / "src"))
sys.path.insert(0, str(PYTHON_HWPX / "scripts"))

from generate_openrate_corpus import (  # noqa: E402
    SUBJECT_BANK,
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

# Same discipline v4-v7 established: a moved/deprecated 5.x name firing its
# shim is a genuine 6.x-migration defect, not something to route around
# silently. Importing generate_openrate_corpus_v4 above already installs
# this filter (its own module-level statement) — restated here so this
# module's contract is legible without reading v4's source.
import warnings  # noqa: E402

warnings.simplefilter("error", DeprecationWarning)

OUT_DIR_V8 = PYTHON_HWPX / "work" / "openrate-corpus-v8"
MANIFEST_SCHEMA = "hwpx.openrate.frozen-manifest.v8"
BOX_ROOT = "C:\\openrate\\v8"
BOX_ROOT_PDF = "C:\\openrate\\v8-pdf"


# ================================================================================
# new-stratum banks (rotation only — no wall clock, no randomness)
# ================================================================================
#: sides for the regular-polygon bank (triangle/pentagon/hexagon); the 4th
#: slot is a 5-point star (handled separately, not a regular polygon).
POLYGON_SIDES_BANK = (3, 5, 6, None)  # None => star
POLYGON_FILL_BANK = ("#A0BEE0", "#F1CB7E", "#86AFDC", "#CCE5FF", "#FFD9CC")

ARC_CORNER_BANK = ("TOP_LEFT", "TOP_RIGHT", "BOTTOM_LEFT", "BOTTOM_RIGHT")
ARC_TYPE_BANK = ("NORMAL", "PIE", "CHORD")
ARC_FILL_BANK = ("#F1CB7E", "#86AFDC", "#CCE5FF")
#: (width, height) in HWPUNIT — rotates so records are not all one size.
ARC_SIZE_BANK = ((12450, 11225), (14400, 7200), (8000, 8000), (10000, 15000))


def _regular_polygon_points_mm(
    *, sides: int, radius_mm: float, center_mm: tuple[float, float] = (40.0, 40.0),
) -> list[tuple[float, float]]:
    cx, cy = center_mm
    return [
        (
            cx + radius_mm * math.sin(2 * math.pi * i / sides),
            cy - radius_mm * math.cos(2 * math.pi * i / sides),
        )
        for i in range(sides)
    ]


def _star_points_mm(
    *, points: int, outer_mm: float, inner_mm: float,
    center_mm: tuple[float, float] = (40.0, 40.0),
) -> list[tuple[float, float]]:
    cx, cy = center_mm
    vertices: list[tuple[float, float]] = []
    for i in range(points * 2):
        radius = outer_mm if i % 2 == 0 else inner_mm
        angle = math.pi * i / points
        vertices.append((cx + radius * math.sin(angle), cy - radius * math.cos(angle)))
    return vertices


def _tool_versions() -> dict[str, str | None]:
    """python-hwpx's own version, pyproject-first (see module docstring)."""

    versions: dict[str, str | None] = {}
    versions["python-hwpx"] = _read_pyproject_version(PYTHON_HWPX / "pyproject.toml")
    if versions["python-hwpx"] is None:
        import hwpx

        versions["python-hwpx"] = str(hwpx.__version__)
    return versions


# ================================================================================
# strata
# ================================================================================
def gen_polygon(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(15):
        rec_id = f"v8-polygon-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            document = _base_document(idx, "다각형 저작 표본")
            sides = POLYGON_SIDES_BANK[idx % len(POLYGON_SIDES_BANK)]
            fill = POLYGON_FILL_BANK[idx % len(POLYGON_FILL_BANK)]
            radius = 20.0 + (idx % 3) * 5.0  # 20/25/30mm — rotates the size too
            if sides is None:
                points_mm = _star_points_mm(points=5, outer_mm=radius, inner_mm=radius * 0.4)
                shape_name = "별형"
            else:
                points_mm = _regular_polygon_points_mm(sides=sides, radius_mm=radius)
                shape_name = {3: "삼각형", 5: "오각형", 6: "육각형"}[sides]
            document.add_paragraph(f"다각형 표본 {idx} ({shape_name}): {cycle(SUBJECT_BANK, idx)}")
            document.shapes.add_polygon(points_mm, fill_color=fill, section=0)
            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-polygon", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001 - withheld is the honest record
            records.append(record(
                rec_id=rec_id, bucket="authored-polygon", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


def gen_arc(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(15):
        rec_id = f"v8-arc-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            document = _base_document(idx, "호 저작 표본")
            corner = ARC_CORNER_BANK[idx % len(ARC_CORNER_BANK)]
            arc_type = ARC_TYPE_BANK[idx % len(ARC_TYPE_BANK)]
            fill = ARC_FILL_BANK[idx % len(ARC_FILL_BANK)]
            width, height = ARC_SIZE_BANK[idx % len(ARC_SIZE_BANK)]
            document.add_paragraph(f"호 표본 {idx} ({corner}/{arc_type}): {cycle(SUBJECT_BANK, idx)}")
            document.shapes.add_arc(
                width, height, corner=corner, arc_type=arc_type,
                fill_color=fill, section=0,
            )
            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-arc", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001
            records.append(record(
                rec_id=rec_id, bucket="authored-arc", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


GENERATORS: tuple[tuple[str, Callable[[Path], list[dict[str, Any]]]], ...] = (
    ("authored-polygon", gen_polygon),
    ("authored-arc", gen_arc),
)


def main() -> int:
    if OUT_DIR_V8.exists() and any(OUT_DIR_V8.iterdir()):
        print(
            f"ERROR: {OUT_DIR_V8} already exists — v8 is frozen once generated. "
            "Delete the tree explicitly to regenerate.",
            file=sys.stderr,
        )
        return 2

    all_records: list[dict[str, Any]] = []
    with _deterministic_object_ids():
        for bucket, generator in GENERATORS:
            bucket_dir = OUT_DIR_V8 / bucket
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
            "v8 is ADDITIVE over v7: 2 new strata exercising the ONLY two "
            "authorable surfaces the 6.4 cycle opened for audit gap #7 "
            "(arc/polygon/curve/connectLine) — doc.shapes.add_polygon "
            "(train 13) and doc.shapes.add_arc (train 14). curve and "
            "connectLine stayed honestly deferred this cycle (see "
            "docs/support-matrix.md and the train-13/14 commits for the "
            "measured evidence — curve's one real example has an orgSz "
            "larger than its anchor-point bounding box with no derivable "
            "fit algorithm; connectLine turned out to be a shape-to-shape "
            "smart connector with a negative offset and non-identity "
            "scaMatrix, not a standalone primitive), so there is "
            "deliberately NO authored-curve or authored-connectline "
            "stratum here — the same 'nothing new to author means nothing "
            "new to measure' discipline v7 already established for "
            "compose/container and comboBox. This is 30 records total "
            "(15+15), not a padded 60 or 90 — the rotation banks (4 "
            "polygon shapes x 5 fill colors x 3 sizes; 4 arc corners x 3 "
            "arc_types x 4 sizes) are small enough that padding either "
            "stratum further would repeat rather than add coverage. It "
            "does not re-touch v3-v7's strata; it does not replace v1-v7, "
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
        },
        "counts": counts,
        "requestedTotal": sum(slot["requested"] for slot in counts.values()),
        "producedTotal": sum(slot["produced"] for slot in counts.values()),
        "items": all_records,
    }
    manifest_path = OUT_DIR_V8 / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    filelist_path = OUT_DIR_V8 / "box_run_v8.filelist"
    lines = [
        f"{BOX_ROOT}\\{entry['bucket']}\\{entry['id']}.hwpx"
        for entry in all_records
        if entry["produced"]
    ]
    lines += list(BOX_NEGATIVE_CONTROLS)
    filelist_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Field names are the render pipeline's contract (see module docstring —
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
    render_jobs_path = OUT_DIR_V8 / "render_jobs_v8.json"
    render_jobs_path.write_text(
        json.dumps(render_jobs, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"v8 corpus: {manifest['producedTotal']}/{manifest['requestedTotal']} produced")
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
