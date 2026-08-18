# SPDX-License-Identifier: Apache-2.0
"""openrate corpus v22 -- first real-Hancom batch for the Windows-surface
train's three measured-contract authoring surfaces (editor-menu reverse-map
third horizon). v22 is ADDITIVE over v21.

Three strata (deterministic -- fixed seeds, bank rotation, no wall clock)
============================================================================

* ``authored-index-mark``      5  ``HwpxOxmlParagraph.add_index_mark`` --
                                   contract from the box GUI golds
                                   (tests/fixtures/gui_probes/index_mark_
                                   *.hwpx, HWP 13.0.0.3901): hp:ctrl>
                                   hp:indexmark before the run's text, keys
                                   as child-element text, secondKey omitted
                                   when absent (DEV-045). Rotates one-key /
                                   two-key / two paragraphs with distinct
                                   marks / two marks in one paragraph
                                   (acceptance boundary -- unobserved) /
                                   composition with a non-default
                                   char_pr_id_ref heading.
* ``authored-mailmerge-field`` 5  ``HwpxOxmlParagraph.add_mail_merge_field``
                                   -- fieldBegin type=MAILMERGE with the
                                   measured 5-parameter block (Fiexde typo
                                   preserved, DEV-046) and {{name}} cache.
                                   Rotates single / two fields / custom
                                   cached text / hangul field name / field
                                   inside a table cell.
* ``authored-license-mark``    5  ``hwpx.oxml.header_compat.set_license_
                                   mark`` -- hh:docOption>hh:licensemark
                                   (DEV-048). Rotates the observed value
                                   (CCL/0/6) / flag variant / lang variant
                                   / unobserved type string (acceptance
                                   boundary) / re-set idempotence.

Generation ONLY -- no Hancom oracle here. Every produced file gets the
static ``validate_editor_open_safety`` pre-filter (necessary, not
sufficient); the real verdict comes from the macOS GUI oracle (root's Mac).
``render_jobs_v22.json`` lists a PDF export job per produced file, same
shape as v4-v21.

    cd python-hwpx
    .venv/bin/python scripts/generate_openrate_corpus_v22.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

PYTHON_HWPX = Path(__file__).resolve().parent.parent
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
from generate_openrate_corpus_v21 import OUT_DIR_V21  # noqa: E402

import warnings  # noqa: E402

warnings.simplefilter("error", DeprecationWarning)

from hwpx.oxml.header_compat import set_license_mark  # noqa: E402

OUT_DIR_V22 = PYTHON_HWPX / "work" / "openrate-corpus-v22"
MANIFEST_SCHEMA = "hwpx.openrate.frozen-manifest.v22"
BOX_ROOT = "C:\\openrate\\v22"
BOX_ROOT_PDF = "C:\\openrate\\v22-pdf"


def gen_index_mark(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(5):
        rec_id = f"v22-index-mark-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            document = _base_document(idx, "색인 표시 저작 표본")
            if idx == 0:
                p = document.add_paragraph(f"{cycle(DEPT_BANK, idx)} 색인 항목 문단.")
                p.add_index_mark("사과")
            elif idx == 1:
                p = document.add_paragraph(f"{cycle(DEPT_BANK, idx)} 두 단계 색인 문단.")
                p.add_index_mark("과일", second="바나나")
            elif idx == 2:
                p1 = document.add_paragraph("첫째 항목 문단.")
                p1.add_index_mark("첫째")
                p2 = document.add_paragraph("둘째 항목 문단.")
                p2.add_index_mark("둘째", second="세부")
            elif idx == 3:
                # acceptance boundary: two marks in ONE paragraph -- not
                # observed in any gold; the oracle decides.
                p = document.add_paragraph("한 문단 두 색인 표식.")
                p.add_index_mark("가나")
                p.add_index_mark("다라", second="마바")
            else:
                cid = document.styles.ensure_run(bold=True, color="#1F4E79")
                h = document.add_heading("색인 합성 표제", level=1, char_pr_id_ref=cid)
                h.add_index_mark("표제")
            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-index-mark", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001
            records.append(record(
                rec_id=rec_id, bucket="authored-index-mark", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


def gen_mailmerge_field(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(5):
        rec_id = f"v22-mailmerge-field-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            document = _base_document(idx, "메일머지 표시 필드 저작 표본")
            if idx == 0:
                p = document.add_paragraph("이름: ")
                p.add_mail_merge_field("name")
            elif idx == 1:
                p = document.add_paragraph("이름: ")
                p.add_mail_merge_field("name")
                q = document.add_paragraph("주소: ")
                q.add_mail_merge_field("address")
            elif idx == 2:
                p = document.add_paragraph("커스텀 캐시: ")
                p.add_mail_merge_field("dept", cached_text="<<부서명>>")
            elif idx == 3:
                p = document.add_paragraph("한글 필드명: ")
                p.add_mail_merge_field("부서")
            else:
                table = document.add_table(rows=2, cols=2)
                cell_paragraph = table.cell(0, 1).paragraphs[0]
                cell_paragraph.add_mail_merge_field("cellfield")
            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-mailmerge-field", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001
            records.append(record(
                rec_id=rec_id, bucket="authored-mailmerge-field", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


def gen_license_mark(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(5):
        rec_id = f"v22-license-mark-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            document = _base_document(idx, "라이선스 표시 저작 표본")
            document.add_paragraph(f"{cycle(DEPT_BANK, idx)} 본문 문단.")
            header = document.parts.headers[0]
            if idx == 0:
                set_license_mark(header, mark_type="CCL", flag="0", lang="6")
            elif idx == 1:
                set_license_mark(header, mark_type="CCL", flag="1", lang="6")
            elif idx == 2:
                set_license_mark(header, mark_type="CCL", flag="0", lang="0")
            elif idx == 3:
                # acceptance boundary: unobserved type string.
                set_license_mark(header, mark_type="KOGL", flag="0", lang="6")
            else:
                # re-set idempotence: second call replaces, no duplicate.
                set_license_mark(header, mark_type="CCL", flag="1", lang="0")
                set_license_mark(header, mark_type="CCL", flag="0", lang="6")
            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-license-mark", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001
            records.append(record(
                rec_id=rec_id, bucket="authored-license-mark", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


GENERATORS: tuple[tuple[str, Callable[[Path], list[dict[str, Any]]]], ...] = (
    ("authored-index-mark", gen_index_mark),
    ("authored-mailmerge-field", gen_mailmerge_field),
    ("authored-license-mark", gen_license_mark),
)


def _tool_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    versions["python-hwpx"] = _read_pyproject_version(PYTHON_HWPX / "pyproject.toml")
    if versions["python-hwpx"] is None:
        import hwpx

        versions["python-hwpx"] = str(hwpx.__version__)
    return versions


def main() -> int:
    if OUT_DIR_V22.exists() and any(OUT_DIR_V22.iterdir()):
        print(
            f"ERROR: {OUT_DIR_V22} already exists -- v22 is frozen once generated. "
            "Delete the tree explicitly to regenerate.",
            file=sys.stderr,
        )
        return 2

    all_records: list[dict[str, Any]] = []
    with _deterministic_object_ids():
        for bucket, generator in GENERATORS:
            bucket_dir = OUT_DIR_V22 / bucket
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
            "v22 is ADDITIVE over v21: 3 new strata covering the Windows-"
            "surface train's measured-contract authoring (editor-menu "
            "reverse-map third horizon; contracts reversed from box GUI "
            "golds on HWP 13.0.0.3901) -- authored-index-mark "
            "(add_index_mark, DEV-045 secondKey omission), "
            "authored-mailmerge-field (add_mail_merge_field, DEV-046 "
            "Fiexde parameter replication, {{name}} cache), "
            "authored-license-mark (set_license_mark, DEV-048). Each "
            "stratum includes one deliberate beyond-observed acceptance "
            "probe (two marks in one paragraph / hangul field name / "
            "unobserved licence type string). It does not re-touch "
            "v3-v21's strata and does not replace v1-v21, which remain "
            "published with their own measurement stack and date."
        ),
        "generatedAt": None,
        "toolVersions": _tool_versions(),
        "generatingCommit": {
            "python-hwpx": _git_commit(PYTHON_HWPX),
        },
        "boxRoot": BOX_ROOT,
        "boxRootPdf": BOX_ROOT_PDF,
        "negativeControlsByReference": list(BOX_NEGATIVE_CONTROLS),
        "frozenPredecessors": {
            f"v{n}": _frozen_reference(out / "manifest.json")
            for n, out in (
                (3, OUT_DIR_V3), (4, OUT_DIR_V4), (5, OUT_DIR_V5), (6, OUT_DIR_V6),
                (7, OUT_DIR_V7), (8, OUT_DIR_V8), (9, OUT_DIR_V9), (10, OUT_DIR_V10),
                (11, OUT_DIR_V11), (12, OUT_DIR_V12), (13, OUT_DIR_V13),
                (14, OUT_DIR_V14), (15, OUT_DIR_V15), (16, OUT_DIR_V16),
                (17, OUT_DIR_V17), (18, OUT_DIR_V18), (19, OUT_DIR_V19),
                (20, OUT_DIR_V20), (21, OUT_DIR_V21),
            )
        },
        "counts": counts,
        "records": all_records,
    }
    (OUT_DIR_V22 / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    jobs = [
        {
            "sourceId": entry["id"],
            "stratum": entry["bucket"],
            "src": str(OUT_DIR_V22 / entry["bucket"] / f"{entry['id']}.hwpx"),
            "pdf": str(OUT_DIR_V22 / entry["bucket"] / f"{entry['id']}.pdf"),
        }
        for entry in all_records
        if entry["produced"]
    ]
    (OUT_DIR_V22 / "render_jobs_v22.json").write_text(
        json.dumps(jobs, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    produced = sum(1 for entry in all_records if entry["produced"])
    print(f"v22 corpus: {produced}/{len(all_records)} produced -> {OUT_DIR_V22}")
    for bucket, slot in sorted(counts.items()):
        print(f"  {bucket}: {slot['produced']}/{slot['requested']}"
              + (f" withheld={slot['withheld_ids']}" if slot['withheld_ids'] else "")
              + (f" static_unsafe={slot['static_unsafe_ids']}" if slot['static_unsafe_ids'] else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
