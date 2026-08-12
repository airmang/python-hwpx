# SPDX-License-Identifier: Apache-2.0
"""openrate corpus v20 -- cross-real-document merge (cycle 6.14 follow-up
audit). v20 is ADDITIVE over v19.

One stratum (deterministic -- fixed pairs/indexes, no wall clock)
============================================================================

* ``cross-real-merge``  12  ``hwpx.tools.document_merge`` append/insert
                            between REAL-Hancom-saved documents (the
                            m3_gongmun_gold trio + the clickhere gold form
                            + the date/proofreading GUI probe). Every prior
                            merge probe (v13) merged OUR generated files,
                            whose headers carry few custom styles and no
                            layout caches -- which is exactly why the
                            property-clone nested-reference aliasing defect
                            (paraPr border/@borderFillIDRef, @tabPrIDRef,
                            charPr 글자-테두리) survived a 30/30 render
                            pass: check_id_integrity stays green on an
                            aliased (non-dangling) reference, and generated
                            sources never had a definition distinctive
                            enough to alias visibly. Real-Hancom sources
                            carry dense header tables on BOTH sides, so a
                            regression of that class renders as visible
                            style corruption here (mfds' borderless 고시
                            cover acquiring seoul's SOLID table borders was
                            the live find). Rotation: 6 pairwise appends
                            over the gongmun trio (both directions), 3
                            mid-document inserts, 2 field-bearing sources
                            (clickhere form, date/proofreading probe), 1
                            chained three-way append.

Generation ONLY -- no Hancom oracle here. Every produced file gets the
static ``validate_editor_open_safety`` pre-filter (necessary, not
sufficient); the real verdict comes from the macOS GUI oracle (root's Mac).
``render_jobs_v20.json`` lists a PDF export job per produced file, same
shape as v4-v19.

Field names are the render pipeline's contract (see v4-v19's own comments)
-- a bare array of ``{sourceId,stratum,src,pdf}``, not wrapped in a
``{"jobs": [...]}`` object.

``toolVersions["python-hwpx"]`` is read from ``pyproject.toml`` directly,
not ``importlib.metadata`` -- same staleness rationale v4-v19 already
established.

    cd python-hwpx
    .venv/bin/python scripts/generate_openrate_corpus_v20.py
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

from generate_openrate_corpus import record  # noqa: E402
from generate_openrate_corpus_v3 import (  # noqa: E402
    BOX_NEGATIVE_CONTROLS,
    OUT_DIR_V3,
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
from generate_openrate_corpus_v18 import OUT_DIR_V18  # noqa: E402
from generate_openrate_corpus_v19 import OUT_DIR_V19  # noqa: E402

from hwpx.document import HwpxDocument  # noqa: E402
from hwpx.tools.document_merge import append_document, insert_document  # noqa: E402

# Same discipline v4-v19 established: a moved/deprecated 5.x name firing its
# shim is a genuine 6.x-migration defect, not something to route around
# silently. Importing generate_openrate_corpus_v4 above already installs
# this filter (its own module-level statement) -- restated here so this
# module's contract is legible without reading v4's source.
import warnings  # noqa: E402

warnings.simplefilter("error", DeprecationWarning)

OUT_DIR_V20 = PYTHON_HWPX / "work" / "openrate-corpus-v20"
MANIFEST_SCHEMA = "hwpx.openrate.frozen-manifest.v20"
BOX_ROOT = "C:\\openrate\\v20"
BOX_ROOT_PDF = "C:\\openrate\\v20-pdf"

_FIXTURES = PYTHON_HWPX / "tests" / "fixtures"
_GOLD = _FIXTURES / "m3_gongmun_gold"
SEOUL = _GOLD / "seoul_sihaengmun.hwpx"
MFDS = _GOLD / "mfds_admin_notice.hwpx"
MPM = _GOLD / "mpm_recruitment_notice.hwpx"
CLICKHERE = PYTHON_HWPX / "tests" / "data" / "clickhere_gold_filled.hwpx"
DATE_PROBE = _FIXTURES / "gui_probes" / "date_and_proofreading_mark.hwpx"


# ================================================================================
# stratum 1 -- cross-real-merge
# ================================================================================
#: (record suffix, target fixture, source fixture, insert-after index or None
#: for append). Indexes are into the TARGET's section-0 paragraph list and
#: chosen to land mid-document on every named fixture (all three gongmun
#: golds have >= 6 section-0 paragraphs).
_MERGE_PLAN: tuple[tuple[str, Path, Path, int | None], ...] = (
    ("append-seoul-mfds", SEOUL, MFDS, None),
    ("append-mfds-seoul", MFDS, SEOUL, None),
    ("append-seoul-mpm", SEOUL, MPM, None),
    ("append-mpm-seoul", MPM, SEOUL, None),
    ("append-mfds-mpm", MFDS, MPM, None),
    ("append-mpm-mfds", MPM, MFDS, None),
    ("insert-seoul-mfds", SEOUL, MFDS, 2),
    ("insert-mfds-seoul", MFDS, SEOUL, 3),
    ("insert-mpm-mfds", MPM, MFDS, 4),
    ("append-seoul-clickhere", SEOUL, CLICKHERE, None),
    ("append-seoul-dateprobe", SEOUL, DATE_PROBE, None),
)


def gen_cross_real_merge(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    def _run(rec_suffix: str, build: Callable[[], HwpxDocument], seed: str) -> None:
        rec_id = f"v20-cross-real-merge-{rec_suffix}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            merged = build()
            merged.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="cross-real-merge", seed=seed,
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001 - withheld is the honest record
            records.append(record(
                rec_id=rec_id, bucket="cross-real-merge", seed=seed,
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))

    for rec_suffix, target_path, source_path, insert_after in _MERGE_PLAN:
        def _build(
            target_path: Path = target_path,
            source_path: Path = source_path,
            insert_after: int | None = insert_after,
        ) -> HwpxDocument:
            target = HwpxDocument.open(target_path)
            if insert_after is None:
                append_document(target, source_path)
            else:
                insert_document(target, source_path, after_paragraph_index=insert_after)
            return target

        _run(rec_suffix, _build, seed=f"{target_path.name}<-{source_path.name}@{insert_after}")

    # chained three-way: both real sources land in one target, back to back --
    # two independent import passes into the same (already-extended) header.
    def _build_chain() -> HwpxDocument:
        target = HwpxDocument.open(SEOUL)
        append_document(target, MFDS)
        append_document(target, MPM)
        return target

    _run("chain-seoul-mfds-mpm", _build_chain, seed="seoul<-mfds<-mpm chained")
    return records


GENERATORS: tuple[tuple[str, Callable[[Path], list[dict[str, Any]]]], ...] = (
    ("cross-real-merge", gen_cross_real_merge),
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
    if OUT_DIR_V20.exists() and any(OUT_DIR_V20.iterdir()):
        print(
            f"ERROR: {OUT_DIR_V20} already exists -- v20 is frozen once generated. "
            "Delete the tree explicitly to regenerate.",
            file=sys.stderr,
        )
        return 2

    all_records: list[dict[str, Any]] = []
    with _deterministic_object_ids():
        for bucket, generator in GENERATORS:
            bucket_dir = OUT_DIR_V20 / bucket
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
            "v20 is ADDITIVE over v19: 1 new stratum covering cross-real-"
            "document merge (hwpx.tools.document_merge append/insert between "
            "real-Hancom-saved sources -- the m3_gongmun_gold trio, the "
            "clickhere gold form, the date/proofreading GUI probe). v13's "
            "merge stratum merged generated files whose headers carry few "
            "custom definitions and no layout caches, which is why the "
            "property-clone nested-reference aliasing class (paraPr border/"
            "tabPr, charPr character-border refs -- non-dangling, so "
            "check_id_integrity stays green) passed 30/30 there while real-"
            "source merges rendered visibly corrupted. This stratum makes "
            "that class corpus-visible. It does not re-touch v3-v19's "
            "strata; it does not replace v1-v19, which remain published "
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
            "v11": _frozen_reference(OUT_DIR_V11 / "manifest.json"),
            "v12": _frozen_reference(OUT_DIR_V12 / "manifest.json"),
            "v13": _frozen_reference(OUT_DIR_V13 / "manifest.json"),
            "v14": _frozen_reference(OUT_DIR_V14 / "manifest.json"),
            "v15": _frozen_reference(OUT_DIR_V15 / "manifest.json"),
            "v16": _frozen_reference(OUT_DIR_V16 / "manifest.json"),
            "v17": _frozen_reference(OUT_DIR_V17 / "manifest.json"),
            "v18": _frozen_reference(OUT_DIR_V18 / "manifest.json"),
            "v19": _frozen_reference(OUT_DIR_V19 / "manifest.json"),
        },
        "counts": counts,
        "requestedTotal": sum(slot["requested"] for slot in counts.values()),
        "producedTotal": sum(slot["produced"] for slot in counts.values()),
        "items": all_records,
    }
    manifest_path = OUT_DIR_V20 / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    filelist_path = OUT_DIR_V20 / "box_run_v20.filelist"
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
    render_jobs_path = OUT_DIR_V20 / "render_jobs_v20.json"
    render_jobs_path.write_text(
        json.dumps(render_jobs, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"v20 corpus: {manifest['producedTotal']}/{manifest['requestedTotal']} produced")
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
