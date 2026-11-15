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
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from html import escape as html_escape
from pathlib import Path
from typing import Union

from ..document import HwpxDocument
from ..errors import HwpxTypeError, HwpxValueError
from ..oxml._document_primitives import _text_element_content
from ..oxml.hyperlink_form import hyperlink_target
from ..oxml.namespaces import tag_local_name
from .exporter import HEADING_MAX_CHARS, _Headings, _header_xml, _ListLabels, escape_line_starts, escape_markdown

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


# 이름으로 고르는 순회는 lxml(과 ElementTree)의 ``{*}이름`` 태그 지정 순회로 한다. 모든 요소의
# 이름을 파이썬에서 꺼내 비교하면 큰 표(5천 행)에서 수백만 번 불린다.
def _direct_children(element, local_name: str):
    return element.findall("{*}" + local_name)


def _descendants(element, local_name: str):
    return [child for child in element.iter("{*}" + local_name) if child is not element]


def _first_descendant(element, local_name: str):
    for child in element.iter("{*}" + local_name):
        if child is not element:
            return child
    return None


def _has_descendant(element, local_name: str) -> bool:
    return _first_descendant(element, local_name) is not None


#: 지금 쓰는 자리: ``""`` 문단(Markdown), ``"pipe"`` 파이프 표 칸(Markdown, ``|`` 이스케이프),
#: ``"html"`` HTML 표 칸(HTML 블록 안에서는 Markdown 서식이 읽히지 않으므로 HTML로 쓴다),
#: ``"html_inline"`` 파이프 칸 안에 든 HTML 표의 칸(서식은 HTML로 쓰되, 둘레가 Markdown 줄이라
#: 글은 파이프 칸처럼 이스케이프한다: 이스케이프하지 않은 ``` ` ```·``*``는 칸을 넘어 짝을 짓는다).
_CELL: ContextVar[str] = ContextVar("hwpx_markdown_cell", default="")
#: 글자색·음영을 ``<span>``·``<mark>``로 싣는가.
_COLORS: ContextVar[bool] = ContextVar("hwpx_markdown_colors", default=True)


def _html_cell() -> bool:
    return _CELL.get().startswith("html")


def _escape_markdown_text(text: str) -> str:
    """Escape source text before applying generated Markdown/HTML wrappers."""
    mode = _CELL.get()
    if mode == "html":
        return html_escape(text, quote=False)
    return escape_markdown(text, pipe=mode in ("pipe", "html_inline"))


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


_HEX_COLOR_RE = re.compile(r"#(?:[0-9A-Fa-f]{8}|[0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})\Z")
_LINK_SCHEMES = ("http://", "https://", "mailto:")
_LINK_ESCAPES = {ord(ch): f"%{ord(ch):02X}" for ch in " \t\r\n()<>\"'`\\"}
# Members written to ``image_dir`` keep their name, so only image types go out.
_IMAGE_SUFFIXES = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp", ".svg", ".wmf", ".emf", ".ico"}
)
_WINDOWS_DEVICE_NAMES = frozenset(
    {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
)


def _hex_color(value: object) -> str | None:
    """Return ``value`` when it is a bare hex colour; the value goes into raw HTML."""

    return value if isinstance(value, str) and _HEX_COLOR_RE.match(value) else None


def _safe_link_url(url: str | None) -> str | None:
    """Return a link target that cannot leave the ``(...)`` of a Markdown link.

    Only web and mail targets are linked; any other scheme (``javascript:``,
    ``file:``, a UNC path) is dropped and the text is written unlinked.
    """

    if not url:
        return None
    candidate = url.strip()
    if not candidate.lower().startswith(_LINK_SCHEMES):
        return None
    return candidate.translate(_LINK_ESCAPES)


def _image_file_name(member: str) -> str | None:
    """Return the file name to write for a ``BinData/`` member, or ``None``.

    The name comes from the package, so it is reduced to a single path
    component with an image suffix: no drive (``C:name``), no stream
    (``name:x``), no device name and no leading or trailing dot or space.
    """

    name = member.replace("\\", "/").rsplit("/", 1)[-1]
    if not name or name != name.strip(" .") or any(ch in name for ch in ':*?"<>|') or any(ord(ch) < 32 for ch in name):
        return None
    stem, dot, suffix = name.rpartition(".")
    if not dot or not stem or f".{suffix.lower()}" not in _IMAGE_SUFFIXES:
        return None
    if stem.split(".", 1)[0].lower() in _WINDOWS_DEVICE_NAMES:
        return None
    return name


def _wrap(text: str, style: dict) -> str:
    """서식을 입힌다. 공백뿐인 글은 그대로 두고, 앞뒤 공백은 표시 밖에 둔다
    (``** **``나 ``**굵게 **``는 Markdown에서 굵게로 읽히지 않는다)."""
    if not text:
        return ""
    out = text.strip()
    if not out:
        return text
    start = text.index(out)
    lead, trail = text[:start], text[start + len(out) :]
    html = _html_cell()
    if _COLORS.get():
        shade = _hex_color(style.get("shade"))
        color = _hex_color(style.get("color"))
        if shade:
            out = f'<mark style="background-color:{shade}">{out}</mark>'
        if color:
            out = f'<span style="color:{color}">{out}</span>'
    if style.get("underline"):
        out = f"<u>{out}</u>"
    if style.get("strike"):
        out = f"<del>{out}</del>" if html else f"~~{out}~~"
    if style.get("italic"):
        out = f"<em>{out}</em>" if html else f"*{out}*"
    if style.get("bold"):
        out = f"<strong>{out}</strong>" if html else f"**{out}**"
    return lead + out + trail


def _style_key(style: dict) -> tuple:
    return tuple(sorted((k, v) for k, v in style.items() if v))


def _render_runs(items, base_cp, chars, *, link: bool = False) -> str:
    """[(cpr_id, text)] 시퀀스를 인접 동일 서식 머지 후 markdown으로.

    *link*면 밑줄·글자색은 싣지 않는다 — 링크 표기가 이미 그 모양이다(한컴도 링크 글을
    파랑 밑줄로 쓴다).
    """
    groups: list[tuple[tuple, str]] = []
    for cpr, text in items:
        if not text:
            continue
        cp = chars.get(str(cpr), base_cp)
        style = _diff_style(cp, base_cp)
        if link:
            style = {**style, "underline": False, "color": None}
        if not _COLORS.get():
            style = {**style, "color": None, "shade": None}
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
        fname = _image_file_name(name)
        if fname is None:
            continue
        data = pkg.read(name)
        (image_dir / fname).write_bytes(data)
        mapping[Path(name).stem] = f"{prefix}/{fname}" if prefix else fname
    return mapping


def _element_caption_text(el) -> str | None:
    """이 개체(hp:pic/hp:tbl/도형)의 hp:caption 텍스트, 없으면 None.

    markdown_export는 raw ElementTree를 순회하므로 ``hwpx.oxml.objects``의
    ``Caption`` 라이브 객체(section 참조가 필요) 대신 이 모듈 자체의
    ``_descendants``/``_direct_children`` 관용구로 직접 읽는다."""

    captions = _direct_children(el, "caption")
    if not captions:
        return None
    text = "".join("".join(t.itertext()) for t in _descendants(captions[0], "t")).strip()
    return text or None


def _paragraph_images(p_el, mapping: dict[str, str]) -> list[str]:
    """paragraph element 안 모든 <hp:pic> → markdown 이미지(+캡션) 라인.

    그림을 꺼내지 않아(``mapping``이 비어) 이미지 줄을 쓰지 않을 때에도 캡션은 쓴다.
    캡션은 문서의 글이다."""
    out = []
    html = _html_cell()
    for pic in _descendants(p_el, "pic"):
        img = _first_descendant(pic, "img")
        ref = img.get("binaryItemIDRef") if img is not None else None
        if ref and mapping:
            rel = mapping.get(ref, f"BinData/{ref}").translate(_LINK_ESCAPES)
            out.append(f'<img src="{html_escape(rel)}" alt="image">' if html else f"![image]({rel})")
        caption_text = _element_caption_text(pic)
        if caption_text:
            out.append(_caption_line(caption_text))
    # 그림·표 밖 개체(묶음 개체·도형·OLE 등)의 캡션도 문서의 글이다. 이 문단 자신의 것만 싣는다
    # (칸·글상자 안 문단의 캡션은 그 문단에서 싣는다).
    for caption in _descendants(p_el, "caption"):
        owner = caption.getparent()
        if owner is None or _local_name(owner) in ("pic", "tbl", *SHAPE_TAGS):
            continue  # 그림·표는 위와 표에서, 도형 캡션 문단은 도형 글에서 싣는다
        parent = owner
        while parent is not None and parent is not p_el and _local_name(parent) != "p":
            parent = parent.getparent()
        if parent is not p_el:
            continue
        caption_text = _element_caption_text(owner)
        if caption_text:
            out.append(_caption_line(caption_text))
    return out


def _caption_line(text: str) -> str:
    escaped = _escape_markdown_text(text)
    return f"<em>{escaped}</em>" if _html_cell() else f"*{escaped}*"


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
    #: 이 문단 안에서 끝나는 메모 필드의 id (표시를 필드 끝에 둔다).
    field_ends: frozenset[str] = frozenset()
    pending_memos: dict[str, str] = field(default_factory=dict)


#: 이 내보내기가 수식을 싣는가. 각주·메모·머리말 안쪽 문단까지 같은 값을 본다.
_EQUATIONS: ContextVar[bool] = ContextVar("hwpx_markdown_equations", default=False)


def equation_markdown(script: str) -> str:
    """한/글 수식 문자열을 Markdown 인라인 수식(``$LaTeX$``)으로.

    LaTeX로 옮기지 못하는 수식은 한/글 수식 문자열을 그대로 코드(`` `…` ``)로 싣는다.
    빈 수식은 빈 문자열이다.
    """

    text = " ".join(script.split())
    if not text:
        return ""
    from ..equation.eqedit import EquationConversionError, eqedit_to_latex

    try:
        latex = eqedit_to_latex(text)
    except (EquationConversionError, RecursionError):
        latex = ""
    if not latex or "$" in latex:
        return "`" + text.replace("`", "'") + "`"
    # ``<``·``>`` 는 Markdown에서 HTML 태그로 읽힐 수 있다. LaTeX의 같은 기호 명령으로 쓴다.
    latex = latex.replace("<", r"\lt ").replace(">", r"\gt ")
    return f"${latex}$"


class _Notes(list):
    """각주·미주(와 메모) 정의를 모으는 목록. ``memos``가 참이면 메모도 모은다."""

    memos: bool = False

    def key(self, note) -> tuple[str, bool]:
        """각주 요소 *note* 의 정의 이름과, 처음 보는 각주인지.

        한/글 5.0 문서에서 옮긴 각주는 ``instId``가 모두 같을 수 있다. 그 번호로 묶으면
        첫 각주의 글만 남으므로 요소마다 이름을 준다. 같은 요소를 다시 그려도 한 번만 싣는다.
        """
        keys = self.__dict__.setdefault("_keys", {})
        if note in keys:
            return keys[note], False
        keys[note] = f"n{len(keys) + 1}"
        return keys[note], True


def _md_flush_items(state: _MdParagraphState, base_cp, chars) -> None:
    if state.items:
        state.output.append(_render_runs(state.items, base_cp, chars))
        state.items = []


def _md_flush_link(state: _MdParagraphState, base_cp, chars) -> None:
    if state.link_url is None:
        return
    text = _render_runs(state.link_items, base_cp, chars, link=True)
    if text:
        url = _safe_link_url(state.link_url)
        if url and _html_cell():
            state.output.append(f'<a href="{html_escape(url)}">{text}</a>')
        else:
            state.output.append(f"[{text}]({url})" if url else text)
    state.link_url = None
    state.link_items = []


def _md_push_text(state: _MdParagraphState, cpr, text) -> None:
    if state.link_url is not None:
        state.link_items.append((cpr, text))
    else:
        state.items.append((cpr, text))


def _md_handle_ctrl_child(child, state: _MdParagraphState, base_cp, chars, doc=None, notes_out=None) -> None:
    for gc in child:
        gctag = _local_name(gc)
        if gctag == "fieldBegin" and gc.get("type") == "HYPERLINK":
            _md_flush_items(state, base_cp, chars)
            state.link_url = hyperlink_target(gc)
        elif gctag == "fieldBegin" and gc.get("type") == "MEMO":
            _md_handle_memo(gc, state, base_cp, chars, doc, notes_out)
        elif gctag == "fieldEnd":
            _md_flush_link(state, base_cp, chars)
            marker = state.pending_memos.pop(gc.get("beginIDRef") or "", None)
            if marker:
                _md_flush_items(state, base_cp, chars)
                state.output.append(marker)
        elif gctag in ("footNote", "endNote"):
            # 실한컴 계약: 각주/미주는 run 안 <hp:ctrl>에 래핑되어 있다.
            _md_handle_note_child(gc, gctag, state, base_cp, chars, doc, notes_out)


def _md_handle_memo(field_begin, state: _MdParagraphState, base_cp, chars, doc, notes_out: list | None) -> None:
    """메모(``fieldBegin type="MEMO"``)를 각주처럼 싣는다: 메모가 걸린 글 뒤에 표시, 내용은 부록.

    메모를 모으지 않는 호출(``memos=False``)과 각주·메모 안쪽(``notes_out is None``)에서는 건너뛴다.
    """

    if notes_out is None or not getattr(notes_out, "memos", False):
        return
    body_parts = _note_body(
        [memo_p for sub_list in _direct_children(field_begin, "subList") for memo_p in _descendants(sub_list, "p")],
        doc,
    )
    if not body_parts:
        return
    field_id = field_begin.get("id") or ""
    inst_id, first = notes_out.key(field_begin) if isinstance(notes_out, _Notes) else (f"{field_id}#{len(notes_out)}", True)
    marker = f"[^memo{inst_id}]"
    if first:
        notes_out.append(("memo", inst_id, "메모: " + " ".join(body_parts)))
    if field_id and field_id in state.field_ends:
        state.pending_memos[field_id] = marker  # 메모가 걸린 글 뒤에
    else:
        _md_flush_items(state, base_cp, chars)
        state.output.append(marker)


def _md_handle_note_child(
    child, tag: str, state: _MdParagraphState, base_cp, chars, doc, notes_out: list | None
) -> None:
    inst_id = child.get("instid") or child.get("instId", "")
    kind = "fn" if tag == "footNote" else "en"
    first = True
    if isinstance(notes_out, _Notes):
        inst_id, first = notes_out.key(child)
    marker = f"[^{kind}{inst_id}]"
    if state.link_url is not None:
        _md_flush_link(state, base_cp, chars)
    else:
        _md_flush_items(state, base_cp, chars)
    state.output.append(marker)
    if notes_out is not None and first:
        notes_out.append((kind, inst_id, " ".join(_note_body(_descendants(child, "p"), doc))))


def _note_body(paragraphs, doc) -> list[str]:
    """각주·메모의 문단들을 부록 한 줄에 실을 Markdown으로. 표 칸 안 각주라도 부록은 문단 자리다."""
    token = _CELL.set("")
    try:
        parts = [_p_element_to_md(p, doc, None).strip() for p in paragraphs]
    finally:
        _CELL.reset(token)
    return [" ".join(part.split("\n")) for part in parts if part]


def _p_element_to_md(p_el, doc, notes_out: list | None = None) -> str:
    chars = doc._root.char_properties
    base_cp = chars.get("0")
    state = _MdParagraphState()
    if getattr(notes_out, "memos", False):
        state.field_ends = frozenset(
            end.get("beginIDRef") or ""
            for run in _direct_children(p_el, "run")
            for ctrl in _direct_children(run, "ctrl")
            for end in _direct_children(ctrl, "fieldEnd")
        )

    for run in _direct_children(p_el, "run"):
        cpr = run.get("charPrIDRef", "0")
        for child in run:
            tag = _local_name(child)
            if tag == "t":
                # 한/글의 하이픈(hp:hyphen)은 보이는 붙임표다(평문 내보내기와 같다).
                text = _text_element_content(child).replace("­", "-")
                if text:
                    _md_push_text(state, cpr, text)
            elif tag == "dutmal":
                # 덧말은 평문 내보내기처럼 본말 뒤에 (덧말:…)로 싣는다.
                main = "".join("".join(c.itertext()) for c in _direct_children(child, "mainText"))
                sub = "".join("".join(c.itertext()) for c in _direct_children(child, "subText"))
                text = f"{main}(덧말:{sub})" if sub else main
                if text:
                    _md_push_text(state, cpr, text)
            elif tag == "ctrl":
                _md_handle_ctrl_child(child, state, base_cp, chars, doc, notes_out)
            elif tag == "equation" and _EQUATIONS.get():
                script = next(iter(_direct_children(child, "script")), None)
                rendered = equation_markdown("".join(script.itertext())) if script is not None else ""
                mode = _CELL.get()
                if mode in ("pipe", "html_inline"):
                    rendered = rendered.replace("|", "\\|")
                elif mode == "html":
                    rendered = html_escape(rendered, quote=False)
                if rendered:
                    if state.link_url is not None:
                        _md_flush_link(state, base_cp, chars)
                    else:
                        _md_flush_items(state, base_cp, chars)
                    state.output.append(rendered)
            elif tag in ("footNote", "endNote"):
                # 구식(5.4 이전 자사 방출) 호환: run 직속 각주도 계속 읽는다.
                _md_handle_note_child(child, tag, state, base_cp, chars, doc, notes_out)

    _md_flush_items(state, base_cp, chars)
    _md_flush_link(state, base_cp, chars)
    state.output.extend(state.pending_memos.values())
    return "".join(state.output)


# ──────────────────────────────────────────────────────────────────
# 도형 / 셀 / 표
# ──────────────────────────────────────────────────────────────────
def _shape_text_lines(scope_el, doc, notes_out: list | None = None) -> list[str]:
    lines: list[str] = []
    # 요소 자체를 담아 둔다: id()는 풀린 lxml 프록시의 번호를 다른 요소가 다시 받아
    # 처음 보는 문단을 본 것으로 여길 수 있다.
    seen_p = set()
    for tag in SHAPE_TAGS:
        for shape in _descendants(scope_el, tag):
            for sub_p in _descendants(shape, "p"):
                if sub_p in seen_p:
                    continue
                seen_p.add(sub_p)
                md = _labelled_md(_p_element_to_md(sub_p, doc, notes_out).strip(), sub_p, block=False)
                if md:
                    lines.append(md)
    return lines


class _LabelCache:
    """문단의 목록 번호·글머리(``_ListLabels``)를 한 번만 센다. 같은 문단을 다시 그려도 번호가 밀리지 않는다."""

    def __init__(self, labels: _ListLabels) -> None:
        self.labels = labels
        self._cache: dict = {}

    def get(self, p_el) -> tuple[str, str | None]:
        found = self._cache.get(p_el)
        if found is None:
            found = (self.labels.label(p_el), self.labels.kind(p_el))
            self._cache[p_el] = found
        return found


#: 목록 번호를 싣는가(``list_labels=``). 실을 때는 번호를 세는 _LabelCache.
_LABELS: ContextVar["_LabelCache | None"] = ContextVar("hwpx_markdown_labels", default=None)
_ORDERED_LABEL = re.compile(r"\d{1,9}[.)]\Z")


def _labelled_md(md: str, p_el, *, block: bool) -> str:
    """*md* 앞에 문단의 목록 번호·글머리를 붙인다. 문단 자리(*block*)에서는 글머리를 ``- ``로,
    ``1.``·``1)`` 꼴 번호는 그대로 Markdown 목록으로 쓴다. 다른 번호(``가.``, ``①``)는 글로 쓴다."""
    cache = _LABELS.get()
    if cache is None:
        return md
    label, kind = cache.get(p_el)
    if not label or not md:
        return md
    if block and kind == "BULLET":
        return "- " + md
    if block and _ORDERED_LABEL.match(label):
        return f"{label} {md}"
    return f"{_escape_markdown_text(label)} {md}"


def _cell_to_md(cell, doc, mapping, depth: int = 0, notes_out: list | None = None) -> str:
    chunks: list[str] = []
    for cp in cell.paragraphs:
        md = _labelled_md(_p_element_to_md(cp.element, doc, notes_out).strip(), cp.element, block=False)
        imgs = _paragraph_images(cp.element, mapping)
        shape_lines = _shape_text_lines(cp.element, doc, notes_out)
        if md:
            chunks.append(md)
        chunks.extend(shape_lines)
        chunks.extend(imgs)
        for sub in cp.tables:
            chunks.append(_table_to_md(sub, doc, mapping, depth + 1, notes_out))
    # 칸 안 줄바꿈은 <br>: 실제 줄바꿈은 파이프 표의 행을, HTML 표에서는 빈 줄이 HTML 블록을 끊는다.
    return "<br>".join(c.replace("\n", "<br>") for c in chunks if c).strip()


def _table_to_md(tbl, doc, mapping, depth: int = 0, notes_out: list | None = None) -> str:
    grid = tbl.get_cell_map()
    rows, cols = tbl.row_count, tbl.column_count
    has_merge = any(not pos.is_anchor for row in grid for pos in row)
    caption_text = _element_caption_text(tbl.element)

    if has_merge or depth > 0:
        # 병합 셀 또는 중첩 — HTML. 칸 안은 HTML로 쓴다(HTML 블록 안의 Markdown 서식은 읽히지 않는다).
        # 파이프 칸 안의 표는 Markdown 줄 안의 HTML이다.
        token = _CELL.set("html_inline" if _CELL.get() in ("pipe", "html_inline") else "html")
        try:
            return _html_table_to_md(tbl, grid, rows, cols, caption_text, doc, mapping, depth, notes_out)
        finally:
            _CELL.reset(token)

    # 단순 — GFM (표 캡션 관례: GFM에 캡션 문법이 없어 굵은 줄로 앞에 둔다)
    lines = []
    if caption_text:
        lines.append(f"**{escape_markdown(caption_text)}**")
        lines.append("")
    token = _CELL.set("pipe")
    try:
        for r in range(rows):
            cells = [
                _cell_to_md(grid[r][c].cell, doc, mapping, depth + 1, notes_out)
                for c in range(cols)
            ]
            lines.append("| " + " | ".join(cells) + " |")
            if r == 0:
                lines.append("| " + " | ".join(["---"] * cols) + " |")
    finally:
        _CELL.reset(token)
    return "\n".join(lines)


def _html_table_to_md(tbl, grid, rows, cols, caption_text, doc, mapping, depth: int, notes_out) -> str:
    if True:  # 들여쓰기를 예전 그대로 둔다
        out = ["<table>"]
        if caption_text:
            out.append(f"<caption>{_escape_markdown_text(caption_text)}</caption>")
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
        # 칸 안에 든 표는 한 줄로: 바깥 칸(파이프 표의 한 행이거나 HTML 칸)을 끊지 않는다.
        return ("" if depth > 0 else "\n").join(out)


# ──────────────────────────────────────────────────────────────────
# 헤딩 감지
# ──────────────────────────────────────────────────────────────────
def _plain_heading_text(text: str) -> str:
    """서식 표시(``**``·``*``·``~~``·태그)를 걷어 낸 제목 글. 문서 글의 이스케이프(``\\*``)는 둔다."""
    out: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text):
            out.append(text[i : i + 2])
            i += 2
        elif ch == "<":
            end = text.find(">", i)
            if end < 0:
                out.append(ch)
                i += 1
            else:
                i = end + 1
        elif text.startswith("~~", i):
            i += 2
        elif ch == "*":
            i += 1
        else:
            out.append(ch)
            i += 1
    return " ".join("".join(out).split())


def _legacy_detect_heading(text: str) -> str | None:
    """7.0 전의 글 모양 판정(``heading_source="text"``): ``Ⅰ.``은 ``#``, 짧은 ``1. 가…``은 ``##``."""
    plain = re.sub(r"~~|\*\*|<[^>]+>|\*", "", text.strip())
    plain = plain.replace("\\[", "[").replace("\\]", "]").replace("\\|", "|")
    if ROMAN_HEAD.match(plain):
        return f"# {plain}"
    if ARABIC_HEAD.match(plain) and len(plain) < 40:
        return f"## {plain}"
    return None


#: 제목이 아닌 줄: 물음(시험 문항), 차례 줄(점선·말줄임, 끝의 쪽 번호), 마침표로 끝나는 문장.
_NOT_HEADING = re.compile(r"[?？]|(?:·{2,}|\.{3,}|…|‥|-{3,}|_{3,})|[.。]\s*$|\s\d+\s*$")


def _detect_heading(text: str) -> str | None:
    """글 모양으로 제목을 짐작한다. 문서에 개요 문단이 없을 때만 쓴다.

    ``Ⅰ.`` 로 시작하는 60자 미만 줄은 ``#``, ``1. 가…`` 로 시작하는 40자 미만 줄은 ``##``.
    물음(시험 문항)·차례 줄·마침표로 끝나는 문장은 제목으로 보지 않는다.
    """
    plain = _plain_heading_text(text.strip())
    bare = re.sub(r"\\(.)", r"\1", plain)
    if _NOT_HEADING.search(bare):
        return None
    if ROMAN_HEAD.match(bare) and len(bare) < 60:
        return f"# {plain}"
    if ARABIC_HEAD.match(bare) and len(bare) < 40:
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

    # 중복 가드 2: 문단 자신의 글이 품은 도형의 글과 같을 때만 뺀다. 도형을 품은
    # 문단도 대개 제 글을 따로 가진다.
    if md and any(_has_descendant(p.element, tag) for tag in SHAPE_TAGS):
        own = "".join((p.text or "").split())
        if own and own in "".join(_shape_plain_text(p.element).split()):
            md = ""
    return md


def _shape_plain_text(p_el) -> str:
    return "".join(
        "".join(t.itertext())
        for tag in SHAPE_TAGS
        for shape in _descendants(p_el, tag)
        for t in _descendants(shape, "t")
    )


def _export_shape_lines(p, doc, notes) -> list[str]:
    # 도형 내부 paragraph 추출 (표 안 도형은 cell_to_md에서 처리됨)
    shape_lines: list[str] = []
    seen_p = set()  # 요소 자체(id()는 풀린 lxml 프록시 번호가 되풀이될 수 있다)
    for sub in p.tables:
        for nested_p in _descendants(sub.element, "p"):
            seen_p.add(nested_p)
    for tag in SHAPE_TAGS:
        for shape in _descendants(p.element, tag):
            for sub_p in _descendants(shape, "p"):
                if sub_p in seen_p:
                    continue
                seen_p.add(sub_p)
                sub_md = _p_element_to_md(sub_p, doc, notes).strip()
                sub_md = _labelled_md(escape_line_starts(sub_md), sub_p, block=True)
                if sub_md:
                    shape_lines.append(sub_md)
    return shape_lines


@dataclass
class _HeadingPlan:
    """제목을 어떻게 정하는가.

    *structure* 가 있으면 문단의 개요 수준(문단 모양의 개요, 개요 스타일)으로 정하고,
    *detector* 가 있으면 글 모양으로 짐작한다(문단·1×1 표 칸의 Markdown → 제목 줄 또는 None).
    """

    structure: "_Headings | None" = None
    detector: Callable[[str], str | None] | None = None


def _export_paragraph_lines(p, doc, mapping, notes, plan: _HeadingPlan) -> list[str]:
    cache = _LABELS.get()
    label = cache.get(p.element)[0] if cache is not None else ""  # 문단 번호를 칸 안 문단보다 먼저 센다
    md = _p_element_to_md(p.element, doc, notes).strip()
    imgs = _paragraph_images(p.element, mapping)
    tables = [_table_to_md(t, doc, mapping, 0, notes) for t in p.tables]

    md = _export_dedupe_md(md, p)
    shape_lines = _export_shape_lines(p, doc, notes)

    promoted = None
    level = plan.structure.level(p.element) if plan.structure is not None else None
    text = _plain_heading_text(md) if level is not None else ""
    if level is not None and md and len(re.sub(r"\\(.)", r"\1", text)) <= HEADING_MAX_CHARS:
        # 문서가 정한 제목: 개요 수준이 곧 제목 수준이다. 아주 긴 문단은 개요 수준에 둔 본문이다.
        if label:
            text = f"{_escape_markdown_text(label)} {text}"
        promoted = "#" * level + " " + text
    elif plan.detector is not None:
        # 글 모양 짐작 (1x1 표 셀에 있는 경우 포함)
        if md:
            promoted = plan.detector(md)
        elif p.tables and len(p.tables) == 1:
            t = p.tables[0]
            if t.row_count == 1 and t.column_count == 1:
                cell_text = _cell_to_md(
                    t.rows[0].cells[0], doc, mapping, 0, notes
                )
                promoted = plan.detector(cell_text)
                if promoted:
                    return [promoted]

    out: list[str] = []
    if promoted:
        out.append(promoted)
    elif md:
        out.append(_labelled_md(escape_line_starts(md), p.element, block=True))
    out.extend(shape_lines)
    out.extend(imgs)
    out.extend(tables)
    return out


def _section_table_lines(element) -> list[str]:
    """구역에 바로 놓인 표(문단 밖 표, 한/글이 아닌 프로그램이 쓴다)를 파이프 표로.

    이런 표는 칸 주소·병합 정보가 빠진 일이 많아 표 모델로 읽지 않고(읽으면 문서를 고친다)
    평문 Markdown 내보내기처럼 칸 주소대로 글만 싣는다.
    """
    from .exporter import _markdown_cell, _table_grid_text

    rows = _table_grid_text(element)
    if not rows:
        return []
    lines = ["| " + " | ".join(_markdown_cell(cell) for cell in rows[0]) + " |"]
    lines.append("| " + " | ".join("---" for _ in rows[0]) + " |")
    lines.extend("| " + " | ".join(_markdown_cell(cell) for cell in row) + " |" for row in rows[1:])
    caption = _element_caption_text(element)
    return ([f"**{escape_markdown(caption)}**"] if caption else []) + ["\n".join(lines)]


_PAGE_TEXT_LABELS = {"header": "머리말", "footer": "꼬리말"}
_PAGE_TYPE_LABELS = {"EVEN": "짝수 쪽", "ODD": "홀수 쪽"}


def _page_text_lines(section_el, tag: str, doc, seen: set[tuple[str, str]]) -> list[str]:
    """구역의 머리말(또는 꼬리말)을 ``> 머리말: 글`` 줄로. 이미 실은 글(*seen*)은 건너뛴다."""

    lines: list[str] = []
    for element in _descendants(section_el, tag):
        parts = [_p_element_to_md(p, doc, None).strip() for p in _descendants(element, "p")]
        text = " ".join(" ".join(part.split("\n")) for part in parts if part)
        if not text or (tag, text) in seen:
            continue
        seen.add((tag, text))
        label = _PAGE_TEXT_LABELS[tag]
        page_type = _PAGE_TYPE_LABELS.get(element.get("applyPageType") or "")
        if page_type:
            label = f"{label}({page_type})"
        lines.append(f"> {label}: {text}")
    return lines


def _unanchored_memo_lines(section_el, doc, notes) -> list[str]:
    """구역의 메모 목록(``hp:memogroup``) 가운데 본문에 걸린 자리가 없는 메모를 ``> 메모: 글`` 줄로."""

    anchored = {text for kind, _, text in notes if kind == "memo"}
    lines: list[str] = []
    for group in _descendants(section_el, "memogroup"):
        for memo in _direct_children(group, "memo"):
            parts = [_p_element_to_md(p, doc, None).strip() for p in _descendants(memo, "p")]
            text = "메모: " + " ".join(" ".join(part.split("\n")) for part in parts if part)
            if text == "메모: " or text in anchored:
                continue
            anchored.add(text)
            lines.append(f"> {text}")
    return lines


def _export_notes_appendix(body: str, notes, notes_section_separator: str) -> str:
    # 각주/미주 instId → fn1/en1 일련번호 매핑 + 정의 부록
    seq_map: dict[str, dict[str, int]] = {"fn": {}, "en": {}, "memo": {}}
    for kind, inst_id, _ in notes:
        if inst_id not in seq_map[kind]:
            seq_map[kind][inst_id] = len(seq_map[kind]) + 1

    def renumber(match: re.Match[str]) -> str:
        seq = seq_map[match.group(1)].get(match.group(2))
        return match.group(0) if seq is None else f"[^{match.group(1)}{seq}]"

    body = re.sub(r"\[\^(fn|en|memo)([^\]\s]+)\]", renumber, body)

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
    heading_detector: Callable[[str], str | None] | None = None,
    notes_section_separator: str = "\n\n---\n",
    headers_and_footers: bool = False,
    memos: bool = False,
    equations: bool = False,
    heading_source: str = "auto",
    list_labels: bool = False,
    colors: bool = True,
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
        제목을 ``#`` 줄로 싣는가. 거짓이면 제목도 보통 문단으로 싣는다.
    heading_detector : callable | None
        Formatted paragraph/cell Markdown to a heading or None. Given, it decides
        every heading (the document's outline is not read). ``detect_headings=False``
        disables it.
    heading_source : ``"auto"`` | ``"outline"`` | ``"text"``
        제목을 정하는 근거. ``"auto"``(기본)는 문단의 개요 수준(문단 모양의 개요 번호,
        ``개요 N`` 스타일)을 제목 수준으로 쓰고, 개요 문단이 하나도 없는 문서에서만
        글 모양(``Ⅰ.``은 ``#``, 짧은 ``1. 가…``은 ``##``; 물음·차례 줄·문장은 빼고)으로
        짐작한다. ``"outline"``은 개요 수준만 본다. ``"text"``는 7.0 전처럼 글 모양만 본다.
    list_labels : bool
        참이면 번호·글머리 문단 앞에 한/글이 그리는 번호를 싣는다. 글머리는 ``- ``,
        ``1.``·``1)`` 꼴 번호는 그대로 Markdown 목록이 되고, 다른 번호(``가.``, ``①``)는
        글로 붙는다. 표 칸 안에서는 번호를 글로 붙인다.
    colors : bool
        거짓이면 글자색·음영(``<span style="color:…">``·``<mark>``)을 싣지 않는다.
    notes_section_separator : str
        각주/미주 정의 부록 앞에 삽입할 separator.
    headers_and_footers : bool
        참이면 머리말을 구역 첫머리에, 꼬리말을 구역 끝에 인용 줄(``> 머리말: …``)로
        싣는다. 같은 글은 한 번만 싣는다. 쪽 번호 같은 자동 번호는 글이 아니라 빠진다.
    memos : bool
        참이면 메모를 각주처럼 싣는다. 메모가 걸린 글 뒤에 ``[^memoN]``, 내용은
        부록에 ``메모: …``로. 작성자와 날짜는 싣지 않는다.
    equations : bool
        참이면 수식을 있던 자리에 ``$LaTeX$``로 싣는다. LaTeX로 옮기지 못하는 수식은
        한/글 수식 문자열을 코드로 싣는다.
    """
    if heading_detector is not None and not callable(heading_detector):
        raise HwpxTypeError("heading_detector must be callable or None", context={"argument": "heading_detector"})
    if heading_source not in ("auto", "outline", "text"):
        raise HwpxValueError(
            f"heading_source must be 'auto', 'outline' or 'text', not {heading_source!r}",
            context={"argument": "heading_source", "value": repr(heading_source)},
            suggestion="heading_source='auto'(개요 수준, 없으면 글 모양), 'outline', 'text' 가운데 하나를 주세요.",
        )
    doc = _export_resolve_doc(source)
    mapping = _build_image_map(doc, Path(image_dir) if image_dir else None, image_ref_prefix)
    header = _header_xml(doc)
    plan = _HeadingPlan()
    if detect_headings:
        if heading_detector is not None:
            plan.detector = heading_detector
        elif heading_source == "text":
            plan.detector = _legacy_detect_heading
        else:
            structure = _Headings(header)
            if heading_source == "outline" or structure.any_in([s.element for s in doc.sections]):
                plan.structure = structure
            else:
                plan.detector = _detect_heading
    tokens = [
        (_EQUATIONS, _EQUATIONS.set(bool(equations))),
        (_COLORS, _COLORS.set(bool(colors))),
        (_LABELS, _LABELS.set(_LabelCache(_ListLabels(header)) if list_labels else None)),
    ]
    try:
        return _export_markdown(doc, mapping, plan, notes_section_separator, headers_and_footers, memos)
    finally:
        for var, token in reversed(tokens):
            var.reset(token)  # type: ignore[attr-defined]


def _export_markdown(
    doc, mapping, plan: _HeadingPlan, notes_section_separator: str, headers_and_footers: bool, memos: bool
) -> str:
    notes: list[tuple] = _Notes()
    notes.memos = bool(memos)  # type: ignore[attr-defined]
    lines: list[str] = []
    seen_outside: set[tuple[str, str]] = set()
    cache = _LABELS.get()

    for section in doc.sections:
        footers: list[str] = []
        if cache is not None:
            cache.labels.start_section(section.element)
        if headers_and_footers:
            lines.extend(_page_text_lines(section.element, "header", doc, seen_outside))
            footers = _page_text_lines(section.element, "footer", doc, seen_outside)
        paragraphs = {p.element: p for p in section.paragraphs}
        for child in section.element:
            p = paragraphs.get(child)
            if p is not None:
                lines.extend(_export_paragraph_lines(p, doc, mapping, notes, plan))
            elif _local_name(child) == "tbl":
                # 구역에 바로 놓인 표(문단 밖)의 글도 문서의 글이다.
                lines.extend(_section_table_lines(child))
        if memos:
            lines.extend(_unanchored_memo_lines(section.element, doc, notes))
        lines.extend(footers)

    body = "\n\n".join(lines)

    if notes:
        body = _export_notes_appendix(body, notes, notes_section_separator)

    return body
