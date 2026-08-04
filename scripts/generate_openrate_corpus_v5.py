# SPDX-License-Identifier: Apache-2.0
"""openrate corpus v5 — the 6.1 read-write gap-closing surface, additive over v4.

Why v5 exists
=============

The 6.1 cycle closed five audit-identified "code-blind" read/write gaps in
the OWPML engine surface: font declaration/substitution authoring
(``doc.styles.ensure_font``), paragraph tab-stop authoring
(``doc.styles.apply_paragraph_format(tab_stops=...)``), a documentcompat/
settings.xml read surface, and shape-internal text + table/shape/picture
captions (``shape.set_draw_text``/``*.set_caption``). v1-v4 never exercised
any of this — it did not exist yet. v5 measures ONLY these four new
surfaces; it is not a v4 re-run and does not re-touch v4's 11 strata.

Four strata (all deterministic — fixed seeds, bank rotation, no wall clock)
=============================================================================

* ``authored-fontface``   15  doc.styles.ensure_font across varied lang
                                (None/single/list, all 7 lang blocks touched
                                at least once) x substFont on/off, each
                                wired to an actual run via
                                doc.styles.ensure_run(font=...) so the
                                fontRef this produces is really referenced,
                                not just declared and orphaned
* ``authored-tabstops``    15  doc.styles.apply_paragraph_format(tab_stops=
                                ...) — 1..4 stops per file, type x leader
                                rotated across the full OWPML vocabulary
                                (LEFT/RIGHT/CENTER/DECIMAL x
                                NONE/DOT/DASH/SOLID/DASH_DOT/LONG_DASH),
                                auto_tab_left/right rotated too
* ``authored-drawtext``    15  shape.set_draw_text on rect/ellipse shapes
                                (alternating), editable on/off
* ``authored-caption``     15  *.set_caption rotated across all three host
                                kinds (table/shape/picture) x all four
                                OWPML sides (TOP/BOTTOM/LEFT/RIGHT)

Generation ONLY — no Hancom oracle here. Every produced file gets the static
``validate_editor_open_safety`` pre-filter (necessary, not sufficient); the
real verdict comes from a Windows box run. ``render_jobs_v5.json`` lists a
PDF export job per produced file, same as v4 — these are visual claims (does
the tab stop land where authored, is the drawText legible inside the shape,
does the caption sit on the requested side) a mere "does it open" check
cannot confirm.

Field names are the render pipeline's contract — v4's own comment records
that its FIRST box run failed because ``render_jobs_v4.json`` wrapped a
different field-name shape (``{id,bucket,input,output}``) inside a
``{"jobs": [...]}`` object; ``hancom_render_batch.ps1`` reads
``$Job.sourceId``/``.stratum``/``.src``/``.pdf`` off a BARE ARRAY. v5 copies
v4's *corrected* shape verbatim (see ``main()`` below) precisely so this
mistake is not rediscovered a second time.

``toolVersions["python-hwpx"]`` is read from ``pyproject.toml`` directly,
not ``importlib.metadata`` — the same staleness v4 already routed around for
``python-hwpx-automation`` (an editable install's dist-info can lag the
sources actually executing) applies just as much to this repo's own
version. 6.1.0 has not been version-bumped at the time this script is
written, so an honest run reports ``6.0.2`` — that is the correct value,
not a bug in the generator.

    cd python-hwpx
    .venv-core/bin/python scripts/generate_openrate_corpus_v5.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

PYTHON_HWPX = Path(__file__).resolve().parent.parent
# Explicit — this worktree's src/ must win over whatever editable install
# the running venv happens to carry (observed: a venv borrowed from a
# sibling worktree silently shadowed this checkout's 6.1 surface with an
# older one, turning every record into a false AttributeError withhold).
sys.path.insert(0, str(PYTHON_HWPX / "src"))
sys.path.insert(0, str(PYTHON_HWPX / "scripts"))

from generate_openrate_corpus import (  # noqa: E402
    DEPT_BANK,
    ORG_BANK,
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
    _deterministic_object_ids,
    _frozen_reference,
    _git_commit,
    _read_pyproject_version,
)

# Same discipline v4 established: a moved/deprecated 5.x name firing its
# shim is a genuine 6.x-migration defect, not something to route around
# silently. Importing generate_openrate_corpus_v4 above already installs
# this filter (its own module-level statement) — restated here so this
# module's contract is legible without reading v4's source.
import warnings  # noqa: E402

warnings.simplefilter("error", DeprecationWarning)

OUT_DIR_V5 = PYTHON_HWPX / "work" / "openrate-corpus-v5"
MANIFEST_SCHEMA = "hwpx.openrate.frozen-manifest.v5"
BOX_ROOT = "C:\\openrate\\v5"
BOX_ROOT_PDF = "C:\\openrate\\v5-pdf"


# ================================================================================
# new-stratum banks (rotation only — no wall clock, no randomness)
# ================================================================================
#: NEVER "함초롬바탕"/"함초롬돋움" — those are HwpxDocument.new()'s own
#: skeleton default fontface names, already declared in every fresh
#: document before ensure_font runs. Using either here would make
#: ensure_font's dedupe silently reuse the skeleton's pre-existing entry
#: instead of authoring a genuinely new one (found empirically: the first
#: draft of this bank led every substFont assertion to fail because
#: dedupe kept landing on the skeleton's un-substituted declaration).
FONT_FACE_BANK = (
    "맑은 고딕", "나눔고딕", "나눔명조", "나눔바른고딕", "바탕체",
    "돋움체", "굴림체", "궁서체", "휴먼명조", "안상수체",
    "Arial", "Times New Roman", "Calibri", "Verdana", "Consolas",
)

#: lang rotation exercising None (register-all-7), each of the 7 single
#: values at least once, and several multi-lang lists — 15 entries, index
#: aligned 1:1 with FONT_FACE_BANK.
LANG_ROTATION: tuple[Any, ...] = (
    None, "HANGUL", "LATIN", "HANJA", "JAPANESE", "OTHER", "SYMBOL", "USER",
    ["HANGUL", "LATIN"], ["HANGUL", "HANJA"], ["JAPANESE", "OTHER"],
    ["SYMBOL", "USER"], None, "HANGUL", ["LATIN", "HANJA", "JAPANESE"],
)

SUBST_FACE_BANK = ("맑은 고딕", "돋움체", "굴림체", "바탕체", "나눔고딕")

TAB_STOP_TYPE_BANK = ("LEFT", "RIGHT", "CENTER", "DECIMAL")
TAB_LEADER_BANK = ("NONE", "DOT", "DASH", "SOLID", "DASH_DOT", "LONG_DASH")

DRAWTEXT_FILL_BANK = ("#CCE5FF", "#FFD9CC", "#E0FFCC", "#F5CCFF", "#FFF3CC")

CAPTION_SIDE_BANK = ("TOP", "BOTTOM", "LEFT", "RIGHT")
#: minimal well-formed PNG payload — content is never inspected, only
#: embedded (same synthetic payload convention as v1-v4's picture strata).
CAPTION_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 40


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
def gen_fontface(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(15):
        rec_id = f"v5-fontface-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            document = _base_document(idx, "글꼴 선언 표본")
            face = FONT_FACE_BANK[idx % len(FONT_FACE_BANK)]
            lang = LANG_ROTATION[idx % len(LANG_ROTATION)]
            subst_face = (
                SUBST_FACE_BANK[idx % len(SUBST_FACE_BANK)] if idx % 2 == 0 else None
            )
            document.styles.ensure_font(face, lang=lang, subst_face=subst_face)
            char_id = document.styles.ensure_run(font=face)
            document.add_paragraph(f"{face} 참조 문단 {idx}", char_pr_id_ref=char_id)
            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-fontface", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001 - withheld is the honest record
            records.append(record(
                rec_id=rec_id, bucket="authored-fontface", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


def gen_tabstops(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(15):
        rec_id = f"v5-tabstops-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            document = _base_document(idx, "탭 정의 표본")
            document.add_paragraph(f"본문 문단 {idx} — 탭 정지가 적용됩니다.")
            paragraph_index = len(document.paragraphs) - 1
            stop_count = 1 + idx % 4
            tab_stops = [
                {
                    "pos_mm": 10 * (stop + 1),
                    "type": TAB_STOP_TYPE_BANK[(idx + stop) % len(TAB_STOP_TYPE_BANK)],
                    "leader": TAB_LEADER_BANK[(idx + stop) % len(TAB_LEADER_BANK)],
                }
                for stop in range(stop_count)
            ]
            document.styles.apply_paragraph_format(
                paragraph_index=paragraph_index,
                tab_stops=tab_stops,
                auto_tab_left=(idx % 2 == 0),
                auto_tab_right=(idx % 3 == 0),
            )
            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-tabstops", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001
            records.append(record(
                rec_id=rec_id, bucket="authored-tabstops", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


def gen_drawtext(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(15):
        rec_id = f"v5-drawtext-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            document = _base_document(idx, "도형 텍스트 표본")
            paragraph = document.add_paragraph(f"본문 문단 {idx}")
            fill = DRAWTEXT_FILL_BANK[idx % len(DRAWTEXT_FILL_BANK)]
            if idx % 2 == 0:
                shape = document.shapes.add_rectangle(
                    20000, 10000, fill_color=fill, paragraph=paragraph,
                )
                kind = "사각형"
            else:
                shape = document.shapes.add_ellipse(
                    18000, 12000, fill_color=fill, paragraph=paragraph,
                )
                kind = "타원"
            shape.set_draw_text(
                f"{kind} {idx}: {cycle(SUBJECT_BANK, idx)}",
                name=f"{kind}{idx}",
                editable=(idx % 3 == 0),
            )
            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-drawtext", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001
            records.append(record(
                rec_id=rec_id, bucket="authored-drawtext", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


def gen_caption(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(15):
        rec_id = f"v5-caption-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            document = _base_document(idx, "캡션 표본")
            side = CAPTION_SIDE_BANK[idx % len(CAPTION_SIDE_BANK)]
            target = idx % 3
            if target == 0:
                table = document.add_table(2, 2, width=42000)
                table.set_caption(f"표 {idx} {cycle(SUBJECT_BANK, idx)}", side=side)
            elif target == 1:
                paragraph = document.add_paragraph(f"본문 문단 {idx}")
                shape = document.shapes.add_rectangle(20000, 10000, paragraph=paragraph)
                shape.set_caption(f"도형 {idx} {cycle(DEPT_BANK, idx)}", side=side)
            else:
                pic = document.add_picture(
                    CAPTION_PNG_BYTES, "png", width=10000, height=8000,
                )
                pic.set_caption(f"그림 {idx}. {cycle(ORG_BANK, idx)}", side=side)
            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-caption", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001
            records.append(record(
                rec_id=rec_id, bucket="authored-caption", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


GENERATORS: tuple[tuple[str, Callable[[Path], list[dict[str, Any]]]], ...] = (
    ("authored-fontface", gen_fontface),
    ("authored-tabstops", gen_tabstops),
    ("authored-drawtext", gen_drawtext),
    ("authored-caption", gen_caption),
)


def main() -> int:
    if OUT_DIR_V5.exists() and any(OUT_DIR_V5.iterdir()):
        print(
            f"ERROR: {OUT_DIR_V5} already exists — v5 is frozen once generated. "
            "Delete the tree explicitly to regenerate.",
            file=sys.stderr,
        )
        return 2

    all_records: list[dict[str, Any]] = []
    with _deterministic_object_ids():
        for bucket, generator in GENERATORS:
            bucket_dir = OUT_DIR_V5 / bucket
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
            "v5 is ADDITIVE over v4: 4 new strata exercising ONLY the 6.1 "
            "read-write gaps closed this cycle — font declaration/"
            "substitution authoring (doc.styles.ensure_font), paragraph "
            "tab-stop authoring (doc.styles.apply_paragraph_format(tab_stops"
            "=...)), shape-internal text (shape.set_draw_text) and table/"
            "shape/picture captions (*.set_caption). It is not a v4 re-run "
            "and does not re-touch v4's 11 strata; it does not replace "
            "v1/v2/v3/v4, which remain published with their own "
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
        },
        "counts": counts,
        "requestedTotal": sum(slot["requested"] for slot in counts.values()),
        "producedTotal": sum(slot["produced"] for slot in counts.values()),
        "items": all_records,
    }
    manifest_path = OUT_DIR_V5 / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    filelist_path = OUT_DIR_V5 / "box_run_v5.filelist"
    lines = [
        f"{BOX_ROOT}\\{entry['bucket']}\\{entry['id']}.hwpx"
        for entry in all_records
        if entry["produced"]
    ]
    lines += list(BOX_NEGATIVE_CONTROLS)
    filelist_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Field names are the render pipeline's contract (see module docstring —
    # this is v4's ALREADY-CORRECTED shape, copied verbatim: a bare array of
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
    render_jobs_path = OUT_DIR_V5 / "render_jobs_v5.json"
    render_jobs_path.write_text(
        json.dumps(render_jobs, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"v5 corpus: {manifest['producedTotal']}/{manifest['requestedTotal']} produced")
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
