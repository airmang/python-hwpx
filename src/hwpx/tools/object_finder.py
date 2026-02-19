"""Helper utilities that locate XML objects inside HWPX archives."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import (
    Callable,
    Dict,
    Iterator,
    List,
    Mapping,
    Optional,
    Pattern,
    Sequence,
    Tuple,
    Union,
)
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from .text_extractor import (
    DEFAULT_NAMESPACES,
    AnnotationOptions,
    SectionInfo,
    TextExtractor,
    _resolve_control_nested_text,
    _resolve_hyperlink_target,
    _resolve_note_text,
    build_parent_map,
    describe_element_path,
    strip_namespace,
    tag_matches,
)

__all__ = ["AttrMatcher", "AnnotationMatch", "FoundElement", "ObjectFinder"]


AttrMatcher = Union[str, Sequence[str], Pattern[str], Callable[[str], bool]]


@dataclass(frozen=True)
class FoundElement:
    """Location information for an XML element that matched a query."""

    section: SectionInfo
    path: str
    element: ET.Element

    @property
    def tag(self) -> str:
        """Return the local tag name for the matched element."""

        return strip_namespace(self.element.tag)

    @property
    def hierarchy(self) -> Tuple[str, ...]:
        """Return the split representation of :pyattr:`path`."""

        return tuple(self.path.split("/"))

    @property
    def text(self) -> Optional[str]:
        """Expose ``element.text`` for convenience."""

        return self.element.text

    def get(self, name: str, default: Optional[str] = None) -> Optional[str]:
        """Fetch an attribute value from the underlying element."""

        return self.element.attrib.get(name, default)

    def __str__(self) -> str:  # pragma: no cover - debugging helper
        section = self.section.name
        return f"{section}:{self.path} <{self.tag}>"


@dataclass(frozen=True)
class AnnotationMatch:
    """Representation of a document annotation located by the finder."""

    kind: str
    element: FoundElement
    value: Optional[str]


class ObjectFinder:
    """Perform element searches across the XML payload in an HWPX document."""

    def __init__(
        self,
        source: Union[str, Path, ZipFile],
        *,
        namespaces: Optional[Mapping[str, str]] = None,
    ) -> None:
        self._source = source
        merged_namespaces = dict(DEFAULT_NAMESPACES)
        if namespaces:
            merged_namespaces.update(namespaces)
        self.namespaces: Dict[str, str] = merged_namespaces

    def iter(
        self,
        *,
        tag: Union[str, Sequence[str], None] = None,
        attrs: Optional[Mapping[str, AttrMatcher]] = None,
        xpath: Optional[str] = None,
        limit: Optional[int] = None,
        section_filter: Optional[Callable[[SectionInfo], bool]] = None,
    ) -> Iterator[FoundElement]:
        """Yield elements that match a combination of criteria."""

        with TextExtractor(self._source, namespaces=self.namespaces) as extractor:
            for section in extractor.iter_sections():
                if section_filter is not None and not section_filter(section):
                    continue
                parent_map = build_parent_map(section.element)
                if xpath is not None:
                    candidates = section.element.findall(xpath, namespaces=self.namespaces)
                else:
                    candidates = section.element.iter()
                for element in candidates:
                    if tag is not None and not tag_matches(element.tag, tag, self.namespaces):
                        continue
                    if attrs and not self._match_attributes(element, attrs):
                        continue
                    path = describe_element_path(element, parent_map)
                    yield FoundElement(section=section, path=path, element=element)
                    if limit is not None:
                        limit -= 1
                        if limit <= 0:
                            return

    def find_first(
        self,
        *,
        tag: Union[str, Sequence[str], None] = None,
        attrs: Optional[Mapping[str, AttrMatcher]] = None,
        xpath: Optional[str] = None,
        section_filter: Optional[Callable[[SectionInfo], bool]] = None,
    ) -> Optional[FoundElement]:
        """Return the first element that matches or ``None`` when absent."""

        return next(
            self.iter(
                tag=tag,
                attrs=attrs,
                xpath=xpath,
                limit=1,
                section_filter=section_filter,
            ),
            None,
        )

    def find_all(
        self,
        *,
        tag: Union[str, Sequence[str], None] = None,
        attrs: Optional[Mapping[str, AttrMatcher]] = None,
        xpath: Optional[str] = None,
        section_filter: Optional[Callable[[SectionInfo], bool]] = None,
        limit: Optional[int] = None,
    ) -> List[FoundElement]:
        """Return every matching element eagerly as a list."""

        return list(
            self.iter(
                tag=tag,
                attrs=attrs,
                xpath=xpath,
                limit=limit,
                section_filter=section_filter,
            )
        )

    def iter_annotations(
        self,
        *,
        kinds: Optional[Sequence[str]] = None,
        options: Optional[AnnotationOptions] = None,
        section_filter: Optional[Callable[[SectionInfo], bool]] = None,
        preserve_breaks: bool = True,
    ) -> Iterator[AnnotationMatch]:
        """Yield annotations such as highlights or notes with formatted values."""

        requested = {
            kind.lower() for kind in (kinds or ("highlight", "footnote", "endnote", "hyperlink", "control"))
        }
        if not requested:
            return

        render_options = options or AnnotationOptions()

        with TextExtractor(self._source, namespaces=self.namespaces) as extractor:
            for section in extractor.iter_sections():
                if section_filter is not None and not section_filter(section):
                    continue
                parent_map = build_parent_map(section.element)

                if "highlight" in requested:
                    for element in section.element.findall(
                        ".//hp:markpenBegin", namespaces=self.namespaces
                    ):
                        path = describe_element_path(element, parent_map)
                        found = FoundElement(section=section, path=path, element=element)
                        color = element.get("color") or ""
                        if render_options.highlight == "markers":
                            value = render_options.highlight_start.format(color=color)
                        else:
                            value = render_options.highlight_summary.format(color=color)
                        yield AnnotationMatch("highlight", found, value)

                if "footnote" in requested:
                    for element in section.element.findall(
                        ".//hp:footNote", namespaces=self.namespaces
                    ):
                        yield self._format_note_annotation(
                            extractor,
                            section,
                            parent_map,
                            element,
                            kind="footnote",
                            options=render_options,
                            preserve_breaks=preserve_breaks,
                        )

                if "endnote" in requested:
                    for element in section.element.findall(
                        ".//hp:endNote", namespaces=self.namespaces
                    ):
                        yield self._format_note_annotation(
                            extractor,
                            section,
                            parent_map,
                            element,
                            kind="endnote",
                            options=render_options,
                            preserve_breaks=preserve_breaks,
                        )

                if "hyperlink" in requested:
                    for element in section.element.findall(
                        ".//hp:fieldBegin", namespaces=self.namespaces
                    ):
                        field_type = (element.get("type") or "").upper()
                        if field_type != "HYPERLINK":
                            continue
                        path = describe_element_path(element, parent_map)
                        found = FoundElement(section=section, path=path, element=element)
                        target = _resolve_hyperlink_target(element, self.namespaces) or ""
                        behavior = render_options.hyperlink
                        if behavior == "target":
                            value = render_options.hyperlink_target_format.format(target=target)
                        elif behavior == "marker":
                            value = render_options.hyperlink_marker_format.format(target=target)
                        else:
                            value = render_options.hyperlink_summary.format(target=target)
                        yield AnnotationMatch("hyperlink", found, value)

                if "control" in requested:
                    for element in section.element.findall(
                        ".//hp:ctrl", namespaces=self.namespaces
                    ):
                        field_begin = element.find("hp:fieldBegin", namespaces=self.namespaces)
                        if field_begin is not None and (field_begin.get("type") or "").upper() == "HYPERLINK":
                            continue
                        if element.find("hp:fieldEnd", namespaces=self.namespaces) is not None:
                            continue
                        path = describe_element_path(element, parent_map)
                        found = FoundElement(section=section, path=path, element=element)
                        first_child = next(iter(element), None)
                        name = strip_namespace(first_child.tag) if first_child is not None else "ctrl"
                        ctrl_type = (
                            first_child.get("type") if first_child is not None else element.get("type") or ""
                        )
                        behavior = render_options.control
                        if behavior == "nested":
                            value = _resolve_control_nested_text(
                                extractor,
                                element,
                                render_options,
                                preserve_breaks=preserve_breaks,
                            )
                        elif behavior == "marker":
                            value = render_options.control_marker_format.format(name=name, type=ctrl_type)
                        else:
                            value = render_options.control_summary.format(name=name, type=ctrl_type)
                        yield AnnotationMatch("control", found, value)

    def _format_note_annotation(
        self,
        extractor: TextExtractor,
        section: SectionInfo,
        parent_map: Mapping[ET.Element, ET.Element],
        element: ET.Element,
        *,
        kind: str,
        options: AnnotationOptions,
        preserve_breaks: bool,
    ) -> AnnotationMatch:
        path = describe_element_path(element, parent_map)
        found = FoundElement(section=section, path=path, element=element)
        inst_id = element.get("instId") or ""
        behavior = options.footnote if kind == "footnote" else options.endnote
        if behavior == "inline":
            text = _resolve_note_text(
                extractor,
                element,
                options,
                preserve_breaks=preserve_breaks,
            )
            value = options.note_inline_format.format(kind=kind, inst_id=inst_id, text=text)
        elif behavior == "marker":
            value = options.note_marker_format.format(kind=kind, inst_id=inst_id)
        else:
            value = options.note_summary.format(kind=kind, inst_id=inst_id)
        return AnnotationMatch(kind, found, value)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _match_attributes(
        element: ET.Element,
        expected: Mapping[str, AttrMatcher],
    ) -> bool:
        for name, matcher in expected.items():
            value = element.attrib.get(name)
            if value is None:
                return False
            if isinstance(matcher, str):
                if value != matcher:
                    return False
            elif isinstance(matcher, Sequence) and not isinstance(matcher, (str, bytes)):
                if value not in matcher:
                    return False
            elif hasattr(matcher, "search"):
                if not matcher.search(value):  # type: ignore[call-arg]
                    return False
            elif callable(matcher):
                if not matcher(value):
                    return False
            else:
                raise TypeError(
                    "Attribute matchers must be str, Sequence, Pattern or callable",
                )
        return True
