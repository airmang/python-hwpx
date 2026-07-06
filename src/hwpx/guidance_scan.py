"""Form guidance scanner — 임의 양식의 안내문·placeholder·색 신호 정찰 (비변형).

목적: 처음 보는 양식(예시·안내문·지워야 할 내용 혼재)에서 "지울 것 / 수정·채울 것 /
그대로 둘 것" 후보를 위치·근거·신뢰도와 함께 보고한다. 채움을 실행하지 않는다.

좌표 규약: table_index는 섹션 내 ``<hp:tbl>`` 문서순(중첩 포함 pre-order) —
``table_patch``(fill_cells/apply_table_ops)와 동일하므로 후속 op 주소로 그대로 쓸 수 있다.
row/col은 ``<hp:cellAddr>`` 값(병합 앵커 좌표).

정직 한계(리포트에도 명시):
- 색 신호는 run의 charPrIDRef가 가리키는 charPr textColor 기준. charPrIDRef가 없는
  run은 기본 charPr("0")로 간주한다.
- 배경색(cell borderFill/shade) 기반 신호는 이 스캐너가 다루지 않는다.
- 여기서 내는 것은 "후보"다 — 삭제/수정 확정은 사용자 승인 후에만 한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Union

from .document import HwpxDocument
from .oxml.namespaces import tag_local_name

__all__ = [
    "CellLoc",
    "ScannedParagraph",
    "LegendBinding",
    "Candidate",
    "GuidanceReport",
    "scan_form_guidance",
]

# 도형 순회는 markdown_export와 동일 정책: rect/ellipse/polygon만.
_SHAPE_TAGS = ("rect", "ellipse", "polygon")

# ── placeholder / 안내 패턴 ─────────────────────────────────────────
_PLACEHOLDER_PATTERNS: dict[str, re.Pattern[str]] = {
    "circle_blank": re.compile(r"[◯○〇]{2,}"),
    "square_blank": re.compile(r"□{2,}"),
    "double_star": re.compile(r"\*\*"),
    "example_marker": re.compile(r"[(〈［\[]\s*예시?\s*[)〉］\]]"),
    "howto_marker": re.compile(r"(작성|기재)\s*요령"),
}
_GUIDANCE_KEYWORD = re.compile(
    r"(유의\)|※|삭제\s*바랍니다|삭제합니다|삭제!!|문의주세요|작성해\s*주세요|맞추어\s*작성)"
)
_CONDITIONAL_CHOICE = re.compile(r"중에서.{0,20}(만\s*남기|남기고|선택)|해당하는\s*것만\s*남기")

# ── 색 범례 ────────────────────────────────────────────────────────
_LEGEND_HINT = re.compile(r"글씨|글자")
_COLOR_WORDS: dict[str, str] = {
    "검정": "black", "검은": "black", "빨간": "red", "빨강": "red", "적색": "red",
    "파란": "blue", "파랑": "blue", "청색": "blue", "초록": "green", "녹색": "green",
}
_ACTION_WORDS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"그대로|유지"), "keep"),
    (re.compile(r"수정"), "modify"),
    (re.compile(r"삭제"), "delete"),
]


def _color_family(hex_color: str) -> str:
    """#RRGGBB → 대략적 색 계열. 정확 hex 일치가 아니라 계열 매칭용."""
    m = re.fullmatch(r"#([0-9A-Fa-f]{6})", hex_color or "")
    if not m:
        return "other"
    r, g, b = (int(m.group(1)[i : i + 2], 16) for i in (0, 2, 4))
    if r <= 0x30 and g <= 0x30 and b <= 0x30:
        return "black"
    if r >= 0xE0 and g >= 0xE0 and b >= 0xE0:
        return "white"
    if r >= 0x96 and g <= 0x78 and b <= 0x78:
        return "red"
    if b >= 0x96 and r <= 0x78:
        return "blue"
    if g >= 0x96 and r <= 0x78 and b <= 0x78:
        return "green"
    if abs(r - g) <= 0x18 and abs(g - b) <= 0x18:
        return "gray"
    return "other"


@dataclass(slots=True)
class CellLoc:
    """표 셀 좌표 (table_patch 규약)."""

    table_index: int
    row: int
    col: int

    def label(self) -> str:
        if self.row == -1 and self.col == -1:
            return f"표{self.table_index} caption"
        return f"표{self.table_index} r{self.row}c{self.col}"


@dataclass(slots=True)
class ScannedParagraph:
    """스캔된 문단 하나 — 본문(¶N) 또는 셀 내부."""

    section_index: int
    body_index: int  # 소속 최상위 문단의 섹션 내 순번
    cell: CellLoc | None
    spans: list[tuple[str, str, str]]  # (char_pr_id, hex_color, text)
    first_char_pr_id: str | None = None  # 텍스트가 비어도 서식 컨텍스트를 잃지 않기 위해

    @property
    def text(self) -> str:
        return "".join(s[2] for s in self.spans)

    def colors(self) -> set[str]:
        return {s[1] for s in self.spans if s[2].strip()}

    def location(self) -> str:
        base = f"§{self.section_index}¶{self.body_index}"
        return f"{base} {self.cell.label()}" if self.cell else f"{base} 본문"


@dataclass(slots=True)
class LegendBinding:
    color_word: str  # 범례가 말한 색 이름
    family: str  # red/blue/black …
    exact_hex: str | None  # 범례 문장 자체 채색에서 추출한 정확 hex(가능 시)
    action: str  # keep / modify / delete
    source_text: str


@dataclass(slots=True)
class Candidate:
    location: str
    signals: list[str]
    confidence: str  # high / medium / low
    text_preview: str
    cell: CellLoc | None = None


@dataclass(slots=True)
class GuidanceReport:
    source: str
    color_inventory: dict[str, dict]  # hex → {runs, family, samples}
    legend: list[LegendBinding]
    delete_candidates: list[Candidate]
    modify_candidates_by_table: dict[str, dict]  # 위치 → 집계(파랑 등 수정 대상)
    placeholder_candidates: list[Candidate]
    conditional_choices: list[Candidate]
    questions: list[str]
    empty_cell_candidates: list[Candidate] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)
    limitations: list[str] = field(
        default_factory=lambda: [
            "색 신호는 run charPr textColor 기준 — 배경색/테두리색 신호는 미커버.",
            "여기 나온 것은 후보다. 삭제/수정 확정은 사용자 승인 후에만 한다.",
        ]
    )

    def to_markdown(self) -> str:
        lines = [f"# 양식 정찰 리포트 — {Path(self.source).name}", ""]
        lines.append(
            f"문단 {self.stats.get('paragraphs', 0)}·표 {self.stats.get('tables', 0)}"
            f"·유색 run {self.stats.get('colored_runs', 0)}"
        )
        lines.append("")
        lines.append("## ① 색 범례 (양식 자체 선언)")
        if self.legend:
            for b in self.legend:
                hex_note = f" (본문 실색 {b.exact_hex})" if b.exact_hex else ""
                lines.append(f"- **{b.color_word}**({b.family}{hex_note}) → **{b.action}** — “{b.source_text[:60]}”")
        else:
            lines.append("- 범례 문장 미발견 — 색 의미는 질문 목록으로.")
        lines.append("")
        lines.append("## ② 색 인벤토리")
        for hex_color, info in sorted(
            self.color_inventory.items(), key=lambda kv: -kv[1]["runs"]
        ):
            samples = " / ".join(info["samples"][:3])
            lines.append(f"- `{hex_color}` ({info['family']}) — run {info['runs']}개 — 예: {samples[:90]}")
        lines.append("")
        lines.append(f"## ③ 지울 것 후보 ({len(self.delete_candidates)})")
        for c in self.delete_candidates:
            lines.append(f"- [{c.confidence}] {c.location} — “{c.text_preview}” 〔{', '.join(c.signals)}〕")
        lines.append("")
        lines.append("## ④ 수정·채움 후보 (표별 집계)")
        for where, agg in self.modify_candidates_by_table.items():
            fmt = agg.get("format_context", "")
            lines.append(
                f"- {where}: 수정대상 문단 {agg['paragraphs']}개 — 예: {agg['sample'][:60]}"
                + (f" — 서식 {fmt}" if fmt else "")
            )
        lines.append("")
        lines.append(f"## ⑤ 빈 셀(채움 후보, {len(self.empty_cell_candidates)}) — 표별")
        by_table: dict[str, list[Candidate]] = {}
        for c in self.empty_cell_candidates:
            key = c.cell.label().split(" ")[0] if c.cell else "본문"
            by_table.setdefault(key, []).append(c)
        for key, cands in by_table.items():
            examples = []
            for c in cands[:3]:
                fmt = next((s.split(":", 1)[1] for s in c.signals if s.startswith("format:")), "")
                detail = ", ".join(part for part in (c.text_preview, fmt) if part)
                examples.append(f"r{c.cell.row}c{c.cell.col}({detail})")
            more = f" 외 {len(cands) - 3}건" if len(cands) > 3 else ""
            lines.append(f"- {key}: 빈 셀 {len(cands)}개 — {' · '.join(examples)}{more}")
        lines.append("")
        lines.append(f"## ⑥ placeholder 후보 ({len(self.placeholder_candidates)})")
        for c in self.placeholder_candidates:
            lines.append(f"- [{c.confidence}] {c.location} — “{c.text_preview}” 〔{', '.join(c.signals)}〕")
        lines.append("")
        lines.append(f"## ⑦ 조건부 선택 블록 ({len(self.conditional_choices)})")
        for c in self.conditional_choices:
            lines.append(f"- {c.location} — “{c.text_preview}”")
        lines.append("")
        lines.append("## ⑧ 질문 목록 (확신 없음 — 사용자 결정 필요)")
        for q in self.questions:
            lines.append(f"- {q}")
        lines.append("")
        lines.append("## 한계(정직)")
        for lim in self.limitations:
            lines.append(f"- {lim}")
        return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────
# 순회 — 셀 내부 포함 스타일-aware 문단 수집
# ──────────────────────────────────────────────────────────────────
def _local(el) -> str:
    return tag_local_name(str(el.tag))


class _Walker:
    def __init__(self, chars: dict) -> None:
        self.chars = chars
        self.table_counter = -1
        self.out: list[ScannedParagraph] = []

    def _hex_of(self, cpr: str) -> str:
        style = self.chars.get(str(cpr))
        if style is None:
            return "#000000"
        return (style.attributes.get("textColor") or "#000000").upper()

    def walk_paragraph(self, p_el, section_index: int, body_index: int, cell: CellLoc | None) -> None:
        spans: list[tuple[str, str, str]] = []
        first_cpr: str | None = None
        for run in (c for c in p_el if _local(c) == "run"):
            cpr = run.get("charPrIDRef", "0")
            if first_cpr is None:
                first_cpr = cpr
            hex_color = self._hex_of(cpr)
            for child in run:
                tag = _local(child)
                if tag == "t":
                    text = "".join(child.itertext())
                    if text:
                        spans.append((cpr, hex_color, text))
                elif tag == "tbl":
                    self.walk_table(child, section_index, body_index)
                elif tag in _SHAPE_TAGS or tag == "container":
                    self.walk_container(child, section_index, body_index, cell)
        self.out.append(
            ScannedParagraph(
                section_index=section_index, body_index=body_index, cell=cell,
                spans=spans, first_char_pr_id=first_cpr,
            )
        )

    def walk_container(self, el, section_index: int, body_index: int, cell: CellLoc | None) -> None:
        for child in el:
            tag = _local(child)
            if tag == "p":
                self.walk_paragraph(child, section_index, body_index, cell)
            elif tag == "tbl":
                self.walk_table(child, section_index, body_index)
            else:
                self.walk_container(child, section_index, body_index, cell)

    def walk_table(self, tbl_el, section_index: int, body_index: int) -> None:
        self.table_counter += 1
        table_index = self.table_counter
        # 캡션(hp:caption > subList > p)도 표 소속 텍스트다 — row/col = -1 로 표기.
        for cap in (c for c in tbl_el if _local(c) == "caption"):
            self.walk_container(
                cap, section_index, body_index, CellLoc(table_index=table_index, row=-1, col=-1)
            )
        for tr in self._direct_rows(tbl_el):
            for tc in (c for c in tr if _local(c) == "tc"):
                row, col = self._cell_addr(tc)
                loc = CellLoc(table_index=table_index, row=row, col=col)
                for sub in (c for c in tc if _local(c) == "subList"):
                    for child in sub:
                        if _local(child) == "p":
                            self.walk_paragraph(child, section_index, body_index, loc)

    @staticmethod
    def _direct_rows(tbl_el) -> Iterable:
        return (c for c in tbl_el if _local(c) == "tr")

    @staticmethod
    def _cell_addr(tc_el) -> tuple[int, int]:
        for child in tc_el:
            if _local(child) == "cellAddr":
                return int(child.get("rowAddr", -1)), int(child.get("colAddr", -1))
        return -1, -1


# ──────────────────────────────────────────────────────────────────
# 분석
# ──────────────────────────────────────────────────────────────────
def _parse_legend(paragraphs: list[ScannedParagraph]) -> list[LegendBinding]:
    bindings: list[LegendBinding] = []
    for para in paragraphs:
        text = para.text
        if not (_LEGEND_HINT.search(text) and any(w in text for w in _COLOR_WORDS)):
            continue
        has_action = any(pat.search(text) for pat, _ in _ACTION_WORDS)
        if not has_action:
            continue
        # 절 단위로 색 단어→가장 가까운 액션 매칭
        clauses = re.split(r"[/,]", text)
        for clause in clauses:
            found_color = next((w for w in _COLOR_WORDS if w in clause), None)
            if found_color is None:
                continue
            action = next((a for pat, a in _ACTION_WORDS if pat.search(clause)), None)
            if action is None:
                continue
            family = _COLOR_WORDS[found_color]
            # 범례 문장 자체 채색에서 정확 hex 추출: 절 텍스트를 포함하는 span 중 계열 일치 색
            exact = None
            for _, hex_color, span_text in para.spans:
                if span_text.strip() and span_text in clause and _color_family(hex_color) == family:
                    exact = hex_color
                    break
            if not any(b.family == family and b.action == action for b in bindings):
                bindings.append(
                    LegendBinding(
                        color_word=found_color, family=family, exact_hex=exact,
                        action=action, source_text=clause.strip(),
                    )
                )
    return bindings


def _preview(text: str, limit: int = 80) -> str:
    flat = re.sub(r"\s+", " ", text).strip()
    return flat[: limit - 1] + "…" if len(flat) > limit else flat


def _format_context(para: ScannedParagraph, chars: dict) -> str:
    for cpr, _, span_text in para.spans:
        if not span_text.strip():
            continue
        style = chars.get(str(cpr))
        if style is None:
            return ""
        height = style.attributes.get("height")
        size = f"{int(height) / 100:g}pt" if height and height.isdigit() else "?"
        bold = "bold" in style.child_attributes
        return f"{size}{'·bold' if bold else ''}"
    return ""


def scan_form_guidance(source: Union[str, Path, HwpxDocument]) -> GuidanceReport:
    """양식을 정찰해 지울 것/수정할 것/placeholder/질문 후보 리포트를 만든다(비변형)."""
    if isinstance(source, HwpxDocument):
        doc, src_name = source, "<document>"
    else:
        doc, src_name = HwpxDocument.open(str(source)), str(source)

    chars = doc._root.char_properties
    paragraphs: list[ScannedParagraph] = []
    tables_total = 0
    for s_idx, section in enumerate(doc.sections):
        walker = _Walker(chars)
        for b_idx, p in enumerate(section.paragraphs):
            walker.walk_paragraph(p.element, s_idx, b_idx, None)
        paragraphs.extend(walker.out)
        tables_total += walker.table_counter + 1

    # 색 인벤토리
    inventory: dict[str, dict] = {}
    colored_runs = 0
    for para in paragraphs:
        for _, hex_color, text in para.spans:
            if not text.strip():
                continue
            fam = _color_family(hex_color)
            if fam in ("black", "white"):
                continue
            colored_runs += 1
            entry = inventory.setdefault(hex_color, {"runs": 0, "family": fam, "samples": []})
            entry["runs"] += 1
            flat = _preview(text, 40)
            if flat and len(entry["samples"]) < 5 and flat not in entry["samples"]:
                entry["samples"].append(flat)

    legend = _parse_legend(paragraphs)
    delete_family = {b.family for b in legend if b.action == "delete"}
    modify_family = {b.family for b in legend if b.action == "modify"}

    delete_candidates: list[Candidate] = []
    placeholder_candidates: list[Candidate] = []
    conditional_choices: list[Candidate] = []
    modify_by_table: dict[str, dict] = {}

    for para in paragraphs:
        text = para.text
        if not text.strip():
            continue
        families = {_color_family(h) for h in para.colors()}
        signals: list[str] = []
        if delete_family & families:
            signals.append("legend:삭제색")
        kw = _GUIDANCE_KEYWORD.search(text)
        if kw:
            signals.append(f"keyword:{kw.group(0)}")
        if signals:
            confidence = "high" if "legend:삭제색" in signals else "medium"
            # 삭제색 신호는 색 run만 있어도 후보(문장 일부만 빨강인 경우 포함)
            if "legend:삭제색" in signals or kw:
                delete_candidates.append(
                    Candidate(
                        location=para.location(), signals=signals, confidence=confidence,
                        text_preview=_preview(text), cell=para.cell,
                    )
                )
        for name, pat in _PLACEHOLDER_PATTERNS.items():
            m = pat.search(text)
            if m:
                placeholder_candidates.append(
                    Candidate(
                        location=para.location(), signals=[f"placeholder:{name}"],
                        confidence="high" if name in ("circle_blank", "square_blank") else "medium",
                        text_preview=_preview(text), cell=para.cell,
                    )
                )
        if _CONDITIONAL_CHOICE.search(text):
            conditional_choices.append(
                Candidate(location=para.location(), signals=["conditional_choice"],
                          confidence="high", text_preview=_preview(text), cell=para.cell)
            )
        if modify_family & families:
            key = f"표{para.cell.table_index}" if para.cell else f"§{para.section_index} 본문"
            agg = modify_by_table.setdefault(
                key, {"paragraphs": 0, "sample": _preview(text, 60),
                      "format_context": _format_context(para, chars)}
            )
            agg["paragraphs"] += 1

    # 채울 곳 후보: 완전히 빈 셀 + 인접 라벨 문맥 + 서식 컨텍스트
    cell_paras: dict[tuple[int, int, int], list[ScannedParagraph]] = {}
    for para in paragraphs:
        if para.cell is not None and para.cell.row >= 0:
            key = (para.cell.table_index, para.cell.row, para.cell.col)
            cell_paras.setdefault(key, []).append(para)

    def _cell_joined(key: tuple[int, int, int]) -> str:
        return "".join(p.text for p in cell_paras.get(key, [])).strip()

    empty_cell_candidates: list[Candidate] = []
    for (tbl, row, col), plist in sorted(cell_paras.items()):
        if _cell_joined((tbl, row, col)):
            continue
        label = ""
        for nkey, tag in (((tbl, row, col - 1), "좌측"), ((tbl, row - 1, col), "상단")):
            ntext = _cell_joined(nkey)
            if ntext:
                label = f"{tag}: {_preview(ntext, 24)}"
                break
        signals = ["empty_cell"]
        cprid = plist[0].first_char_pr_id
        if cprid is not None:
            style = chars.get(str(cprid))
            if style is not None:
                height = style.attributes.get("height")
                size = f"{int(height) / 100:g}pt" if height and height.isdigit() else "?"
                bold = "·bold" if "bold" in style.child_attributes else ""
                signals.append(f"format:{size}{bold}")
        empty_cell_candidates.append(
            Candidate(
                location=plist[0].location(), signals=signals, confidence="medium",
                text_preview=label or "(라벨 없음)", cell=plist[0].cell,
            )
        )

    # 질문 목록
    questions: list[str] = []
    bound = {b.family for b in legend}
    for hex_color, info in sorted(inventory.items(), key=lambda kv: -kv[1]["runs"]):
        if info["family"] not in bound and info["runs"] >= 3:
            questions.append(
                f"`{hex_color}`({info['family']}) run {info['runs']}개의 의미가 범례에 없음 — 유지/수정/삭제 중 무엇인가? 예: {info['samples'][0] if info['samples'] else ''}"
            )
    for c in conditional_choices:
        questions.append(f"{c.location} 조건부 블록 — 어느 쪽을 남길지 결정 필요: “{c.text_preview[:60]}”")
    for c in placeholder_candidates:
        if "placeholder:circle_blank" in c.signals:
            questions.append(f"{c.location} 빈칸(◯◯◯) — 들어갈 실제 값은? “{c.text_preview[:40]}”")
    if not legend:
        questions.append("색 범례 문장을 찾지 못함 — 색의 의미(유지/수정/삭제)를 알려달라.")

    return GuidanceReport(
        source=src_name,
        color_inventory=inventory,
        legend=legend,
        delete_candidates=delete_candidates,
        modify_candidates_by_table=modify_by_table,
        placeholder_candidates=placeholder_candidates,
        conditional_choices=conditional_choices,
        questions=questions,
        empty_cell_candidates=empty_cell_candidates,
        stats={
            "paragraphs": len(paragraphs),
            "tables": tables_total,
            "colored_runs": colored_runs,
        },
    )
