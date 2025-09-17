"""High-level routines for traversing text inside HWPX documents."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, Mapping, Optional, Sequence, Tuple, Union, Literal
from xml.etree import ElementTree as ET
from zipfile import ZipFile

__all__ = [
    "DEFAULT_NAMESPACES",
    "AnnotationOptions",
    "ParagraphInfo",
    "SectionInfo",
    "TextExtractor",
    "build_parent_map",
    "describe_element_path",
    "strip_namespace",
]

DEFAULT_NAMESPACES: Dict[str, str] = {
    "hp": "http://www.hancom.co.kr/hwpml/2011/paragraph",
    "hp10": "http://www.hancom.co.kr/hwpml/2016/paragraph",
    "hs": "http://www.hancom.co.kr/hwpml/2011/section",
    "hc": "http://www.hancom.co.kr/hwpml/2011/core",
    "ha": "http://www.hancom.co.kr/hwpml/2011/app",
    "hh": "http://www.hancom.co.kr/hwpml/2011/head",
    "hhs": "http://www.hancom.co.kr/hwpml/2011/history",
    "hm": "http://www.hancom.co.kr/hwpml/2011/master-page",
    "hpf": "http://www.hancom.co.kr/schema/2011/hpf",
    "dc": "http://purl.org/dc/elements/1.1/",
    "opf": "http://www.idpf.org/2007/opf/",
}

_SECTION_PATTERN = re.compile(r"^Contents/section(\d+)\.xml$")

_OBJECT_CONTAINERS = {
    "tbl",
    "container",
    "line",
    "rect",
    "ellipse",
    "arc",
    "polygon",
    "curve",
    "connectLine",
    "textart",
    "pic",
    "compose",
    "switch",
    "equation",
    "ole",
    "edit",
    "btn",
    "checkBtn",
    "radioBtn",
}

_ObjectBehavior = Union[str, None]

HighlightBehavior = Literal["ignore", "markers"]
NoteBehavior = Literal["ignore", "placeholder", "inline"]
HyperlinkBehavior = Literal["ignore", "placeholder", "target"]
ControlBehavior = Literal["ignore", "placeholder", "nested"]


@dataclass(frozen=True)
class AnnotationOptions:
    """Configuration describing how inline annotations should be rendered."""

    highlight: HighlightBehavior = "ignore"
    highlight_start: str = "[HIGHLIGHT color={color}]"
    highlight_end: str = "[/HIGHLIGHT]"
    highlight_summary: str = "color={color}"

    footnote: NoteBehavior = "ignore"
    endnote: NoteBehavior = "ignore"
    note_inline_format: str = "[{kind}:{text}]"
    note_placeholder: str = "[{kind}:{inst_id}]"
    note_summary: str = "{kind}:{inst_id}"
    note_joiner: str = " "

    hyperlink: HyperlinkBehavior = "ignore"
    hyperlink_target_format: str = "<{target}>"
    hyperlink_placeholder: str = "[LINK:{target}]"
    hyperlink_summary: str = "{target}"

    control: ControlBehavior = "ignore"
    control_placeholder: str = "[CTRL:{name}]"
    control_summary: str = "{name}"
    control_joiner: str = "\n"


@dataclass(frozen=True)
class SectionInfo:
    """Metadata for a section XML file bundled within an HWPX document."""

    index: int
    """Zero-based index of the section as it appears in ``content.hpf``."""

    name: str
    """Path of the section XML entry within the archive."""

    element: ET.Element
    """Parsed XML element representing the ``hs:sec`` root node."""


@dataclass(frozen=True)
class ParagraphInfo:
    """Container describing a paragraph extracted from a section."""

    section: SectionInfo
    index: int
    element: ET.Element
    path: str
    hierarchy: Tuple[str, ...]
    _extractor: "TextExtractor"

    @property
    def tag(self) -> str:
        """Return the local tag name (normally ``p``)."""

        return strip_namespace(self.element.tag)

    @property
    def ancestors(self) -> Tuple[str, ...]:
        """Return the hierarchy leading to the paragraph (excluding itself)."""

        return self.hierarchy[:-1]

    @property
    def is_nested(self) -> bool:
        """Whether the paragraph resides inside an object such as a table."""

        return len(self.ancestors) > 1

    def text(
        self,
        *,
        object_behavior: _ObjectBehavior = "skip",
        object_placeholder: Optional[str] = None,
        preserve_breaks: bool = True,
        annotations: Optional[AnnotationOptions] = None,
    ) -> str:
        """Return the paragraph text using the parent extractor's settings."""

        return self._extractor.paragraph_text(
            self.element,
            object_behavior=object_behavior,
            object_placeholder=object_placeholder,
            preserve_breaks=preserve_breaks,
            annotations=annotations,
        )

    def __str__(self) -> str:  # pragma: no cover - convenience only
        return self.text()


class TextExtractor:
    """High level helper that walks through sections and paragraphs."""

    def __init__(
        self,
        source: Union[str, Path, ZipFile],
        *,
        namespaces: Optional[Mapping[str, str]] = None,
    ) -> None:
        self._source = source
        self._zip: Optional[ZipFile] = None
        self._owns_zip = False
        merged_namespaces = dict(DEFAULT_NAMESPACES)
        if namespaces:
            merged_namespaces.update(namespaces)
        self.namespaces: Dict[str, str] = merged_namespaces

    # ------------------------------------------------------------------
    # Context manager helpers
    # ------------------------------------------------------------------
    def open(self) -> ZipFile:
        """Open the underlying archive if necessary and return it."""

        if self._zip is None:
            if isinstance(self._source, ZipFile):
                self._zip = self._source
                self._owns_zip = False
            else:
                self._zip = ZipFile(self._source)  # type: ignore[arg-type]
                self._owns_zip = True
        return self._zip

    def close(self) -> None:
        """Close the archive when owned by the extractor."""

        if self._zip is not None and self._owns_zip:
            self._zip.close()
        self._zip = None
        self._owns_zip = False

    def __enter__(self) -> "TextExtractor":  # pragma: no cover - trivial
        self.open()
        return self

    def __exit__(self, *_exc: object) -> None:  # pragma: no cover - trivial
        self.close()

    # ------------------------------------------------------------------
    # Iteration helpers
    # ------------------------------------------------------------------
    def iter_sections(self) -> Iterator[SectionInfo]:
        """Yield :class:`SectionInfo` objects for each section XML entry."""

        archive = self.open()
        section_files = list(self._iter_section_files(archive))
        for index, name in enumerate(section_files):
            data = archive.read(name)
            element = ET.fromstring(data)
            yield SectionInfo(index=index, name=name, element=element)

    def iter_paragraphs(
        self,
        section: SectionInfo,
        *,
        include_nested: bool = True,
    ) -> Iterator[ParagraphInfo]:
        """Yield paragraphs contained inside *section* in document order."""

        root = section.element
        parent_map = build_parent_map(root)
        if include_nested:
            paragraph_elements = list(root.findall(".//hp:p", namespaces=self.namespaces))
        else:
            paragraph_elements = [
                child
                for child in root
                if tag_matches(child.tag, "hp:p", self.namespaces)
            ]

        for index, element in enumerate(paragraph_elements):
            path = describe_element_path(element, parent_map)
            hierarchy = tuple(path.split("/"))
            yield ParagraphInfo(
                section=section,
                index=index,
                element=element,
                path=path,
                hierarchy=hierarchy,
                _extractor=self,
            )

    def iter_document_paragraphs(
        self,
        *,
        include_nested: bool = True,
    ) -> Iterator[ParagraphInfo]:
        """Yield every paragraph across all sections."""

        for section in self.iter_sections():
            yield from self.iter_paragraphs(section, include_nested=include_nested)

    # ------------------------------------------------------------------
    # Text helpers
    # ------------------------------------------------------------------
    def paragraph_text(
        self,
        paragraph: ET.Element,
        *,
        object_behavior: _ObjectBehavior = "skip",
        object_placeholder: Optional[str] = None,
        preserve_breaks: bool = True,
        annotations: Optional[AnnotationOptions] = None,
    ) -> str:
        """Return a string representation of a paragraph element."""

        fragments: list[str] = []
        for run in paragraph.findall("hp:run", namespaces=self.namespaces):
            for child in run:
                tag = strip_namespace(child.tag)
                if tag == "t":
                    self._render_text_element(child, fragments, annotations)
                elif tag == "lineBreak":
                    if preserve_breaks:
                        fragments.append("\n")
                elif tag == "tab":
                    fragments.append("\t" if preserve_breaks else " ")
                elif tag in {"footNote", "endNote"}:
                    self._handle_note(
                        child,
                        fragments,
                        tag,
                        annotations=annotations,
                        preserve_breaks=preserve_breaks,
                    )
                elif tag == "ctrl":
                    self._handle_control(
                        child,
                        fragments,
                        annotations=annotations,
                        preserve_breaks=preserve_breaks,
                    )
                elif tag in _OBJECT_CONTAINERS:
                    self._handle_object(
                        child,
                        fragments,
                        behavior=object_behavior,
                        placeholder=object_placeholder,
                        preserve_breaks=preserve_breaks,
                        annotations=annotations,
                    )
                else:
                    self._handle_unexpected(
                        child,
                        fragments,
                        behavior=object_behavior,
                        placeholder=object_placeholder,
                        preserve_breaks=preserve_breaks,
                        annotations=annotations,
                    )
        return "".join(fragments)

    def _handle_object(
        self,
        element: ET.Element,
        fragments: list[str],
        *,
        behavior: _ObjectBehavior,
        placeholder: Optional[str],
        preserve_breaks: bool,
        annotations: Optional[AnnotationOptions],
    ) -> None:
        tag = strip_namespace(element.tag)
        if behavior == "skip" or behavior is None:
            return
        if behavior == "placeholder":
            placeholder = placeholder or "[{type}]"
            fragments.append(placeholder.format(type=tag))
            return
        if behavior == "nested":
            for inner_paragraph in element.findall(".//hp:p", namespaces=self.namespaces):
                text = self.paragraph_text(
                    inner_paragraph,
                    object_behavior=behavior,
                    object_placeholder=placeholder,
                    preserve_breaks=preserve_breaks,
                    annotations=annotations,
                )
                if text:
                    fragments.append(text)
                    if preserve_breaks:
                        fragments.append("\n")
            if fragments and fragments[-1] == "\n":
                fragments.pop()
            return
        raise ValueError(f"Unsupported object behavior: {behavior!r}")

    def _handle_unexpected(
        self,
        element: ET.Element,
        fragments: list[str],
        *,
        behavior: _ObjectBehavior,
        placeholder: Optional[str],
        preserve_breaks: bool,
        annotations: Optional[AnnotationOptions],
    ) -> None:
        tag = strip_namespace(element.tag)
        if tag == "ctrl":
            self._handle_control(
                element,
                fragments,
                annotations=annotations,
                preserve_breaks=preserve_breaks,
            )
            return
        if behavior == "placeholder":
            placeholder = placeholder or "[{type}]"
            fragments.append(placeholder.format(type=tag))
        elif behavior == "nested":
            # Attempt to gather nested paragraph text for unknown containers.
            for inner_paragraph in element.findall(".//hp:p", namespaces=self.namespaces):
                text = self.paragraph_text(
                    inner_paragraph,
                    object_behavior=behavior,
                    object_placeholder=placeholder,
                    preserve_breaks=preserve_breaks,
                    annotations=annotations,
                )
                if text:
                    fragments.append(text)
                    if preserve_breaks:
                        fragments.append("\n")
            if fragments and fragments[-1] == "\n":
                fragments.pop()
        else:
            # Default: ignore the element silently.
            return

    def _render_text_element(
        self,
        element: ET.Element,
        fragments: list[str],
        annotations: Optional[AnnotationOptions],
    ) -> None:
        if element.text:
            fragments.append(element.text)

        highlight_stack: list[Optional[str]] = []
        highlight_mode = annotations.highlight if annotations else "ignore"

        for child in element:
            tag = strip_namespace(child.tag)
            if tag == "markpenBegin":
                color = child.get("color") or ""
                highlight_stack.append(color)
                if annotations and highlight_mode == "markers":
                    fragments.append(
                        annotations.highlight_start.format(color=color or "")
                    )
            elif tag == "markpenEnd":
                color = highlight_stack.pop() if highlight_stack else ""
                if annotations and highlight_mode == "markers":
                    fragments.append(
                        annotations.highlight_end.format(color=color or "")
                    )
            else:
                self._render_text_element(child, fragments, annotations)

            if child.tail:
                fragments.append(child.tail)

        while highlight_stack:
            color = highlight_stack.pop()
            if annotations and highlight_mode == "markers":
                fragments.append(annotations.highlight_end.format(color=color or ""))

    def _handle_note(
        self,
        element: ET.Element,
        fragments: list[str],
        kind: str,
        *,
        annotations: Optional[AnnotationOptions],
        preserve_breaks: bool,
    ) -> None:
        if annotations is None:
            return
        option = annotations.footnote if kind == "footNote" else annotations.endnote
        if option == "ignore":
            return

        kind_name = "footnote" if kind == "footNote" else "endnote"
        inst_id = element.get("instId") or ""

        if option == "placeholder":
            fragments.append(
                annotations.note_placeholder.format(kind=kind_name, inst_id=inst_id)
            )
            return

        if option == "inline":
            note_text = _resolve_note_text(
                self,
                element,
                annotations,
                preserve_breaks=preserve_breaks,
            )
            fragments.append(
                annotations.note_inline_format.format(
                    kind=kind_name, inst_id=inst_id, text=note_text
                )
            )

    def _handle_control(
        self,
        element: ET.Element,
        fragments: list[str],
        *,
        annotations: Optional[AnnotationOptions],
        preserve_breaks: bool,
    ) -> None:
        if annotations is None:
            return

        field_begin = element.find("hp:fieldBegin", namespaces=self.namespaces)
        if field_begin is not None:
            field_type = field_begin.get("type") or ""
            if field_type == "HYPERLINK":
                self._handle_hyperlink(field_begin, fragments, annotations)
                return

        if element.find("hp:fieldEnd", namespaces=self.namespaces) is not None:
            return

        behavior = annotations.control
        if behavior == "ignore":
            return
        if behavior == "nested":
            text = _resolve_control_nested_text(
                self,
                element,
                annotations,
                preserve_breaks=preserve_breaks,
            )
            if text:
                fragments.append(text)
            return
        if behavior == "placeholder":
            first_child = next(iter(element), None)
            name = strip_namespace(first_child.tag) if first_child is not None else "ctrl"
            ctrl_type = (
                first_child.get("type") if first_child is not None else element.get("type")
            )
            fragments.append(
                annotations.control_placeholder.format(name=name, type=ctrl_type or "")
            )

    def _handle_hyperlink(
        self,
        field_begin: ET.Element,
        fragments: list[str],
        annotations: AnnotationOptions,
    ) -> None:
        behavior = annotations.hyperlink
        target = _resolve_hyperlink_target(field_begin, self.namespaces)
        if behavior == "placeholder":
            fragments.append(
                annotations.hyperlink_placeholder.format(target=target or "")
            )
        elif behavior == "target":
            if target:
                fragments.append(
                    annotations.hyperlink_target_format.format(target=target)
                )

    def extract_text(
        self,
        *,
        paragraph_separator: str = "\n",
        skip_empty: bool = True,
        include_nested: bool = True,
        object_behavior: _ObjectBehavior = "skip",
        object_placeholder: Optional[str] = None,
        preserve_breaks: bool = True,
        annotations: Optional[AnnotationOptions] = None,
    ) -> str:
        """Return the plain text for all paragraphs in the document."""

        texts: list[str] = []
        for paragraph in self.iter_document_paragraphs(include_nested=include_nested):
            text = paragraph.text(
                object_behavior=object_behavior,
                object_placeholder=object_placeholder,
                preserve_breaks=preserve_breaks,
                annotations=annotations,
            )
            if skip_empty and not text.strip():
                continue
            texts.append(text)
        return paragraph_separator.join(texts)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _iter_section_files(self, archive: ZipFile) -> Iterator[str]:
        try:
            manifest = archive.read("Contents/content.hpf")
        except KeyError:
            manifest = None

        if manifest:
            root = ET.fromstring(manifest)
            items = [
                item.get("href")
                for item in root.findall(".//opf:item", namespaces=self.namespaces)
                if item.get("href") and _SECTION_PATTERN.match(item.get("href"))
            ]
            if items:
                return iter(items)

        section_files = [
            name
            for name in archive.namelist()
            if _SECTION_PATTERN.match(name)
        ]
        section_files.sort(key=_section_sort_key)
        return iter(section_files)


# ----------------------------------------------------------------------
# General XML helpers shared with the object finder
# ----------------------------------------------------------------------


def _resolve_note_text(
    extractor: "TextExtractor",
    element: ET.Element,
    annotations: Optional[AnnotationOptions],
    *,
    preserve_breaks: bool,
) -> str:
    sub_list = element.find("hp:subList", namespaces=extractor.namespaces)
    if sub_list is None:
        return ""

    texts: list[str] = []
    for inner_paragraph in sub_list.findall(".//hp:p", namespaces=extractor.namespaces):
        text = extractor.paragraph_text(
            inner_paragraph,
            object_behavior="skip",
            object_placeholder=None,
            preserve_breaks=preserve_breaks,
            annotations=annotations,
        )
        if text:
            texts.append(text)

    joiner = annotations.note_joiner if annotations else " "
    return joiner.join(texts)


def _resolve_control_nested_text(
    extractor: "TextExtractor",
    element: ET.Element,
    annotations: Optional[AnnotationOptions],
    *,
    preserve_breaks: bool,
) -> str:
    texts: list[str] = []
    for inner_paragraph in element.findall(".//hp:p", namespaces=extractor.namespaces):
        text = extractor.paragraph_text(
            inner_paragraph,
            object_behavior="skip",
            object_placeholder=None,
            preserve_breaks=preserve_breaks,
            annotations=annotations,
        )
        if text:
            texts.append(text)

    if not texts:
        return ""
    joiner = annotations.control_joiner if annotations else "\n"
    return joiner.join(texts)


def _resolve_hyperlink_target(
    field_begin: ET.Element,
    namespaces: Mapping[str, str],
) -> Optional[str]:
    params = field_begin.find("hp:parameters", namespaces=namespaces)
    if params is None:
        return None

    for string_param in params.findall("hp:stringParam", namespaces=namespaces):
        if string_param.get("name") == "Command":
            value = string_param.text or ""
            if "|" in value:
                return value.split("|", 1)[0]
            return value
    return None


def strip_namespace(tag: str) -> str:
    """Return the local component of an XML tag."""

    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def tag_matches(candidate: str, query: Union[str, Sequence[str]], namespaces: Mapping[str, str]) -> bool:
    """Return ``True`` when *candidate* matches *query* according to namespaces."""

    if isinstance(query, Sequence) and not isinstance(query, str):
        return any(tag_matches(candidate, item, namespaces) for item in query)

    if isinstance(query, str):
        if query.startswith("{"):
            return candidate == query
        if ":" in query:
            prefix, local = query.split(":", 1)
            namespace = namespaces.get(prefix)
            if namespace is None:
                return False
            return candidate == f"{{{namespace}}}{local}"
        return strip_namespace(candidate) == query

    raise TypeError("query must be a string or sequence of strings")


def build_parent_map(root: ET.Element) -> Dict[ET.Element, ET.Element]:
    """Construct a mapping that describes the parent of every node in *root*."""

    return {child: parent for parent in root.iter() for child in parent}


def describe_element_path(
    element: ET.Element,
    parent_map: Mapping[ET.Element, ET.Element],
) -> str:
    """Return an XPath-like representation for *element*."""

    parts: list[str] = []
    current: Optional[ET.Element] = element
    while current is not None:
        parent = parent_map.get(current)
        local = strip_namespace(current.tag)
        if parent is None:
            parts.append(local)
            break
        siblings = [child for child in parent if strip_namespace(child.tag) == local]
        if len(siblings) > 1:
            index = siblings.index(current)
            parts.append(f"{local}[{index}]")
        else:
            parts.append(local)
        current = parent
    return "/".join(reversed(parts))


def _section_sort_key(name: str) -> Tuple[int, str]:
    match = _SECTION_PATTERN.match(name)
    if match:
        return (int(match.group(1)), name)
    return (0, name)
