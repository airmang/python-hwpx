# SPDX-License-Identifier: Apache-2.0
"""Editor surface inventory v1 (cycle 6.8, train 29) -- the "feature axis"
measuring instrument.

``scripts/coverage_ledger.py`` measures python-hwpx against the *element
axis* (every OWPML tag/attribute a real Hancom document can contain). It
cannot answer a different, equally real question: does our engine cover
every *user-visible feature* of the Hancom editor -- 서식(formatting),
개체(objects), 표(tables), 필드(fields), 검토(review), 보안(security),
레이아웃(layout), 인쇄(print), etc.? A feature can be well-covered on the
element axis (every element it touches is read=True/write=api) while never
having been named as its own row anywhere -- or a whole feature family
(e.g. page layout) can exist as real, working code with zero capability-
area or support-matrix representation at all. This script builds and
drift-guards the AUTO-GENERATED part of ``docs/editor-surface-
inventory.md`` from our three existing assets:

1. ``hwpx.capabilities._CAPABILITY_AREAS`` -- the 23 registered capability
   areas (imported directly, not text-scraped).
2. ``docs/support-matrix.md``'s "매트릭스" table (능력 영역/상태/증거) and
   "6.0 표면 위치" table (능력 영역/네임스페이스) -- text-parsed, since
   this doc has no importable structure.
3. ``docs/coverage-ledger.json``'s summary block -- a single cross-check
   line, not a per-row source (the element axis is finer-grained than the
   feature axis; folding every element in would defeat the point of a
   second, coarser instrument).

What this script does NOT do (v1 scope, per the owner's explicit "과설계
금지"): it does not enumerate features beyond what these three assets
already name. Real Hancom editor features with zero trace in any of our
three assets (page layout, character formatting, hyperlinks/bookmarks'
independent verification, find & replace, list formatting, font
registration, tab-stop editing, navigation-based table fill, and a
hand-curated list of standard word-processor features with no evidence at
all -- spell check, macros, mail merge, print dialog specifics, digital
signatures) are recorded by hand in ``docs/editor-surface-inventory.md``'s
own prose sections, which this script never touches and cannot regenerate
(there is no automatic source to regenerate them from -- that absence is
itself the finding).

Usage:

    python scripts/editor_surface_inventory.py          # regenerate
    python scripts/editor_surface_inventory.py --check  # drift guard
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

INVENTORY_PATH = ROOT / "docs" / "editor-surface-inventory.md"
SUPPORT_MATRIX_PATH = ROOT / "docs" / "support-matrix.md"
LEDGER_JSON_PATH = ROOT / "docs" / "coverage-ledger.json"

AUTO_BEGIN = "<!-- AUTO-GENERATED:BEGIN (scripts/editor_surface_inventory.py) -->"
AUTO_END = "<!-- AUTO-GENERATED:END -->"

#: Every registered capability area, by hand, into one of the owner's
#: named categories (서식·개체·표·필드·검토·보안·레이아웃·인쇄 + two natural
#: extensions this survey needed: 참조 for reference/link mechanisms and
#: 자동화 for batch/plan-driven editing). This mapping has no automatic
#: source -- capabilities.py itself carries no category field -- so it is
#: reviewed by hand whenever a new area is registered (matches this
#: project's "새 능력 영역은 여기 화이트리스트에 등록" convention elsewhere).
CATEGORY_MAP: dict[str, str] = {
    "paragraph-table-authoring": "서식",
    "table-structure": "표",
    "table-create": "표",
    "form-fill": "필드",
    "edit-plan": "자동화",
    "shape-authoring": "개체",
    "shape-escape-hatch": "개체",
    "curve-objects": "개체",
    "container-authoring": "개체",
    "picture": "개체",
    "chart": "개체",
    "equation": "개체",
    "redline": "검토",
    "highlight": "서식",
    "border-fill-image-gradient": "서식",
    "memo": "검토",
    "footnote-endnote": "참조",
    "toc-crossref": "참조",
    "encrypted-hwpx": "보안/호환성",
    "hwp5-binary": "보안/호환성",
    "form-field-create": "필드",
    "check-box": "필드",
    "document-options-compatibility": "보안/호환성",
    # 6.8 트레인㉚ — 트레인㉙이 찾은 측정 갭 등재.
    "page-layout": "레이아웃",
    "character-formatting": "서식",
    "list-formatting": "서식",
    "font-registration": "서식",
    "table-navigation-fill": "표",
    "find-replace": "서식",
    "hyperlink-bookmark": "참조",
    # 6.8 트레인㉛ — 트레인㉚이 찾은 mail_merge 측정 갭 등재.
    "mail-merge": "자동화",
    # 6.9 트레인㉝ — 트레인㉙의 macOS 메뉴 전수 스캔이 찾은 문서 병합 갭 등재.
    "document-merge": "자동화",
    # 6.9 트레인㉞ — 덧말·글자 겹치기 저작.
    "dutmal-compose": "개체",
}

CATEGORY_ORDER: tuple[str, ...] = (
    "서식", "표", "개체", "필드", "참조", "검토", "보안/호환성", "레이아웃", "인쇄", "자동화",
)


def _load_capability_areas() -> list[dict]:
    from hwpx.capabilities import _CAPABILITY_AREAS

    return list(_CAPABILITY_AREAS)


def _parse_support_matrix() -> tuple[dict[str, tuple[str, str]], dict[str, str]]:
    """Returns (matrix_row -> (status, evidence)), (matrix_row -> 6.0 위치)."""

    text = SUPPORT_MATRIX_PATH.read_text(encoding="utf-8")

    matrix_section = re.search(r"## 매트릭스\n\n(.*?)\n\n## ", text, re.S)
    assert matrix_section is not None, "매트릭스 section not found in support-matrix.md"
    status_evidence: dict[str, tuple[str, str]] = {}
    for line in matrix_section.group(1).splitlines():
        m = re.match(r"\| (.+?) \| (.+?) \| (.+?) \|$", line)
        if not m or m.group(1) in ("능력 영역", "---"):
            continue
        row, status, evidence = m.groups()
        status_evidence[row.strip()] = (status.strip(), evidence.strip())

    position_section = re.search(r"## 6\.0 표면 위치\n\n.*?\n\n(\| 능력 영역.*?)\n\n", text, re.S)
    assert position_section is not None, "6.0 표면 위치 section not found in support-matrix.md"
    positions: dict[str, str] = {}
    for line in position_section.group(1).splitlines():
        m = re.match(r"\| (.+?) \| (.+?) \|$", line)
        if not m or m.group(1) in ("능력 영역", "---"):
            continue
        row, position = m.groups()
        positions[row.strip()] = position.strip()

    return status_evidence, positions


def _engine_status_from_grade(status: str) -> str:
    """지원 매트릭스 등급 문자열 -> [엔진 상태] 4갈래(저작 api/읽기만/보존만/없음)."""

    if "Create" in status or "Edit" in status:
        return "저작 api"
    if "Unsupported-and-rejected" in status:
        return "없음(거부)"
    if "Preserve" in status or "Unsupported-but-preserved" in status:
        return "보존만"
    if "Parse" in status:
        return "읽기만"
    return "미확인"  # defensive -- every registered row should hit one of the above


def _verification_status(status: str) -> str:
    if "Render-verified(부분)" in status:
        # A partial-coverage receipt (e.g. only 5 of doc.page's 19 methods, or
        # only a handful of ensure_run's 17 kwargs) -- collapsing this to a
        # bare "Render-verified" would misrepresent an unverified majority as
        # covered. Keep the qualifier; the full grade string is still cited
        # verbatim in the evidence cell for readers who want the specifics.
        return "Render-verified(부분만 -- 근거 칸의 등급 문자열 참조)"
    if "Render-verified" in status:
        experimental = "(experimental 저작 포함)" if "experimental" in status else ""
        return f"Render-verified{experimental}"
    if "Unsupported-and-rejected" in status:
        return "해당없음(의도적 거부, 실측으로 확인)"
    return "미실측"


def generate_auto_rows() -> str:
    areas = _load_capability_areas()
    status_evidence, positions = _parse_support_matrix()

    missing_category = [a["area"] for a in areas if a["area"] not in CATEGORY_MAP]
    if missing_category:
        raise SystemExit(
            f"CATEGORY_MAP is missing area(s): {missing_category} -- add them by hand "
            "before regenerating (see the module docstring: this mapping has no "
            "automatic source)."
        )

    by_category: dict[str, list[dict]] = {}
    for area in areas:
        by_category.setdefault(CATEGORY_MAP[area["area"]], []).append(area)

    lines: list[str] = []
    for category in CATEGORY_ORDER:
        rows = by_category.get(category)
        if not rows:
            continue
        lines.append(f"### {category}\n")
        lines.append("| 기능 | 엔진 상태 | 근거 | 실한컴 검증 |")
        lines.append("|---|---|---|---|")
        for area in sorted(rows, key=lambda a: a["matrix_row"]):
            matrix_row = area["matrix_row"]
            status, _evidence = status_evidence.get(matrix_row, ("미확인", ""))
            position = positions.get(matrix_row, "미확인")
            engine_status = _engine_status_from_grade(status)
            verification = _verification_status(status)
            # `position` (support-matrix.md's own "6.0 표면 위치" column) already
            # contains its own inline code spans (e.g. "루트 -- `doc.add_paragraph`
            # ..."), so it is NOT re-wrapped in another backtick pair here -- doing
            # so would nest backticks, which breaks markdown rendering.
            evidence_cell = (
                f"지원 매트릭스 「{matrix_row}」(`{status}`) · capabilities 영역 "
                f"`{area['area']}` · 위치 {position}"
            )
            lines.append(
                f"| {matrix_row} | {engine_status} | {evidence_cell} | {verification} |"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _summary_line() -> str:
    ledger = json.loads(LEDGER_JSON_PATH.read_text(encoding="utf-8"))
    summary = ledger["summary"]
    areas = _load_capability_areas()
    return (
        f"자동 생성 시점 교차 확인: 원장(요소 축) {summary['renderVerified']}건 "
        f"render-verified(요소 {sum(1 for _ in ledger['elements'])}개 중) · "
        f"캐파빌리티 영역(기능 축) {len(areas)}개 등록됨.\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    auto_rows = generate_auto_rows()
    summary_line = _summary_line()
    new_block = f"{AUTO_BEGIN}\n\n{summary_line}\n{auto_rows}\n{AUTO_END}"

    if not INVENTORY_PATH.exists():
        print(f"ERROR: {INVENTORY_PATH} does not exist -- create it first with the "
              f"{AUTO_BEGIN} / {AUTO_END} markers in place (this script only replaces "
              "the block between them, never creates the surrounding hand-authored "
              "document).", file=sys.stderr)
        return 2

    current_text = INVENTORY_PATH.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(AUTO_BEGIN) + r".*?" + re.escape(AUTO_END), re.S)
    if not pattern.search(current_text):
        print(f"ERROR: markers {AUTO_BEGIN!r}/{AUTO_END!r} not found in {INVENTORY_PATH}",
              file=sys.stderr)
        return 2

    updated_text = pattern.sub(lambda _m: new_block, current_text, count=1)

    if args.check:
        if updated_text == current_text:
            print("editor surface inventory (auto section) in sync")
            return 0
        print("DRIFT: docs/editor-surface-inventory.md's auto-generated section is stale "
              "-- run `python scripts/editor_surface_inventory.py` to regenerate.",
              file=sys.stderr)
        return 1

    if updated_text != current_text:
        INVENTORY_PATH.write_text(updated_text, encoding="utf-8")
        print(f"[OK] {INVENTORY_PATH} (auto section regenerated)")
    else:
        print(f"[OK] {INVENTORY_PATH} (auto section already current)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
