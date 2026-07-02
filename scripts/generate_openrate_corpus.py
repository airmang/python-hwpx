# SPDX-License-Identifier: Apache-2.0
"""007-open-rate P2 / 010-corpus-publication P1 — FROZEN stratified corpora of
GENERATED .hwpx outputs + provenance manifests, for real-Hancom open-rate runs.

v1 (default mode, specs/007 P2): the published N=100 baseline. It is FROZEN —
this script now REFUSES to regenerate it while ``work/openrate-corpus/
manifest.json`` exists (builder buckets are not bit-stable, so a rerun would
silently invalidate the published sha256 freeze). ``--force-v1`` overrides.

v2 (``--v2``, specs/010 FR-002): ADDITIVE ONLY. Writes a NEW tree
``work/openrate-corpus-v2/`` + fresh manifest (``hwpx.openrate.frozen-
manifest.v2``) that references v1 by relative path + sha256 and NEVER touches
v1 bytes. New strata: form-fit-wide (full 25-input x 3-length sweep minus the
combos already frozen in v1), redline-wide (all v1 authored docs x tracked
insert/delete/replace round-robin, minus v1-covered combos), pii-merge
(synthetic machine-PII roster, masking DEFAULT-ON, raw probe values recorded
per record for the P3 0-leak sweep), authored-toc (native TABLEOFCONTENTS
field docs), reading-runformat (named run formatting + footnote docs,
footnotes preclassified expected-degrade), and shipped-artifacts (read-only
inventory of real demo/ + hwpx-skill outputs — referenced, never copied).
A combined v1+v2 manifest (``combined_manifest.json``) is emitted for the box
filelist step. ``--dry-run`` prints planned per-stratum counts, writes nothing.

Generation ONLY. No Hancom oracle, no commit, no scorecard. The composer
WITHHOLDS bytes when its static open-safety gate fails (server
``_save_generated_document`` raises on ``openSafety.ok == False``), so produced
may be < requested. We record, per bucket: requested / produced / the list of
REQUESTED-BUT-WITHHELD items (end-to-end FAILURES, not absent rows), and compute
``emit_rate = produced / requested``. Every produced file ALSO gets a STATIC
pre-filter result via ``validate_editor_open_safety`` — a structural pre-filter,
NOT the Hancom verdict (that comes later, on Windows).

Determinism: fixed seeds, sorted iteration, stable IDs, no wall-clock in IDs and
``generatedAt`` is left ``null`` (root stamps it).

v1 runs from the mcp-server env (installed surface + editable python-hwpx):

    cd hwpx-mcp-server
    uv run --with-editable ../python-hwpx python \\
        ../python-hwpx/scripts/generate_openrate_corpus.py

v2 needs only python-hwpx (no MCP surface):

    cd python-hwpx
    .venv/bin/python scripts/generate_openrate_corpus.py --v2 [--dry-run]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import traceback
import zipfile
from pathlib import Path
from typing import Any, Sequence

# --- repo geometry --------------------------------------------------------------
PYTHON_HWPX = Path(__file__).resolve().parent.parent          # .../python-hwpx
HWPX_ROOT = PYTHON_HWPX.parent                                 # .../hwpx
MCP_SERVER = HWPX_ROOT / "hwpx-mcp-server"
OUT_DIR = PYTHON_HWPX / "work" / "openrate-corpus"
OUT_DIR_V2 = PYTHON_HWPX / "work" / "openrate-corpus-v2"
SPEC_EVIDENCE = HWPX_ROOT / "specs" / "007-open-rate" / "evidence"
SPEC_EVIDENCE_V2 = HWPX_ROOT / "specs" / "010-corpus-publication" / "evidence"

M2_CORPUS = PYTHON_HWPX / "tests" / "fixtures" / "m2_corpus"
EXAM_FIXTURES = PYTHON_HWPX / "tests" / "fixtures" / "exam"
PUBLIC_CORPUS = PYTHON_HWPX / "work" / "public-document-corpus"

# shipped real artifacts (read-only inventory roots — NEVER written to)
SHIPPED_ROOTS: list[tuple[str, Path]] = [
    ("demo", HWPX_ROOT / "demo"),
    ("skill-examples", HWPX_ROOT / "hwpx-skill" / "examples" / "out"),
]

# --- imports (editable python-hwpx; the MCP surface is imported lazily in
# gen_authored so v2 mode / unit tests do not require hwpx_mcp_server) -----------
from hwpx.document import HwpxDocument  # noqa: E402
from hwpx.exam.compose import compose_exam_into_form  # noqa: E402
from hwpx.form_fit import FitPolicy  # noqa: E402
from hwpx.form_fit.apply import fit_cell_text  # noqa: E402
from hwpx.tools import toc_author  # noqa: E402
from hwpx.tools.mail_merge import mail_merge  # noqa: E402
from hwpx.tools.package_validator import validate_editor_open_safety  # noqa: E402
from hwpx.visual import oracle as visual_oracle  # noqa: E402


# ================================================================================
# helpers
# ================================================================================
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def static_open_safety_ok(path: Path) -> bool:
    """Structural pre-filter (necessary-not-sufficient). NOT the Hancom verdict."""
    try:
        return bool(validate_editor_open_safety(path).ok)
    except Exception:
        return False


def record(
    *,
    rec_id: str,
    bucket: str,
    seed: str,
    output_path: Path | None,
    produced: bool,
    withheld_reason: str | None = None,
    input_path: Path | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": rec_id,
        "bucket": bucket,
        "seed": seed,
        "requested": True,
        "produced": produced,
        "output_path": str(output_path) if output_path else None,
        "output_sha256": None,
        "input_path": str(input_path) if input_path else None,
        "input_sha256": (sha256_file(input_path) if input_path and input_path.exists() else None),
        "withheld_reason": withheld_reason,
        "static_open_safety_ok": None,
    }
    if produced and output_path and output_path.exists():
        out["output_sha256"] = sha256_file(output_path)
        out["static_open_safety_ok"] = static_open_safety_ok(output_path)
    return out


# ================================================================================
# deterministic Korean banks (NO real persons / NO real orgs)
# ================================================================================
ORG_BANK = ["○○교육지원청", "△△군청", "□□시청", "◇◇구청", "☆☆교육청"]
ISSUER_BANK = ["○○교육지원청교육장", "△△군수", "□□시장", "◇◇구청장", "☆☆교육감"]
SUBJECT_BANK = [
    "교육협력 사업 추진 협조 요청",
    "안전점검 결과 통보",
    "예산 집행 실적 제출 안내",
    "행사 개최 협조 요청",
    "시설 보수 계획 알림",
]
DATE_BANK = ["2026. 6. 27.", "2026. 7. 3.", "2026. 7. 10.", "2026. 7. 18.", "2026. 8. 4."]
DEPT_BANK = ["기획부", "운영부", "지원부", "총무부", "관리부", "협력부", "교육부", "안전부"]

# synthetic mail-merge roster (30 rows) — NO real persons
SURNAMES = ["김", "이", "박", "최", "정", "강", "조", "윤", "장", "임"]
GIVEN = ["민준", "서연", "도윤", "지우", "예준", "하은", "주원", "지민", "현우", "수아"]


def cycle(bank: list[str], idx: int) -> str:
    return bank[idx % len(bank)]


# ================================================================================
# bucket 1 — authored (40) : 공문 15 / 보고서 15 / 가정통신문 10
# ================================================================================
def _table_block(rows_n: int) -> dict[str, Any]:
    cols = [
        {"key": "dept", "label": "부서"},
        {"key": "goal", "label": "목표"},
        {"key": "done", "label": "실적"},
        {"key": "rate", "label": "달성률"},
    ]
    rows = []
    for r in range(rows_n):
        goal = 10 + r * 2
        done = goal - (r % 3)
        rate = f"{round(done / goal * 100)}%"
        rows.append({"dept": cycle(DEPT_BANK, r), "goal": str(goal), "done": str(done), "rate": rate})
    return {"type": "table", "columns": cols, "rows": rows}


def authored_plans() -> list[tuple[str, str, dict[str, Any]]]:
    """Return (rec_id, seed, plan) parameter-sweep, deterministic & sorted."""
    plans: list[tuple[str, str, dict[str, Any]]] = []
    table_rows_cycle = [3, 5, 8]

    # 공문 15 : vary org/subject/date + gyeolmun present/absent
    for i in range(15):
        seed = f"authored:gongmun:{i:02d}"
        org = cycle(ORG_BANK, i)
        subject = cycle(SUBJECT_BANK, i)
        date = cycle(DATE_BANK, i)
        has_gyeolmun = (i % 2 == 0)
        plan: dict[str, Any] = {
            "schemaVersion": "hwpx.document_plan.v1",
            "title": f"2026학년도 {subject}",
            "metadata": {"document_type": "공문"},
            "blocks": [
                {"type": "paragraph", "text": "수신  각급기관장"},
                {"type": "heading", "level": 1, "text": "1. 관련"},
                {"type": "paragraph", "text": f"가. {org} {subject} 계획({date})"},
                {"type": "heading", "level": 1, "text": "2. 협조 요청 사항"},
                {"type": "paragraph", "text": "가. 붙임 서식을 작성하여 회신하여 주시기 바랍니다."},
                {"type": "paragraph", "text": "나. 원활한 추진을 위하여 적극 협조하여 주시기 바랍니다."},
                {"type": "paragraph", "text": "붙임  관련 서식 1부.  끝."},
            ],
        }
        if has_gyeolmun:
            plan["gyeolmun"] = {
                "issuer": cycle(ISSUER_BANK, i),
                "productionNumber": f"행정과-{1000 + i}",
                "enforcementDate": date,
                "disclosure": "공개" if i % 3 else "부분공개",
            }
        plans.append((f"authored-gongmun-{i:02d}", seed, plan))

    # 보고서 15 : vary title/dept + table present/absent + row counts 3/5/8
    for i in range(15):
        seed = f"authored:bogoseo:{i:02d}"
        org = cycle(ORG_BANK, i)
        has_table = (i % 3 != 0)  # ~2/3 with a table
        rows_n = table_rows_cycle[i % 3]
        blocks: list[dict[str, Any]] = [
            {"type": "heading", "level": 1, "text": "1. 추진 개요"},
            {"type": "paragraph", "text": f"가. {org} 2026년 상반기 추진 실적을 다음과 같이 보고합니다."},
            {"type": "heading", "level": 2, "text": "가. 부서별 실적 요약"},
        ]
        if has_table:
            blocks.append(_table_block(rows_n))
        else:
            blocks.append({"type": "paragraph", "text": "가. 전 부서 목표 대비 95% 이상을 달성하였습니다."})
        blocks += [
            {"type": "heading", "level": 1, "text": "2. 향후 계획"},
            {"type": "paragraph", "text": "가. 미달 부서에 대한 보완 계획을 수립하여 하반기에 반영한다."},
        ]
        plan = {
            "schemaVersion": "hwpx.document_plan.v1",
            "title": f"부서별 추진실적 보고서 ({i + 1}호)",
            "metadata": {"document_type": "보고서"},
            "blocks": blocks,
        }
        plans.append((f"authored-bogoseo-{i:02d}", seed, plan))

    # 가정통신문 10 : vary title/date
    for i in range(10):
        seed = f"authored:gajeong:{i:02d}"
        date = cycle(DATE_BANK, i)
        plan = {
            "schemaVersion": "hwpx.document_plan.v1",
            "title": f"생활 안내 가정통신문 ({i + 1}차)",
            "metadata": {"document_type": "가정통신문"},
            "blocks": [
                {"type": "paragraph", "text": "학부모님, 안녕하십니까? 학교 교육활동에 보내주신 관심에 감사드립니다."},
                {"type": "heading", "level": 1, "text": "1. 안내 기간"},
                {"type": "paragraph", "text": f"가. {date}부터 적용됩니다."},
                {"type": "heading", "level": 1, "text": "2. 생활 안내"},
                {"type": "paragraph", "text": "가. 규칙적인 생활과 안전 수칙 준수에 유의하여 주시기 바랍니다."},
                {"type": "paragraph", "text": "나. 가정에서 자녀의 독서와 휴식이 균형을 이루도록 지도 부탁드립니다."},
                {"type": "paragraph", "text": date},
                {"type": "paragraph", "text": "○○중학교장"},
            ],
        }
        plans.append((f"authored-gajeong-{i:02d}", seed, plan))

    plans.sort(key=lambda t: t[0])
    return plans


def gen_authored(out_dir: Path) -> tuple[list[dict[str, Any]], list[Path]]:
    from hwpx_mcp_server import server  # lazy: v1-only dependency (installed MCP surface)

    records: list[dict[str, Any]] = []
    produced_paths: list[Path] = []
    bucket_dir = out_dir / "authored"
    bucket_dir.mkdir(parents=True, exist_ok=True)
    for rec_id, seed, plan in authored_plans():
        out_path = bucket_dir / f"{rec_id}.hwpx"
        if out_path.exists():
            out_path.unlink()
        produced = False
        withheld_reason: str | None = None
        try:
            res = server.create_document_from_plan(
                str(out_path), plan, verify_render=False, verbosity="compact"
            )
            if res.get("created") and out_path.exists():
                produced = True
            else:
                withheld_reason = (
                    res.get("error")
                    or res.get("handoff_status")
                    or "create_document_from_plan returned created=False"
                )
        except Exception as exc:  # composer withheld bytes on open-safety gate fail
            withheld_reason = f"{type(exc).__name__}: {exc}".strip()[:400]
        rec = record(
            rec_id=rec_id, bucket="authored", seed=seed,
            output_path=out_path if produced else None,
            produced=produced, withheld_reason=withheld_reason,
        )
        records.append(rec)
        if produced:
            produced_paths.append(out_path)
        print(f"[authored] {rec_id} produced={produced} "
              f"static_ok={rec['static_open_safety_ok']} {withheld_reason or ''}")
    return records, produced_paths


# ================================================================================
# bucket 2 — mail-merge (30) : one 30-row synthetic roster over 1-2 templates
# ================================================================================
def build_merge_template(path: Path, kind: str) -> None:
    """A small placeholder template ({{name}} in a narrow table cell + body text)."""
    doc = HwpxDocument.new()
    if kind == "award":
        doc.add_paragraph("상  장")
        doc.add_paragraph("위 사람은 {{org}} 행사에서 우수한 성적을 거두었기에")
        doc.add_paragraph("이 상장을 수여합니다.  ({{date}})")
        table = doc.add_paragraph("").add_table(1, 2)
        table.cell(0, 0).set_text("성명")
        table.cell(0, 1).set_size(width=5000)
        table.cell(0, 1).set_text("{{name}}")
    else:  # notice
        doc.add_paragraph("가정통신문 — {{org}}")
        doc.add_paragraph("{{name}} 학부모님께 안내드립니다. ({{date}})")
        table = doc.add_paragraph("").add_table(1, 2)
        table.cell(0, 0).set_text("수신")
        table.cell(0, 1).set_size(width=5000)
        table.cell(0, 1).set_text("{{name}}")
    doc.save_to_path(path)


def synthetic_roster() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for r in range(30):
        name = cycle(SURNAMES, r) + cycle(GIVEN, (r * 7) % len(GIVEN))
        rows.append({
            "name": name,
            "org": cycle(ORG_BANK, r),
            "date": cycle(DATE_BANK, r),
        })
    return rows


def gen_mail_merge(out_dir: Path) -> tuple[list[dict[str, Any]], list[Path]]:
    records: list[dict[str, Any]] = []
    produced_paths: list[Path] = []
    bucket_dir = out_dir / "mail-merge"
    bucket_dir.mkdir(parents=True, exist_ok=True)
    tmpl_dir = bucket_dir / "_templates"
    tmpl_dir.mkdir(parents=True, exist_ok=True)

    roster = synthetic_roster()
    # 2 templates; split the 30 rows 15/15 deterministically so each produced
    # file is 1 .hwpx per row (effective-N caveat: clones share a template).
    templates = [("award", roster[:15], 0), ("notice", roster[15:], 15)]

    for kind, rows, base in templates:
        tmpl_path = tmpl_dir / f"template_{kind}.hwpx"
        build_merge_template(tmpl_path, kind)
        tmpl_sha = sha256_file(tmpl_path)
        report = mail_merge(
            tmpl_path,
            rows,
            output_dir=bucket_dir / kind,
            filename_pattern=f"mm-{kind}-{{index:02d}}.hwpx",
            fit_policy=FitPolicy.keep(),
            strict=False,
        )
        row_reports = {r["rowIndex"]: r for r in report["rows"]}
        for local_idx in range(1, len(rows) + 1):
            global_idx = base + local_idx
            rec_id = f"mailmerge-{kind}-{global_idx:02d}"
            seed = f"mailmerge:{kind}:row{global_idx:02d}"
            rr = row_reports.get(local_idx, {})
            produced = bool(rr.get("created"))
            out_path = Path(rr["filename"]) if rr.get("filename") else None
            withheld_reason = None
            if not produced:
                reasons = rr.get("reasons") or []
                withheld_reason = (
                    ",".join(reasons) if reasons
                    else "mail_merge did not create this row"
                )
            rec = record(
                rec_id=rec_id, bucket="mail-merge", seed=seed,
                output_path=out_path if produced else None,
                produced=produced, withheld_reason=withheld_reason,
            )
            rec["input_path"] = str(tmpl_path)
            rec["input_sha256"] = tmpl_sha
            # surface fit/needs-review without dropping the produced file
            if rr.get("reasons"):
                rec["needs_review_reasons"] = rr["reasons"]
            records.append(rec)
            if produced and out_path:
                produced_paths.append(out_path)
            print(f"[mail-merge] {rec_id} produced={produced} "
                  f"static_ok={rec['static_open_safety_ok']} {withheld_reason or ''}")
    return records, produced_paths


# ================================================================================
# bucket 3 — form-fit over REAL forms (20) : sweep value-length {short,med,overflow}
# ================================================================================
LENGTH_SWEEP = {
    "short": "김민준",
    "medium": "행정안전부 정책기획관실 협력담당",
    "overflow": "아주아주아주아주아주아주아주아주아주아주아주긴값입니다정말로굉장히길어서칸을넘칩니다" * 2,
}


def _first_fillable_cell(doc: HwpxDocument):
    """Deterministic target: the first empty table cell (sorted document order)."""
    for p in doc.sections[0].paragraphs:
        for t in p.tables:
            for row in t.rows:
                for c in row.cells:
                    txt = "".join(
                        getattr(pp, "text", "") or "" for pp in getattr(c, "paragraphs", [])
                    )
                    if txt.strip() == "":
                        return c
    return None


def form_fit_inputs() -> list[tuple[str, Path]]:
    """Sorted, deterministic input list: 3 m2 forms + open-safety-ok corpus."""
    inputs: list[tuple[str, Path]] = []
    for name in sorted(p.name for p in M2_CORPUS.glob("*.hwpx")):
        inputs.append((f"m2:{Path(name).stem}", M2_CORPUS / name))
    manifest = json.loads((PUBLIC_CORPUS / "manifest.json").read_text(encoding="utf-8"))
    corpus_ok = [
        e for e in manifest["entries"] if e.get("open_safety_ok")
    ]
    corpus_ok.sort(key=lambda e: e["local_path"])
    for e in corpus_ok:
        lp = Path(e["local_path"])
        inputs.append((f"corpus:{lp.stem}", lp))
    return inputs


def gen_form_fit(out_dir: Path, target_n: int = 20) -> tuple[list[dict[str, Any]], list[Path]]:
    records: list[dict[str, Any]] = []
    produced_paths: list[Path] = []
    bucket_dir = out_dir / "form-fit"
    bucket_dir.mkdir(parents=True, exist_ok=True)

    inputs = form_fit_inputs()
    sweep_order = ["short", "medium", "overflow"]
    emitted = 0
    for tag, in_path in inputs:
        if emitted >= target_n:
            break
        if not in_path.exists():
            continue
        for length in sweep_order:
            if emitted >= target_n:
                break
            rec_id = f"formfit-{tag.replace(':', '_')}-{length}"
            seed = f"formfit:{tag}:{length}"
            out_path = bucket_dir / f"{rec_id}.hwpx"
            if out_path.exists():
                out_path.unlink()
            value = LENGTH_SWEEP[length]
            produced = False
            withheld_reason: str | None = None
            try:
                doc = HwpxDocument.open(in_path)
                cell = _first_fillable_cell(doc)
                if cell is None:
                    withheld_reason = "no empty table cell found for programmatic fill"
                    doc.close()
                else:
                    fit_cell_text(cell, value, FitPolicy.keep(), document=doc)
                    doc.save_to_path(out_path)
                    doc.close()
                    if out_path.exists() and static_open_safety_ok(out_path):
                        produced = True
                    elif out_path.exists():
                        # produced bytes but static pre-filter flags it: keep the
                        # file (Hancom is the real judge) — still counts produced.
                        produced = True
            except Exception as exc:
                withheld_reason = f"{type(exc).__name__}: {exc}".strip()[:400]
            rec = record(
                rec_id=rec_id, bucket="form-fit", seed=seed,
                output_path=out_path if produced else None,
                produced=produced, withheld_reason=withheld_reason,
                input_path=in_path,
            )
            rec["value_length_class"] = length
            records.append(rec)
            if produced:
                produced_paths.append(out_path)
                emitted += 1
            print(f"[form-fit] {rec_id} produced={produced} "
                  f"static_ok={rec['static_open_safety_ok']} {withheld_reason or ''}")
    return records, produced_paths


# ================================================================================
# bucket 4 — exam (5) : A_form x exam md of {5,10,15} questions
# ================================================================================
def _slice_exam_md(src_md: str, n_questions: int) -> str:
    """Take the first N top-level (## ) questions from the sample exam markdown."""
    lines = src_md.splitlines()
    header_lines: list[str] = []
    body_lines: list[str] = []
    q_count = 0
    in_body = False
    for ln in lines:
        is_q_head = bool(re.match(r"^##\s+\d", ln)) or bool(re.match(r"^##\s+\d+[∼~]", ln))
        if is_q_head:
            in_body = True
            q_count += 1
            if q_count > n_questions:
                break
        if not in_body:
            header_lines.append(ln)
        else:
            body_lines.append(ln)
    return "\n".join(header_lines + body_lines).strip() + "\n"


def gen_exam(out_dir: Path) -> tuple[list[dict[str, Any]], list[Path]]:
    records: list[dict[str, Any]] = []
    produced_paths: list[Path] = []
    bucket_dir = out_dir / "exam"
    bucket_dir.mkdir(parents=True, exist_ok=True)

    a_form = EXAM_FIXTURES / "A_form.hwpx"
    sample_md = (EXAM_FIXTURES / "sample_exam.md").read_text(encoding="utf-8")
    null_oracle = visual_oracle.NullOracle()  # generation only — never render

    # 5 outputs = {5,10,15} questions, then 5 and 10 again to reach 5 files
    variants = [5, 10, 15, 5, 10]
    for vi, n_q in enumerate(variants):
        rec_id = f"exam-{vi:02d}-q{n_q:02d}"
        seed = f"exam:Aform:q{n_q}:v{vi}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        if out_path.exists():
            out_path.unlink()
        exam_md = _slice_exam_md(sample_md, n_q)
        produced = False
        withheld_reason: str | None = None
        try:
            res = compose_exam_into_form(
                str(a_form), exam_md, str(out_path), oracle=null_oracle
            )
            if out_path.exists():
                produced = True
            else:
                withheld_reason = "compose produced no output file"
            _ = res  # render_checked False / needs_review True by design (no oracle)
        except Exception as exc:
            withheld_reason = f"{type(exc).__name__}: {exc}".strip()[:400]
        rec = record(
            rec_id=rec_id, bucket="exam", seed=seed,
            output_path=out_path if produced else None,
            produced=produced, withheld_reason=withheld_reason,
            input_path=a_form,
        )
        rec["n_questions"] = n_q
        records.append(rec)
        if produced:
            produced_paths.append(out_path)
        print(f"[exam] {rec_id} produced={produced} "
              f"static_ok={rec['static_open_safety_ok']} {withheld_reason or ''}")
    return records, produced_paths


# ================================================================================
# bucket 5 — redline (5) : take 5 authored outputs, apply tracked changes
# ================================================================================
def gen_redline(out_dir: Path, authored_paths: list[Path]) -> tuple[list[dict[str, Any]], list[Path]]:
    records: list[dict[str, Any]] = []
    produced_paths: list[Path] = []
    bucket_dir = out_dir / "redline"
    bucket_dir.mkdir(parents=True, exist_ok=True)

    sources = sorted(authored_paths, key=lambda p: p.name)[:5]
    for i, src in enumerate(sources):
        rec_id = f"redline-{i:02d}-{src.stem}"
        seed = f"redline:{src.stem}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        if out_path.exists():
            out_path.unlink()
        produced = False
        withheld_reason: str | None = None
        try:
            doc = HwpxDocument.open(src)
            paras = [p for p in doc.sections[0].paragraphs
                     if (getattr(p, "text", "") or "").strip()]
            applied = 0
            # tracked insert on the 1st text para
            if paras:
                doc.add_tracked_insert(paras[0], " [검토필]", author="검토자",
                                       date="2026-07-01T00:00:00")
                applied += 1
            # tracked replace on a para containing a known token, else delete-clip
            for p in paras[1:]:
                txt = getattr(p, "text", "") or ""
                if "가." in txt:
                    try:
                        doc.add_tracked_replace(p, "가.", "가.(수정)",
                                                author="검토자",
                                                date="2026-07-01T00:00:00")
                        applied += 1
                        break
                    except Exception:
                        continue
            if applied == 0:
                withheld_reason = "no eligible paragraph for a tracked change"
                doc.close()
            else:
                doc.save_to_path(out_path)
                doc.close()
                if out_path.exists():
                    produced = True
        except Exception as exc:
            withheld_reason = f"{type(exc).__name__}: {exc}".strip()[:400]
        rec = record(
            rec_id=rec_id, bucket="redline", seed=seed,
            output_path=out_path if produced else None,
            produced=produced, withheld_reason=withheld_reason,
            input_path=src,
        )
        records.append(rec)
        if produced:
            produced_paths.append(out_path)
        print(f"[redline] {rec_id} produced={produced} "
              f"static_ok={rec['static_open_safety_ok']} {withheld_reason or ''}")
    return records, produced_paths


# ================================================================================
# ================================================================================
# corpus v2 (specs/010-corpus-publication FR-002) — ADDITIVE strata only.
# v1 is FROZEN: v2 READS v1 outputs/manifest but never writes into OUT_DIR.
# ================================================================================
# ================================================================================
V2_SCHEMA = "hwpx.openrate.frozen-manifest.v2"
COMBINED_SCHEMA = "hwpx.openrate.combined-manifest.v1"
V2_TRACK_AUTHOR = "검토자"
V2_TRACK_DATE = "2026-07-02T00:00:00"  # fixed timestamp — deterministic, not wall-clock
REDLINE_OPS = ("insert", "delete", "replace")
PII_MERGE_N = 35
AUTHORED_TOC_N = 15
READING_RUNFORMAT_N = 10
READING_FOOTNOTE_N = 3

TOC_HEADING_BANK = ["추진 배경", "추진 계획", "세부 과제", "기대 효과", "향후 일정"]
COLOR_BANK = ["#C00000", "#0070C0", "#00B050", "#7030A0"]
FONT_BANK = ["함초롬돋움", "함초롬바탕"]


def record_v2(
    *,
    rec_id: str,
    stratum: str,
    seed: str,
    output_path: Path | None,
    produced: bool,
    withheld_reason: str | None = None,
    input_path: Path | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """A v1 record + v2 fields: stratum, hostile_input (tagging hook — future
    hwpxlib-derived inputs set True so input-attributed failures separate), extras."""
    rec = record(
        rec_id=rec_id, bucket=stratum, seed=seed,
        output_path=output_path, produced=produced,
        withheld_reason=withheld_reason, input_path=input_path,
    )
    rec["stratum"] = stratum
    rec["hostile_input"] = False
    rec.update(extra)
    return rec


# --------------------------------------------------------------------------------
# pure planners (unit-tested; no filesystem writes)
# --------------------------------------------------------------------------------
def v1_formfit_combos(v1_manifest: dict[str, Any]) -> set[tuple[str, str]]:
    """(input-tag, length) combos already frozen in v1 — v2 must SKIP these.

    v1 form-fit seeds are ``formfit:{tag}:{length}`` where tag itself contains a
    colon (``m2:form_002`` / ``corpus:aikorea-…``).
    """
    combos: set[tuple[str, str]] = set()
    for rec in v1_manifest.get("records", []):
        if rec.get("bucket") != "form-fit":
            continue
        parts = str(rec.get("seed", "")).split(":")
        if len(parts) >= 3 and parts[0] == "formfit":
            combos.add((":".join(parts[1:-1]), parts[-1]))
    return combos


def plan_form_fit_wide(
    inputs: Sequence[tuple[str, Path]],
    v1_combos: set[tuple[str, str]],
    sweep_order: Sequence[str] = ("short", "medium", "overflow"),
) -> list[tuple[str, Path, str]]:
    """Full input x length sweep minus v1-frozen combos. Deterministic order."""
    planned: list[tuple[str, Path, str]] = []
    for tag, in_path in inputs:
        for length in sweep_order:
            if (tag, length) in v1_combos:
                continue
            planned.append((tag, in_path, length))
    return planned


def v1_authored_sources(v1_manifest: dict[str, Any]) -> list[tuple[str, Path]]:
    """(stem, path) of every produced v1 authored doc, sorted by stem (pure)."""
    out: list[tuple[str, Path]] = []
    for rec in v1_manifest.get("records", []):
        if rec.get("bucket") == "authored" and rec.get("produced") and rec.get("output_path"):
            p = Path(rec["output_path"])
            out.append((p.stem, p))
    out.sort(key=lambda t: t[0])
    return out


def v1_redline_covered(
    v1_manifest: dict[str, Any],
    v1_ops: Sequence[str] = ("insert", "replace"),
) -> set[tuple[str, str]]:
    """(source-stem, op) combos v1 already exercises. The frozen v1 generator
    applied a tracked INSERT always and a tracked REPLACE conditionally on each
    of its 5 sources, so both ops count as covered for those stems."""
    covered: set[tuple[str, str]] = set()
    for rec in v1_manifest.get("records", []):
        if rec.get("bucket") != "redline":
            continue
        seed = str(rec.get("seed", ""))
        stem = seed.split(":", 1)[1] if ":" in seed else seed
        for op in v1_ops:
            covered.add((stem, op))
    return covered


def plan_redline_wide(
    source_stems: Sequence[str],
    covered: set[tuple[str, str]],
) -> list[tuple[str, str]]:
    """One tracked op per source, round-robin insert/delete/replace by index,
    skipping (source, op) combos v1 already covers. Deterministic."""
    planned: list[tuple[str, str]] = []
    for i, stem in enumerate(source_stems):
        op = REDLINE_OPS[i % len(REDLINE_OPS)]
        if (stem, op) in covered:
            continue
        planned.append((stem, op))
    return planned


def luhn_check_digit(payload: str) -> str:
    """Check digit that makes ``payload + digit`` Luhn-valid."""
    total = 0
    for pos, ch in enumerate(reversed(payload)):
        d = int(ch)
        if pos % 2 == 0:  # doubling starts at the digit adjacent to the check digit
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return str((10 - total % 10) % 10)


def luhn_ok(number: str) -> bool:
    digits = re.sub(r"\D", "", number)
    if not digits:
        return False
    total = 0
    for pos, ch in enumerate(reversed(digits)):
        d = int(ch)
        if pos % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def synthetic_pii_roster(n: int = PII_MERGE_N) -> list[dict[str, str]]:
    """Deterministic SYNTHETIC machine-PII roster (NO real persons, NO random).

    Every value derives from the row index: rrn is pattern-valid (YYMMDD-GNNNNNN,
    plausible date, gender 1-4) but a range-safe fake; phone is 010-xxxx-xxxx;
    email is under example.com; card is 16-digit Luhn-valid (so the shipped
    masking engine detects and masks it — the corpus property under test).
    """
    rows: list[dict[str, str]] = []
    for i in range(n):
        name = cycle(SURNAMES, i) + cycle(GIVEN, (i * 7) % len(GIVEN))
        yy = 70 + (i % 30)
        mm = (i % 12) + 1
        dd = (i % 28) + 1
        gender = 1 + (i % 4)
        rrn = f"{yy:02d}{mm:02d}{dd:02d}-{gender}{234500 + i:06d}"
        phone = f"010-{1000 + i:04d}-{5600 + i:04d}"
        email = f"user{i:02d}@example.com"
        card_payload = f"4111{2200 + i:04d}{3300 + i:04d}{100 + (i % 900):03d}"
        card_digits = card_payload + luhn_check_digit(card_payload)
        card = "-".join(card_digits[j:j + 4] for j in range(0, 16, 4))
        rows.append({
            "name": name,
            "org": cycle(ORG_BANK, i),
            "date": cycle(DATE_BANK, i),
            "rrn": rrn,
            "phone": phone,
            "email": email,
            "card": card,
        })
    return rows


def merge_manifests(
    v1_manifest: dict[str, Any],
    v2_manifest: dict[str, Any],
    *,
    v1_root: Path,
    v2_root: Path,
    shipped_root: Path,
) -> dict[str, Any]:
    """Combined v1+v2 manifest for the box filelist step (pure; inputs unmodified).

    v1 records are merged BY REFERENCE (copied dicts, untouched files). Every
    produced record gains ``box_rel`` — its path under the box mirror layout
    ``{v1/**, v2/**, shipped/**}`` — so openrate_box_filelist --combined can emit
    exact box paths without guessing roots.
    """
    def _box_rel(path_str: str, root: Path, prefix: str) -> str:
        p = Path(path_str)
        try:
            rel = p.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:  # not under the expected root — basename fallback
            rel = p.name
        return f"{prefix}/{rel}"

    records: list[dict[str, Any]] = []
    for rec in v1_manifest.get("records", []):
        rr = dict(rec)
        rr["corpus"] = "v1"
        rr.setdefault("stratum", rr.get("bucket"))
        rr["box_rel"] = (
            _box_rel(str(rr["output_path"]), v1_root, "v1") if rr.get("output_path") else None
        )
        records.append(rr)
    for rec in v2_manifest.get("records", []):
        rr = dict(rec)
        rr["corpus"] = "v2"
        rr.setdefault("stratum", rr.get("bucket"))
        if rr.get("output_path"):
            if rr.get("stratum") == "shipped-artifacts":
                rr["box_rel"] = _box_rel(str(rr["output_path"]), shipped_root, "shipped")
            else:
                rr["box_rel"] = _box_rel(str(rr["output_path"]), v2_root, "v2")
        else:
            rr["box_rel"] = None
        records.append(rr)

    requested_total = len(records)
    produced_total = sum(1 for r in records if r.get("produced"))
    counts: dict[str, dict[str, int]] = {}
    for r in records:
        key = f"{r['corpus']}:{r.get('stratum') or r.get('bucket')}"
        slot = counts.setdefault(key, {"requested": 0, "produced": 0})
        slot["requested"] += 1
        if r.get("produced"):
            slot["produced"] += 1

    return {
        "schemaVersion": COMBINED_SCHEMA,
        "generatedAt": None,  # root stamps it — DO NOT call datetime.now
        "note": (
            "Combined v1+v2 population for the box run. v1 records merged BY "
            "REFERENCE (frozen bytes untouched); box_rel is the path under the "
            "box mirror layout {v1/**, v2/**, shipped/**}."
        ),
        "v1_schema": v1_manifest.get("schemaVersion"),
        "v2_schema": v2_manifest.get("schemaVersion"),
        "counts_per_stratum": counts,
        "requested_total": requested_total,
        "produced_total": produced_total,
        "records": records,
    }


# --------------------------------------------------------------------------------
# stratum 1 — form-fit-wide: FULL input x length sweep minus v1 combos (~+55)
# --------------------------------------------------------------------------------
def gen_form_fit_wide(
    out_dir: Path, v1_manifest: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[Path]]:
    records: list[dict[str, Any]] = []
    produced_paths: list[Path] = []
    bucket_dir = out_dir / "form-fit-wide"
    bucket_dir.mkdir(parents=True, exist_ok=True)

    inputs = [(tag, p) for tag, p in form_fit_inputs() if p.exists()]
    planned = plan_form_fit_wide(inputs, v1_formfit_combos(v1_manifest))
    for tag, in_path, length in planned:
        rec_id = f"formfit-wide-{tag.replace(':', '_')}-{length}"
        seed = f"formfit-wide:{tag}:{length}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        if out_path.exists():
            out_path.unlink()
        value = LENGTH_SWEEP[length]
        produced = False
        withheld_reason: str | None = None
        try:
            doc = HwpxDocument.open(in_path)
            cell = _first_fillable_cell(doc)
            if cell is None:
                withheld_reason = "no empty table cell found for programmatic fill"
                doc.close()
            else:
                fit_cell_text(cell, value, FitPolicy.keep(), document=doc)
                doc.save_to_path(out_path)
                doc.close()
                if out_path.exists():
                    # static pre-filter recorded either way (Hancom is the judge)
                    produced = True
        except Exception as exc:
            withheld_reason = f"{type(exc).__name__}: {exc}".strip()[:400]
        rec = record_v2(
            rec_id=rec_id, stratum="form-fit-wide", seed=seed,
            output_path=out_path if produced else None,
            produced=produced, withheld_reason=withheld_reason,
            input_path=in_path,
            value_length_class=length,
        )
        records.append(rec)
        if produced:
            produced_paths.append(out_path)
        print(f"[form-fit-wide] {rec_id} produced={produced} "
              f"static_ok={rec['static_open_safety_ok']} {withheld_reason or ''}")
    return records, produced_paths


# --------------------------------------------------------------------------------
# stratum 2 — redline-wide: all v1 authored sources x insert/delete/replace (~+37)
# --------------------------------------------------------------------------------
def _apply_tracked_op(doc: HwpxDocument, op: str) -> str | None:
    """Apply one tracked op deterministically. Returns a withheld reason or None."""
    paras = [p for p in doc.sections[0].paragraphs
             if (getattr(p, "text", "") or "").strip()]
    if not paras:
        return "no text paragraph in source"
    if op == "insert":
        doc.add_tracked_insert(paras[0], " [검토필]",
                               author=V2_TRACK_AUTHOR, date=V2_TRACK_DATE)
        return None
    if op == "delete":
        target = paras[1] if len(paras) > 1 else paras[0]
        doc.add_tracked_delete(target, author=V2_TRACK_AUTHOR, date=V2_TRACK_DATE)
        return None
    if op == "replace":
        for p in paras:
            if "가." in (getattr(p, "text", "") or ""):
                doc.add_tracked_replace(p, "가.", "가.(수정)",
                                        author=V2_TRACK_AUTHOR, date=V2_TRACK_DATE)
                return None
        return "no eligible paragraph for tracked replace"
    return f"unknown tracked op: {op}"


def gen_redline_wide(
    out_dir: Path, v1_manifest: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[Path]]:
    records: list[dict[str, Any]] = []
    produced_paths: list[Path] = []
    bucket_dir = out_dir / "redline-wide"
    bucket_dir.mkdir(parents=True, exist_ok=True)

    sources = v1_authored_sources(v1_manifest)          # READ-ONLY v1 inputs
    path_by_stem = dict(sources)
    planned = plan_redline_wide([s for s, _ in sources],
                                v1_redline_covered(v1_manifest))
    for stem, op in planned:
        src = path_by_stem[stem]
        rec_id = f"redlinewide-{op}-{stem}"
        seed = f"redline-wide:{stem}:{op}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        if out_path.exists():
            out_path.unlink()
        produced = False
        withheld_reason: str | None = None
        if not src.exists():
            withheld_reason = "v1 source file missing on disk"
        else:
            try:
                doc = HwpxDocument.open(src)
                withheld_reason = _apply_tracked_op(doc, op)
                if withheld_reason is None:
                    doc.save_to_path(out_path)
                    doc.close()
                    if out_path.exists():
                        produced = True
                else:
                    doc.close()
            except Exception as exc:
                withheld_reason = f"{type(exc).__name__}: {exc}".strip()[:400]
        rec = record_v2(
            rec_id=rec_id, stratum="redline-wide", seed=seed,
            output_path=out_path if produced else None,
            produced=produced, withheld_reason=withheld_reason,
            input_path=src,
            tracked_op=op, source_stem=stem,
        )
        records.append(rec)
        if produced:
            produced_paths.append(out_path)
        print(f"[redline-wide] {rec_id} produced={produced} "
              f"static_ok={rec['static_open_safety_ok']} {withheld_reason or ''}")
    return records, produced_paths


# --------------------------------------------------------------------------------
# stratum 3 — pii-merge: machine-PII roster, masking DEFAULT-ON (~+35)
# --------------------------------------------------------------------------------
def build_pii_merge_template(path: Path) -> None:
    """Placeholder template whose merged fields carry MACHINE PII values."""
    doc = HwpxDocument.new()
    doc.add_paragraph("개인정보 수집·이용 확인서 — {{org}}")
    doc.add_paragraph("성명: {{name}} / 작성일: {{date}}")
    table = doc.add_paragraph("").add_table(4, 2)
    for r, (label, key) in enumerate([
        ("주민등록번호", "rrn"),
        ("휴대전화", "phone"),
        ("이메일", "email"),
        ("카드번호", "card"),
    ]):
        table.cell(r, 0).set_text(label)
        table.cell(r, 1).set_size(width=20000)
        table.cell(r, 1).set_text("{{" + key + "}}")
    doc.save_to_path(path)


def gen_pii_merge(out_dir: Path, n: int = PII_MERGE_N) -> tuple[list[dict[str, Any]], list[Path]]:
    records: list[dict[str, Any]] = []
    produced_paths: list[Path] = []
    bucket_dir = out_dir / "pii-merge"
    bucket_dir.mkdir(parents=True, exist_ok=True)
    tmpl_dir = bucket_dir / "_templates"
    tmpl_dir.mkdir(parents=True, exist_ok=True)

    tmpl_path = tmpl_dir / "template_pii.hwpx"
    build_pii_merge_template(tmpl_path)
    tmpl_sha = sha256_file(tmpl_path)

    roster = synthetic_pii_roster(n)
    # masking_policy defaults to DEFAULT_POLICY — the SHIPPED default (M5). The
    # merged outputs must contain MASKED values; each record carries the raw
    # probe values so the P3 0-leak sweep can grep for them (expected: 0 hits).
    report = mail_merge(
        tmpl_path,
        roster,
        output_dir=bucket_dir / "merged",
        filename_pattern="pii-{index:02d}.hwpx",
        fit_policy=FitPolicy.keep(),
        strict=False,
    )
    row_reports = {r["rowIndex"]: r for r in report["rows"]}
    for idx in range(1, len(roster) + 1):
        row = roster[idx - 1]
        rec_id = f"piimerge-{idx:02d}"
        seed = f"pii-merge:row{idx:02d}"
        rr = row_reports.get(idx, {})
        produced = bool(rr.get("created"))
        out_path = Path(rr["filename"]) if rr.get("filename") else None
        withheld_reason = None
        if not produced:
            reasons = rr.get("reasons") or []
            withheld_reason = (
                ",".join(reasons) if reasons else "mail_merge did not create this row"
            )
        rec = record_v2(
            rec_id=rec_id, stratum="pii-merge", seed=seed,
            output_path=out_path if produced else None,
            produced=produced, withheld_reason=withheld_reason,
            template="pii_v2",  # effective-N grouping key (clones off one template)
            masking_default_on=True,
            masked_fields=rr.get("maskedFields") or [],
            # raw probe values — consumed by the P3 0-leak sweep (grep targets)
            pii_probe_values={
                "rrn": row["rrn"],
                "phone": row["phone"],
                "email": row["email"],
                "card": row["card"],
            },
        )
        rec["input_path"] = str(tmpl_path)
        rec["input_sha256"] = tmpl_sha
        if rr.get("reasons"):
            rec["needs_review_reasons"] = rr["reasons"]
        records.append(rec)
        if produced and out_path:
            produced_paths.append(out_path)
        print(f"[pii-merge] {rec_id} produced={produced} "
              f"masked={rec['masked_fields']} {withheld_reason or ''}")
    return records, produced_paths


# --------------------------------------------------------------------------------
# stratum 4 — authored-toc: native TABLEOFCONTENTS field docs (~+15)
# --------------------------------------------------------------------------------
def _outline_style_refs_local(doc: HwpxDocument, level: int = 1) -> dict[str, Any]:
    """Style refs for a HWP outline heading level (vendored — the plan-v2 native
    flag being wired into hwpx.authoring by another workstream is NOT a dependency
    here; this only scans the shipped default template's styles)."""
    safe_level = min(10, max(1, int(level)))
    for style in doc.styles.values():
        name = str(style.name or "")
        eng_name = str(style.eng_name or "")
        if name == f"개요 {safe_level}" or eng_name == f"Outline {safe_level}":
            style_id = style.raw_id if style.raw_id is not None else style.id
            if style_id is None:
                continue
            refs: dict[str, Any] = {"style_id_ref": style_id}
            if style.para_pr_id_ref is not None:
                refs["para_pr_id_ref"] = int(style.para_pr_id_ref)
            return refs
    return {}


def gen_authored_toc(out_dir: Path, n: int = AUTHORED_TOC_N) -> tuple[list[dict[str, Any]], list[Path]]:
    records: list[dict[str, Any]] = []
    produced_paths: list[Path] = []
    bucket_dir = out_dir / "authored-toc"
    bucket_dir.mkdir(parents=True, exist_ok=True)

    for i in range(n):
        rec_id = f"authoredtoc-{i:02d}"
        seed = f"authored-toc:{i:02d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        if out_path.exists():
            out_path.unlink()
        n_headings = 3 + (i % 3)
        body_paras = 2 + (i % 2)
        body_reps = 8 + 4 * (i % 4)
        produced = False
        withheld_reason: str | None = None
        try:
            doc = HwpxDocument.new()
            refs = _outline_style_refs_local(doc, 1)
            if not refs:
                withheld_reason = "no 개요/Outline style in the default template"
            else:
                headings = []
                for h_idx in range(n_headings):
                    title = cycle(TOC_HEADING_BANK, h_idx + i)
                    h = doc.add_paragraph(title, **refs)
                    headings.append(h)
                    for _ in range(body_paras):
                        # M7 ContentsStyles trap: body MUST NOT sit on style 0
                        # (바탕글 is collected as TOC entries on regeneration) —
                        # give it 본문 (style 1) like the M7 demo.
                        doc.add_paragraph(
                            f"{title}에 대한 상세 설명 문장입니다. 본문 내용이 이어집니다. " * body_reps,
                            style_id_ref="1", para_pr_id_ref=1,
                        )
                summary = toc_author.add_native_toc(doc, headings=headings, hyperlink=False)
                doc.save_to_path(out_path)
                if out_path.exists():
                    produced = True
        except Exception as exc:
            withheld_reason = f"{type(exc).__name__}: {exc}".strip()[:400]
        rec = record_v2(
            rec_id=rec_id, stratum="authored-toc", seed=seed,
            output_path=out_path if produced else None,
            produced=produced, withheld_reason=withheld_reason,
            toc_native=True,
            toc_entry_count=(summary["entryCount"] if produced else None),
        )
        records.append(rec)
        if produced:
            produced_paths.append(out_path)
        print(f"[authored-toc] {rec_id} produced={produced} "
              f"static_ok={rec['static_open_safety_ok']} {withheld_reason or ''}")
    return records, produced_paths


# --------------------------------------------------------------------------------
# stratum 5 — reading-runformat: named run formatting + footnotes (~+10)
# --------------------------------------------------------------------------------
def gen_reading_runformat(
    out_dir: Path, n: int = READING_RUNFORMAT_N, footnote_count: int = READING_FOOTNOTE_N
) -> tuple[list[dict[str, Any]], list[Path]]:
    records: list[dict[str, Any]] = []
    produced_paths: list[Path] = []
    bucket_dir = out_dir / "reading-runformat"
    bucket_dir.mkdir(parents=True, exist_ok=True)

    for i in range(n):
        rec_id = f"runformat-{i:02d}"
        seed = f"reading-runformat:{i:02d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        if out_path.exists():
            out_path.unlink()
        has_footnote = i < footnote_count
        produced = False
        withheld_reason: str | None = None
        try:
            doc = HwpxDocument.new()
            doc.add_paragraph(f"M9 런서식 표본 문서 ({i + 1}호)")
            p = doc.add_paragraph("이 문단은 ")
            p.add_run("굵게", bold=True)
            p.add_run(", ")
            p.add_run("기울임", italic=True)
            p.add_run(", ")
            p.add_run("밑줄", underline=True)
            p.add_run(", ")
            p.add_run("취소선", strike=True)
            p.add_run(", ")
            p.add_run("색상", color=cycle(COLOR_BANK, i))
            p.add_run(", ")
            p.add_run("크기", size=12 + (i % 8))
            p.add_run(", ")
            p.add_run("글꼴", font=cycle(FONT_BANK, i))
            p.add_run(" 을 섞어 씁니다.")
            if has_footnote:
                note = p.add_footnote("각주 본문의 ")
                note.add_run("강조", bold=True)
                note.add_run(" 서식 포함.")
            doc.add_paragraph("서식 축 전체(굵게·기울임·밑줄·취소선·색·크기·글꼴)를 시험하는 문서입니다.")
            doc.save_to_path(out_path)
            if out_path.exists():
                produced = True
        except Exception as exc:
            withheld_reason = f"{type(exc).__name__}: {exc}".strip()[:400]
        extra: dict[str, Any] = {"has_footnote": has_footnote}
        if has_footnote:
            # M3 finding: Hancom does not render our footnotes — preclassified,
            # honest: a render miss on these files is EXPECTED, not a regression.
            extra["expected_render"] = "footnote-expected-degrade"
        rec = record_v2(
            rec_id=rec_id, stratum="reading-runformat", seed=seed,
            output_path=out_path if produced else None,
            produced=produced, withheld_reason=withheld_reason,
            **extra,
        )
        records.append(rec)
        if produced:
            produced_paths.append(out_path)
        print(f"[reading-runformat] {rec_id} produced={produced} "
              f"static_ok={rec['static_open_safety_ok']} footnote={has_footnote}")
    return records, produced_paths


# --------------------------------------------------------------------------------
# stratum 6 — shipped-artifacts: READ-ONLY inventory of real shipped outputs
# --------------------------------------------------------------------------------
def inventory_shipped_artifacts(
    roots: Sequence[tuple[str, Path]],
    *,
    base_root: Path | None = None,
    check_open_safety: bool = True,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Inventory existing .hwpx under *roots* — referenced in place, NEVER copied
    (the box filelist ships them at P2 time). Returns (records, excluded_paths);
    files that fail the zip container check are EXCLUDED defensively."""
    base = (base_root or HWPX_ROOT).resolve()
    records: list[dict[str, Any]] = []
    excluded: list[str] = []
    for label, root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.hwpx")):
            try:
                is_zip = zipfile.is_zipfile(path)
            except OSError:
                is_zip = False
            if not is_zip:
                excluded.append(str(path))
                continue
            try:
                rel = path.resolve().relative_to(base)
                provenance = rel.parent.as_posix()
                rel_str = rel.as_posix()
            except ValueError:
                provenance = f"{label}:{path.parent.name}"
                rel_str = path.name
            try:
                rel_under_root = path.resolve().relative_to(root.resolve())
                milestone = (
                    rel_under_root.parts[0] if len(rel_under_root.parts) > 1 else label
                )
            except ValueError:
                milestone = label
            slug = re.sub(r"[^A-Za-z0-9가-힣._-]+", "-", rel_str[:-len(".hwpx")])
            records.append({
                "id": f"shipped-{slug}",
                "bucket": "shipped-artifacts",
                "stratum": "shipped-artifacts",
                "seed": f"shipped:{rel_str}",
                "requested": True,
                "produced": True,
                "output_path": str(path),
                "output_sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
                "input_path": None,
                "input_sha256": None,
                "withheld_reason": None,
                "static_open_safety_ok": (
                    static_open_safety_ok(path) if check_open_safety else None
                ),
                "provenance": provenance,
                "provenance_root": label,
                "milestone": milestone,
                "hostile_input": False,
            })
    return records, excluded


def plan_shipped_artifacts(roots: Sequence[tuple[str, Path]]) -> tuple[int, int]:
    """(includable, excluded) counts — the cheap dry-run variant (zip check only)."""
    included = 0
    excluded = 0
    for _label, root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.hwpx")):
            try:
                ok = zipfile.is_zipfile(path)
            except OSError:
                ok = False
            if ok:
                included += 1
            else:
                excluded += 1
    return included, excluded


# --------------------------------------------------------------------------------
# v2 planning + main
# --------------------------------------------------------------------------------
def plan_v2_counts(v1_manifest: dict[str, Any]) -> dict[str, Any]:
    """Planned per-stratum counts (no writes) — the --dry-run payload."""
    inputs = [(tag, p) for tag, p in form_fit_inputs() if p.exists()]
    ff = plan_form_fit_wide(inputs, v1_formfit_combos(v1_manifest))
    sources = v1_authored_sources(v1_manifest)
    rl = plan_redline_wide([s for s, _ in sources], v1_redline_covered(v1_manifest))
    shipped_n, shipped_excluded = plan_shipped_artifacts(SHIPPED_ROOTS)
    counts = {
        "form-fit-wide": len(ff),
        "redline-wide": len(rl),
        "pii-merge": PII_MERGE_N,
        "authored-toc": AUTHORED_TOC_N,
        "reading-runformat": READING_RUNFORMAT_N,
        "shipped-artifacts": shipped_n,
    }
    v1_produced = int(v1_manifest.get("produced_total") or 0)
    v2_total = sum(counts.values())
    return {
        "counts": counts,
        "shipped_excluded_non_zip": shipped_excluded,
        "v2_planned_total": v2_total,
        "v1_produced_total": v1_produced,
        "combined_planned_total": v1_produced + v2_total,
    }


def main_v2(*, dry_run: bool) -> int:
    v1_manifest_path = OUT_DIR / "manifest.json"
    if not v1_manifest_path.exists():
        print(f"ERROR: frozen v1 manifest not found: {v1_manifest_path}", file=sys.stderr)
        return 2
    v1_manifest = json.loads(v1_manifest_path.read_text(encoding="utf-8"))
    v1_manifest_sha = sha256_file(v1_manifest_path)

    if dry_run:
        plan = plan_v2_counts(v1_manifest)
        print("=== V2 DRY RUN (planned, nothing written) ===")
        for stratum in sorted(plan["counts"]):
            print(f"  {stratum:18s} {plan['counts'][stratum]:4d}")
        print(f"  {'V2 TOTAL':18s} {plan['v2_planned_total']:4d}"
              f"  (shipped excluded non-zip: {plan['shipped_excluded_non_zip']})")
        print(f"  {'COMBINED':18s} {plan['combined_planned_total']:4d}"
              f"  (= v1 {plan['v1_produced_total']} by reference + v2 planned)")
        return 0

    OUT_DIR_V2.mkdir(parents=True, exist_ok=True)
    SPEC_EVIDENCE_V2.mkdir(parents=True, exist_ok=True)

    all_records: list[dict[str, Any]] = []
    ff_recs, _ = gen_form_fit_wide(OUT_DIR_V2, v1_manifest)
    all_records += ff_recs
    rl_recs, _ = gen_redline_wide(OUT_DIR_V2, v1_manifest)
    all_records += rl_recs
    pii_recs, _ = gen_pii_merge(OUT_DIR_V2)
    all_records += pii_recs
    toc_recs, _ = gen_authored_toc(OUT_DIR_V2)
    all_records += toc_recs
    rf_recs, _ = gen_reading_runformat(OUT_DIR_V2)
    all_records += rf_recs
    shipped_recs, shipped_excluded = inventory_shipped_artifacts(SHIPPED_ROOTS)
    all_records += shipped_recs

    all_records.sort(key=lambda r: (r["bucket"], r["id"]))

    counts_per_stratum: dict[str, Any] = {}
    requested_total = 0
    produced_total = 0
    for rec in all_records:
        b = rec["bucket"]
        slot = counts_per_stratum.setdefault(
            b, {"requested": 0, "produced": 0, "withheld_ids": [], "emit_rate": None}
        )
        slot["requested"] += 1
        requested_total += 1
        if rec["produced"]:
            slot["produced"] += 1
            produced_total += 1
        else:
            slot["withheld_ids"].append(rec["id"])
    for slot in counts_per_stratum.values():
        slot["emit_rate"] = (
            round(slot["produced"] / slot["requested"], 4) if slot["requested"] else None
        )

    v1_produced = int(v1_manifest.get("produced_total") or 0)
    v2_manifest = {
        "schemaVersion": V2_SCHEMA,
        "generatedAt": None,  # root stamps it — DO NOT call datetime.now
        "spec": "specs/010-corpus-publication/spec.md (P1, FR-002)",
        "note": (
            "ADDITIVE corpus v2. v1 (N=100) stays FROZEN and is referenced below "
            "by relative path + sha256 — its files are never regenerated or "
            "copied. shipped-artifacts records reference real M2-M7 outputs in "
            "place (demo/, hwpx-skill/examples/out/); the box filelist ships "
            "them at P2 time. static_open_safety_ok is a structural pre-filter "
            "(necessary-not-sufficient); the real judge is Hancom COM Open() on "
            "Windows. hostile_input is a tagging hook — hwpxlib-derived inputs "
            "(future) set it true so input-attributed failures separate."
        ),
        "v1_reference": {
            "manifest_path": "../openrate-corpus/manifest.json",  # relative to this dir
            "manifest_sha256": v1_manifest_sha,
            "schemaVersion": v1_manifest.get("schemaVersion"),
            "requested_total": v1_manifest.get("requested_total"),
            "produced_total": v1_produced,
        },
        "determinism": {
            "ids_stable": True,
            "membership_stable": True,
            "bytes_bit_stable": False,
            "caveat": (
                "Record IDs, seeds, and stratum membership are fully deterministic "
                "across runs (all values derive from indices; tracked-change "
                "timestamps are fixed constants). Output bytes are NOT bit-stable "
                "for builder strata (redline-wide/pii-merge/authored-toc/reading-"
                "runformat): python-hwpx assigns random hp:p paragraph ids at "
                "save time. form-fit-wide IS bit-stable (source-package patch, no "
                "rebuild); shipped-artifacts is a read-only inventory of frozen "
                "bytes. The manifest is regenerated together with the files, so "
                "output_sha256 always matches the on-disk corpus per run."
            ),
        },
        "shipped_excluded_non_zip": shipped_excluded,
        "counts_per_stratum": counts_per_stratum,
        "requested_total": requested_total,
        "produced_total": produced_total,
        "combined_produced_total": v1_produced + produced_total,
        "tool_versions": {
            "python-hwpx": _pyproject_version(PYTHON_HWPX / "pyproject.toml"),
            "hwpx-mcp-server": _pyproject_version(MCP_SERVER / "pyproject.toml"),
        },
        "records": all_records,
    }

    manifest_path = OUT_DIR_V2 / "manifest.json"
    manifest_path.write_text(
        json.dumps(v2_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    spec_copy = SPEC_EVIDENCE_V2 / "p1-frozen-manifest-v2.json"
    spec_copy.write_text(
        json.dumps(v2_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    combined = merge_manifests(
        v1_manifest, v2_manifest,
        v1_root=OUT_DIR, v2_root=OUT_DIR_V2, shipped_root=HWPX_ROOT,
    )
    combined_path = OUT_DIR_V2 / "combined_manifest.json"
    combined_path.write_text(
        json.dumps(combined, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print("\n=== V2 SUMMARY ===")
    for b in sorted(counts_per_stratum):
        s = counts_per_stratum[b]
        print(f"  {b:18s} requested={s['requested']:3d} produced={s['produced']:3d} "
              f"emit_rate={s['emit_rate']}  withheld={len(s['withheld_ids'])}")
    print(f"  {'V2 TOTAL':18s} requested={requested_total:3d} produced={produced_total:3d}")
    print(f"  {'COMBINED':18s} produced={v1_produced + produced_total:3d} "
          f"(= v1 {v1_produced} by reference + v2 {produced_total})")
    if shipped_excluded:
        print(f"  shipped excluded (non-zip): {len(shipped_excluded)}")
    print(f"\nv2 manifest:       {manifest_path}")
    print(f"spec copy:         {spec_copy}")
    print(f"combined manifest: {combined_path}")
    return 0


# ================================================================================
# tool versions (read from pyproject)
# ================================================================================
def _pyproject_version(pyproject: Path) -> str | None:
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
    return m.group(1) if m else None


# ================================================================================
# main
# ================================================================================
def main_v1(*, force: bool = False, dry_run: bool = False) -> int:
    v1_manifest_path = OUT_DIR / "manifest.json"
    if dry_run:
        print("=== V1 DRY RUN (planned, nothing written) ===")
        for bucket, n in (("authored", 40), ("mail-merge", 30), ("form-fit", 20),
                          ("exam", 5), ("redline", 5)):
            print(f"  {bucket:11s} {n:4d}")
        print(f"  {'TOTAL':11s} {100:4d}")
        return 0
    if v1_manifest_path.exists() and not force:
        print(
            "REFUSING to regenerate the v1 corpus: it is the FROZEN published "
            f"baseline ({v1_manifest_path} exists) and builder buckets are not "
            "bit-stable — a rerun would invalidate the sha256 freeze. Corpus "
            "extension is ADDITIVE via --v2. Pass --force-v1 only if you really "
            "mean to re-freeze v1.",
            file=sys.stderr,
        )
        return 2
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SPEC_EVIDENCE.mkdir(parents=True, exist_ok=True)

    all_records: list[dict[str, Any]] = []

    auth_recs, auth_paths = gen_authored(OUT_DIR)
    all_records += auth_recs

    mm_recs, _mm_paths = gen_mail_merge(OUT_DIR)
    all_records += mm_recs

    ff_recs, _ff_paths = gen_form_fit(OUT_DIR, target_n=20)
    all_records += ff_recs

    exam_recs, _exam_paths = gen_exam(OUT_DIR)
    all_records += exam_recs

    rl_recs, _rl_paths = gen_redline(OUT_DIR, auth_paths)
    all_records += rl_recs

    all_records.sort(key=lambda r: (r["bucket"], r["id"]))

    # per-bucket requested/produced + emit_rate
    counts_per_bucket: dict[str, Any] = {}
    requested_total = 0
    produced_total = 0
    for rec in all_records:
        b = rec["bucket"]
        slot = counts_per_bucket.setdefault(
            b, {"requested": 0, "produced": 0, "withheld_ids": [], "emit_rate": None}
        )
        slot["requested"] += 1
        requested_total += 1
        if rec["produced"]:
            slot["produced"] += 1
            produced_total += 1
        else:
            slot["withheld_ids"].append(rec["id"])
    for b, slot in counts_per_bucket.items():
        slot["emit_rate"] = (
            round(slot["produced"] / slot["requested"], 4) if slot["requested"] else None
        )

    summary = {
        "schemaVersion": "hwpx.openrate.frozen-manifest.v1",
        "generatedAt": None,  # root stamps it — DO NOT call datetime.now
        "spec": "specs/007-open-rate/spec.md (P2)",
        "note": (
            "GENERATED .hwpx outputs only. NOT a Hancom verdict. "
            "static_open_safety_ok is a structural pre-filter (necessary-not-"
            "sufficient); the real judge is Hancom COM Open() on Windows (P3). "
            "withheld items = end-to-end FAILURES (composer open-safety gate), "
            "not absent rows."
        ),
        "determinism": {
            "ids_stable": True,
            "membership_stable": True,
            "bytes_bit_stable": False,
            "caveat": (
                "Record IDs, seeds, and bucket membership are fully deterministic "
                "across runs. Output bytes are NOT bit-stable for builder buckets "
                "(authored/mail-merge/exam/redline): python-hwpx assigns random "
                "hp:p paragraph element ids at save time, so section XML differs "
                "run-to-run (content identical). form-fit IS bit-stable (it patches "
                "the source package without a rebuild). The manifest is regenerated "
                "together with the files, so its output_sha256 values always match "
                "the current on-disk corpus — the freeze is self-consistent per run."
            ),
        },
        "counts_per_bucket": counts_per_bucket,
        "requested_total": requested_total,
        "produced_total": produced_total,
        "emit_rate": round(produced_total / requested_total, 4) if requested_total else None,
        "tool_versions": {
            "python-hwpx": _pyproject_version(PYTHON_HWPX / "pyproject.toml"),
            "hwpx-mcp-server": _pyproject_version(MCP_SERVER / "pyproject.toml"),
        },
        "records": all_records,
    }

    manifest_path = OUT_DIR / "manifest.json"
    manifest_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    spec_copy = SPEC_EVIDENCE / "p2-frozen-manifest.json"
    spec_copy.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print("\n=== SUMMARY ===")
    for b in sorted(counts_per_bucket):
        s = counts_per_bucket[b]
        print(f"  {b:11s} requested={s['requested']:3d} produced={s['produced']:3d} "
              f"emit_rate={s['emit_rate']}  withheld={len(s['withheld_ids'])}")
    print(f"  {'TOTAL':11s} requested={requested_total:3d} produced={produced_total:3d} "
          f"emit_rate={summary['emit_rate']}")
    print(f"\nmanifest: {manifest_path}")
    print(f"spec copy: {spec_copy}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="generate_openrate_corpus", description=__doc__)
    ap.add_argument("--v2", action="store_true",
                    help="generate the ADDITIVE corpus v2 into work/openrate-corpus-v2/ "
                         "(v1 stays frozen, referenced by path+sha256)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print planned per-stratum counts; write nothing")
    ap.add_argument("--force-v1", action="store_true",
                    help="override the v1 freeze guard and regenerate v1 (DANGEROUS: "
                         "invalidates the published sha256 freeze)")
    args = ap.parse_args(argv)
    if args.v2:
        return main_v2(dry_run=args.dry_run)
    return main_v1(force=args.force_v1, dry_run=args.dry_run)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # surface a full trace for debugging
        traceback.print_exc()
        sys.exit(1)
