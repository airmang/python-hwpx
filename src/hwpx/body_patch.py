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
- ``reorder_paragraphs``  {start, end, order}
    연속 구간 [start..end]를 order(구간 내 상대 인덱스 순열)로 재배열.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .patch import (
    _finalize,
    _patch_zip_entries,
    _read_source_bytes,
    _rewrite_zip_entries,
    _strip_paragraph_layout_cache,
    _text_edit_for_paragraph,
)

__all__ = ["BodyOpsResult", "apply_body_ops", "direct_paragraph_spans"]

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


_OPS = {
    "replace_text": _op_replace_text,
    "delete_paragraph": _op_delete_paragraph,
    "insert_paragraph_by_clone": _op_insert_paragraph_by_clone,
    "reorder_paragraphs": _op_reorder_paragraphs,
}


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

    with zipfile.ZipFile(io.BytesIO(source_bytes)) as z:
        sections = {
            n: z.read(n).decode("utf-8")
            for n in z.namelist()
            if re.search(r"section\d+\.xml$", n)
        }

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
    if changed:
        payload = {sp: sections[sp].encode("utf-8") for sp in changed}
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
