# SPDX-License-Identifier: Apache-2.0
"""openrate corpus v21 -- first real-Hancom batch for train 48's titleMark
authoring (cycle 6.15, editor-menu reverse-map gap closure, DEV-044). v21
is ADDITIVE over v20.

One stratum (deterministic -- fixed seeds, bank rotation, no wall clock)
============================================================================

* ``authored-title-mark``  5  ``HwpxOxmlParagraph.add_title_mark(in_toc=)``
                               -- caret-paragraph targeting confirmed via
                               team-lead's Windows box COM SetPos+
                               MarkTitle/HideTitle 3-variant probe
                               (tests/fixtures/gui_probes/title_mark_
                               caret_p{1,2}_{mark,hide}.hwpx). Rotates
                               in_toc True/False (표시/숨김 polarity),
                               single vs two-heading documents, which of
                               two headings gets marked, both headings
                               marked independently with opposite
                               polarity (proves no cross-paragraph
                               leakage), and composition with a non-
                               default char_pr_id_ref on the heading's
                               own run (proves titleMark insertion into
                               the existing hp:t doesn't disturb sibling
                               character formatting, since add_title_mark
                               never creates a new run).

Generation ONLY -- no Hancom oracle here. Every produced file gets the
static ``validate_editor_open_safety`` pre-filter (necessary, not
sufficient); the real verdict comes from the macOS GUI oracle (root's Mac).
``render_jobs_v21.json`` lists a PDF export job per produced file, same
shape as v4-v20.

Field names are the render pipeline's contract (see v4-v20's own comments)
-- a bare array of ``{sourceId,stratum,src,pdf}``, not wrapped in a
``{"jobs": [...]}`` object.

``toolVersions["python-hwpx"]`` is read from ``pyproject.toml`` directly,
not ``importlib.metadata`` -- same staleness rationale v4-v20 already
established.

    cd python-hwpx
    .venv-core/bin/python scripts/generate_openrate_corpus_v21.py
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
from generate_openrate_corpus_v18 import OUT_DIR_V18  # noqa: E402
from generate_openrate_corpus_v19 import OUT_DIR_V19  # noqa: E402
from generate_openrate_corpus_v20 import OUT_DIR_V20  # noqa: E402

from hwpx.document import HwpxDocument  # noqa: E402

# Same discipline v4-v20 established: a moved/deprecated 5.x name firing its
# shim is a genuine 6.x-migration defect, not something to route around
# silently. Importing generate_openrate_corpus_v4 above already installs
# this filter (its own module-level statement) -- restated here so this
# module's contract is legible without reading v4's source.
import warnings  # noqa: E402

warnings.simplefilter("error", DeprecationWarning)

OUT_DIR_V21 = PYTHON_HWPX / "work" / "openrate-corpus-v21"
MANIFEST_SCHEMA = "hwpx.openrate.frozen-manifest.v21"
BOX_ROOT = "C:\\openrate\\v21"
BOX_ROOT_PDF = "C:\\openrate\\v21-pdf"


# ================================================================================
# stratum 1 -- authored-title-mark
# ================================================================================


def gen_title_mark(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(5):
        rec_id = f"v21-title-mark-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            document = _base_document(idx, "제목 차례 표시 저작 표본")
            if idx == 0:
                # single heading, in_toc=True -- matches title_mark_caret_
                # p2_mark.hwpx's shape.
                heading = document.add_heading(f"{cycle(DEPT_BANK, idx)} 제목", level=1)
                heading.add_title_mark(in_toc=True)
            elif idx == 1:
                # single heading, in_toc=False -- matches title_mark_caret_
                # p2_hide.hwpx's shape.
                heading = document.add_heading(f"{cycle(DEPT_BANK, idx)} 제목", level=1)
                heading.add_title_mark(in_toc=False)
            elif idx == 2:
                # two headings, only the first gets marked -- matches
                # title_mark_caret_p1_mark.hwpx's shape (proves no
                # accidental spillover onto the second heading).
                first = document.add_heading("제목 A", level=1)
                document.add_heading("제목 B", level=1)
                first.add_title_mark(in_toc=True)
            elif idx == 3:
                # both headings marked independently with opposite
                # polarity -- proves no cross-paragraph leakage in either
                # direction.
                first = document.add_heading("제목 A", level=1)
                second = document.add_heading("제목 B", level=1)
                first.add_title_mark(in_toc=True)
                second.add_title_mark(in_toc=False)
            else:
                # composition with a non-default char_pr_id_ref already on
                # the heading's own run -- proves inserting titleMark into
                # the existing hp:t (no new run created) doesn't disturb
                # sibling character formatting.
                cid = document.styles.ensure_run(bold=True, color="#1F4E79")
                heading = document.add_heading(
                    f"{cycle(DEPT_BANK, idx)} 제목", level=1, char_pr_id_ref=cid
                )
                heading.add_title_mark(in_toc=True)

            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-title-mark", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001 - withheld is the honest record
            records.append(record(
                rec_id=rec_id, bucket="authored-title-mark", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


GENERATORS: tuple[tuple[str, Callable[[Path], list[dict[str, Any]]]], ...] = (
    ("authored-title-mark", gen_title_mark),
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
    if OUT_DIR_V21.exists() and any(OUT_DIR_V21.iterdir()):
        print(
            f"ERROR: {OUT_DIR_V21} already exists -- v21 is frozen once generated. "
            "Delete the tree explicitly to regenerate.",
            file=sys.stderr,
        )
        return 2

    all_records: list[dict[str, Any]] = []
    with _deterministic_object_ids():
        for bucket, generator in GENERATORS:
            bucket_dir = OUT_DIR_V21 / bucket
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
            "v21 is ADDITIVE over v20: 1 new stratum covering train 48's "
            "titleMark authoring (DEV-044, editor-menu reverse-map gap "
            "closure -- caret-paragraph targeting confirmed via team-lead's "
            "Windows box COM SetPos+MarkTitle/HideTitle 3-variant probe, "
            "not a GUI probe on this Mac) -- authored-title-mark "
            "(HwpxOxmlParagraph.add_title_mark(in_toc=), rotating "
            "in_toc True/False polarity, single vs two-heading documents, "
            "which heading gets marked, both headings marked independently "
            "with opposite polarity, and composition with a non-default "
            "char_pr_id_ref already on the heading's run). It does not "
            "re-touch v3-v20's strata; it does not replace v1-v20, which "
            "remain published with their own measurement stack and date."
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
            "v20": _frozen_reference(OUT_DIR_V20 / "manifest.json"),
        },
        "counts": counts,
        "requestedTotal": sum(slot["requested"] for slot in counts.values()),
        "producedTotal": sum(slot["produced"] for slot in counts.values()),
        "items": all_records,
    }
    manifest_path = OUT_DIR_V21 / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    filelist_path = OUT_DIR_V21 / "box_run_v21.filelist"
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
    render_jobs_path = OUT_DIR_V21 / "render_jobs_v21.json"
    render_jobs_path.write_text(
        json.dumps(render_jobs, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"v21 corpus: {manifest['producedTotal']}/{manifest['requestedTotal']} produced")
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
