# SPDX-License-Identifier: Apache-2.0
"""openrate corpus v13 -- the 6.9 cycle's three new-capability first
judgments: document insertion/merge (train 33), 덧말/글자 겹치기 authoring
(train 34), and mail-merge's first real-Hancom batch (a code-shipped-first
gap trains 30/31 already found but never batched), additive over v12.

Why v13 exists
===============

Train 33 shipped ``hwpx.tools.document_merge`` (``append_document``/
``insert_document``) -- header-owned shared-resource id remapping across 8
id-spaces, contract-first (``docs/2026-08-08-document-merge-contract.md``).
Three real bugs surfaced during independent verification and follow-up
testing (all fixed, ``e4bfb7a``): a ``linkListIDRef``/``linkListNextIDRef``
over-rejection that made every table-bearing merge -- including this
library's own ``add_table`` output -- fail; a save-path dirty-tracking gap
that silently corrupted any picture-free merge on disk; and a whole-run
``hp:secPr`` removal that deleted a real corpus table document's table and
text along with its section setup. ``authored-docmerge`` is the first
real-Hancom batch for this area, deliberately including table-bearing
merges in every stratum (the exact shape all three bugs hit).

Train 34 shipped ``hp:dutmal``(덧말)/``hp:compose``(글자 겹치기) authoring
(``doc.shapes.add_dutmal``/``.add_composed_character``) -- ``hp:compose``'s
read model existed since ``6f88e2e`` with no authoring API or capability
registration; ``hp:dutmal`` was reverse-engineered here for the first time,
from a single real-corpus sample whose ``option``/``szRatio`` values
directly contradict the schema's own declared constraints (DEV-041).
``authored-dutmal-compose`` is this area's first real-Hancom batch.

``hwpx.tools.mail_merge.merge_template_rows`` shipped generations ago
(train 30/31 found and registered the capability-area gap, code itself
predates that) but has never had a real-Hancom batch of its own --
``authored-mailmerge`` is that area's first, rotating the three supported
placeholder syntaxes (``{{field}}``/``${field}``/``<<field>>``) across
three template variants.

Three strata (deterministic -- fixed seeds, bank rotation, no wall clock)
============================================================================

* ``authored-docmerge``         10  Each record merges a freshly-authored
                                     source document into a base target via
                                     ``append_document``/``insert_document``
                                     (alternating), rotating source content
                                     kind across 5 banks (table, styled
                                     text with custom font, numbered
                                     heading, bulleted heading, mixed --
                                     table+text+heading together) so every
                                     stratum has multiple table-bearing
                                     records, the exact shape all three
                                     train-33 bugs hit. Insert position
                                     rotates too (-1/0/last).
* ``authored-dutmal-compose``   10  Each record combines one
                                     ``add_dutmal`` call (main/sub text and
                                     pos_type/align rotating across banks,
                                     sz_ratio/option left at their real-
                                     measured defaults -- DEV-041) with one
                                     ``add_composed_character`` call
                                     (compose_text/circle_type/compose_type
                                     rotating across the schema's own
                                     enum).
* ``authored-mailmerge``        10  Rotates across 3 template documents,
                                     one per placeholder syntax
                                     (``{{field}}``/``${field}``/
                                     ``<<field>>`` exclusively per
                                     template, never mixed within one --
                                     the syntax axis this stratum exists to
                                     exercise), each merged against one row
                                     of rotating data via
                                     ``merge_template_rows``.

Generation ONLY -- no Hancom oracle here. Every produced file gets the
static ``validate_editor_open_safety`` pre-filter (necessary, not
sufficient); the real verdict comes from the macOS GUI oracle (root's Mac).
``render_jobs_v13.json`` lists a PDF export job per produced file, same
shape as v4-v12.

Field names are the render pipeline's contract (see v4-v12's own comments)
-- a bare array of ``{sourceId,stratum,src,pdf}``, not wrapped in a
``{"jobs": [...]}`` object.

``toolVersions["python-hwpx"]`` is read from ``pyproject.toml`` directly,
not ``importlib.metadata`` -- same staleness rationale v4-v12 already
established.

    cd python-hwpx
    .venv-core/bin/python scripts/generate_openrate_corpus_v13.py
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
    DATE_BANK,
    DEPT_BANK,
    ORG_BANK,
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

from hwpx.document import HwpxDocument  # noqa: E402
from hwpx.tools.document_merge import append_document, insert_document  # noqa: E402
from hwpx.tools.mail_merge import merge_template_rows  # noqa: E402

# Same discipline v4-v12 established: a moved/deprecated 5.x name firing its
# shim is a genuine 6.x-migration defect, not something to route around
# silently. Importing generate_openrate_corpus_v4 above already installs
# this filter (its own module-level statement) -- restated here so this
# module's contract is legible without reading v4's source.
import warnings  # noqa: E402

warnings.simplefilter("error", DeprecationWarning)

OUT_DIR_V13 = PYTHON_HWPX / "work" / "openrate-corpus-v13"
MANIFEST_SCHEMA = "hwpx.openrate.frozen-manifest.v13"
BOX_ROOT = "C:\\openrate\\v13"
BOX_ROOT_PDF = "C:\\openrate\\v13-pdf"


# ================================================================================
# stratum 1 -- authored-docmerge
# ================================================================================
#: Source content kind rotation -- "table"/"mixed" both include a table
#: (train 33's three real bugs all hit table-bearing merges specifically),
#: so 4/10 records in this stratum carry a table by rotation, not
#: coincidence.
_SOURCE_CONTENT_BANK: tuple[str, ...] = ("table", "styled_text", "numbered", "bulleted", "mixed")
_MERGE_MODE_BANK: tuple[str, ...] = ("append", "insert")
#: after_paragraph_index rotation for insert-mode records: -1 (before the
#: first paragraph, exercises the "target's own secPr must survive" path)/
#: 0/-2 (roughly "last", clamped per-target below).
_INSERT_POSITION_BANK: tuple[int, ...] = (-1, 0, -2)


def _build_docmerge_source(idx: int, content_kind: str) -> HwpxDocument:
    source = HwpxDocument.new()
    if content_kind == "table":
        source.add_table(rows=2 + (idx % 2), cols=2 + (idx % 3))
    elif content_kind == "styled_text":
        source.styles.ensure_font("맑은 고딕", lang="HANGUL")
        cid = source.styles.ensure_run(font="맑은 고딕", bold=True, color="#1F4E79")
        source.add_paragraph(f"{cycle(ORG_BANK, idx)} 병합 표본 {idx}", char_pr_id_ref=cid)
    elif content_kind == "numbered":
        para_pr_ids = source.styles.ensure_numbering(kind="number")
        source.add_paragraph(f"{idx + 1}. {cycle(DEPT_BANK, idx)} 안건", para_pr_id_ref=para_pr_ids[0])
        source.add_paragraph(f"{idx + 2}. {cycle(DEPT_BANK, idx + 1)} 안건", para_pr_id_ref=para_pr_ids[0])
    elif content_kind == "bulleted":
        para_pr_ids = source.styles.ensure_numbering(kind="bullet")
        source.add_paragraph(f"{cycle(DEPT_BANK, idx)} 항목", para_pr_id_ref=para_pr_ids[0])
    elif content_kind == "mixed":
        source.styles.ensure_font("맑은 고딕", lang="HANGUL")
        cid = source.styles.ensure_run(font="맑은 고딕", italic=True)
        para_pr_ids = source.styles.ensure_numbering(kind="number")
        source.add_paragraph(f"{idx + 1}. 혼합 표본", char_pr_id_ref=cid, para_pr_id_ref=para_pr_ids[0])
        source.add_table(rows=2, cols=2)
    else:  # pragma: no cover - bank is closed
        raise ValueError(f"unknown content_kind {content_kind!r}")
    return source


def gen_docmerge(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(10):
        rec_id = f"v13-docmerge-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        source: HwpxDocument | None = None
        try:
            content_kind = _SOURCE_CONTENT_BANK[idx % len(_SOURCE_CONTENT_BANK)]
            mode = _MERGE_MODE_BANK[idx % len(_MERGE_MODE_BANK)]

            source = _build_docmerge_source(idx, content_kind)
            target = _base_document(idx, f"문서 병합 대상 {idx} ({content_kind}/{mode})")

            if mode == "append":
                append_document(target, source)
            else:
                total = len(target.sections[0].paragraphs)
                requested = _INSERT_POSITION_BANK[idx % len(_INSERT_POSITION_BANK)]
                after_index = max(-1, min(requested, total - 1))
                insert_document(target, source, after_paragraph_index=after_index)

            target.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-docmerge", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001 - withheld is the honest record
            records.append(record(
                rec_id=rec_id, bucket="authored-docmerge", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
        finally:
            if source is not None:
                source.close()
    return records


# ================================================================================
# stratum 2 -- authored-dutmal-compose
# ================================================================================
#: (main_text, sub_text, pos_type, align) -- pos_type/align rotate across
#: their schema-legal values; sz_ratio/option are left at add_dutmal's own
#: real-measured defaults (0/0, DEV-041) rather than overridden here, since
#: this stratum's whole point is exercising that default.
_DUTMAL_BANK: tuple[tuple[str, str, str, str], ...] = (
    ("주식회사", "korea", "TOP", "CENTER"),
    ("협동조합", "coop", "BOTTOM", "LEFT"),
    ("사단법인", "assoc", "TOP", "RIGHT"),
    ("재단법인", "found", "BOTTOM", "CENTER"),
)
#: (compose_text, circle_type, compose_type) -- circle_type rotates across
#: the schema's own enum (ParaList XML schema.xml:544-556); compose_type
#: alternates SPREAD/OVERLAP.
_COMPOSE_BANK: tuple[tuple[str, str, str], ...] = (
    ("가", "SHAPE_CIRCLE", "OVERLAP"),
    ("나", "SHAPE_REVERSAL_CIRCLE", "SPREAD"),
    ("주", "SHAPE_RECTANGLE", "OVERLAP"),
    ("의", "CHAR", "SPREAD"),
    ("特", "SHAPE_RHOMBUS", "OVERLAP"),
)


def gen_dutmal_compose(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(10):
        rec_id = f"v13-dutmalcompose-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            main_text, sub_text, pos_type, align = _DUTMAL_BANK[idx % len(_DUTMAL_BANK)]
            compose_text, circle_type, compose_type = _COMPOSE_BANK[(idx + 1) % len(_COMPOSE_BANK)]

            document = _base_document(idx, "덧말·글자 겹치기 저작 표본")
            paragraph = document.add_paragraph(f"본문 {idx}: ")
            document.shapes.add_dutmal(
                f"{main_text}{idx}", f"{sub_text}{idx}",
                paragraph=paragraph, pos_type=pos_type, align=align,
            )
            document.shapes.add_composed_character(
                compose_text, paragraph=paragraph,
                circle_type=circle_type, compose_type=compose_type,
            )

            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-dutmal-compose", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001 - withheld is the honest record
            records.append(record(
                rec_id=rec_id, bucket="authored-dutmal-compose", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


# ================================================================================
# stratum 3 -- authored-mailmerge
# ================================================================================
#: One template per placeholder syntax -- never mixed within a template,
#: since the syntax axis itself is what this stratum exercises. Fields
#: reuse this whole generator family's own no-real-persons/no-real-orgs
#: banks (ORG_BANK/DATE_BANK/DEPT_BANK).
_MAILMERGE_SYNTAXES: tuple[tuple[str, str], ...] = (
    ("brace", "{{%s}}"),
    ("dollar", "${%s}"),
    ("angle", "<<%s>>"),
)
_MAILMERGE_FIELDS: tuple[str, ...] = ("org", "subject", "date", "dept")


def _build_mailmerge_template(token_fmt: str) -> HwpxDocument:
    document = HwpxDocument.new()
    document.add_paragraph(token_fmt % "org")
    document.add_paragraph(f"제목: {token_fmt % 'subject'}")
    document.add_paragraph(f"시행일: {token_fmt % 'date'} · 담당: {token_fmt % 'dept'}")
    return document


def gen_mailmerge(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    template_dir = bucket_dir / "_templates"
    template_dir.mkdir(parents=True, exist_ok=True)

    # Build the 3 syntax-exclusive templates once, reused across records.
    template_paths: dict[str, Path] = {}
    for syntax_name, token_fmt in _MAILMERGE_SYNTAXES:
        template = _build_mailmerge_template(token_fmt)
        template_path = template_dir / f"template-{syntax_name}.hwpx"
        template.save_to_path(str(template_path))
        template_paths[syntax_name] = template_path

    for idx in range(10):
        rec_id = f"v13-mailmerge-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            syntax_name, _token_fmt = _MAILMERGE_SYNTAXES[idx % len(_MAILMERGE_SYNTAXES)]
            template_path = template_paths[syntax_name]
            row = {
                "org": cycle(ORG_BANK, idx),
                "subject": f"메일머지 표본 {idx}",
                "date": cycle(DATE_BANK, idx),
                "dept": cycle(DEPT_BANK, idx),
            }

            result = merge_template_rows(
                template_path, [row],
                output_dir=bucket_dir, filename_pattern=f"{rec_id}.hwpx",
            )
            row_report = result["rows"][0]
            produced = bool(row_report["created"]) and out_path.exists()

            records.append(record(
                rec_id=rec_id, bucket="authored-mailmerge", seed=str(idx),
                output_path=out_path if produced else None, produced=produced,
                withheld_reason=(
                    None if produced
                    else f"mail_merge row not created: {row_report.get('reasons')}"
                ),
            ))
        except Exception as exc:  # noqa: BLE001 - withheld is the honest record
            records.append(record(
                rec_id=rec_id, bucket="authored-mailmerge", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


GENERATORS: tuple[tuple[str, Callable[[Path], list[dict[str, Any]]]], ...] = (
    ("authored-docmerge", gen_docmerge),
    ("authored-dutmal-compose", gen_dutmal_compose),
    ("authored-mailmerge", gen_mailmerge),
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
    if OUT_DIR_V13.exists() and any(OUT_DIR_V13.iterdir()):
        print(
            f"ERROR: {OUT_DIR_V13} already exists -- v13 is frozen once generated. "
            "Delete the tree explicitly to regenerate.",
            file=sys.stderr,
        )
        return 2

    all_records: list[dict[str, Any]] = []
    with _deterministic_object_ids():
        for bucket, generator in GENERATORS:
            bucket_dir = OUT_DIR_V13 / bucket
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
            "v13 is ADDITIVE over v12: 3 new strata, the 6.9 cycle's three "
            "new-capability first judgments. authored-docmerge (10) targets "
            "hwpx.tools.document_merge (train 33) -- 4/10 records carry a "
            "table by rotation (the exact shape all three real bugs found "
            "and fixed in that train hit: linkListIDRef over-rejection, "
            "save-path dirty-tracking, whole-run hp:secPr removal), the "
            "rest rotate styled-text/numbered/bulleted source content and "
            "append vs insert (varying position). authored-dutmal-compose "
            "(10) targets doc.shapes.add_dutmal/add_composed_character "
            "(train 34) -- add_dutmal's sz_ratio/option are left at their "
            "real-measured defaults (DEV-041) rather than overridden, "
            "since that default is exactly what needs Hancom's verdict. "
            "authored-mailmerge (10) targets hwpx.tools.mail_merge."
            "merge_template_rows -- code shipped generations ago, capability "
            "area registered in train 30/31, but never independently "
            "batched against a real oracle until now; rotates the three "
            "supported placeholder syntaxes ({{field}}/${field}/<<field>>) "
            "across three syntax-exclusive template documents. It does not "
            "re-touch v3-v12's strata; it does not replace v1-v12, which "
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
        },
        "counts": counts,
        "requestedTotal": sum(slot["requested"] for slot in counts.values()),
        "producedTotal": sum(slot["produced"] for slot in counts.values()),
        "items": all_records,
    }
    manifest_path = OUT_DIR_V13 / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    filelist_path = OUT_DIR_V13 / "box_run_v13.filelist"
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
    render_jobs_path = OUT_DIR_V13 / "render_jobs_v13.json"
    render_jobs_path.write_text(
        json.dumps(render_jobs, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"v13 corpus: {manifest['producedTotal']}/{manifest['requestedTotal']} produced")
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
