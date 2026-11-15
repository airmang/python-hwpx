# SPDX-License-Identifier: Apache-2.0
"""HWPX and HWP 5.0 ingest converter."""

from __future__ import annotations

import html
import re
from typing import Any, BinaryIO, Iterable, Iterator
from zipfile import BadZipFile, ZipFile

from hwpx.document import HwpxDocument

from .base import DocumentIngestResult, DocumentSourceInfo
from ..errors import HwpxValueError
from ..opc.package import HwpxPackage
from ..opc.security import (
    MAX_ZIP_MIMETYPE_BYTES as _MAX_MIMETYPE_BYTES,
    HwpxSecurityError,
    guard_zip_file,
    read_member,
)


class HwpxMarkdownConverter:
    """Convert HWPX packages and HWP 5.0 (``.hwp``) files to rich Markdown and
    lightweight structure metadata.

    An ``.hwp`` file is read through the same document model
    (:meth:`HwpxDocument.open`); the result says ``source_format="hwp"`` and
    carries what that conversion could not bring over in
    ``metadata["hwp_conversion"]``.
    """

    name = "HwpxMarkdownConverter"

    def accepts(self, file_stream: BinaryIO, source_info: DocumentSourceInfo) -> bool:
        extension = (source_info.extension or "").lower()
        if extension == ".hwpx":
            return True
        mimetype = (source_info.mimetype or "").lower()
        if mimetype in {"application/hwp+zip", "application/x-hwp+zip"}:
            return True
        # 확장자가 .hwp면 내용이 HWP 5.0이 아니어도 받는다. 그래야 HWP 3.x나
        # 암호 문서를 열 수 없는 사유가 변환 시도 기록에 남는다.
        if extension == ".hwp" or _starts_with_ole2(file_stream):
            return True
        if not extension and not mimetype:
            # 이름 없는 바이트·스트림: 받아서 열어 본다. 그래야 경로로 넘길 때처럼 못 여는
            # 사유(HWP 3.x, 빈 파일, 깨진 파일)가 남는다.
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
        # 읽는 쪽(LLM·색인)에는 본문 밖의 글도 문서의 글이다.
        markdown_kwargs.setdefault("headers_and_footers", True)
        markdown_kwargs.setdefault("memos", True)
        markdown_kwargs.setdefault("equations", True)
        # 목록 번호는 글의 일부다. 글자색 표시(<span>)는 읽는 쪽에 잡음이다.
        markdown_kwargs.setdefault("list_labels", True)
        markdown_kwargs.setdefault("colors", False)

        if not data:
            raise HwpxValueError(
                "빈 파일입니다. HWPX나 HWP 문서가 아닙니다.",
                context={"bytes": 0},
                suggestion="파일이 끝까지 저장·전송되었는지 확인하세요.",
            )
        doc = HwpxDocument.open(data)
        try:
            markdown = doc.text.markdown(rich=True, **markdown_kwargs)
            sections = _sections_payload(doc)
            tables = _tables_payload(doc)
            paragraph_count = len(list(doc.paragraphs))
            left_out = _left_out_content(doc, markdown)
            report = doc.conversion_report
        finally:
            doc.close()

        metadata: dict[str, Any] = {
            "section_count": len(sections),
            "paragraph_count": paragraph_count,
            "table_count": len(tables),
            "converter": self.name,
            "left_out": {kind: entry["count"] for kind, entry in left_out.items()},
        }
        warnings = _left_out_warnings(left_out)
        lossiness = _lossiness(left_out, markdown)
        if report is not None:
            metadata["hwp_conversion"] = {
                "unconverted": dict(report.unconverted),
                "dropped": dict(report.dropped),
            }
            if report.unconverted:
                summary = ", ".join(
                    f"{kind} {count}곳" for kind, count in sorted(report.unconverted.items())
                )
                warnings.append(f".hwp에서 문서 모델로 옮기지 못한 내용: {summary}")
                if lossiness == "low":
                    lossiness = "medium"

        return DocumentIngestResult(
            markdown=markdown,
            source_info=source_info,
            source_format="hwpx" if report is None else "hwp",
            engine="python-hwpx",
            engine_version=_python_hwpx_version(),
            metadata=metadata,
            sections=sections,
            tables=tables,
            warnings=warnings,
            lossiness=lossiness,
        )


_HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
_HP = f"{{{_HP_NS}}}"

#: 글을 담는 요소 → 종류. 종류 이름은 ``metadata["left_out"]``의 키이자 계약이다.
#: 문단은 가장 가까운 담는 요소(또는 아래 _SKIPPED_OWNERS)의 것으로 센다. 표 칸 안
#: 각주는 각주로, 글상자 안 표는 표로 한 번만 센다.
_TEXT_CONTAINERS: dict[str, str] = {
    "header": "header",
    "footer": "footer",
    "memo": "memo",
    "footNote": "footnote",
    "endNote": "endnote",
    "drawText": "text_box",
    "caption": "caption",
    "tbl": "table",
}
#: 문단을 품지만 따로 세지 않는 요소: 메모 필드(같은 메모가 ``hp:memo``로도 있다)와 숨은 설명.
_SKIPPED_OWNERS = frozenset({"fieldBegin", "hiddenComment"})
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
    "caption": "캡션",
    "table": "표",
}
#: Markdown이 글 사이에 끼우는 표시: 링크 주소, HTML 태그(문서 글의 ``<``는 ``&lt;``로 나간다).
_LINK_TARGET = re.compile(r"\]\([^)\s]*\)")
_HTML_TAG = re.compile(r"</?(?:span|mark|u|br|table|tr|td|th|caption|strong|em|del|s|a|img|sup)\b[^<>]*>")
_BACKSLASH_ESCAPE = re.compile(r"\\([!-/:-@\[-`{-~])")
#: 비교에서 지우는 글자: 공백과 Markdown 서식·이스케이프 기호. 양쪽에서 같이 지운다.
_MARKDOWN_NOISE = re.compile(r"[\s\\*_~`|#>\[\]]+")


def _squash(text: str) -> str:
    """공백과 Markdown 서식 기호를 지운 비교용 글."""

    return _MARKDOWN_NOISE.sub("", text)


def _markdown_haystack(markdown: str) -> str:
    """Markdown을 글만 남겨 비교용으로: 링크 주소·태그를 빼고 이스케이프와 HTML 엔티티를 되돌린다."""

    text = _LINK_TARGET.sub("]", markdown)
    text = _HTML_TAG.sub("", text)
    text = _BACKSLASH_ESCAPE.sub(r"\1", text)
    return _squash(html.unescape(text))


def _own_segments(paragraph: Any) -> Iterator[str]:
    """문단 자신의 run에 든 글을, 글이 아닌 run 자식(컨트롤·수식·개체)에서 끊어 낸다.

    Markdown은 그 자리에 각주 표시·수식·링크를 끼우므로 한 덩어리로 찾으면 실린 글도
    빠진 것으로 보인다.
    """

    buffer: list[str] = []
    for run in paragraph.iterfind(f"{_HP}run"):
        for child in run:
            if child.tag == f"{_HP}t":
                # 내보내기는 한/글 하이픈(U+00AD)을 "-"로 쓴다.
                buffer.append("".join(child.itertext()).replace("­", "-"))
            elif buffer:
                yield "".join(buffer)
                buffer = []
    if buffer:
        yield "".join(buffer)


def _owned_paragraphs(owner: Any) -> Iterator[Any]:
    """*owner* 의 문단 가운데 더 가까운 담는 요소가 없는 것."""

    for paragraph in owner.iter(f"{_HP}p"):
        parent = paragraph.getparent()
        while parent is not None and parent is not owner:
            if _owner_name(parent) is not None:
                break
            parent = parent.getparent()
        else:
            yield paragraph


def _owner_name(element: Any) -> str | None:
    tag = element.tag
    if not isinstance(tag, str) or not tag.startswith(_HP):
        return None
    name = tag[len(_HP) :]
    return name if name in _TEXT_CONTAINERS or name in _SKIPPED_OWNERS else None


def _paragraph_texts(container: Any) -> Iterator[str]:
    for paragraph in _owned_paragraphs(container):
        for segment in _own_segments(paragraph):
            if segment.strip():
                yield segment


def _candidates(root: Any) -> Iterator[tuple[str, list[str]]]:
    """``(종류, 그 요소가 담은 글 조각들)``을 문서 순서로 낸다."""

    from ..tools.markdown_export import equation_markdown

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
            # 수식은 LaTeX로 바뀌어 실린다. 실린 모양 그대로를 찾는다.
            yield "equation", [equation_markdown("".join(script.itertext())) if script is not None else ""]
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

    haystack = _markdown_haystack(markdown)
    found: dict[str, dict[str, int]] = {}
    seen: set[tuple[str, tuple[str, ...]]] = set()
    cursor = 0

    def present(piece: str) -> bool:
        # 조각은 대개 문서 순서로 실려 있다. 앞서 찾은 자리부터 찾으면 큰 문서도 한 번 훑는다.
        nonlocal cursor
        index = haystack.find(piece, cursor)
        if index < 0:
            index = haystack.find(piece)
        if index < 0:
            return False
        cursor = index + len(piece)
        return True

    def record(kind: str, pieces: Iterable[str]) -> None:
        missing = [piece for piece in pieces if _squash(piece) and not present(_squash(piece))]
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
        record(
            "master_page",
            [
                segment
                for paragraph in master_page.element.iter(f"{_HP}p")
                for segment in _own_segments(paragraph)
                if segment.strip()
            ],
        )

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


_OLE2_MAGIC = HwpxPackage.OLE2_MAGIC


def _starts_with_ole2(file_stream: BinaryIO) -> bool:
    """HWP 5.0(``.hwp``)이 쓰는 복합 파일로 시작하는가."""

    cur_pos = file_stream.tell()
    try:
        return file_stream.read(len(_OLE2_MAGIC)) == _OLE2_MAGIC
    finally:
        file_stream.seek(cur_pos)


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
