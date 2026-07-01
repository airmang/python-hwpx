# SPDX-License-Identifier: Apache-2.0
"""007-open-rate P2 — generate a FROZEN, stratified N=100 population of GENERATED
.hwpx outputs + a provenance manifest, for a later real-Hancom open-rate run.

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

Run from the mcp-server env (installed surface + editable python-hwpx):

    cd hwpx-mcp-server
    uv run --with-editable ../python-hwpx python \\
        ../python-hwpx/scripts/generate_openrate_corpus.py
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import traceback
from pathlib import Path
from typing import Any

# --- repo geometry --------------------------------------------------------------
PYTHON_HWPX = Path(__file__).resolve().parent.parent          # .../python-hwpx
HWPX_ROOT = PYTHON_HWPX.parent                                 # .../hwpx
MCP_SERVER = HWPX_ROOT / "hwpx-mcp-server"
OUT_DIR = PYTHON_HWPX / "work" / "openrate-corpus"
SPEC_EVIDENCE = HWPX_ROOT / "specs" / "007-open-rate" / "evidence"

M2_CORPUS = PYTHON_HWPX / "tests" / "fixtures" / "m2_corpus"
EXAM_FIXTURES = PYTHON_HWPX / "tests" / "fixtures" / "exam"
PUBLIC_CORPUS = PYTHON_HWPX / "work" / "public-document-corpus"

# --- imports (installed MCP surface + editable python-hwpx) ----------------------
from hwpx_mcp_server import server  # noqa: E402
from hwpx.document import HwpxDocument  # noqa: E402
from hwpx.exam.compose import compose_exam_into_form  # noqa: E402
from hwpx.form_fit import FitPolicy  # noqa: E402
from hwpx.form_fit.apply import fit_cell_text  # noqa: E402
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
def main() -> int:
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


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # surface a full trace for debugging
        traceback.print_exc()
        sys.exit(1)
