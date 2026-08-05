# SPDX-License-Identifier: Apache-2.0
"""openrate corpus v6 — the 6.2 read-write gap-closing surface, additive over v5.

Why v6 exists
=============

The 6.2 cycle closed four audit-identified "code-blind" write gaps: text
highlighting (``doc.text.highlight``, DEV-010's read-honesty finding sits
beside this), border-fill image/gradient authoring
(``doc.styles.ensure_border_fill(fill_image=/fill_gradient=)`` +
``HwpxOxmlTable.set_cell_fill_image``/``set_cell_fill_gradient``), memo-shape
definition authoring (``doc.styles.ensure_memo_shape``), and mid-document
page-number control (``doc.page.restart_page_number``/``hide_page_elements``).
v1-v5 never exercised any of this — it did not exist yet. v6 measures ONLY
these four new surfaces; it is not a v5 re-run and does not re-touch v5's
four strata (or v4's 11, or v3/v2/v1's).

Four strata (all deterministic — fixed seeds, bank rotation, no wall clock)
=============================================================================

* ``authored-highlight``   15  doc.text.highlight — color rotated across a
                                5-value bank, ~1/3 of records additionally
                                nest a second highlight inside the first
                                (a substring of the already-highlighted
                                match, exercising the LIFO pairing
                                doc.text.highlights() reads back), and the
                                *target paragraph* rotates across all three
                                of _base_document's paragraphs so the match
                                is never always paragraph 0
* ``authored-fill``        15  HwpxOxmlTable.set_cell_fill_image (mode
                                TOTAL/TILE rotated) on one cell +
                                set_cell_fill_gradient (type LINEAR/RADIAL
                                rotated, angle rotated, 2- and 3-color sets
                                rotated) on another cell of the same table —
                                every record exercises both fill kinds
* ``authored-memoshape``   15  doc.styles.ensure_memo_shape — line width/
                                line color/fill color/active color each
                                rotated across independent banks (not
                                locked together, so shapes genuinely
                                differ) — wired to an actual
                                doc.notes.add_memo(memo_shape_id_ref=...)
                                so the shape this produces is really
                                referenced, not just declared and orphaned
* ``authored-pagecontrol`` 15  doc.page.restart_page_number (number
                                rotated, kind rotated across the schema's
                                full 7-value AutoNumNewNumType vocabulary —
                                real corpus only ever shows PAGE, the other
                                six are schema-legal and worth exercising
                                structurally) + hide_page_elements (rotated
                                across 7 boolean combinations spanning
                                single-flag to all-six-set)

Generation ONLY — no Hancom oracle here. Every produced file gets the static
``validate_editor_open_safety`` pre-filter (necessary, not sufficient); the
real verdict comes from a Windows box run. ``render_jobs_v6.json`` lists a
PDF export job per produced file, same as v4/v5 — these are visual claims
(does the highlight color/nesting render, does the cell image/gradient fill
land, does the memo shape's color show, does the mid-document page restart
+ hiding actually take effect) a mere "does it open" check cannot confirm.

Field names are the render pipeline's contract (see v4/v5's own comments —
v4's first box run failed because its render-jobs file wrapped a different
field-name shape inside a ``{"jobs": [...]}`` object; the pipeline reads
``$Job.sourceId``/``.stratum``/``.src``/``.pdf`` off a BARE ARRAY). v6 copies
v5's already-corrected shape verbatim (see ``main()`` below).

``toolVersions["python-hwpx"]`` is read from ``pyproject.toml`` directly, not
``importlib.metadata`` — same staleness rationale v4/v5 already established.

    cd python-hwpx
    .venv-core/bin/python scripts/generate_openrate_corpus_v6.py
"""
from __future__ import annotations

import json
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

PYTHON_HWPX = Path(__file__).resolve().parent.parent
# Explicit — this worktree's src/ must win over whatever editable install the
# running venv happens to carry (v5's own comment records the exact failure
# mode: a venv borrowed from a sibling worktree silently shadowing this
# checkout's surface with an older one, turning every record into a false
# AttributeError withhold).
sys.path.insert(0, str(PYTHON_HWPX / "src"))
sys.path.insert(0, str(PYTHON_HWPX / "scripts"))

from generate_openrate_corpus import (  # noqa: E402
    DEPT_BANK,
    OUT_DIR,
    OUT_DIR_V2,
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
    _deterministic_object_ids as _v4_deterministic_object_ids,
    _frozen_reference,
    _git_commit,
    _read_pyproject_version,
)
from generate_openrate_corpus_v5 import OUT_DIR_V5  # noqa: E402

# Same discipline v4/v5 established: a moved/deprecated 5.x name firing its
# shim is a genuine 6.x-migration defect, not something to route around
# silently. Importing generate_openrate_corpus_v4 above already installs
# this filter (its own module-level statement) — restated here so this
# module's contract is legible without reading v4's source.
import warnings  # noqa: E402

warnings.simplefilter("error", DeprecationWarning)

@contextmanager
def _deterministic_object_ids() -> Iterator[None]:
    """v4's id-source reseed, extended to cover a determinism gap v6's own
    ``authored-memoshape`` stratum is the first generator to hit.

    ``hwpx._document.memos.add_memo_with_anchor`` mints its field-anchor id
    via bare ``import uuid; uuid.uuid4().hex`` — a *second*, independent
    ``uuid4`` reference v4's reseed (which only patches
    ``hwpx.oxml._document_primitives.uuid4``, the ``from uuid import uuid4``
    binding ``_paragraph_id``/``_object_id``/``_memo_id`` share) does not
    touch. Confirmed empirically: a first v6 run produced 15/15
    ``authored-memoshape`` files with non-reproducible ``output_sha256``
    across two otherwise-identical runs — every other stratum (none of
    which call ``add_memo(anchor=...)``) was already byte-stable. Patching
    the stdlib ``uuid`` module's own ``uuid4`` attribute here covers any
    ``import uuid``-style caller across the whole process, layered inside
    v4's reseed so both id sources share one counter sequence.
    """

    with _v4_deterministic_object_ids():
        original_uuid4 = uuid.uuid4
        # Disjoint range from v4's own counter (which starts at 1) — these
        # two id sources land in different XML attribute spaces (paragraph/
        # object/memo id vs. memo field-anchor id) so collision is not a
        # correctness problem either way, but keeping them visibly separate
        # makes a manifest diff easier to read.
        next_id = 1_000_000

        def _seeded_uuid4() -> uuid.UUID:
            nonlocal next_id
            value = uuid.UUID(int=next_id)
            next_id += 1
            return value

        uuid.uuid4 = _seeded_uuid4  # type: ignore[assignment]
        try:
            yield
        finally:
            uuid.uuid4 = original_uuid4  # type: ignore[assignment]


OUT_DIR_V6 = PYTHON_HWPX / "work" / "openrate-corpus-v6"
MANIFEST_SCHEMA = "hwpx.openrate.frozen-manifest.v6"
BOX_ROOT = "C:\\openrate\\v6"
BOX_ROOT_PDF = "C:\\openrate\\v6-pdf"


# ================================================================================
# new-stratum banks (rotation only — no wall clock, no randomness)
# ================================================================================
HIGHLIGHT_COLOR_BANK = ("#FFFF00", "#00CCFF", "#CCFF99", "#FFCCE5", "#E5CCFF")
#: nested-highlight second color, index-offset from HIGHLIGHT_COLOR_BANK so a
#: nested record's outer/inner colors are always distinct.
HIGHLIGHT_NESTED_COLOR_BANK = ("#00CCFF", "#CCFF99", "#FFCCE5", "#E5CCFF", "#FFFF00")

#: minimal well-formed PNG payload — content is never inspected, only
#: embedded (same synthetic payload convention v1-v5's picture/caption
#: strata already established).
FILL_IMAGE_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
FILL_IMAGE_MODE_BANK = ("TOTAL", "TILE")
FILL_GRADIENT_TYPE_BANK = ("LINEAR", "RADIAL")
FILL_GRADIENT_COLOR_SETS: tuple[tuple[str, ...], ...] = (
    ("#FFFFFF", "#4B87CB"),
    ("#A3CF78", "#FFFFFF"),
    ("#000000", "#888888", "#FFFFFF"),
)

MEMO_LINE_WIDTH_BANK = (1, 2, 3)
MEMO_LINE_COLOR_BANK = ("#000000", "#B6D7AE", "#A9A9A9", "#333333")
MEMO_FILL_COLOR_BANK = ("#CCFF99", "#F0FFE9", "#CBFF99", "#FFEEDD")
MEMO_ACTIVE_COLOR_BANK = ("#FFFF99", "#CFF1C7", "#FDBCDD", "#FFD9CC")

#: hp:AutoNumNewNumType/@numType — the schema's full 7-value vocabulary.
#: Real corpus only ever shows PAGE (DEV-008); the other six are
#: schema-legal and worth exercising structurally even without real-corpus
#: attestation.
NEWNUM_KIND_BANK = (
    "PAGE", "FOOTNOTE", "ENDNOTE", "PICTURE", "TABLE", "EQUATION", "TOTAL_PAGE",
)

#: hp:pageHiding boolean-combination rotation, single-flag through
#: all-six-set.
HIDE_COMBO_BANK: tuple[dict[str, bool], ...] = (
    {"header": True},
    {"footer": True},
    {"master_page": True},
    {"header": True, "footer": True},
    {"border": True, "fill": True},
    {"page_num": True},
    {
        "header": True, "footer": True, "master_page": True,
        "border": True, "fill": True, "page_num": True,
    },
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
# strata
# ================================================================================
def gen_highlight(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(15):
        rec_id = f"v6-highlight-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            document = _base_document(idx, "형광펜 표본")
            # paragraphs[0] is HwpxDocument.new()'s own empty skeleton
            # paragraph — _base_document's three real sentences start at [1].
            target_paragraph = document.paragraphs[1 + idx % 3]
            words = target_paragraph.text.split()
            word = words[0] if words else target_paragraph.text
            color = HIGHLIGHT_COLOR_BANK[idx % len(HIGHLIGHT_COLOR_BANK)]
            document.text.highlight(target_paragraph, word, color=color)
            if idx % 3 == 0 and len(word) >= 3:
                inner = word[1:-1]
                inner_color = HIGHLIGHT_NESTED_COLOR_BANK[idx % len(HIGHLIGHT_NESTED_COLOR_BANK)]
                document.text.highlight(target_paragraph, inner, color=inner_color)
            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-highlight", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001 - withheld is the honest record
            records.append(record(
                rec_id=rec_id, bucket="authored-highlight", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


def gen_fill(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(15):
        rec_id = f"v6-fill-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            document = _base_document(idx, "채우기 표본")
            table = document.add_table(2, 2, width=42000)
            image = document.media.add_image(FILL_IMAGE_BYTES, "png")
            mode = FILL_IMAGE_MODE_BANK[idx % len(FILL_IMAGE_MODE_BANK)]
            table.set_cell_fill_image(0, 0, image, mode=mode)
            gradient_type = FILL_GRADIENT_TYPE_BANK[idx % len(FILL_GRADIENT_TYPE_BANK)]
            colors = list(FILL_GRADIENT_COLOR_SETS[idx % len(FILL_GRADIENT_COLOR_SETS)])
            table.set_cell_fill_gradient(
                1, 1, colors, gradient_type=gradient_type, angle=(idx * 15) % 360,
            )
            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-fill", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001
            records.append(record(
                rec_id=rec_id, bucket="authored-fill", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


def gen_memoshape(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(15):
        rec_id = f"v6-memoshape-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            document = _base_document(idx, "메모 모양 표본")
            paragraph = document.add_paragraph(f"검토 대상 문단 {idx}")
            shape_id = document.styles.ensure_memo_shape(
                line_width=MEMO_LINE_WIDTH_BANK[idx % len(MEMO_LINE_WIDTH_BANK)],
                line_color=MEMO_LINE_COLOR_BANK[idx % len(MEMO_LINE_COLOR_BANK)],
                fill_color=MEMO_FILL_COLOR_BANK[idx % len(MEMO_FILL_COLOR_BANK)],
                active_color=MEMO_ACTIVE_COLOR_BANK[idx % len(MEMO_ACTIVE_COLOR_BANK)],
            )
            document.notes.add_memo(
                f"검토 의견 {idx}: {cycle(SUBJECT_BANK, idx)}",
                anchor=paragraph,
                memo_shape_id_ref=shape_id,
                # add_memo's own default is datetime.now() — wall-clock, and
                # therefore the one remaining determinism gap after the
                # uuid4 reseed above. A fixed value keeps output_sha256
                # stable across separate process runs (empirically
                # confirmed: this was the actual cause, not uuid4 — see
                # _deterministic_object_ids' docstring for the id-source
                # fix that turned out NOT to be sufficient alone).
                created="2026-08-01 00:00:00",
            )
            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-memoshape", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001
            records.append(record(
                rec_id=rec_id, bucket="authored-memoshape", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


def gen_pagecontrol(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(15):
        rec_id = f"v6-pagecontrol-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            document = _base_document(idx, "쪽번호 제어 표본")
            paragraph = document.add_paragraph(f"재시작·숨김 지점 {idx} — {cycle(DEPT_BANK, idx)}")
            kind = NEWNUM_KIND_BANK[idx % len(NEWNUM_KIND_BANK)]
            document.page.restart_page_number(paragraph, number=1 + idx, kind=kind)
            hide_kwargs = HIDE_COMBO_BANK[idx % len(HIDE_COMBO_BANK)]
            document.page.hide_page_elements(paragraph, **hide_kwargs)
            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-pagecontrol", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001
            records.append(record(
                rec_id=rec_id, bucket="authored-pagecontrol", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


GENERATORS: tuple[tuple[str, Callable[[Path], list[dict[str, Any]]]], ...] = (
    ("authored-highlight", gen_highlight),
    ("authored-fill", gen_fill),
    ("authored-memoshape", gen_memoshape),
    ("authored-pagecontrol", gen_pagecontrol),
)


def main() -> int:
    if OUT_DIR_V6.exists() and any(OUT_DIR_V6.iterdir()):
        print(
            f"ERROR: {OUT_DIR_V6} already exists — v6 is frozen once generated. "
            "Delete the tree explicitly to regenerate.",
            file=sys.stderr,
        )
        return 2

    all_records: list[dict[str, Any]] = []
    with _deterministic_object_ids():
        for bucket, generator in GENERATORS:
            bucket_dir = OUT_DIR_V6 / bucket
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
            "v6 is ADDITIVE over v5: 4 new strata exercising ONLY the 6.2 "
            "read-write gaps closed this cycle — text highlighting "
            "(doc.text.highlight), border-fill image/gradient authoring "
            "(doc.styles.ensure_border_fill(fill_image=/fill_gradient=), "
            "HwpxOxmlTable.set_cell_fill_image/set_cell_fill_gradient), "
            "memo-shape definition authoring (doc.styles.ensure_memo_shape) "
            "and mid-document page-number control "
            "(doc.page.restart_page_number/hide_page_elements). It is not a "
            "v5 re-run and does not re-touch v5's 4 strata; it does not "
            "replace v1/v2/v3/v4/v5, which remain published with their own "
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
            "v1": _frozen_reference(OUT_DIR / "manifest.json"),
            "v2": _frozen_reference(OUT_DIR_V2 / "manifest.json"),
            "v3": _frozen_reference(OUT_DIR_V3 / "manifest.json"),
            "v4": _frozen_reference(OUT_DIR_V4 / "manifest.json"),
            "v5": _frozen_reference(OUT_DIR_V5 / "manifest.json"),
        },
        "counts": counts,
        "requestedTotal": sum(slot["requested"] for slot in counts.values()),
        "producedTotal": sum(slot["produced"] for slot in counts.values()),
        "items": all_records,
    }
    manifest_path = OUT_DIR_V6 / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    filelist_path = OUT_DIR_V6 / "box_run_v6.filelist"
    lines = [
        f"{BOX_ROOT}\\{entry['bucket']}\\{entry['id']}.hwpx"
        for entry in all_records
        if entry["produced"]
    ]
    lines += list(BOX_NEGATIVE_CONTROLS)
    filelist_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Field names are the render pipeline's contract (see module docstring —
    # this is v5's ALREADY-CORRECTED shape, copied verbatim: a bare array of
    # {sourceId,stratum,src,pdf}, not {id,bucket,input,output} wrapped in a
    # {"jobs": [...]} object. v4's first box run failed on exactly the
    # wrapped shape; do not reintroduce it here.
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
    render_jobs_path = OUT_DIR_V6 / "render_jobs_v6.json"
    render_jobs_path.write_text(
        json.dumps(render_jobs, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"v6 corpus: {manifest['producedTotal']}/{manifest['requestedTotal']} produced")
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
