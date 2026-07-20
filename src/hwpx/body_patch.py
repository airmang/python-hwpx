"""본문(섹션 직속 문단) 바이트보존 op — Stage 2 결정표의 표-밖 실행 어휘.

KACE 투고본 변환 스파이크(본문 인용 [n] 치환 · 참고문헌 문단 재배열)의 스택 승격.
:func:`hwpx.table_patch.apply_table_ops` 와 동형 계약: 순차 적용, fail-closed
(정합 불가 시 이유와 함께 skip), op별 transcript, ``dry_run`` (해석·검증은 전부
실제로 수행하되 파일은 쓰지 않음 — 상의 루프의 승인 근거).

Ops (index = 섹션 직속 ``<hp:p>`` 문서순, **op 실행 시점의 현재 상태** 기준):

- ``replace_text``  {find, replace, count=1}
    ``<hp:t>`` 텍스트 콘텐츠 안에서만 매치(태그/속성 불가침). 발견 수가 count와
    다르면 refuse — 런 경계를 걸친 문자열은 매치되지 않아 자연히 refuse된다.
- ``delete_paragraph``  {index}
    표를 품은 문단은 refuse(표까지 무음 소실 방지, ``allow_tables=True``로 해제).
- ``insert_paragraph_by_clone``  {ref_index, count=1, texts=[...]?}
    참조 문단을 서식 verbatim 복제(id 재작성·linesegarray 제거) 후 ref 뒤에 삽입.
    texts[i]가 있으면 해당 클론의 텍스트를 교체 — **이웃 문단 서식 상속** 경로.
- ``set_paragraph_text``  {index, text}
    index번째 섹션 직속 문단의 텍스트를 통째 설정(fill_cell의 본문판) — 빈/마커
    문단("가." 등)에 내용을 넣을 때. 첫 런 서식 상속, stale linesegarray 제거.
- ``reorder_paragraphs``  {start, end, order}
    연속 구간 [start..end]를 order(구간 내 상대 인덱스 순열)로 재배열.
- ``restyle_text``  {find, count=1, text_color?, drop_italic=True}
    find를 품은 런의 charPr을 정규화 변형(색 교체·이탤릭 제거)으로 재매핑 —
    안내용 슬롯 서식(파란 이탤릭 등)을 상속한 채움 텍스트를 "사람이 작성한
    본문"으로 만든다(2026-07-07 AI중점학교 신청서 실측). 원본 charPr은 불변,
    변형은 header에 새 id로 추가(dedupe).
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .mutation_report import MutationReport, project_byte_splice
from .patch import (
    _finalize,
    _patch_zip_entries,
    _read_source_bytes,
    _rewrite_zip_entries,
    _strip_paragraph_layout_cache,
    _text_edit_for_paragraph,
)

__all__ = [
    "BodyOpsResult", "apply_body_ops", "direct_paragraph_spans",
    "strip_runs_by_color", "recolor_runs_by_color",
]

_P_EDGE_RE = re.compile(r"<hp:p[ >]|</hp:p>")
_T_CONTENT_RE = re.compile(r"<hp:t(?:\s[^>]*)?>(.*?)</hp:t>", re.S)
_PARA_ID_RE = re.compile(r'(<hp:p\b[^>]*\bid=")(\d+)(")')
_TBL_RE = re.compile(r"<hp:tbl\b")


def direct_paragraph_spans(section_xml: str) -> list[tuple[int, int]]:
    """섹션 직속 ``<hp:p>`` 블록들의 (start, end) — 중첩(셀 내부) 문단 제외."""
    spans: list[tuple[int, int]] = []
    depth, start = 0, -1
    for m in _P_EDGE_RE.finditer(section_xml):
        if m.group().startswith("</"):
            depth -= 1
            if depth == 0 and start >= 0:
                spans.append((start, m.end()))
                start = -1
        else:
            if depth == 0:
                start = m.start()
            depth += 1
    return spans


def _all_paragraph_spans(section_xml: str) -> list[tuple[int, int]]:
    """모든 깊이의 ``<hp:p>`` 블록 span (셀 내부 포함) — lineseg 무효화 대상 탐색용."""
    spans: list[tuple[int, int]] = []
    stack: list[int] = []
    for m in _P_EDGE_RE.finditer(section_xml):
        if m.group().startswith("</"):
            if stack:
                spans.append((stack.pop(), m.end()))
        else:
            stack.append(m.start())
    return spans


def _preview(text: str, limit: int = 60) -> str:
    flat = re.sub(r"\s+", " ", text).strip()
    return flat[: limit - 1] + "…" if len(flat) > limit else flat


@dataclass(frozen=True)
class BodyOpsResult:
    data: bytes
    skipped: tuple[dict[str, Any], ...]
    transcript: tuple[dict[str, Any], ...]
    changed_parts: tuple[str, ...]
    byte_identical: bool
    open_safety: dict[str, Any]

    @property
    def ok(self) -> bool:
        return bool(self.open_safety.get("ok")) and not self.skipped

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "skipped": list(self.skipped),
            "transcript": list(self.transcript),
            "changedParts": list(self.changed_parts),
            "byteIdentical": self.byte_identical,
            "openSafety": self.open_safety,
        }

    def as_mutation_report(self, *, source: bytes | str | Path | None = None) -> MutationReport:
        """Project this body-ops result onto ``hwpx.mutation-report/v1`` (specs/032
        §3). Additive — the fields above are untouched. This path never renders,
        so the visual verdict stays ``not_performed``. Pass the original *source*
        for real ranges and a measured preservation summary.
        """

        return project_byte_splice(
            data=self.data,
            changed_part_names=self.changed_parts,
            byte_identical=self.byte_identical,
            open_safety=self.open_safety,
            source=source,
        )


def _op_replace_text(xml: str, op: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    find = str(op["find"])
    replace = str(op.get("replace", ""))
    expected = int(op.get("count", 1))
    esc_find = html.escape(find, quote=False)
    esc_replace = html.escape(replace, quote=False)
    hits: list[tuple[int, int]] = []
    for t in _T_CONTENT_RE.finditer(xml):
        a, b = t.start(1), t.end(1)
        pos = xml.find(esc_find, a)
        while pos != -1 and pos + len(esc_find) <= b:
            hits.append((pos, pos + len(esc_find)))
            pos = xml.find(esc_find, pos + 1)
            if pos >= b:
                break
    if len(hits) != expected:
        raise ValueError(
            f"replace_text: {find!r} matched {len(hits)} time(s) inside <hp:t> "
            f"(expected {expected}) — run-spanning or ambiguous text is refused"
        )
    # 편집된 문단의 linesegarray(한컴 줄배치 캐시)를 함께 제거해야 한다 — 안 지우면
    # 한컴이 옛 텍스트 기준 줄배치를 재사용해 긴 새 텍스트가 겹쳐 렌더된다
    # (2026-07-07 AI중점학교 신청서 실측: 교체 문단만 줄겹침, lineseg 제거된
    # 클론 문단은 정상). 문단 단위로 묶어 뒤에서부터: 치환 → 캐시 제거 → 재조립.
    para_spans = _all_paragraph_spans(xml)

    def _innermost(pos: int) -> tuple[int, int]:
        best = None
        for a, b in para_spans:
            if a <= pos < b and (best is None or (a >= best[0] and b <= best[1])):
                best = (a, b)
        if best is None:
            raise ValueError("replace_text: match outside any <hp:p> paragraph")
        return best

    by_para: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for hit in hits:
        by_para.setdefault(_innermost(hit[0]), []).append(hit)
    for (pa, pb), phits in sorted(by_para.items(), reverse=True):
        block = xml[pa:pb]
        for a, b in sorted(phits, reverse=True):
            block = block[: a - pa] + esc_replace + block[b - pa:]
        block = _strip_paragraph_layout_cache(block.encode("utf-8")).decode("utf-8")
        xml = xml[:pa] + block + xml[pb:]
    return xml, {"find": _preview(find), "replace": _preview(replace), "hits": expected}


def _op_delete_paragraph(xml: str, op: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    spans = direct_paragraph_spans(xml)
    index = int(op["index"])
    if not 0 <= index < len(spans):
        raise ValueError(f"delete_paragraph: index {index} out of range (0..{len(spans) - 1})")
    a, b = spans[index]
    block = xml[a:b]
    if _TBL_RE.search(block) and not op.get("allow_tables"):
        raise ValueError(
            "delete_paragraph: paragraph wraps a table — refuse (allow_tables=True to override)"
        )
    old = "".join(m.group(1) for m in _T_CONTENT_RE.finditer(block))
    return xml[:a] + xml[b:], {"index": index, "old": _preview(html.unescape(old))}


def _op_insert_paragraph_by_clone(xml: str, op: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    spans = direct_paragraph_spans(xml)
    ref = int(op["ref_index"])
    count = int(op.get("count", 1))
    texts = list(op.get("texts") or [])
    if not 0 <= ref < len(spans):
        raise ValueError(f"insert_paragraph_by_clone: ref_index {ref} out of range")
    if count < 1:
        raise ValueError("insert_paragraph_by_clone: count must be >= 1")
    if texts and len(texts) != count:
        raise ValueError("insert_paragraph_by_clone: len(texts) must equal count")
    a, b = spans[ref]
    block = xml[a:b]
    if _TBL_RE.search(block):
        raise ValueError("insert_paragraph_by_clone: ref paragraph wraps a table — refuse")
    stripped = _strip_paragraph_layout_cache(block.encode("utf-8")).decode("utf-8")
    clones: list[str] = []
    for i in range(count):
        clone = _PARA_ID_RE.sub(
            lambda m: m.group(1) + str((int(m.group(2)) + (i + 1) * 100003) & 0x7FFFFFFF) + m.group(3),
            stripped,
        )
        if texts:
            edited = _text_edit_for_paragraph(clone.encode("utf-8"), str(texts[i]))
            if edited is None:
                raise ValueError("insert_paragraph_by_clone: ref paragraph has no text run to fill")
            clone = edited[2].decode("utf-8")
        clones.append(clone)
    return xml[:b] + "".join(clones) + xml[b:], {
        "refIndex": ref,
        "count": count,
        "texts": [_preview(str(t)) for t in texts],
    }


def _op_reorder_paragraphs(xml: str, op: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    spans = direct_paragraph_spans(xml)
    start, end = int(op["start"]), int(op["end"])
    order = [int(i) for i in op["order"]]
    if not (0 <= start <= end < len(spans)):
        raise ValueError(f"reorder_paragraphs: range {start}..{end} out of bounds")
    size = end - start + 1
    if sorted(order) != list(range(size)):
        raise ValueError("reorder_paragraphs: order must be a permutation of 0..end-start")
    region = spans[start:end + 1]
    for (a0, b0), (a1, _b1) in zip(region, region[1:]):
        if xml[b0:a1].strip():
            raise ValueError("reorder_paragraphs: non-whitespace content between paragraphs — refuse")
    blocks = [xml[a:b] for a, b in region]
    new_region = "".join(blocks[i] for i in order)
    return xml[: region[0][0]] + new_region + xml[region[-1][1]:], {
        "start": start, "end": end, "order": order,
    }


def _materialize_restyled_charpr(
    header: str, base_id: str, text_color: str | None, drop_italic: bool,
    cache: dict[tuple, str],
) -> tuple[str, str]:
    """charPr *base_id*를 색/이탤릭만 바꾼 변형으로 복제해 header에 추가."""
    key = (base_id, text_color, drop_italic)
    if key in cache:
        return header, cache[key]
    bid = re.escape(base_id)
    m = re.search(r'<(?:[A-Za-z_][\w.-]*:)?charPr\b[^>]*?\bid="' + bid + r'".*?</(?:[A-Za-z_][\w.-]*:)?charPr>', header, re.DOTALL)
    if m is None:
        m = re.search(r'<(?:[A-Za-z_][\w.-]*:)?charPr\b[^>]*?\bid="' + bid + r'"[^>]*/>', header)
    if m is None:
        raise ValueError(f"restyle_text: base charPr {base_id} not found in header")
    ids = [int(x) for x in re.findall(r'<(?:[A-Za-z_][\w.-]*:)?charPr\b[^>]*?\bid="(\d+)"', header)]
    new_id = str(max(ids) + 1 if ids else 0)
    clone = re.sub(r'(\bid=")\d+(")', r"\g<1>" + new_id + r"\g<2>", m.group(0), count=1)
    if text_color is not None:
        if re.search(r'\btextColor="[^"]*"', clone):
            clone = re.sub(r'(\btextColor=")[^"]*(")', r"\g<1>" + text_color + r"\g<2>", clone, count=1)
        else:
            clone = re.sub(r'(<(?:[A-Za-z_][\w.-]*:)?charPr\b)', r"\g<1>" + f' textColor="{text_color}"', clone, count=1)
    if drop_italic:
        clone = re.sub(r'<(?:[A-Za-z_][\w.-]*:)?italic\b[^>]*/>', "", clone)
        clone = re.sub(r'<((?:[A-Za-z_][\w.-]*:)?)italic\b[^>]*>.*?</\1italic>', "", clone, flags=re.DOTALL)
    close = re.search(r'</(?:[A-Za-z_][\w.-]*:)?charProperties>', header)
    if close is None:
        raise ValueError("restyle_text: charProperties close tag not found")
    header = header[: close.start()] + clone + header[close.start():]
    header = re.sub(
        r'(<(?:[A-Za-z_][\w.-]*:)?charProperties\b[^>]*?\bitemCnt=")(\d+)(")',
        lambda mm: mm.group(1) + str(int(mm.group(2)) + 1) + mm.group(3),
        header, count=1,
    )
    cache[key] = new_id
    return header, new_id


def _op_restyle_text(xml: str, op: Mapping[str, Any], ctx: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    find = str(op["find"])
    expected = int(op.get("count", 1))
    text_color = op.get("text_color", op.get("textColor"))
    drop_italic = bool(op.get("drop_italic", op.get("dropItalic", True)))
    esc_find = html.escape(find, quote=False)
    hits: list[int] = []
    for t in _T_CONTENT_RE.finditer(xml):
        a, b = t.start(1), t.end(1)
        pos = xml.find(esc_find, a)
        while pos != -1 and pos + len(esc_find) <= b:
            hits.append(pos)
            pos = xml.find(esc_find, pos + 1)
            if pos >= b:
                break
    if len(hits) != expected:
        raise ValueError(
            f"restyle_text: {find!r} matched {len(hits)} time(s) inside <hp:t> (expected {expected})"
        )
    remapped = []
    for pos in sorted(hits, reverse=True):
        run_open = xml.rfind("<hp:run", 0, pos)
        if run_open < 0:
            raise ValueError("restyle_text: enclosing <hp:run> not found")
        tag_end = xml.find(">", run_open)
        open_tag = xml[run_open: tag_end + 1]
        m = re.search(r'charPrIDRef="(\d+)"', open_tag)
        if m is None:
            raise ValueError("restyle_text: run has no charPrIDRef")
        base = m.group(1)
        ctx["header"], new_id = _materialize_restyled_charpr(
            ctx["header"], base, text_color, drop_italic, ctx["charpr_cache"]
        )
        ctx["header_changed"] = True
        new_tag = open_tag.replace(f'charPrIDRef="{base}"', f'charPrIDRef="{new_id}"', 1)
        xml = xml[:run_open] + new_tag + xml[tag_end + 1:]
        remapped.append(f"{base}→{new_id}")
    return xml, {"find": _preview(find), "hits": expected, "charPr": remapped,
                 "textColor": text_color, "dropItalic": drop_italic}


def _op_set_paragraph_text(xml: str, op: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    spans = direct_paragraph_spans(xml)
    index = int(op["index"])
    if not 0 <= index < len(spans):
        raise ValueError(f"set_paragraph_text: index {index} out of range (0..{len(spans) - 1})")
    a, b = spans[index]
    block = xml[a:b]
    if _TBL_RE.search(block):
        raise ValueError("set_paragraph_text: paragraph wraps a table — refuse")
    edited = _text_edit_for_paragraph(block.encode("utf-8"), str(op["text"]))
    if edited is None:
        raise ValueError("set_paragraph_text: paragraph has no text run to set")
    new_block = _strip_paragraph_layout_cache(edited[2]).decode("utf-8")
    old = "".join(m.group(1) for m in _T_CONTENT_RE.finditer(block))
    return xml[:a] + new_block + xml[b:], {"index": index, "old": _preview(html.unescape(old)),
                                           "new": _preview(str(op["text"]))}


_OPS = {
    "replace_text": _op_replace_text,
    "delete_paragraph": _op_delete_paragraph,
    "insert_paragraph_by_clone": _op_insert_paragraph_by_clone,
    "reorder_paragraphs": _op_reorder_paragraphs,
    "set_paragraph_text": _op_set_paragraph_text,
    "restyle_text": _op_restyle_text,  # dispatch에서 ctx 전달로 특수 처리
}


def recolor_runs_by_color(
    source: str | Path | bytes,
    from_hexes: Sequence[str],
    to_color: str,
    *,
    output_path: str | Path | None = None,
    dry_run: bool = False,
) -> BodyOpsResult:
    """문서 전체(셀 포함)에서 지정 색(정확 hex)의 run을 to_color로 재색.

    양식이 "이 색 글씨는 과목별로 수정"(평가계획 파랑)이라 선언한 슬롯을 채우면
    슬롯 색을 상속하는데, 채운 내용은 사람 본문이므로 검정이어야 한다. from_hexes와
    정확히 일치하는 charPr을 to_color 변형으로 복제(header)하고 해당 run의
    charPrIDRef만 재매핑한다(글꼴·크기 등 나머지 서식 보존). 디자인색 오염 방지를
    위해 계열이 아닌 **정확 hex** 매칭."""
    source_bytes = _read_source_bytes(source)
    from_set = {h.upper() for h in from_hexes}
    import io, zipfile

    with zipfile.ZipFile(io.BytesIO(source_bytes)) as z:
        names = z.namelist()
        header_name = next((n for n in names if n.endswith("header.xml")), None)
        header_xml = z.read(header_name).decode("utf-8") if header_name else ""
        sections = {n: z.read(n).decode("utf-8") for n in names if re.search(r"section\d+\.xml$", n)}

    ids = set()
    for cm in re.finditer(r"<(?:[A-Za-z_][\w.-]*:)?charPr\b[^>]*?>", header_xml):
        idm = re.search(r'\bid="(\d+)"', cm.group(0))
        colm = re.search(r'\btextColor="([^"]+)"', cm.group(0))
        if idm and colm and colm.group(1).upper() in from_set:
            ids.add(idm.group(1))

    cache: dict[tuple, str] = {}
    idmap: dict[str, str] = {}
    for rid in sorted(ids, key=int):
        header_xml, new_id = _materialize_restyled_charpr(header_xml, rid, to_color, False, cache)
        idmap[rid] = new_id

    transcript: list[dict[str, Any]] = []
    changed: set[str] = set()
    for sp, xml in sections.items():
        n = [0]

        def _remap(m: "re.Match") -> str:
            old = m.group(1)
            if old not in idmap:
                return m.group(0)
            n[0] += 1
            return m.group(0).replace(f'charPrIDRef="{old}"', f'charPrIDRef="{idmap[old]}"', 1)

        new_xml = re.sub(r'<hp:run\b[^>]*\bcharPrIDRef="(\d+)"[^>]*>', _remap, xml)
        if n[0] == 0:
            continue
        sections[sp] = new_xml
        changed.add(sp)
        transcript.append({"op": "recolor_runs_by_color", "sectionPath": sp,
                          "runsRecolored": n[0], "toColor": to_color,
                          "status": "would_apply" if dry_run else "applied"})

    intermediate = source_bytes
    if changed and header_name:
        payload = {sp: sections[sp].encode("utf-8") for sp in changed}
        payload[header_name] = header_xml.encode("utf-8")
        try:
            intermediate = _patch_zip_entries(source_bytes, payload)
        except ValueError:
            intermediate = _rewrite_zip_entries(source_bytes, payload)
    open_safety, _ = _finalize(intermediate, None if dry_run else output_path, source=source)
    return BodyOpsResult(intermediate, (), tuple(transcript), tuple(sorted(changed)),
                         intermediate == source_bytes, open_safety)


def strip_runs_by_color(
    source: str | Path | bytes,
    hex_colors: Sequence[str],
    *,
    output_path: str | Path | None = None,
    dry_run: bool = False,
) -> BodyOpsResult:
    """문서 전체(셀 내부 포함)에서 지정 색의 run 텍스트를 비운다(런 구조 유지).

    양식이 색 범례로 "이 색 글씨는 모두 삭제"를 선언한 경우(평가계획 빨강)의
    일괄 청소 — 안내문·범례가 셀·헤딩 표에 흩어진 red run이라 문단 op가 못 닿는
    문제를 해결한다. charPrIDRef가 header에서 target textColor를 가리키는 run의
    ``<hp:t>`` 내용을 비우고, 그 run이 든 문단의 stale linesegarray를 제거한다.
    미변경 부분은 byte-identical."""
    source_bytes = _read_source_bytes(source)
    import io, zipfile

    targets = {h.upper() for h in hex_colors}
    with zipfile.ZipFile(io.BytesIO(source_bytes)) as z:
        names = z.namelist()
        header_name = next((n for n in names if n.endswith("header.xml")), None)
        header_xml = z.read(header_name).decode("utf-8") if header_name else ""
        sections = {n: z.read(n).decode("utf-8") for n in names if re.search(r"section\d+\.xml$", n)}

    # 계열 매칭(잔존 게이트와 정렬): 대상 색의 _color_family에 드는 모든 charPr.
    from .guidance_scan import _color_family
    target_families = {_color_family(h) for h in targets}
    ids = set()
    for cm in re.finditer(r"<(?:[A-Za-z_][\w.-]*:)?charPr\b[^>]*?>", header_xml):
        tag = cm.group(0)
        idm = re.search(r'\bid="(\d+)"', tag)
        colm = re.search(r'\btextColor="([^"]+)"', tag)
        if not (idm and colm):
            continue
        col = colm.group(1).upper()
        if col in targets or _color_family(col) in target_families:
            ids.add(idm.group(1))
    transcript: list[dict[str, Any]] = []
    changed: set[str] = set()
    total = 0
    counter = {"n": 0}
    run_re = re.compile(
        r"(?P<open><hp:run\b[^>]*\bcharPrIDRef=\"(\d+)\"[^>]*>)(?P<body>.*?)(?P<close></hp:run>)",
        re.S,
    )

    def _sub(m: "re.Match") -> str:
        if m.group(2) not in ids:
            return m.group(0)
        body = re.sub(r"(<hp:t\b[^>]*>).*?(</hp:t>)", r"\1\2", m.group("body"), flags=re.S)
        if body != m.group("body"):
            counter["n"] += 1
        return m.group("open") + body + m.group("close")

    for sp, xml in sections.items():
        counter["n"] = 0
        new_xml = run_re.sub(_sub, xml)
        n = counter["n"]
        if n == 0:
            continue
        # 편집된 문단들의 linesegarray 제거(재계산)
        new_xml = re.sub(
            r"(<hp:p\b(?:(?!</hp:p>).)*?<hp:t\b[^>]*></hp:t>(?:(?!</hp:p>).)*?)"
            r"<(?P<ns>(?:[A-Za-z_][\w.-]*:)?)linesegarray\b(?:[^>]*?/>|[^>]*>.*?</(?P=ns)linesegarray>)",
            r"\1", new_xml, flags=re.S,
        )
        sections[sp] = new_xml
        changed.add(sp)
        total += n
        transcript.append({"op": "strip_runs_by_color", "sectionPath": sp,
                           "runsBlanked": n, "status": "would_apply" if dry_run else "applied"})

    intermediate = source_bytes
    if changed:
        payload = {sp: sections[sp].encode("utf-8") for sp in changed}
        try:
            intermediate = _patch_zip_entries(source_bytes, payload)
        except ValueError:
            intermediate = _rewrite_zip_entries(source_bytes, payload)
    open_safety, _ = _finalize(intermediate, None if dry_run else output_path, source=source)
    return BodyOpsResult(intermediate, (), tuple(transcript), tuple(sorted(changed)),
                         intermediate == source_bytes, open_safety)


def apply_body_ops(
    source: str | Path | bytes,
    ops: Sequence[Mapping[str, Any]],
    *,
    output_path: str | Path | None = None,
    dry_run: bool = False,
) -> BodyOpsResult:
    """섹션 직속 문단 op들을 바이트보존으로 적용한다 (모듈 docstring 참조)."""
    source_bytes = _read_source_bytes(source)
    import io, zipfile

    header_part: str | None = None
    with zipfile.ZipFile(io.BytesIO(source_bytes)) as z:
        sections = {
            n: z.read(n).decode("utf-8")
            for n in z.namelist()
            if re.search(r"section\d+\.xml$", n)
        }
        header_part = next((n for n in z.namelist() if n.endswith("header.xml")), None)
        header_xml = z.read(header_part).decode("utf-8") if header_part else ""

    ctx: dict[str, Any] = {"header": header_xml, "header_changed": False, "charpr_cache": {}}
    skipped: list[dict[str, Any]] = []
    transcript: list[dict[str, Any]] = []
    changed: set[str] = set()

    for op in ops:
        name = str(op.get("op"))
        sp = str(op.get("section_path") or op.get("sectionPath") or "Contents/section0.xml")
        entry: dict[str, Any] = {"op": name, "sectionPath": sp}
        handler = _OPS.get(name)
        if handler is None:
            entry["status"] = f"refused: unknown op {name!r}"
            skipped.append(dict(entry))
            transcript.append(entry)
            continue
        xml = sections.get(sp)
        if xml is None:
            entry["status"] = "refused: section part not found"
            skipped.append(dict(entry))
            transcript.append(entry)
            continue
        try:
            if name == "restyle_text":
                new_xml, detail = _op_restyle_text(xml, op, ctx)
            else:
                new_xml, detail = handler(xml, op)
        except (ValueError, KeyError, TypeError) as exc:
            entry["status"] = f"refused: {exc}"
            skipped.append(dict(entry))
            transcript.append(entry)
            continue
        sections[sp] = new_xml
        changed.add(sp)
        entry.update(detail)
        entry["status"] = "would_apply" if dry_run else "applied"
        transcript.append(entry)

    intermediate = source_bytes
    if changed or ctx["header_changed"]:
        payload = {sp: sections[sp].encode("utf-8") for sp in changed}
        if ctx["header_changed"] and header_part:
            payload[header_part] = ctx["header"].encode("utf-8")
        try:
            intermediate = _patch_zip_entries(source_bytes, payload)
        except ValueError:
            intermediate = _rewrite_zip_entries(source_bytes, payload)

    open_safety, _ = _finalize(intermediate, None if dry_run else output_path, source=source)
    return BodyOpsResult(
        intermediate,
        tuple(skipped),
        tuple(transcript),
        tuple(sorted(changed)),
        intermediate == source_bytes,
        open_safety,
    )
