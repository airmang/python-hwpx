# SPDX-License-Identifier: Apache-2.0
"""openrate corpus v12 -- the 6.8 cycle's two remaining capability-area
first judgments: page-layout's uncovered majority, and hyperlink-bookmark
(carved out of toc-crossref in train 30), additive over v11.

Why v12 exists
===============

Train 30 registered ``page-layout`` (``doc.page``, 19 methods) with an
explicitly *partial* ``Render-verified(부분)`` grade -- only 5 methods
(``set_visibility``/``set_line_numbers``/``set_grid`` via v4's
``authored-page-structure``, ``restart_page_number``/``hide_page_elements``
via v6's ``authored-pagecontrol``) had real evidence; the majority (paper
size, margins, header/footer text, page numbering, columns, removal) did
not. ``authored-pagelayout`` is the first real-Hancom batch aimed at that
uncovered majority -- widening the grade from "부분" toward "전체" once
measured, not asserting it here (generation only, no oracle in this
environment).

Train 30 also split ``add_hyperlink``/``add_bookmark`` out of
``toc-crossref`` into their own ``hyperlink-bookmark`` area, registered
honestly as unverified (``Create`` only, no Render-verified) -- that
area's evidence was entirely about TOC structure, never independently
covering hyperlinks or bookmarks despite them riding the same area for
cycles. ``authored-hyperlink-bookmark`` is this area's first real-Hancom
batch, the same "hp:label/v11" precedent chain train 28's own docstring
already names.

Two strata (deterministic -- fixed seeds, bank rotation, no wall clock)
============================================================================

* ``authored-pagelayout``          15  Each record combines ``doc.page.
                                        set_size``/``set_margins``/
                                        ``set_header``/``set_footer``/
                                        ``set_page_number``/``set_columns``
                                        (six independently-rotating banks,
                                        each offset by its own stride so
                                        records combine differently rather
                                        than moving in lockstep) plus,
                                        every third record, one of
                                        ``restart_page_number``/
                                        ``hide_page_elements``/
                                        ``remove_header`` layered on top
                                        (widening v4/v6's already-real
                                        evidence for those, and exercising
                                        the removal path v4/v6 never
                                        touched at all). Page size uses the
                                        schema's real ``landscape``
                                        vocabulary (``WIDELY``/``NARROWLY``,
                                        not the informal ``PORTRAIT``/
                                        ``LANDSCAPE`` some call sites in
                                        this repo's own test suite pass --
                                        those are accepted as opaque
                                        strings by our own writer, but only
                                        the schema's own enum has any
                                        real-corpus precedent, e.g. DEV-023).
* ``authored-hyperlink-bookmark``  15  Each record creates a bookmark via
                                        ``doc.refs.add_bookmark`` and then
                                        a hyperlink via ``doc.refs.
                                        add_hyperlink`` -- rotating between
                                        external URLs (schema-legal
                                        arbitrary strings) and in-document
                                        anchor references (``#<bookmark
                                        name>``, the same internal-link
                                        shape this repo's own v7 stratum
                                        used for CROSSREF-style targets).
                                        Every record clears the same
                                        static open-safety pre-filter
                                        every other stratum does.

Generation ONLY -- no Hancom oracle here. Every produced file gets the
static ``validate_editor_open_safety`` pre-filter (necessary, not
sufficient); the real verdict comes from the macOS GUI oracle (root's Mac).
``render_jobs_v12.json`` lists a PDF export job per produced file, same
shape as v4-v11.

Field names are the render pipeline's contract (see v4-v11's own comments)
-- a bare array of ``{sourceId,stratum,src,pdf}``, not wrapped in a
``{"jobs": [...]}`` object.

``toolVersions["python-hwpx"]`` is read from ``pyproject.toml`` directly,
not ``importlib.metadata`` -- same staleness rationale v4-v11 already
established.

    cd python-hwpx
    .venv-core/bin/python scripts/generate_openrate_corpus_v12.py
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
from generate_openrate_corpus_v11 import OUT_DIR_V11  # noqa: E402

# Same discipline v4-v11 established: a moved/deprecated 5.x name firing its
# shim is a genuine 6.x-migration defect, not something to route around
# silently. Importing generate_openrate_corpus_v4 above already installs
# this filter (its own module-level statement) -- restated here so this
# module's contract is legible without reading v4's source.
import warnings  # noqa: E402

warnings.simplefilter("error", DeprecationWarning)

OUT_DIR_V12 = PYTHON_HWPX / "work" / "openrate-corpus-v12"
MANIFEST_SCHEMA = "hwpx.openrate.frozen-manifest.v12"
BOX_ROOT = "C:\\openrate\\v12"
BOX_ROOT_PDF = "C:\\openrate\\v12-pdf"


# ================================================================================
# authored-pagelayout banks
# ================================================================================
#: (width, height, orientation, gutter_type) -- HWPUNIT (7200/inch). orientation
#: uses the schema's own landscape vocabulary (WIDELY/NARROWLY), not the
#: PORTRAIT/LANDSCAPE strings some existing call sites pass (those are opaque
#: to our writer, but only the schema enum has real-corpus precedent).
_PAGE_SIZE_BANK: tuple[tuple[int, int, str, str], ...] = (
    (59528, 84188, "NARROWLY", "LEFT_ONLY"),   # A4 portrait, schema default gutter
    (84188, 59528, "WIDELY", "LEFT_ONLY"),     # A4 landscape
    (59528, 84188, "NARROWLY", "LEFT_RIGHT"),  # A4 portrait, book-bound gutter
    (41528, 59528, "NARROWLY", "TOP_BOTTOM"),  # A5-ish portrait, top/bottom gutter
    (59528, 84188, "NARROWLY", "LEFT_ONLY"),
)

#: (left, right, top, bottom, header, footer, gutter) -- HWPUNIT.
_MARGIN_BANK: tuple[tuple[int, int, int, int, int, int, int], ...] = (
    (8504, 8504, 5668, 4252, 4252, 4252, 0),
    (5668, 5668, 4252, 4252, 3400, 3400, 850),
    (11338, 11338, 8504, 8504, 4252, 4252, 0),
    (8504, 8504, 5668, 4252, 4252, 4252, 1700),
)

#: (header_text, footer_text, page_type) -- BOTH/EVEN/ODD rotation.
_HEADER_FOOTER_BANK: tuple[tuple[str, str, str], ...] = (
    ("업무 보고서", "기밀 - 사내용", "BOTH"),
    ("월간 운영 계획", "페이지", "EVEN"),
    ("공지사항", "담당부서 배포", "ODD"),
    ("표본 문서", "", "BOTH"),
)

#: (target, format, position, prefix, suffix).
_PAGE_NUMBER_BANK: tuple[tuple[str, str, str, str, str], ...] = (
    ("footer", "page", "BOTTOM_CENTER", "- ", " -"),
    ("footer", "page/total", "BOTTOM_RIGHT", "Page ", ""),
    ("header", "page", "TOP_RIGHT", "", ""),
)

#: (col_count, col_type, layout).
_COLUMN_BANK: tuple[tuple[int, str, str], ...] = (
    (2, "NEWSPAPER", "LEFT"),
    (3, "NEWSPAPER", "LEFT"),
    (2, "NEWSPAPER_FLOW", "RIGHT"),
)

#: Every third record (idx % 3 == 0) also layers one of these on top --
#: widening v4/v6's already-real evidence for restart_page_number/
#: hide_page_elements, and exercising the removal path (remove_header) v4/v6
#: never touched at all.
_EXTRA_OPS: tuple[str, ...] = ("restart_page_number", "hide_page_elements", "remove_header")


def _tool_versions() -> dict[str, str | None]:
    """python-hwpx's own version, pyproject-first (see module docstring)."""

    versions: dict[str, str | None] = {}
    versions["python-hwpx"] = _read_pyproject_version(PYTHON_HWPX / "pyproject.toml")
    if versions["python-hwpx"] is None:
        import hwpx

        versions["python-hwpx"] = str(hwpx.__version__)
    return versions


# ================================================================================
# stratum 1 -- authored-pagelayout
# ================================================================================
def gen_pagelayout(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(15):
        rec_id = f"v12-pagelayout-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            width, height, orientation, gutter_type = _PAGE_SIZE_BANK[idx % len(_PAGE_SIZE_BANK)]
            left, right, top, bottom, header_m, footer_m, gutter = (
                _MARGIN_BANK[(idx + 1) % len(_MARGIN_BANK)]
            )
            header_text, footer_text, page_type = (
                _HEADER_FOOTER_BANK[(idx + 2) % len(_HEADER_FOOTER_BANK)]
            )
            pn_target, pn_format, pn_position, pn_prefix, pn_suffix = (
                _PAGE_NUMBER_BANK[(idx + 3) % len(_PAGE_NUMBER_BANK)]
            )
            col_count, col_type, col_layout = _COLUMN_BANK[(idx + 4) % len(_COLUMN_BANK)]

            document = _base_document(idx, "페이지 레이아웃(doc.page) 저작 표본")
            document.page.set_size(
                width=width, height=height, orientation=orientation, gutter_type=gutter_type
            )
            document.page.set_margins(
                left=left, right=right, top=top, bottom=bottom,
                header=header_m, footer=footer_m, gutter=gutter,
            )
            document.page.set_header(text=header_text, page_type=page_type)
            if footer_text:
                document.page.set_footer(text=footer_text, page_type=page_type)
            document.page.set_page_number(
                target=pn_target, format=pn_format, position=pn_position,
                prefix=pn_prefix, suffix=pn_suffix,
            )
            document.page.set_columns(col_count, col_type=col_type, layout=col_layout)

            summary = document.add_paragraph(
                f"표본 {idx}: size={width}x{height}/{orientation}, "
                f"margins(l={left},r={right}), header={header_text!r}, "
                f"columns={col_count}/{col_type}"
            )

            # idx % 3 == 0 selects every third record (0, 3, 6, 9, 12); dividing
            # by 3 first before indexing _EXTRA_OPS (also length 3) is required
            # -- indexing by idx % 3 directly would always land on index 0,
            # since idx is already a multiple of 3 on every selected record.
            extra_op = _EXTRA_OPS[(idx // 3) % len(_EXTRA_OPS)] if idx % 3 == 0 else None
            if extra_op == "restart_page_number":
                document.page.restart_page_number(summary, number=(idx % 5) + 1)
            elif extra_op == "hide_page_elements":
                document.page.hide_page_elements(
                    summary, header=(idx % 2 == 0), page_num=(idx % 4 == 0),
                )
            elif extra_op == "remove_header":
                document.page.remove_header(page_type=page_type)

            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-pagelayout", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001 - withheld is the honest record
            records.append(record(
                rec_id=rec_id, bucket="authored-pagelayout", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


# ================================================================================
# stratum 2 -- authored-hyperlink-bookmark
# ================================================================================
#: External URLs -- schema-legal arbitrary strings, no real-corpus vocabulary
#: constraint known (unlike e.g. DEV-023's landscape enum).
_EXTERNAL_URL_BANK: tuple[str, ...] = (
    "https://example.invalid/report",
    "https://example.invalid/policy?id=42",
    "https://example.invalid/",
)


def gen_hyperlink_bookmark(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(15):
        rec_id = f"v12-linkbookmark-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            document = _base_document(idx, "하이퍼링크·책갈피 저작 표본")
            bookmark_name = f"anchor{idx}"
            anchor_paragraph = document.add_paragraph(f"북마크 대상 문단 {idx}")
            document.refs.add_bookmark(bookmark_name, paragraph=anchor_paragraph)

            link_paragraph = document.add_paragraph(f"링크 문단 {idx}")
            if idx % 2 == 0:
                # External URL, every other record.
                url = _EXTERNAL_URL_BANK[idx % len(_EXTERNAL_URL_BANK)]
                document.refs.add_hyperlink(
                    url, f"외부 링크 {idx}", paragraph=link_paragraph,
                )
            else:
                # In-document anchor reference -- same #<name> shape v7's own
                # stratum already used for CROSSREF-style internal targets.
                document.refs.add_hyperlink(
                    f"#{bookmark_name}", f"내부 링크 {idx}", paragraph=link_paragraph,
                )

            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-hyperlink-bookmark", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001 - withheld is the honest record
            records.append(record(
                rec_id=rec_id, bucket="authored-hyperlink-bookmark", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


GENERATORS: tuple[tuple[str, Callable[[Path], list[dict[str, Any]]]], ...] = (
    ("authored-pagelayout", gen_pagelayout),
    ("authored-hyperlink-bookmark", gen_hyperlink_bookmark),
)


def main() -> int:
    if OUT_DIR_V12.exists() and any(OUT_DIR_V12.iterdir()):
        print(
            f"ERROR: {OUT_DIR_V12} already exists -- v12 is frozen once generated. "
            "Delete the tree explicitly to regenerate.",
            file=sys.stderr,
        )
        return 2

    all_records: list[dict[str, Any]] = []
    with _deterministic_object_ids():
        for bucket, generator in GENERATORS:
            bucket_dir = OUT_DIR_V12 / bucket
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
            "v12 is ADDITIVE over v11: 2 new strata, the 6.8 cycle's two "
            "remaining capability-area first judgments (train 30). "
            "authored-pagelayout (15) targets doc.page's uncovered majority "
            "-- set_size/set_margins/set_header/set_footer/set_page_number/"
            "set_columns (6 independently-rotating banks) plus, every third "
            "record, restart_page_number/hide_page_elements/remove_header "
            "layered on top (widening v4/v6's already-real evidence, and "
            "exercising the removal path v4/v6 never touched). This is the "
            "first real-Hancom batch that could widen page-layout's grade "
            "from Render-verified(부분) toward full coverage -- generation "
            "only, the actual widening happens on ledger reflow after the "
            "real oracle batch. authored-hyperlink-bookmark (15) targets "
            "add_hyperlink/add_bookmark, split out of toc-crossref in train "
            "30 with zero independent real-Hancom evidence of their own -- "
            "this is that area's first real-Hancom batch, rotating external "
            "URLs against in-document #<bookmark> anchor references. It "
            "does not re-touch v3-v11's strata; it does not replace v1-v11, "
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
        },
        "counts": counts,
        "requestedTotal": sum(slot["requested"] for slot in counts.values()),
        "producedTotal": sum(slot["produced"] for slot in counts.values()),
        "items": all_records,
    }
    manifest_path = OUT_DIR_V12 / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    filelist_path = OUT_DIR_V12 / "box_run_v12.filelist"
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
    render_jobs_path = OUT_DIR_V12 / "render_jobs_v12.json"
    render_jobs_path.write_text(
        json.dumps(render_jobs, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"v12 corpus: {manifest['producedTotal']}/{manifest['requestedTotal']} produced")
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
