# SPDX-License-Identifier: Apache-2.0
"""openrate corpus v14 -- 검증 부채 소탕: 편집기 표면 인벤토리(트레인㉙)의
"미실측" 저작 API 8개 + 6.9/6.10의 두 신규 저작 표면 각각의 미실측 각을
채우는 정리 트레인, additive over v13.

Why v14 exists
===============

``docs/editor-surface-inventory.md``의 실측 상태 컬럼이 "미실측"으로 남긴
저작 api 항목 중 8개(목록 서식·찾아바꾸기·표 구조 변경·표 탐색 기반 채움·
그림 삽입/치환·차트·변경추적·편집 계획 실행)와, 코드는 있지만 커버리지
렛저에 요소로 등록 안 된 ``ensure_run``의 나머지 9개 매개변수(v7의
``authored-charformat``이 놓친 부분 — underline/strike/ratio/spacing/
shadow), 그리고 이번 사이클 트레인 38(문서 병합 v2: 정책 4축 + MEMO
지원)의 산출물을 하나로 묶는다. 스트라텀 이름은 v13이 세운
``authored-<영역>`` 관례를 따른다(v3/v4의 옛 ``edit-plan``/
``authored-chart``와는 별도 버킷 — coverage_ledger의 강접(fold) 로직이
같은 이름의 스트라텀을 여러 report-vN.json에 걸쳐 OR로 누적하므로,
``authored-chart``는 v4와 이름이 같아도 그 자체로 안전하다: 참조
증거를 늘릴 뿐 덮어쓰지 않는다. ``authored-editplan``은 v3/v4의
``edit-plan``과 이름이 달라 별개 버킷으로 집계된다).

10 스트라타(결정적 — 고정 시드, 뱅크 로테이션, wall clock 없음), 각 5건
============================================================================

* ``authored-charformat2``    5  ``doc.styles.ensure_run``의 outline/
                                  emboss/engrave/supscript/subscript
                                  (v7의 ``authored-charformat``이 이미
                                  다룸) 이외 9개 매개변수 —
                                  underline/underline_shape/
                                  underline_color/strike/strike_shape/
                                  ratio/letter_spacing/shadow/
                                  base_char_pr_id.
* ``authored-listformat``     5  ``doc.styles.apply_list_format`` —
                                  글머리표/번호매기기, level 1·2 로테이션,
                                  bullet_char/number_format/start 오버라이드.
* ``authored-tablestructure`` 5  ``hwpx.table_patch.apply_table_ops`` —
                                  delete_column/delete_row/
                                  insert_row_by_clone/set_column_widths/
                                  autofit_columns, 한 레코드당 한 op.
* ``authored-tablenavfill``   5  ``doc.tables.fill_by_path`` — 라벨
                                  매칭 네비게이션(right/down 단일 홉 +
                                  multi-hop 1건).
* ``authored-findreplace``    5  ``doc.text.replace`` — 무제한 치환과
                                  char_pr_id_ref로 좁힌 스타일 한정
                                  치환을 번갈아.
* ``authored-redline``        5  ``doc.tracking.insert``/``.delete``/
                                  ``.replace`` 로테이션.
* ``authored-chart``          5  ``doc.shapes.add_chart`` — pie/bar/line
                                  로테이션, 자체 최소 ChartML 빌더(아래
                                  "정직 고지" 참조 — python-hwpx-automation
                                  의 ``build_chart_ml``은 core 저장소에서
                                  임포트 불가라 재발명이 아니라 필수).
* ``authored-picture``        5  ``doc.add_picture`` 크기 변주(4건) +
                                  ``doc.media.replace_picture``(1건).
* ``authored-editplan``       5  ``hwpx.plan.apply_edit_plan`` —
                                  paragraph_patch/fill_cells/
                                  apply_table_ops(중첩)/
                                  recolor_runs_by_color/
                                  strip_runs_by_color, 한 레코드당 한 op
                                  강조(v3/v4의 ``edit-plan``이 이미
                                  다룬 paragraph_patch+fill_cells 조합
                                  이외의 3개 op가 이번 신규 실증분).
* ``authored-docmerge2``      5  트레인 38(문서 병합 v2)의 산출물 —
                                  MEMO 병합(단일/센티널 기본값/대상
                                  기존 memogroup 합류/표 동반)과, 4축
                                  기본값 매개변수를 명시로 통과시킨
                                  호출(수용 증명, 다른 값은 typed 오류라
                                  애초에 이 생성기가 만들 "정상 산출물"이
                                  없음 — 별도 스트라텀 대상이 아님).

정직 고지(honest limitations)
==============================

- **차트**: ``python-hwpx-automation``의 ``hwpx_automation.office.
  charting.build_chart_ml``이 만드는 것보다 훨씬 소박한, 손으로 쓴 최소
  ChartML(``_build_chart_ml``, 이 스크립트 자체 함수)을 쓴다 — core
  저장소는 automation 저장소에 의존하면 안 되므로(단방향 아키텍처,
  MCP/automation→core만 허용) v4의 ``gen_chart``를 그대로 재사용할 수
  없었다. ``doc.shapes.add_chart``의 파이썬 쪽 검증은 정상-XML +
  루트태그 일치만 확인하므로 이 최소 ChartML도 만들기(생성)는
  통과하지만, 렌더된 시각 품질(막대/선 차트의 축·범례 완성도)은 v4의
  15건보다 낮을 수 있다 — 실한컴 판정 시 참고.
- **메모 상자 렌더 형태**: ``authored-docmerge2``가 만드는 MEMO는 정적
  PDF만으로 "접힘/펼침" 표시 상태를 판단하기 애매할 수 있다(한컴
  뷰어의 상호작용 상태이지 문서 자체의 고정 속성이 아님) — 열림/파싱
  가능 여부만 이 스트라텀의 판정 기준으로 삼고, 접힘 표시 자체는
  별도 판단 대상으로 보지 않는다.
- **``authored-tablenavfill``/``authored-findreplace``/
  ``authored-editplan``은 capabilityArea가 없다(coverage_ledger.py의
  기존 주석 — 새 요소를 안 만들고 기존 요소를 변형만 하므로 태깅 대상이
  없음). 이 스트라텀들의 근거는 report JSON 원문 + support-matrix.md
  산문 인용으로만 남는다 — 코드에 새 라우팅 엔트리를 만들지 않는다.

Generation ONLY -- no Hancom oracle here. Every produced file gets the
static ``validate_editor_open_safety`` pre-filter (necessary, not
sufficient); the real verdict comes from the macOS GUI oracle (root's Mac).
``render_jobs_v14.json`` lists a PDF export job per produced file, same
shape as v4-v13.

Field names are the render pipeline's contract (see v4-v13's own comments)
-- a bare array of ``{sourceId,stratum,src,pdf}``, not wrapped in a
``{"jobs": [...]}`` object.

``toolVersions["python-hwpx"]`` is read from ``pyproject.toml`` directly,
not ``importlib.metadata`` -- same staleness rationale v4-v13 already
established.

    cd python-hwpx
    .venv-core/bin/python scripts/generate_openrate_corpus_v14.py
"""
from __future__ import annotations

import base64
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
from generate_openrate_corpus_v13 import OUT_DIR_V13  # noqa: E402

from hwpx.document import HwpxDocument  # noqa: E402
from hwpx.plan import apply_edit_plan  # noqa: E402
from hwpx.table_patch import apply_table_ops  # noqa: E402
from hwpx.tools.document_merge import append_document, insert_document  # noqa: E402

# Same discipline v4-v13 established: a moved/deprecated 5.x name firing its
# shim is a genuine 6.x-migration defect, not something to route around
# silently. Importing generate_openrate_corpus_v4 above already installs
# this filter (its own module-level statement) -- restated here so this
# module's contract is legible without reading v4's source.
import warnings  # noqa: E402

warnings.simplefilter("error", DeprecationWarning)

OUT_DIR_V14 = PYTHON_HWPX / "work" / "openrate-corpus-v14"
MANIFEST_SCHEMA = "hwpx.openrate.frozen-manifest.v14"
BOX_ROOT = "C:\\openrate\\v14"
BOX_ROOT_PDF = "C:\\openrate\\v14-pdf"

# A minimal valid 1x1 PNG (same fixture bytes as tests/test_document_merge.py).
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/axwAqkAAAAASUVORK5CYII="
)

#: Fixed-timestamp bank, "%Y-%m-%d %H:%M:%S" (the exact format
#: doc.tracking.*/doc.notes.add_memo's own date/created formatting uses,
#: see src/hwpx/_document/memos.py:108). Found live (not assumed in
#: advance) via this generator's own cross-run determinism check: both
#: doc.tracking.insert/delete/replace's date= and doc.notes.add_memo's
#: created= silently default to datetime.now() when omitted -- a
#: wall-clock leak this whole generator family's own discipline (no wall
#: clock) forbids. Every call site below passes one of these explicitly.
_TIMESTAMP_BANK: tuple[str, ...] = (
    "2026-08-08 09:00:00", "2026-08-08 09:05:00", "2026-08-08 09:10:00",
    "2026-08-08 09:15:00", "2026-08-08 09:20:00",
)


def _last_paragraph_index(document: HwpxDocument, section_index: int = 0) -> int:
    """Robust "index of the paragraph I just added" -- avoids hardcoding an
    assumed base-document paragraph count (a real trap: v4's own
    ``gen_edit_plan`` hardcodes ``paragraphIndex: 3``, which only happens to
    be right for a document shape that no longer matches
    ``HwpxDocument.new()``'s current default-empty-paragraph behavior)."""

    return len(document.sections[section_index].paragraphs) - 1


# ================================================================================
# stratum 1 -- authored-charformat2 (ensure_run's other 9 params)
# ================================================================================
#: One combo per record, rotating through all 9 params v7's
#: authored-charformat stratum does NOT cover (that one only exercises
#: outline/emboss/engrave/supscript/subscript). base_char_pr_id (idx 4) is
#: handled specially in the generator body, not via this bank, since it
#: needs a live id minted earlier in the SAME document.
_CHARFORMAT2_BANK: tuple[dict[str, Any], ...] = (
    {"underline": True, "underline_shape": "WAVE", "underline_color": "#C00000"},
    {"strike": True, "strike_shape": "DOUBLE_SLIM"},
    {"ratio": 130, "letter_spacing": -15},
    {"shadow": "#808080"},
    {"underline": True, "strike": True, "ratio": 90},
)


def gen_charformat2(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(5):
        rec_id = f"v14-charformat2-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            document = _base_document(idx, "글자 모양 확장 표본")
            kwargs = dict(_CHARFORMAT2_BANK[idx])
            if idx == 4:
                base_id = document.styles.ensure_run(font="맑은 고딕", bold=True)
                kwargs["base_char_pr_id"] = base_id
            cid = document.styles.ensure_run(**kwargs)
            document.add_paragraph(f"{cycle(DEPT_BANK, idx)} 확장 서식 표본 {idx}", char_pr_id_ref=cid)

            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-charformat2", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001 - withheld is the honest record
            records.append(record(
                rec_id=rec_id, bucket="authored-charformat2", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


# ================================================================================
# stratum 2 -- authored-listformat
# ================================================================================
_LISTFORMAT_BANK: tuple[dict[str, Any], ...] = (
    {"kind": "bullet", "level": 1, "bullet_char": "●"},
    {"kind": "number", "level": 1, "number_format": "DIGIT", "start": 3},
    {"kind": "bullet", "level": 2, "bullet_char": "▶"},
    {"kind": "number", "level": 2, "number_format": "HANGUL_SYLLABLE", "start": 1},
    {"kind": "bullet", "level": 1, "bullet_char": "◆"},
)


def gen_listformat(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(5):
        rec_id = f"v14-listformat-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            document = _base_document(idx, "목록 서식 표본")
            document.add_paragraph(f"{cycle(DEPT_BANK, idx)} 목록 항목 {idx}")
            target_index = _last_paragraph_index(document)

            kwargs = dict(_LISTFORMAT_BANK[idx])
            result = document.styles.apply_list_format(paragraph_index=target_index, **kwargs)
            if result.formatted != 1:
                raise RuntimeError(f"apply_list_format formatted {result.formatted}, expected 1")

            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-listformat", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001 - withheld is the honest record
            records.append(record(
                rec_id=rec_id, bucket="authored-listformat", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


# ================================================================================
# stratum 3 -- authored-tablestructure
# ================================================================================
#: One struct op per record -- apply_table_ops's own docstring groups these
#: as "structure ops" (grid-validated, fail-closed on an invalid result).
_TABLESTRUCTURE_OPS_BANK: tuple[dict[str, Any], ...] = (
    {"op": "delete_column", "col": 1},
    {"op": "delete_row", "row": 1},
    {"op": "insert_row_by_clone", "ref_row": 0, "count": 1},
    {"op": "set_column_widths", "widths": {0: 8000, 1: 12000, 2: 10000}},
    {"op": "autofit_columns"},
)


def gen_tablestructure(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(5):
        rec_id = f"v14-tablestructure-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            document = _base_document(idx, "표 구조 변경 표본")
            table = document.add_table(rows=3, cols=3, width=42000)
            for row in range(3):
                for col in range(3):
                    table.cell(row, col).text = cycle(DEPT_BANK, idx + row + col)
            data = document.to_bytes()

            op = dict(_TABLESTRUCTURE_OPS_BANK[idx])
            op["table_index"] = 0
            result = apply_table_ops(data, [op], output_path=out_path)
            if not result.ok:
                raise RuntimeError(f"apply_table_ops not ok: skipped={result.skipped}")

            records.append(record(
                rec_id=rec_id, bucket="authored-tablestructure", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001 - withheld is the honest record
            records.append(record(
                rec_id=rec_id, bucket="authored-tablestructure", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


# ================================================================================
# stratum 4 -- authored-tablenavfill (label-matching navigation)
# ================================================================================


def gen_tablenavfill(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(5):
        rec_id = f"v14-tablenavfill-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            document = _base_document(idx, "표 탐색 기반 채움 표본")
            if idx < 4:
                # single-hop right/down alternating.
                table = document.add_table(rows=2, cols=2)
                label = f"항목{idx}"
                table.cell(0, 0).text = label
                direction = "right" if idx % 2 == 0 else "down"
                path = f"{label} > {direction}"
                fill_value = f"{cycle(DEPT_BANK, idx)} 채움값"
            else:
                # multi-hop -- mirrors the confirmed-working shape from
                # tests/test_table_navigation.py::
                # test_fill_by_path_supports_multi_step_navigation.
                table = document.add_table(rows=3, cols=2)
                table.cell(0, 0).text = "합계"
                path = "합계 > down > right"
                fill_value = "100"

            result = document.tables.fill_by_path({path: fill_value})
            if result["failed_count"] or result["applied_count"] != 1:
                raise RuntimeError(f"fill_by_path did not apply cleanly: {result}")

            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-tablenavfill", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001 - withheld is the honest record
            records.append(record(
                rec_id=rec_id, bucket="authored-tablenavfill", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


# ================================================================================
# stratum 5 -- authored-findreplace
# ================================================================================


def gen_findreplace(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(5):
        rec_id = f"v14-findreplace-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            document = _base_document(idx, "찾아바꾸기 표본")
            term = cycle(DEPT_BANK, idx)
            if idx % 2 == 0:
                # unscoped -- matches any run.
                document.add_paragraph(f"{term} 원본 표현입니다.")
                count = document.text.replace(term, f"교체된 {cycle(DEPT_BANK, idx + 1)}")
            else:
                # style-scoped -- only runs carrying this exact charPr match.
                cid = document.styles.ensure_run(bold=True, color="#1F4E79")
                document.add_paragraph(f"{term} 스타일 한정 표현입니다.", char_pr_id_ref=cid)
                document.add_paragraph(f"{term} 스타일 밖 표현입니다.")
                count = document.text.replace(term, f"한정치환 {idx}", char_pr_id_ref=cid)
            if count < 1:
                raise RuntimeError(f"replace matched 0 occurrences (count={count})")

            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-findreplace", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001 - withheld is the honest record
            records.append(record(
                rec_id=rec_id, bucket="authored-findreplace", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


# ================================================================================
# stratum 6 -- authored-redline (change tracking)
# ================================================================================
_REDLINE_MODE_BANK: tuple[str, ...] = ("insert", "delete", "replace", "insert", "delete")


def gen_redline(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(5):
        rec_id = f"v14-redline-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            document = _base_document(idx, "변경추적 표본")
            term = cycle(DEPT_BANK, idx)
            document.add_paragraph(f"{term} 원본 문단입니다.")
            target_index = _last_paragraph_index(document)

            mode = _REDLINE_MODE_BANK[idx]
            date = _TIMESTAMP_BANK[idx]
            if mode == "insert":
                document.tracking.insert(target_index, f" 삽입된 표현 {idx}", date=date)
            elif mode == "delete":
                document.tracking.delete(target_index, match=term, date=date)
            else:
                document.tracking.replace(target_index, term, f"수정된 부서 {idx}", date=date)

            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-redline", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001 - withheld is the honest record
            records.append(record(
                rec_id=rec_id, bucket="authored-redline", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


# ================================================================================
# stratum 7 -- authored-chart
# ================================================================================
#: Hand-built minimal ChartML -- see this module's "정직 고지" docstring
#: section for why (core cannot import python-hwpx-automation's fuller
#: build_chart_ml). Structurally mirrors tests/test_chart_authoring.py's
#: own confirmed-working PIE_CHARTML shape (CHART_HEAD/plotArea/chart/
#: chartSpace nesting), generalized across pie/bar/line.
_CHART_XML_HEAD = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>'
    '<c:chartSpace xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart">'
    "<c:chart><c:plotArea><c:layout/>"
)
_CHART_XML_TAIL = "</c:plotArea></c:chart></c:chartSpace>"
_CHART_TYPE_BANK: tuple[str, ...] = ("pie", "bar", "line", "pie", "bar")


def _build_chart_ml(chart_type: str, categories: list[str], values: list[float], title: str) -> str:
    cat_pts = "".join(f'<c:pt idx="{i}"><c:v>{cat}</c:v></c:pt>' for i, cat in enumerate(categories))
    val_pts = "".join(f'<c:pt idx="{i}"><c:v>{v}</c:v></c:pt>' for i, v in enumerate(values))
    series = (
        '<c:ser><c:idx val="0"/><c:order val="0"/>'
        f"<c:tx><c:strRef><c:f>Sheet1!$B$1</c:f><c:strCache>"
        f'<c:pt idx="0"><c:v>{title}</c:v></c:pt></c:strCache></c:strRef></c:tx>'
        f"<c:cat><c:strRef><c:f>Sheet1!$A$2:$A${1 + len(categories)}</c:f>"
        f'<c:strCache><c:ptCount val="{len(categories)}"/>{cat_pts}</c:strCache></c:strRef></c:cat>'
        f"<c:val><c:numRef><c:f>Sheet1!$B$2:$B${1 + len(values)}</c:f>"
        f'<c:numCache><c:formatCode>General</c:formatCode>'
        f'<c:ptCount val="{len(values)}"/>{val_pts}</c:numCache></c:numRef></c:val>'
        "</c:ser>"
    )
    if chart_type == "pie":
        body = f'<c:pieChart><c:varyColors val="1"/>{series}</c:pieChart>'
    elif chart_type == "line":
        body = f'<c:lineChart><c:grouping val="standard"/>{series}</c:lineChart>'
    else:  # bar
        body = f'<c:barChart><c:barDir val="col"/><c:grouping val="clustered"/>{series}</c:barChart>'
    return _CHART_XML_HEAD + body + _CHART_XML_TAIL


def gen_chart(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(5):
        rec_id = f"v14-chart-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        chart_type = _CHART_TYPE_BANK[idx]
        try:
            categories = [cycle(DEPT_BANK, idx + offset) for offset in range(3)]
            values = [float(10 + idx), float(20 + idx % 7), float(15 + idx % 5)]
            chart_xml = _build_chart_ml(
                chart_type, categories, values,
                title=f"{cycle(ORG_BANK, idx)} {chart_type} 표본 {idx}",
            )
            document = _base_document(idx, "차트 표본")
            document.shapes.add_chart(chart_xml, size=(60000, 40000))

            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-chart", seed=f"{chart_type}:{idx}",
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001 - withheld is the honest record
            records.append(record(
                rec_id=rec_id, bucket="authored-chart", seed=f"{chart_type}:{idx}",
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


# ================================================================================
# stratum 8 -- authored-picture (insert + replace)
# ================================================================================
_PICTURE_SIZE_BANK: tuple[tuple[float, float], ...] = ((20.0, 15.0), (30.0, 20.0), (15.0, 15.0), (25.0, 18.0))


def gen_picture(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(5):
        rec_id = f"v14-picture-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        try:
            document = _base_document(idx, "그림 삽입/치환 표본")
            if idx < 4:
                width_mm, height_mm = _PICTURE_SIZE_BANK[idx]
                document.add_picture(PNG_1X1, "png", width_mm=width_mm, height_mm=height_mm)
            else:
                document.add_picture(PNG_1X1, "png")
                # "치환" half -- swap the asset while preserving geometry
                # (media.replace_picture's own documented contract). Reuses
                # the same fixture bytes for the replacement -- this
                # exercises the structural swap path, not a visual
                # asset-content difference (no second distinct PNG fixture
                # in this generator family; not worth inventing one for a
                # structural-only exercise).
                replacement = document.media.replace_picture(PNG_1X1, "png", picture_index=0)
                if replacement.item_id == replacement.previous_item_id:
                    raise RuntimeError("replace_picture did not mint a new binary item id")

            document.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-picture", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001 - withheld is the honest record
            records.append(record(
                rec_id=rec_id, bucket="authored-picture", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


# ================================================================================
# stratum 9 -- authored-editplan (hwpx.plan)
# ================================================================================
#: One PLAN_OPS op emphasized per record -- v3/v4's own "edit-plan" bucket
#: (a DIFFERENT, older-named stratum) already exercised paragraph_patch +
#: fill_cells chained together; this stratum's job is the 3 ops that
#: bucket never touched (apply_table_ops nested inside a plan,
#: recolor_runs_by_color, strip_runs_by_color) plus one fresh
#: paragraph_patch/fill_cells example each, all under the newer
#: "authored-" naming convention.
_EDITPLAN_OP_BANK: tuple[str, ...] = (
    "paragraph_patch", "fill_cells", "apply_table_ops", "recolor_runs_by_color", "strip_runs_by_color",
)


def gen_editplan(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    base_dir = bucket_dir / "_bases"
    base_dir.mkdir(parents=True, exist_ok=True)
    for idx in range(5):
        rec_id = f"v14-editplan-{idx:03d}"
        base_path = base_dir / f"{rec_id}-base.hwpx"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        op_name = _EDITPLAN_OP_BANK[idx]
        try:
            document = _base_document(idx, "편집 계획 실행 표본")
            document.add_paragraph("치환 대상 문단입니다.")
            paragraph_index = _last_paragraph_index(document)

            if op_name in ("recolor_runs_by_color", "strip_runs_by_color"):
                red_cid = document.styles.ensure_run(color="#C00000")
                document.add_paragraph(f"{cycle(DEPT_BANK, idx)} 색상 표시 문단", char_pr_id_ref=red_cid)
            table = document.add_table(2, 2, width=42000)
            table.cell(0, 0).text = "라벨"
            document.save_to_path(str(base_path))

            if op_name == "paragraph_patch":
                step = {"op": "paragraph_patch", "args": {"patches": [
                    {"paragraphIndex": paragraph_index, "text": f"계획으로 치환된 문단 {idx}"},
                ]}}
            elif op_name == "fill_cells":
                step = {"op": "fill_cells", "args": {"cells": [
                    {"tableIndex": 0, "row": 0, "col": 1, "text": cycle(DEPT_BANK, idx)},
                ]}}
            elif op_name == "apply_table_ops":
                step = {"op": "apply_table_ops", "args": {"ops": [
                    {"op": "set_column_widths", "table_index": 0, "widths": {0: 8000, 1: 12000}},
                ]}}
            elif op_name == "recolor_runs_by_color":
                step = {"op": "recolor_runs_by_color", "args": {
                    "from_hexes": ["#C00000"], "to_color": "#1F4E79",
                }}
            else:  # strip_runs_by_color
                step = {"op": "strip_runs_by_color", "args": {"hex_colors": ["#C00000"]}}

            plan = {
                "schemaVersion": "hwpx.edit-plan/v1",
                "source": str(base_path),
                "output": str(out_path),
                "steps": [{"id": "s1", **step}],
            }
            report = apply_edit_plan(plan)
            if not report.ok:
                raise RuntimeError(f"edit plan failed: {report.to_dict().get('failedStepId')}")

            records.append(record(
                rec_id=rec_id, bucket="authored-editplan", seed=op_name,
                output_path=out_path, produced=True, input_path=base_path,
            ))
        except Exception as exc:  # noqa: BLE001 - withheld is the honest record
            records.append(record(
                rec_id=rec_id, bucket="authored-editplan", seed=op_name,
                output_path=None, produced=False, input_path=base_path,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
    return records


# ================================================================================
# stratum 10 -- authored-docmerge2 (train 38: 4-axis params + MEMO merge)
# ================================================================================


def gen_docmerge2(bucket_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for idx in range(5):
        rec_id = f"v14-docmerge2-{idx:03d}"
        out_path = bucket_dir / f"{rec_id}.hwpx"
        source: HwpxDocument | None = None
        try:
            source = HwpxDocument.new()
            shape_id = None
            if idx in (0, 3):
                # real (non-sentinel) memoShapeIDRef -- exercises the
                # memoShapeIDRef remap path, not just the "65535" default.
                shape_id = source.styles.ensure_memo_shape(fill_color="#F0FFE9")
            anchor = source.add_paragraph(f"{cycle(DEPT_BANK, idx)} 병합 v2 메모 표본 {idx}")
            # field_id= pinned explicitly -- attach_memo_field's own
            # fallback (_document/memos.py:103, `uuid.uuid4().hex`) does
            # NOT go through _document_primitives' patched uuid4 binding,
            # so it's genuinely unseeded even inside
            # _deterministic_object_ids(). For source-side memos this gets
            # masked (the merge's own _refresh_field_and_bookmark_ids
            # overwrites id/fieldid on every copied fieldBegin/fieldEnd
            # regardless of their starting value) -- pinned here anyway,
            # for robustness rather than relying on that overwrite as an
            # implicit assumption.
            source.notes.add_memo(
                f"메모 내용 {idx}", anchor=anchor, memo_shape_id_ref=shape_id,
                created=_TIMESTAMP_BANK[idx], field_id=f"v14-docmerge2-{idx:03d}-src-field",
            )
            if idx == 3:
                source.add_table(rows=2, cols=2)

            target = _base_document(idx, "문서 병합 v2 대상")
            if idx == 2:
                # target already owns a memo (its own memogroup) -- the
                # merge must join it, not create a duplicate memogroup.
                # UNLIKE the source-side memo above, target's own field is
                # never touched by the merge's refresh pass at all (only
                # source content gets refreshed) -- field_id= here is load
                # -bearing for determinism, not just defensive.
                target_anchor = target.sections[0].paragraphs[0]
                target.notes.add_memo(
                    "대상 문서 자체 메모", anchor=target_anchor, created=_TIMESTAMP_BANK[idx],
                    field_id=f"v14-docmerge2-{idx:03d}-tgt-field",
                )

            # Explicit default-value axis kwargs -- proves the new v2
            # parameters are accepted end-to-end, not just unit-tested in
            # isolation. Non-default values raise a typed error before any
            # side effect (see the contract doc's 정책 4축 section) --
            # there is no "successful non-default merge" artifact for this
            # generator to produce, so no such record exists here.
            axis_kwargs: dict[str, bool] = {
                "keep_character_shape": True, "keep_style": True,
                "keep_paragraph_shape": True, "keep_page_shape": False,
            }
            if idx % 2 == 0:
                append_document(target, source, **axis_kwargs)
            else:
                total = len(target.sections[0].paragraphs)
                insert_document(target, source, after_paragraph_index=total - 1, **axis_kwargs)

            target.save_to_path(str(out_path))
            records.append(record(
                rec_id=rec_id, bucket="authored-docmerge2", seed=str(idx),
                output_path=out_path, produced=True,
            ))
        except Exception as exc:  # noqa: BLE001 - withheld is the honest record
            records.append(record(
                rec_id=rec_id, bucket="authored-docmerge2", seed=str(idx),
                output_path=None, produced=False,
                withheld_reason=f"{type(exc).__name__}: {exc}",
            ))
        finally:
            if source is not None:
                source.close()
    return records


GENERATORS: tuple[tuple[str, Callable[[Path], list[dict[str, Any]]]], ...] = (
    ("authored-charformat2", gen_charformat2),
    ("authored-listformat", gen_listformat),
    ("authored-tablestructure", gen_tablestructure),
    ("authored-tablenavfill", gen_tablenavfill),
    ("authored-findreplace", gen_findreplace),
    ("authored-redline", gen_redline),
    ("authored-chart", gen_chart),
    ("authored-picture", gen_picture),
    ("authored-editplan", gen_editplan),
    ("authored-docmerge2", gen_docmerge2),
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
    if OUT_DIR_V14.exists() and any(OUT_DIR_V14.iterdir()):
        print(
            f"ERROR: {OUT_DIR_V14} already exists -- v14 is frozen once generated. "
            "Delete the tree explicitly to regenerate.",
            file=sys.stderr,
        )
        return 2

    all_records: list[dict[str, Any]] = []
    with _deterministic_object_ids():
        for bucket, generator in GENERATORS:
            bucket_dir = OUT_DIR_V14 / bucket
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
            "v14 is ADDITIVE over v13: 10 new strata, a verification-debt "
            "sweep targeting docs/editor-surface-inventory.md's remaining "
            "미실측 (unmeasured) authoring-api rows (8 of them: "
            "list-formatting, find-replace, table-structure, "
            "table-navigation-fill, picture, chart, redline, edit-plan) "
            "plus ensure_run's 9 params not covered by v7's "
            "authored-charformat (underline/strike/ratio/spacing/shadow/"
            "base_char_pr_id) and cycle 6.10 train 38's document-merge v2 "
            "output (4-axis policy parameters + MEMO merge). Stratum "
            "bucket names follow v13's authored-<area> convention "
            "(authored-chart/authored-editplan are DISTINCT buckets from "
            "v4's authored-chart / v3-v4's edit-plan, by name -- "
            "coverage_ledger.py folds same-named strata across report-vN "
            "files via OR, so authored-chart accumulates rather than "
            "collides; authored-editplan is a fresh, differently-named "
            "bucket). authored-tablenavfill/authored-findreplace/"
            "authored-editplan intentionally have no capabilityArea "
            "routing (coverage_ledger.py's own documented reasoning: they "
            "mutate existing elements rather than create new ones, so "
            "there is nothing to tag) -- their grade evidence lives only "
            "in this report JSON plus support-matrix.md prose citation. "
            "authored-chart uses a hand-built minimal ChartML "
            "(_build_chart_ml, this script's own function) rather than "
            "python-hwpx-automation's fuller build_chart_ml -- core "
            "cannot import the automation package (one-way architecture); "
            "visual chart richness may be lower than v4's 15-record batch, "
            "an honest limitation, not a functional gap. It does not "
            "re-touch v3-v13's strata; it does not replace v1-v13, which "
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
        },
        "counts": counts,
        "requestedTotal": sum(slot["requested"] for slot in counts.values()),
        "producedTotal": sum(slot["produced"] for slot in counts.values()),
        "items": all_records,
    }
    manifest_path = OUT_DIR_V14 / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    filelist_path = OUT_DIR_V14 / "box_run_v14.filelist"
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
    render_jobs_path = OUT_DIR_V14 / "render_jobs_v14.json"
    render_jobs_path.write_text(
        json.dumps(render_jobs, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"v14 corpus: {manifest['producedTotal']}/{manifest['requestedTotal']} produced")
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
