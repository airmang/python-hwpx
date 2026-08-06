# SPDX-License-Identifier: Apache-2.0
"""openrate corpus v9 — the 6.5 cycle's two authoring surfaces, additive over v8.

Why v9 exists
=============

Cycle 6.5 (trains 18-19) opened two new authoring surfaces, reverse-engineered
from real corpus: ``doc.shapes.add_container`` (grouping already-built
rect/ellipse/polygon members into an ``hp:container``, train 18) and
``paragraph.add_run(text, expand_special_characters=True)`` (converting
embedded ``"\n"``/``"\u00a0"``/``"\u3000"`` to ``hp:lineBreak``/``hp:nbSpace``/
``hp:fwSpace`` nested inside a single ``hp:t``, train 19 — which also fixed a
real *reading* bug for the same three markers, unrelated to what this corpus
measures). Neither surface has been exposed to a real Hancom oracle yet.

Two strata (all deterministic — fixed seeds, bank rotation, no wall clock)
=============================================================================

* ``authored-container``   15  ``doc.shapes.add_container`` — member count
                                rotates 2/3/4 (5 records each), member kind
                                (rect/ellipse/polygon, via
                                ``ContainerMember.rect``/``.ellipse``/
                                ``.polygon``) rotates per member slot with a
                                per-record starting offset so different
                                records emphasize different kind orderings,
                                not just different counts. Fill color rotates
                                independently per member.
* ``authored-inlineatoms``  15  ``paragraph.add_run(expand_special_characters=
                                True)`` — the 15 records are the complete set
                                of non-empty ordered combinations of the 3
                                atoms up to length 3 that actually differ:
                                3 singles (L/N/F) + 6 ordered pairs (LN, NL,
                                LF, FL, NF, FN) + 6 ordered triples (the
                                3! = 6 permutations of L, N, F) = 15 exactly
                                — every record exercises a distinct atom
                                subset-and-order, not just a repeated pattern
                                padded to 15.

Generation ONLY — no Hancom oracle here. Every produced file gets the static
``validate_editor_open_safety`` pre-filter (necessary, not sufficient); the
real verdict comes from the macOS GUI oracle (osascript-driven, root's Mac).
``render_jobs_v9.json`` lists a PDF export job per produced file, same shape
as v4-v8.

Field names are the render pipeline's contract (see v4-v8's own comments) —
a bare array of ``{sourceId,stratum,src,pdf}``, not wrapped in a
``{"jobs": [...]}`` object.

``toolVersions["python-hwpx"]`` is read from ``pyproject.toml`` directly, not
``importlib.metadata`` — same staleness rationale v4-v8 already established.

    cd python-hwpx
    .venv-core/bin/python scripts/generate_openrate_corpus_v9.py
"""
from __future__ import annotations

import json
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
from generate_openrate_corpus_v8 import OUT_DIR_V8  # noqa: E402

from hwpx.oxml import ContainerMember  # noqa: E402

# Same discipline v4-v8 established: a moved/deprecated 5.x name firing its
# shim is a genuine 6.x-migration defect, not something to route around
# silently. Importing generate_openrate_corpus_v4 above already installs
# this filter (its own module-level statement) — restated here so this
# module's contract is legible without reading v4's source.
import warnings  # noqa: E402

warnings.simplefilter("error", DeprecationWarning)

OUT_DIR_V9 = PYTHON_HWPX / "work" / "openrate-corpus-v9"
MANIFEST_SCHEMA = "hwpx.openrate.frozen-manifest.v9"
BOX_ROOT = "C:\\openrate\\v9"
BOX_ROOT_PDF = "C:\\openrate\\v9-pdf"


# ================================================================================
# authored-container banks
# ================================================================================
#: member count per record, 15 records rotating 2/3/4 (5 records each) —
#: "2~4부재 회전" from the train assignment.
_CONTAINER_MEMBER_COUNT_BANK = tuple(2 + (i % 3) for i in range(15))

_CONTAINER_MEMBER_KIND_BANK = ("rect", "ellipse", "polygon")
_CONTAINER_FILL_BANK = ("#A0BEE0", "#F1CB7E", "#86AFDC", "#CCE5FF", "#FFD9CC")

#: HWPUNIT — every member shares one bbox size so a record's members line up
#: cleanly in a row regardless of kind; the polygon member is a triangle
#: inscribed in that same bbox, not a separately-sized shape.
_CONTAINER_MEMBER_WIDTH = 4000
_CONTAINER_MEMBER_HEIGHT = 3000
_CONTAINER_MEMBER_GAP = 500


def _build_container_member(kind: str, x: int, y: int, fill: str) -> "ContainerMember":
    if kind == "rect":
        return ContainerMember.rect(x, y, _CONTAINER_MEMBER_WIDTH, _CONTAINER_MEMBER_HEIGHT, fill_color=fill)
    if kind == "ellipse":
        return ContainerMember.ellipse(x, y, _CONTAINER_MEMBER_WIDTH, _CONTAINER_MEMBER_HEIGHT, fill_color=fill)
    if kind == "polygon":
        points = [
            (0, _CONTAINER_MEMBER_HEIGHT),
            (_CONTAINER_MEMBER_WIDTH, _CONTAINER_MEMBER_HEIGHT),
            (_CONTAINER_MEMBER_WIDTH // 2, 0),
        ]
        return ContainerMember.polygon(x, y, points, fill_color=fill)
    raise ValueError(f"unknown container member kind: {kind!r}")  # pragma: no cover - bank is closed


# ================================================================================
# authored-inlineatoms banks
# ================================================================================
#: L=hp:lineBreak ("\n"), N=hp:nbSpace (U+00A0), F=hp:fwSpace (U+3000) — see
#: add_run's own docstring (oxml/paragraph.py) for the character mapping.
_ATOM_CHARS = {"L": "\n", "N": "\xa0", "F": "\u3000"}

#: The complete set of non-empty ordered atom combinations up to length 3
#: that are actually distinct: 3 singles + 6 ordered pairs (all 3*2
#: permutations of 2-of-3) + 6 ordered triples (all 3! permutations of
#: 3-of-3) = 15 exactly. Not padded, not repeated — every record here is a
#: genuinely different combination-and-order.
_ATOM_COMBO_BANK = (
    "L", "N", "F",
    "LN", "NL", "LF", "FL", "NF", "FN",
    "LNF", "NFL", "FLN", "LFN", "NLF", "FNL",
)
assert len(_ATOM_COMBO_BANK) == 15
assert len(set(_ATOM_COMBO_BANK)) == 15, "combo bank must have no duplicates"


def _atom_combo_text(idx: int, combo: str) -> str:
    """Join len(combo)+1 rotating text fragments with the atom characters
    combo names, in order — e.g. combo="LN" over fragments a/b/c becomes
    "a" + lineBreak + "b" + nbSpace + "c"."""

    fragments = [cycle(SUBJECT_BANK, idx + i) for i in range(len(combo) + 1)]
    parts = [fragments[0]]
    for i, code in enumerate(combo):
        parts.append(_ATOM_CHARS[code])
        parts.append(fragments[i + 1])
    return "".join(parts)


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
def gen_container(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(15):
        rec_id = f"v9-container-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            document = _base_document(idx, "그룹 개체 저작 표본")
            count = _CONTAINER_MEMBER_COUNT_BANK[idx]
            members = []
            kinds_used: list[str] = []
            for m in range(count):
                kind = _CONTAINER_MEMBER_KIND_BANK[(idx + m) % len(_CONTAINER_MEMBER_KIND_BANK)]
                kinds_used.append(kind)
                x = m * (_CONTAINER_MEMBER_WIDTH + _CONTAINER_MEMBER_GAP)
                fill = _CONTAINER_FILL_BANK[(idx + m) % len(_CONTAINER_FILL_BANK)]
                members.append(_build_container_member(kind, x, 0, fill))
            document.add_paragraph(
                f"그룹 표본 {idx} ({count}부재: {'/'.join(kinds_used)}): {cycle(SUBJECT_BANK, idx)}"
            )
            document.shapes.add_container(members, section=0)
            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-container", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001 - withheld is the honest record
            records.append(record(
                rec_id=rec_id, bucket="authored-container", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


def gen_inlineatoms(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(15):
        rec_id = f"v9-inlineatoms-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            document = _base_document(idx, "인라인 원자 저작 표본")
            combo = _ATOM_COMBO_BANK[idx]
            document.add_paragraph(f"인라인 원자 표본 {idx} (조합 {combo})")
            atom_paragraph = document.add_paragraph("", include_run=False)
            atom_paragraph.add_run(
                _atom_combo_text(idx, combo), expand_special_characters=True,
            )
            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-inlineatoms", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001
            records.append(record(
                rec_id=rec_id, bucket="authored-inlineatoms", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


GENERATORS: tuple[tuple[str, Callable[[Path], list[dict[str, Any]]]], ...] = (
    ("authored-container", gen_container),
    ("authored-inlineatoms", gen_inlineatoms),
)


def main() -> int:
    if OUT_DIR_V9.exists() and any(OUT_DIR_V9.iterdir()):
        print(
            f"ERROR: {OUT_DIR_V9} already exists — v9 is frozen once generated. "
            "Delete the tree explicitly to regenerate.",
            file=sys.stderr,
        )
        return 2

    all_records: list[dict[str, Any]] = []
    with _deterministic_object_ids():
        for bucket, generator in GENERATORS:
            bucket_dir = OUT_DIR_V9 / bucket
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
            "v9 is ADDITIVE over v8: 2 new strata exercising the two "
            "authoring surfaces the 6.5 cycle opened — doc.shapes."
            "add_container (train 18, grouping rect/ellipse/polygon "
            "members) and paragraph.add_run(expand_special_characters="
            "True) (train 19, hp:lineBreak/nbSpace/fwSpace authoring). "
            "This is 30 records total (15+15), not a padded 60 or 90 — "
            "authored-container's rotation space (3 member counts x 3 "
            "kinds per slot) and authored-inlineatoms' (the complete "
            "15-combination set of non-empty ordered atom subsets up to "
            "length 3) are both exactly the size that produces no "
            "repeats. It does not re-touch v3-v8's strata; it does not "
            "replace v1-v8, which remain published with their own "
            "measurement stack and date."
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
        },
        "counts": counts,
        "requestedTotal": sum(slot["requested"] for slot in counts.values()),
        "producedTotal": sum(slot["produced"] for slot in counts.values()),
        "items": all_records,
    }
    manifest_path = OUT_DIR_V9 / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    filelist_path = OUT_DIR_V9 / "box_run_v9.filelist"
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
    render_jobs_path = OUT_DIR_V9 / "render_jobs_v9.json"
    render_jobs_path.write_text(
        json.dumps(render_jobs, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"v9 corpus: {manifest['producedTotal']}/{manifest['requestedTotal']} produced")
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
