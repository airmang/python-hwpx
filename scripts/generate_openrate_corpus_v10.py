# SPDX-License-Identifier: Apache-2.0
"""openrate corpus v10 -- the 6.6 cycle's document-options/compatibility
authoring surface, additive over v9.

Why v10 exists
===============

Cycle 6.6 (train 23) opened one new authoring surface, reverse-engineered
from real corpus and exposed as ``doc.parts.set_*``
(``src/hwpx/oxml/header_compat.py``): ``hh:compatibleDocument/
@targetProgram``, ``hh:compatibleDocument/hh:layoutCompatibility``'s flag
children, ``hh:docOption/hh:linkinfo``'s three attributes, and ``hh:paraPr/
hh:autoSpacing``. None of it has been exposed to a real Hancom oracle yet.

One stratum (deterministic -- fixed seeds, bank rotation, no wall clock)
============================================================================

* ``authored-compat``  15  All four settings combined per record via
                            ``doc.parts.set_compatible_document_target_
                            program``/``set_layout_compatibility_flags``/
                            ``set_doc_option_link_info``/
                            ``set_paragraph_auto_spacing``. Each of the 4
                            banks (target program, layout-compat flags,
                            link info, auto spacing) rotates with its own
                            stride so records combine differently across
                            axes rather than moving in lockstep. Weighted
                            toward the corpus-observed distribution (DEV-020:
                            targetProgram="HWP201X" 47/47, layoutCompatibility
                            0 flags 47/47, linkinfo path="" 47/47,
                            footnoteInherit="0" 47/47, pageInherit varies
                            8/47 "1") but deliberately includes a handful of
                            out-of-distribution combinations this repo has
                            never seen a real document exercise (targetProgram
                            ="HWP2018" -- schema-plausible per
                            hwpx.tools.package_validator.ACCEPTED_HANCOM_
                            TARGETS; 1-2 real layoutCompatibility flag names
                            actually set; footnoteInherit="1"; a non-empty
                            linkinfo path) -- this is the whole point of
                            handing it to the real oracle: those combinations
                            are schema-legal and our own static validators
                            accept them, but no real corpus evidence says
                            whether Hancom itself tolerates them silently,
                            warns, or rejects the file outright. Every record
                            still has to clear the same static
                            open-safety pre-filter every other stratum does
                            before it is ever produced -- this corpus does
                            not intentionally ship anything our own checks
                            already know is broken.

Generation ONLY -- no Hancom oracle here. Every produced file gets the
static ``validate_editor_open_safety`` pre-filter (necessary, not
sufficient); the real verdict comes from the macOS GUI oracle (root's Mac).
``render_jobs_v10.json`` lists a PDF export job per produced file, same
shape as v4-v9.

Field names are the render pipeline's contract (see v4-v9's own comments)
-- a bare array of ``{sourceId,stratum,src,pdf}``, not wrapped in a
``{"jobs": [...]}`` object.

``toolVersions["python-hwpx"]`` is read from ``pyproject.toml`` directly,
not ``importlib.metadata`` -- same staleness rationale v4-v9 already
established.

    cd python-hwpx
    .venv-core/bin/python scripts/generate_openrate_corpus_v10.py
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
from generate_openrate_corpus_v9 import OUT_DIR_V9  # noqa: E402

# Same discipline v4-v9 established: a moved/deprecated 5.x name firing its
# shim is a genuine 6.x-migration defect, not something to route around
# silently. Importing generate_openrate_corpus_v4 above already installs
# this filter (its own module-level statement) -- restated here so this
# module's contract is legible without reading v4's source.
import warnings  # noqa: E402

warnings.simplefilter("error", DeprecationWarning)

OUT_DIR_V10 = PYTHON_HWPX / "work" / "openrate-corpus-v10"
MANIFEST_SCHEMA = "hwpx.openrate.frozen-manifest.v10"
BOX_ROOT = "C:\\openrate\\v10"
BOX_ROOT_PDF = "C:\\openrate\\v10-pdf"


# ================================================================================
# authored-compat banks
# ================================================================================
#: DEV-020: 47/47 real files read "HWP201X" -- one out-of-distribution probe
#: ("HWP2018") mixed in. Both are schema-plausible per package_validator.py's
#: own ACCEPTED_HANCOM_TARGETS, but only "HWP201X" has real-corpus precedent.
_TARGET_PROGRAM_BANK: tuple[str, ...] = ("HWP201X", "HWP201X", "HWP201X", "HWP201X", "HWP2018")

#: DEV-020: 47/47 real files have zero flags despite the schema declaring 48
#: names. Mostly empty here too, with two out-of-distribution combinations
#: (real flag names, actually set) to probe the acceptance boundary.
_LAYOUT_COMPAT_FLAGS_BANK: tuple[tuple[str, ...], ...] = (
    (),
    (),
    (),
    (),
    ("applyFontWeightToBold",),
    ("useInnerUnderline", "doNotApplyShapeComment"),
)

#: DEV-020: path always "" (47/47), footnoteInherit always "0" (47/47),
#: pageInherit the only real-corpus-varying attribute (8/47 "1"). Two
#: out-of-distribution entries: footnote_inherit=True (0 real precedent) and
#: a non-empty path (simulating a master-document link, 0 real precedent).
_LINK_INFO_BANK: tuple[dict[str, Any], ...] = (
    {"path": "", "page_inherit": False, "footnote_inherit": False},
    {"path": "", "page_inherit": True, "footnote_inherit": False},
    {"path": "", "page_inherit": False, "footnote_inherit": False},
    {"path": "", "page_inherit": True, "footnote_inherit": False},
    {"path": "", "page_inherit": False, "footnote_inherit": True},
    {"path": "C:\\master.hwpx", "page_inherit": False, "footnote_inherit": False},
)

#: hh:autoSpacing -- unlike the three banks above, both booleans genuinely
#: vary in the real corpus already (138/1832 True for each), so there is no
#: out-of-distribution combination to add here -- all 4 (eAsianEng,
#: eAsianNum) pairs already have real precedent. Weighted toward the
#: corpus-majority (False, False) = 1694/1832.
_AUTO_SPACING_BANK: tuple[tuple[bool, bool], ...] = (
    (False, False),
    (False, False),
    (False, False),
    (True, True),
    (True, False),
    (False, True),
)


def _tool_versions() -> dict[str, str | None]:
    """python-hwpx's own version, pyproject-first (see module docstring)."""

    versions: dict[str, str | None] = {}
    versions["python-hwpx"] = _read_pyproject_version(PYTHON_HWPX / "pyproject.toml")
    if versions["python-hwpx"] is None:
        import hwpx

        versions["python-hwpx"] = str(hwpx.__version__)
    return versions


# ================================================================================
# stratum
# ================================================================================
def gen_compat(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(15):
        rec_id = f"v10-compat-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            target_program = _TARGET_PROGRAM_BANK[idx % len(_TARGET_PROGRAM_BANK)]
            flags = _LAYOUT_COMPAT_FLAGS_BANK[(idx + 1) % len(_LAYOUT_COMPAT_FLAGS_BANK)]
            link_info = _LINK_INFO_BANK[(idx + 2) % len(_LINK_INFO_BANK)]
            auto_eng, auto_num = _AUTO_SPACING_BANK[(idx + 3) % len(_AUTO_SPACING_BANK)]

            document = _base_document(idx, "문서 옵션·호환성 저작 표본")
            document.parts.set_compatible_document_target_program(target_program)
            document.parts.set_layout_compatibility_flags(flags)
            document.parts.set_doc_option_link_info(
                path=link_info["path"],
                page_inherit=link_info["page_inherit"],
                footnote_inherit=link_info["footnote_inherit"],
            )

            summary = (
                f"표본 {idx}: targetProgram={target_program} / "
                f"layoutCompatibility flags={list(flags)} / "
                f"linkinfo={link_info} / "
                f"autoSpacing(eAsianEng={auto_eng}, eAsianNum={auto_num}): "
                f"{cycle(SUBJECT_BANK, idx)}"
            )
            document.add_paragraph(summary)
            para_pr_id = document.oxml.headers[0].ensure_paragraph_format(alignment="LEFT")
            document.parts.set_paragraph_auto_spacing(
                para_pr_id, e_asian_eng=auto_eng, e_asian_num=auto_num
            )

            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-compat", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001 - withheld is the honest record
            records.append(record(
                rec_id=rec_id, bucket="authored-compat", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


GENERATORS: tuple[tuple[str, Callable[[Path], list[dict[str, Any]]]], ...] = (
    ("authored-compat", gen_compat),
)


def main() -> int:
    if OUT_DIR_V10.exists() and any(OUT_DIR_V10.iterdir()):
        print(
            f"ERROR: {OUT_DIR_V10} already exists -- v10 is frozen once generated. "
            "Delete the tree explicitly to regenerate.",
            file=sys.stderr,
        )
        return 2

    all_records: list[dict[str, Any]] = []
    with _deterministic_object_ids():
        for bucket, generator in GENERATORS:
            bucket_dir = OUT_DIR_V10 / bucket
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
            "v10 is ADDITIVE over v9: 1 new stratum exercising the sole "
            "authoring surface the 6.6 cycle opened (train 23) -- "
            "doc.parts.set_compatible_document_target_program/"
            "set_layout_compatibility_flags/set_doc_option_link_info/"
            "set_paragraph_auto_spacing. This is 15 records, not a padded "
            "30 or 45 -- the rotation space (5 target-program values x 6 "
            "flag combos x 6 link-info combos x 6 auto-spacing pairs, each "
            "bank offset by its own stride) already produces 15 genuinely "
            "different combinations without needing the full cartesian "
            "product. Deliberately mixes in a handful of combinations no "
            "real document in this repo's corpus has ever exercised "
            "(targetProgram=HWP2018, real layoutCompatibility flags "
            "actually set, footnoteInherit=1, a non-empty linkinfo path) -- "
            "each one is schema-legal and passes this repo's own static "
            "validators, so the real oracle batch is what actually tells "
            "us whether Hancom accepts, silently ignores, or rejects them. "
            "It does not re-touch v3-v9's strata; it does not replace "
            "v1-v9, which remain published with their own measurement "
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
        },
        "counts": counts,
        "requestedTotal": sum(slot["requested"] for slot in counts.values()),
        "producedTotal": sum(slot["produced"] for slot in counts.values()),
        "items": all_records,
    }
    manifest_path = OUT_DIR_V10 / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    filelist_path = OUT_DIR_V10 / "box_run_v10.filelist"
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
    render_jobs_path = OUT_DIR_V10 / "render_jobs_v10.json"
    render_jobs_path.write_text(
        json.dumps(render_jobs, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"v10 corpus: {manifest['producedTotal']}/{manifest['requestedTotal']} produced")
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
