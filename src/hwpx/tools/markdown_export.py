"""Rich HWPX → Markdown converter.

Preserves:
- 인라인 서식 (bold/italic/color/shade) via run charPrIDRef diff
- 표 병합 셀 (colspan/rowspan) via HTML
- 중첩 표 재귀 HTML
- 도형(rect/ellipse/polygon) 내부 paragraph
- 이미지 (BinData → ![image](path))
- 헤딩 (Ⅰ. / 1. 패턴)
- 각주/미주 정확 위치 + fn1/en1 일련번호 + 본문 인라인 서식
- 하이퍼링크 [text](url) (fieldBegin/End 추적)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html import escape as html_escape
from pathlib import Path
from typing import Union

from ..document import HwpxDocument
from ..oxml.namespaces import tag_local_name

# 도형은 rect/ellipse/polygon만 순회. drawText/container는 이들의 자식이라
# 별도 순회하면 같은 paragraph가 중복 처리됨.
SHAPE_TAGS = ("rect", "ellipse", "polygon")

ROMAN_HEAD = re.compile(r"^\s*[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]\.\s*.+")
ARABIC_HEAD = re.compile(r"^\s*\d+\.\s+[가-힣A-Za-z].+")


# ──────────────────────────────────────────────────────────────────
# 인라인 서식
# ──────────────────────────────────────────────────────────────────
def _local_name(element) -> str:
    return tag_local_name(str(element.tag))


def _direct_children(element, local_name: str):
    return [child for child in list(element) if _local_name(child) == local_name]


def _descendants(element, local_name: str):
    return [
        child
        for child in element.iter()
        if child is not element and _local_name(child) == local_name
    ]


def _first_descendant(element, local_name: str):
    for child in element.iter():
        if child is not element and _local_name(child) == local_name:
            return child
    return None


def _has_descendant(element, local_name: str) -> bool:
    return _first_descendant(element, local_name) is not None


def _escape_markdown_text(text: str) -> str:
    """Escape source text before applying generated Markdown/HTML wrappers."""
    escaped = html_escape(text, quote=False)
    for char in ("\\", "`", "*", "[", "]", "|"):
        escaped = escaped.replace(char, "\\" + char)
    return escaped


def _diff_style(cp, base_cp) -> dict:
    if cp is None:
        return {}
    ca, a = cp.child_attributes, cp.attributes
    base_ca = base_cp.child_attributes if base_cp is not None else {}
    base_a = base_cp.attributes if base_cp is not None else {}

    bold = "bold" in ca and "bold" not in base_ca
    italic = "italic" in ca and "italic" not in base_ca
    underline = (
        ca.get("underline", {}).get("type", "NONE") != "NONE"
        and base_ca.get("underline", {}).get("type", "NONE") == "NONE"
    )
    strike = (
        ca.get("strikeout", {}).get("shape", "NONE") != "NONE"
        and base_ca.get("strikeout", {}).get("shape", "NONE") == "NONE"
    )
    color = a.get("textColor", "#000000")
    base_color = base_a.get("textColor", "#000000")
    # 흰색은 어두운 배경 위 디자인 효과로 가정 → 시각 의미 없음
    color_changed = (
        color != base_color and color.upper() not in ("#000000", "#FFFFFF")
    )
    shade = a.get("shadeColor", "none")
    base_shade = base_a.get("shadeColor", "none")
    shade_changed = shade.lower() not in ("none", "", base_shade.lower())

    return {
        "bold": bold,
        "italic": italic,
        "underline": underline,
        "strike": strike,
        "color": color if color_changed else None,
        "shade": shade if shade_changed else None,
    }


def _wrap(text: str, style: dict) -> str:
    if not text:
        return ""
    out = text
    if style.get("shade"):
        out = f'<mark style="background-color:{style["shade"]}">{out}</mark>'
    if style.get("color"):
        out = f'<span style="color:{style["color"]}">{out}</span>'
    if style.get("underline"):
        out = f"<u>{out}</u>"
    if style.get("strike"):
        out = f"~~{out}~~"
    if style.get("italic"):
        out = f"*{out}*"
    if style.get("bold"):
        out = f"**{out}**"
    return out


def _style_key(style: dict) -> tuple:
    return tuple(sorted((k, v) for k, v in style.items() if v))


def _render_runs(items, base_cp, chars) -> str:
    """[(cpr_id, text)] 시퀀스를 인접 동일 서식 머지 후 markdown으로."""
    groups: list[tuple[tuple, str]] = []
    for cpr, text in items:
        if not text:
            continue
        cp = chars.get(str(cpr), base_cp)
        style = _diff_style(cp, base_cp)
        key = _style_key(style)
        escaped = _escape_markdown_text(text)
        if groups and groups[-1][0] == key:
            groups[-1] = (key, groups[-1][1] + escaped)
        else:
            groups.append((key, escaped))
    return "".join(_wrap(text, dict(key)) for key, text in groups)


# ──────────────────────────────────────────────────────────────────
# 이미지 매핑
# ──────────────────────────────────────────────────────────────────
def _build_image_map(
    doc: HwpxDocument,
    image_dir: Path | None,
    image_ref_prefix: str | None,
) -> dict[str, str]:
    """doc._package의 BinData/* 를 image_dir에 추출하고 {ref_stem → rel_path} 반환.
    image_dir이 None이면 추출 없이 빈 dict (마크다운에 ![image]() 안 들어감).
    """
    if image_dir is None:
        return {}
    image_dir = Path(image_dir)
    image_dir.mkdir(parents=True, exist_ok=True)
    prefix = image_ref_prefix if image_ref_prefix is not None else image_dir.name
    mapping: dict[str, str] = {}
    pkg = doc._package
    for name in pkg.files():
        if not name.startswith("BinData/"):
            continue
        data = pkg.read(name)
        fname = Path(name).name
        (image_dir / fname).write_bytes(data)
        mapping[Path(name).stem] = f"{prefix}/{fname}" if prefix else fname
    return mapping


def _paragraph_images(p_el, mapping: dict[str, str]) -> list[str]:
    """paragraph element 안 모든 <hp:pic> → markdown 이미지 라인."""
    out = []
    for pic in _descendants(p_el, "pic"):
        img = _first_descendant(pic, "img")
        if img is None:
            continue
        ref = img.get("binaryItemIDRef")
        if not ref or not mapping:
            continue
        rel = mapping.get(ref, f"BinData/{ref}")
        out.append(f"![image]({rel})")
    return out


# ──────────────────────────────────────────────────────────────────
# Paragraph element → markdown (재귀 진입점)
# ──────────────────────────────────────────────────────────────────
@dataclass
class _MdParagraphState:
    """Accumulator threaded through the run/ctrl/note handlers below.

    A dataclass (not bare locals in a closure) so each handler can be a
    plain top-level function instead of a nested closure over ``nonlocal``.
    """

    output: list[str] = field(default_factory=list)
    items: list[tuple] = field(default_factory=list)
    link_url: str | None = None
    link_items: list[tuple] = field(default_factory=list)


def _md_flush_items(state: _MdParagraphState, base_cp, chars) -> None:
    if state.items:
        state.output.append(_render_runs(state.items, base_cp, chars))
        state.items = []


def _md_flush_link(state: _MdParagraphState, base_cp, chars) -> None:
    if state.link_url is None:
        return
    text = _render_runs(state.link_items, base_cp, chars)
    if text:
        state.output.append(f"[{text}]({state.link_url})" if state.link_url else text)
    state.link_url = None
    state.link_items = []


def _md_push_text(state: _MdParagraphState, cpr, text) -> None:
    if state.link_url is not None:
        state.link_items.append((cpr, text))
    else:
        state.items.append((cpr, text))


def _md_handle_ctrl_child(child, state: _MdParagraphState, base_cp, chars) -> None:
    for gc in child:
        gctag = _local_name(gc)
        if gctag == "fieldBegin" and gc.get("type") == "HYPERLINK":
            _md_flush_items(state, base_cp, chars)
            state.link_url = gc.get("name", "")
        elif gctag == "fieldEnd":
            _md_flush_link(state, base_cp, chars)


def _md_handle_note_child(
    child, tag: str, state: _MdParagraphState, base_cp, chars, doc, notes_out: list | None
) -> None:
    inst_id = child.get("instId", "")
    kind = "fn" if tag == "footNote" else "en"
    marker = f"[^{kind}{inst_id}]"
    if state.link_url is not None:
        _md_flush_link(state, base_cp, chars)
    else:
        _md_flush_items(state, base_cp, chars)
    state.output.append(marker)
    if notes_out is not None:
        body_parts = []
        for fp in _descendants(child, "p"):
            sub_md = _p_element_to_md(fp, doc, None).strip()
            if sub_md:
                body_parts.append(sub_md)
        notes_out.append((kind, inst_id, " ".join(body_parts)))


def _p_element_to_md(p_el, doc, notes_out: list | None = None) -> str:
    chars = doc._root.char_properties
    base_cp = chars.get("0")
    state = _MdParagraphState()

    for run in _direct_children(p_el, "run"):
        cpr = run.get("charPrIDRef", "0")
        for child in run:
            tag = _local_name(child)
            if tag == "t":
                if child.text:
                    _md_push_text(state, cpr, child.text)
            elif tag == "ctrl":
                _md_handle_ctrl_child(child, state, base_cp, chars)
            elif tag in ("footNote", "endNote"):
                _md_handle_note_child(child, tag, state, base_cp, chars, doc, notes_out)

    _md_flush_items(state, base_cp, chars)
    _md_flush_link(state, base_cp, chars)
    return "".join(state.output)


# ──────────────────────────────────────────────────────────────────
# 도형 / 셀 / 표
# ──────────────────────────────────────────────────────────────────
def _shape_text_lines(scope_el, doc, notes_out: list | None = None) -> list[str]:
    lines: list[str] = []
    seen_p = set()
    for tag in SHAPE_TAGS:
        for shape in _descendants(scope_el, tag):
            for sub_p in _descendants(shape, "p"):
                pid = id(sub_p)
                if pid in seen_p:
                    continue
                seen_p.add(pid)
                md = _p_element_to_md(sub_p, doc, notes_out).strip()
                if md:
                    lines.append(md)
    return lines


def _cell_to_md(cell, doc, mapping, depth: int = 0, notes_out: list | None = None) -> str:
    chunks: list[str] = []
    for cp in cell.paragraphs:
        md = _p_element_to_md(cp.element, doc, notes_out).strip()
        imgs = _paragraph_images(cp.element, mapping)
        shape_lines = _shape_text_lines(cp.element, doc, notes_out)
        if md:
            chunks.append(md)
        chunks.extend(shape_lines)
        chunks.extend(imgs)
        for sub in cp.tables:
            chunks.append(_table_to_md(sub, doc, mapping, depth + 1, notes_out))
    return "<br>".join(c for c in chunks if c).strip()


def _table_to_md(tbl, doc, mapping, depth: int = 0, notes_out: list | None = None) -> str:
    grid = tbl.get_cell_map()
    rows, cols = tbl.row_count, tbl.column_count
    has_merge = any(not pos.is_anchor for row in grid for pos in row)

    if has_merge or depth > 0:
        # 병합 셀 또는 중첩 — HTML
        out = ["<table>"]
        for r in range(rows):
            out.append("<tr>")
            for c in range(cols):
                pos = grid[r][c]
                if not pos.is_anchor:
                    continue
                col_end = c
                while (
                    col_end + 1 < cols
                    and not grid[r][col_end + 1].is_anchor
                    and grid[r][col_end + 1].cell is pos.cell
                ):
                    col_end += 1
                row_end = r
                while (
                    row_end + 1 < rows
                    and not grid[row_end + 1][c].is_anchor
                    and grid[row_end + 1][c].cell is pos.cell
                ):
                    row_end += 1
                colspan = col_end - c + 1
                rowspan = row_end - r + 1
                attrs = []
                if colspan > 1:
                    attrs.append(f'colspan="{colspan}"')
                if rowspan > 1:
                    attrs.append(f'rowspan="{rowspan}"')
                attr_s = (" " + " ".join(attrs)) if attrs else ""
                content = _cell_to_md(pos.cell, doc, mapping, depth + 1, notes_out)
                tag = "th" if r == 0 else "td"
                out.append(f"<{tag}{attr_s}>{content}</{tag}>")
            out.append("</tr>")
        out.append("</table>")
        return "\n".join(out)

    # 단순 — GFM
    lines = []
    for r in range(rows):
        cells = [
            _cell_to_md(grid[r][c].cell, doc, mapping, depth + 1, notes_out)
            for c in range(cols)
        ]
        lines.append("| " + " | ".join(cells) + " |")
        if r == 0:
            lines.append("| " + " | ".join(["---"] * cols) + " |")
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────
# 헤딩 감지
# ──────────────────────────────────────────────────────────────────
def _detect_heading(text: str) -> str | None:
    plain = re.sub(r"~~|\*\*|<[^>]+>|\*", "", text.strip())
    plain = plain.replace("\\[", "[").replace("\\]", "]").replace("\\|", "|")
    if ROMAN_HEAD.match(plain):
        return f"# {plain}"
    if ARABIC_HEAD.match(plain) and len(plain) < 40:
        return f"## {plain}"
    return None


# ──────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────
def _export_resolve_doc(source: Union[HwpxDocument, str, Path, bytes]) -> HwpxDocument:
    if isinstance(source, HwpxDocument):
        return source
    if isinstance(source, (bytes, bytearray)):
        import io
        return HwpxDocument.open(io.BytesIO(source))
    return HwpxDocument.open(str(source))


def _export_dedupe_md(md: str, p) -> str:
    # 중복 가드 1: paragraph text가 표 셀 안에 동일하게 들어있으면 표가 정식
    if md and p.tables:
        plain = (p.text or "").strip()
        all_cell_text = "".join(
            (cell.text or "")
            for tbl in p.tables
            for row in tbl.rows
            for cell in row.cells
        )
        if plain and plain in all_cell_text:
            md = ""

    # 중복 가드 2: 도형 보유 시 paragraph text는 도형 텍스트의 흘러나옴
    if md and any(_has_descendant(p.element, tag) for tag in SHAPE_TAGS):
        md = ""
    return md


def _export_shape_lines(p, doc, notes) -> list[str]:
    # 도형 내부 paragraph 추출 (표 안 도형은 cell_to_md에서 처리됨)
    shape_lines: list[str] = []
    seen_p = set()
    for sub in p.tables:
        for nested_p in _descendants(sub.element, "p"):
            seen_p.add(id(nested_p))
    for tag in SHAPE_TAGS:
        for shape in _descendants(p.element, tag):
            for sub_p in _descendants(shape, "p"):
                pid = id(sub_p)
                if pid in seen_p:
                    continue
                seen_p.add(pid)
                sub_md = _p_element_to_md(sub_p, doc, notes).strip()
                if sub_md:
                    shape_lines.append(sub_md)
    return shape_lines


def _export_paragraph_lines(p, doc, mapping, notes, detect_headings: bool) -> list[str]:
    md = _p_element_to_md(p.element, doc, notes).strip()
    imgs = _paragraph_images(p.element, mapping)
    tables = [_table_to_md(t, doc, mapping, 0, notes) for t in p.tables]

    md = _export_dedupe_md(md, p)
    shape_lines = _export_shape_lines(p, doc, notes)

    # 헤딩 감지 (1x1 표 셀에 있는 경우 포함)
    promoted = None
    if detect_headings:
        if md:
            promoted = _detect_heading(md)
        elif p.tables and len(p.tables) == 1:
            t = p.tables[0]
            if t.row_count == 1 and t.column_count == 1:
                cell_text = _cell_to_md(
                    t.rows[0].cells[0], doc, mapping, 0, notes
                )
                promoted = _detect_heading(cell_text)
                if promoted:
                    return [promoted]

    out: list[str] = []
    if promoted:
        out.append(promoted)
    elif md:
        out.append(md)
    out.extend(shape_lines)
    out.extend(imgs)
    out.extend(tables)
    return out


def _export_notes_appendix(body: str, notes, notes_section_separator: str) -> str:
    # 각주/미주 instId → fn1/en1 일련번호 매핑 + 정의 부록
    seq_map: dict[str, dict[str, int]] = {"fn": {}, "en": {}}
    for kind, inst_id, _ in notes:
        if inst_id not in seq_map[kind]:
            seq_map[kind][inst_id] = len(seq_map[kind]) + 1

    for kind, m in seq_map.items():
        for inst_id, seq in m.items():
            body = body.replace(f"[^{kind}{inst_id}]", f"[^{kind}{seq}]")

    body += notes_section_separator
    seen = set()
    for kind, inst_id, text in notes:
        key = (kind, inst_id)
        if key in seen:
            continue
        seen.add(key)
        seq = seq_map[kind][inst_id]
        body += f"\n[^{kind}{seq}]: {text}\n"
    return body


def export_markdown(
    source: Union[HwpxDocument, str, Path, bytes],
    *,
    image_dir: Union[str, Path, None] = None,
    image_ref_prefix: str | None = None,
    detect_headings: bool = True,
    notes_section_separator: str = "\n\n---\n",
) -> str:
    """HWPX → rich markdown.

    Parameters
    ----------
    source : HwpxDocument | path | bytes
        HwpxDocument 인스턴스 또는 파일 경로/바이트.
    image_dir : path | None
        BinData/* 추출 대상 디렉토리. None이면 이미지 마커 생성하지 않음.
    image_ref_prefix : str | None
        markdown 이미지 경로의 prefix. None이면 image_dir의 basename.
    detect_headings : bool
        Ⅰ./1. 패턴 감지로 `#`/`##` 헤딩 격상 여부.
    notes_section_separator : str
        각주/미주 정의 부록 앞에 삽입할 separator.
    """
    doc = _export_resolve_doc(source)
    mapping = _build_image_map(doc, Path(image_dir) if image_dir else None, image_ref_prefix)
    notes: list[tuple] = []
    lines: list[str] = []

    for section in doc.sections:
        for p in section.paragraphs:
            lines.extend(_export_paragraph_lines(p, doc, mapping, notes, detect_headings))

    body = "\n\n".join(lines)

    if notes:
        body = _export_notes_appendix(body, notes, notes_section_separator)

    return body
