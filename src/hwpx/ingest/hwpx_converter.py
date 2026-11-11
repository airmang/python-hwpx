# SPDX-License-Identifier: Apache-2.0
"""HWPX ingest converter."""

from __future__ import annotations

import re
from typing import Any, BinaryIO, Iterable, Iterator
from zipfile import BadZipFile, ZipFile

from hwpx.document import HwpxDocument

from .base import DocumentIngestResult, DocumentSourceInfo
from ..opc.security import (
    MAX_ZIP_MIMETYPE_BYTES as _MAX_MIMETYPE_BYTES,
    HwpxSecurityError,
    guard_zip_file,
    read_member,
)


class HwpxMarkdownConverter:
    """Convert HWPX packages to rich Markdown and lightweight structure metadata."""

    name = "HwpxMarkdownConverter"

    def accepts(self, file_stream: BinaryIO, source_info: DocumentSourceInfo) -> bool:
        extension = (source_info.extension or "").lower()
        if extension == ".hwpx":
            return True
        mimetype = (source_info.mimetype or "").lower()
        if mimetype in {"application/hwp+zip", "application/x-hwp+zip"}:
            return True
        return _looks_like_hwpx_package(file_stream)

    def convert(
        self,
        file_stream: BinaryIO,
        source_info: DocumentSourceInfo,
        **kwargs: Any,
    ) -> DocumentIngestResult:
        start_pos = file_stream.tell()
        data = file_stream.read()
        file_stream.seek(start_pos)

        markdown_kwargs = dict(kwargs.pop("markdown_options", {}) or {})
        markdown_kwargs.setdefault("detect_headings", True)

        doc = HwpxDocument.open(data)
        try:
            markdown = doc.text.markdown(rich=True, **markdown_kwargs)
            sections = _sections_payload(doc)
            tables = _tables_payload(doc)
            paragraph_count = len(list(doc.paragraphs))
            left_out = _left_out_content(doc, markdown)
        finally:
            doc.close()

        return DocumentIngestResult(
            markdown=markdown,
            source_info=source_info,
            source_format="hwpx",
            engine="python-hwpx",
            engine_version=_python_hwpx_version(),
            metadata={
                "section_count": len(sections),
                "paragraph_count": paragraph_count,
                "table_count": len(tables),
                "converter": self.name,
                "left_out": {kind: entry["count"] for kind, entry in left_out.items()},
            },
            sections=sections,
            tables=tables,
            warnings=_left_out_warnings(left_out),
            lossiness=_lossiness(left_out, markdown),
        )


_HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
_HP = f"{{{_HP_NS}}}"

#: 글을 담는 요소 → 종류. 종류 이름은 ``metadata["left_out"]``의 키이자 계약이다.
_TEXT_CONTAINERS: dict[str, str] = {
    "header": "header",
    "footer": "footer",
    "memo": "memo",
    "footNote": "footnote",
    "endNote": "endnote",
    "drawText": "text_box",
}
#: 글을 속성에 담는 요소 → (종류, 속성 이름).
_ATTRIBUTE_TEXT: dict[str, tuple[str, str]] = {
    "compose": ("composed_character", "composeText"),
    "checkBtn": ("form_caption", "caption"),
    "radioBtn": ("form_caption", "caption"),
    "btn": ("form_caption", "caption"),
    "textart": ("text_art", "text"),
}
_KIND_LABELS: dict[str, str] = {
    "header": "머리말",
    "footer": "꼬리말",
    "memo": "메모",
    "footnote": "각주",
    "endnote": "미주",
    "text_box": "글상자·도형 안 글",
    "equation": "수식",
    "ruby": "덧말",
    "composed_character": "글자 겹침",
    "form_caption": "양식 개체 캡션",
    "text_art": "글맵시",
    "master_page": "바탕쪽",
}
_MARKDOWN_NOISE = re.compile(r"[\\\s]+")


def _squash(text: str) -> str:
    """Markdown 이스케이프(백슬래시)와 공백을 지운 비교용 글."""

    return _MARKDOWN_NOISE.sub("", text)


def _own_text(paragraph: Any) -> str:
    """문단 자신의 run에 든 글(문단 안 개체의 글은 뺀다)."""

    return "".join(
        "".join(text.itertext()) for text in paragraph.iterfind(f"{_HP}run/{_HP}t")
    )


def _paragraph_texts(container: Any) -> Iterator[str]:
    for paragraph in container.iter(f"{_HP}p"):
        text = _own_text(paragraph)
        if text.strip():
            yield text


def _candidates(root: Any) -> Iterator[tuple[str, list[str]]]:
    """``(종류, 그 요소가 담은 글 조각들)``을 문서 순서로 낸다."""

    for element in root.iter():
        tag = element.tag
        if not isinstance(tag, str) or not tag.startswith(_HP):
            continue
        name = tag[len(_HP) :]
        if name in _TEXT_CONTAINERS:
            yield _TEXT_CONTAINERS[name], list(_paragraph_texts(element))
        elif name in _ATTRIBUTE_TEXT:
            kind, attribute = _ATTRIBUTE_TEXT[name]
            yield kind, [element.get(attribute) or ""]
        elif name == "equation":
            script = element.find(f"{_HP}script")
            yield "equation", ["".join(script.itertext()) if script is not None else ""]
        elif name == "dutmal":
            yield "ruby", [
                "".join(child.itertext())
                for child in element
                if child.tag in (f"{_HP}mainText", f"{_HP}subText")
            ]


def _left_out_content(doc: HwpxDocument, markdown: str) -> dict[str, dict[str, int]]:
    """Markdown에 글이 실리지 않은 요소를 종류별로 센다.

    미리 정한 목록이 아니라 결과와 대조해서 센다. 요소가 담은 글 조각이
    Markdown(이스케이프·공백 무시)에 없으면 그 요소를 빠진 것으로 본다. 그래서
    내보내기가 나중에 어떤 종류를 싣게 되면 이 보고에서도 저절로 빠진다.
    글이 같은 조각이 본문 다른 곳에 있으면 실린 것으로 보므로, 세는 값은
    하한이다.
    """

    haystack = _squash(markdown)
    found: dict[str, dict[str, int]] = {}
    seen: set[tuple[str, tuple[str, ...]]] = set()

    def record(kind: str, pieces: Iterable[str]) -> None:
        missing = [piece for piece in pieces if _squash(piece) and _squash(piece) not in haystack]
        if not missing:
            return
        # 머리말·꼬리말은 구역 설정과 본문 컨트롤에 같은 내용이 두 번 저장된다.
        key = (kind, tuple(missing))
        if kind in ("header", "footer") and key in seen:
            return
        seen.add(key)
        entry = found.setdefault(kind, {"count": 0, "chars": 0})
        entry["count"] += 1
        entry["chars"] += sum(len(_squash(piece)) for piece in missing)

    for section in doc.sections:
        for kind, pieces in _candidates(section.element):
            record(kind, pieces)
    for master_page in doc.parts.master_pages:
        record("master_page", _paragraph_texts(master_page.element))

    deleted = sum(
        1 for section in doc.sections for _ in section.element.iter(f"{_HP}deleteBegin")
    )
    if deleted:
        found["tracked_deletion"] = {"count": deleted, "chars": 0}
    return found


def _left_out_warnings(left_out: dict[str, dict[str, int]]) -> list[str]:
    warnings = [
        f"Markdown에 없는 내용: {_KIND_LABELS[kind]} {entry['count']}곳({entry['chars']}자)"
        for kind, entry in left_out.items()
        if kind != "tracked_deletion"
    ]
    if "tracked_deletion" in left_out:
        warnings.append(
            f"변경 추적으로 지운 글 표시가 {left_out['tracked_deletion']['count']}곳 있습니다. "
            "지운 글이 살아 있는 글과 구분 없이 Markdown에 섞여 나올 수 있습니다."
        )
    return warnings


def _lossiness(left_out: dict[str, dict[str, int]], markdown: str) -> str:
    """``low``: 빠진 것이 없다. ``medium``: 빠진 것이 있다. ``high``: 빠진 글이
    Markdown에 실린 글보다 많다."""

    if not left_out:
        return "low"
    missing_chars = sum(entry["chars"] for entry in left_out.values())
    return "high" if missing_chars > len(_squash(markdown)) else "medium"


def _looks_like_hwpx_package(file_stream: BinaryIO) -> bool:
    cur_pos = file_stream.tell()
    try:
        with ZipFile(file_stream) as archive:
            guard_zip_file(archive)
            names = set(archive.namelist())
            if "mimetype" in names:
                try:
                    mimetype = (
                        read_member(archive, "mimetype", limit=_MAX_MIMETYPE_BYTES)
                        .decode("utf-8", "replace")
                        .strip()
                    )
                    if "hwp" in mimetype.lower() or "hwpx" in mimetype.lower():
                        return True
                except Exception:
                    pass
            return any(name.startswith("Contents/section") and name.endswith(".xml") for name in names)
    except (BadZipFile, OSError, HwpxSecurityError):
        return False
    finally:
        file_stream.seek(cur_pos)


def _sections_payload(doc: HwpxDocument) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    for index, section in enumerate(doc.sections):
        paragraphs = list(section.paragraphs)
        sections.append(
            {
                "index": index,
                "paragraph_count": len(paragraphs),
                "text_preview": "\n".join(
                    (paragraph.text or "").strip()
                    for paragraph in paragraphs[:5]
                    if (paragraph.text or "").strip()
                )[:500],
            }
        )
    return sections


def _tables_payload(doc: HwpxDocument) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []
    for paragraph_index, paragraph in enumerate(doc.paragraphs):
        for table in paragraph.tables:
            rows = [[cell.text for cell in row.cells] for row in table.rows]
            tables.append(
                {
                    "table_index": len(tables),
                    "paragraph_index": paragraph_index,
                    "rows": len(rows),
                    "cols": max((len(row) for row in rows), default=0),
                    "data": rows,
                }
            )
    return tables


def _python_hwpx_version() -> str:
    from importlib.metadata import PackageNotFoundError, version as package_version

    try:
        return package_version("python-hwpx")
    except PackageNotFoundError:
        return "0+unknown"
