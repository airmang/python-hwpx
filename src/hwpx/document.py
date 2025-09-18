"""High-level representation of an HWPX document."""

from __future__ import annotations

from datetime import datetime
import uuid
import xml.etree.ElementTree as ET

from os import PathLike
from typing import BinaryIO, Iterator, List, Tuple

from .oxml import (
    HwpxOxmlDocument,
    HwpxOxmlHeader,
    HwpxOxmlInlineObject,
    HwpxOxmlMemo,
    HwpxOxmlParagraph,
    HwpxOxmlRun,
    HwpxOxmlSection,
    HwpxOxmlSectionHeaderFooter,
    HwpxOxmlTable,
    MemoShape,
    RunStyle,
)
from .package import HwpxPackage
from .templates import blank_document_bytes

_HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
_HP = f"{{{_HP_NS}}}"
_HH_NS = "http://www.hancom.co.kr/hwpml/2011/head"
_HH = f"{{{_HH_NS}}}"


class HwpxDocument:
    """Provides a user-friendly API for editing HWPX documents."""

    def __init__(self, package: HwpxPackage, root: HwpxOxmlDocument):
        self._package = package
        self._root = root

    # ------------------------------------------------------------------
    # construction helpers
    @classmethod
    def open(
        cls,
        source: str | PathLike[str] | bytes | BinaryIO,
    ) -> "HwpxDocument":
        """Open *source* and return a :class:`HwpxDocument` instance."""
        package = HwpxPackage.open(source)
        root = HwpxOxmlDocument.from_package(package)
        return cls(package, root)

    @classmethod
    def new(cls) -> "HwpxDocument":
        """Return a new blank document based on the default skeleton template."""

        return cls.open(blank_document_bytes())

    @classmethod
    def from_package(cls, package: HwpxPackage) -> "HwpxDocument":
        """Create a document backed by an existing :class:`HwpxPackage`."""
        root = HwpxOxmlDocument.from_package(package)
        return cls(package, root)

    # ------------------------------------------------------------------
    # properties exposing document content
    @property
    def package(self) -> HwpxPackage:
        """Return the :class:`HwpxPackage` backing this document."""
        return self._package

    @property
    def oxml(self) -> HwpxOxmlDocument:
        """Return the low-level XML object tree representing the document."""
        return self._root

    @property
    def sections(self) -> List[HwpxOxmlSection]:
        """Return the sections contained in the document."""
        return self._root.sections

    @property
    def headers(self) -> List[HwpxOxmlHeader]:
        """Return the header parts referenced by the document."""
        return self._root.headers

    @property
    def memo_shapes(self) -> dict[str, MemoShape]:
        """Return memo shapes available in the header reference lists."""

        return self._root.memo_shapes

    def memo_shape(self, memo_shape_id_ref: int | str | None) -> MemoShape | None:
        """Return the memo shape definition referenced by *memo_shape_id_ref*."""

        return self._root.memo_shape(memo_shape_id_ref)

    @property
    def memos(self) -> List[HwpxOxmlMemo]:
        """Return all memo entries declared in every section."""

        memos: List[HwpxOxmlMemo] = []
        for section in self._root.sections:
            memos.extend(section.memos)
        return memos

    def add_memo(
        self,
        text: str = "",
        *,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        memo_shape_id_ref: str | int | None = None,
        memo_id: str | None = None,
        char_pr_id_ref: str | int | None = None,
        attributes: dict[str, str] | None = None,
    ) -> HwpxOxmlMemo:
        """Create a memo entry inside *section* (or the last section by default)."""

        if section is None and section_index is not None:
            section = self._root.sections[section_index]
        if section is None:
            if not self._root.sections:
                raise ValueError("document does not contain any sections")
            section = self._root.sections[-1]
        return section.add_memo(
            text,
            memo_shape_id_ref=memo_shape_id_ref,
            memo_id=memo_id,
            char_pr_id_ref=char_pr_id_ref,
            attributes=attributes,
        )

    def remove_memo(self, memo: HwpxOxmlMemo) -> None:
        """Remove *memo* from the section it belongs to."""

        memo.remove()

    def attach_memo_field(
        self,
        paragraph: HwpxOxmlParagraph,
        memo: HwpxOxmlMemo,
        *,
        field_id: str | None = None,
        author: str | None = None,
        created: datetime | str | None = None,
        number: int = 1,
        char_pr_id_ref: str | int | None = None,
    ) -> str:
        """Attach a MEMO field control to *paragraph* so Hangul shows *memo*."""

        if paragraph.section is None:
            raise ValueError("paragraph must belong to a section before anchoring a memo")
        if memo.group.section is None:
            raise ValueError("memo is not attached to a section")

        field_value = field_id or uuid.uuid4().hex
        author_value = author or memo.attributes.get("author") or ""

        created_value = created if created is not None else memo.attributes.get("createDateTime")
        if isinstance(created_value, datetime):
            created_value = created_value.strftime("%Y-%m-%d %H:%M:%S")
        elif created_value is None:
            created_value = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        else:
            created_value = str(created_value)

        memo_shape_id = memo.memo_shape_id_ref or ""

        char_ref = char_pr_id_ref
        if char_ref is None:
            char_ref = paragraph.char_pr_id_ref
        if char_ref is None:
            char_ref = memo._infer_char_pr_id_ref()
        if char_ref is None:
            char_ref = "0"
        char_ref = str(char_ref)

        run_begin = ET.Element(f"{_HP}run", {"charPrIDRef": char_ref})
        ctrl_begin = ET.SubElement(run_begin, f"{_HP}ctrl")
        field_begin = ET.SubElement(
            ctrl_begin,
            f"{_HP}fieldBegin",
            {
                "id": field_value,
                "type": "MEMO",
                "editable": "true",
                "dirty": "false",
                "fieldid": field_value,
            },
        )

        parameters = ET.SubElement(field_begin, f"{_HP}parameters", {"count": "5", "name": ""})
        ET.SubElement(parameters, f"{_HP}stringParam", {"name": "ID"}).text = memo.id or ""
        ET.SubElement(parameters, f"{_HP}integerParam", {"name": "Number"}).text = str(max(1, number))
        ET.SubElement(parameters, f"{_HP}stringParam", {"name": "CreateDateTime"}).text = created_value
        ET.SubElement(parameters, f"{_HP}stringParam", {"name": "Author"}).text = author_value
        ET.SubElement(parameters, f"{_HP}stringParam", {"name": "MemoShapeID"}).text = memo_shape_id

        sub_list = ET.SubElement(
            field_begin,
            f"{_HP}subList",
            {
                "id": f"memo-field-{memo.id or field_value}",
                "textDirection": "HORIZONTAL",
                "lineWrap": "BREAK",
                "vertAlign": "TOP",
            },
        )
        sub_para = ET.SubElement(
            sub_list,
            f"{_HP}p",
            {
                "id": f"memo-field-{(memo.id or field_value)}-p",
                "paraPrIDRef": "0",
                "styleIDRef": "0",
                "pageBreak": "0",
                "columnBreak": "0",
                "merged": "0",
            },
        )
        sub_run = ET.SubElement(sub_para, f"{_HP}run", {"charPrIDRef": char_ref})
        ET.SubElement(sub_run, f"{_HP}t").text = memo.id or field_value

        run_end = ET.Element(f"{_HP}run", {"charPrIDRef": char_ref})
        ctrl_end = ET.SubElement(run_end, f"{_HP}ctrl")
        ET.SubElement(ctrl_end, f"{_HP}fieldEnd", {"beginIDRef": field_value, "fieldid": field_value})

        paragraph.element.insert(0, run_begin)
        paragraph.element.append(run_end)
        paragraph.section.mark_dirty()

        return field_value

    def add_memo_with_anchor(
        self,
        text: str = "",
        *,
        paragraph: HwpxOxmlParagraph | None = None,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        paragraph_text: str | None = None,
        memo_shape_id_ref: str | int | None = None,
        memo_id: str | None = None,
        char_pr_id_ref: str | int | None = None,
        attributes: dict[str, str] | None = None,
        field_id: str | None = None,
        author: str | None = None,
        created: datetime | str | None = None,
        number: int = 1,
        anchor_char_pr_id_ref: str | int | None = None,
    ) -> tuple[HwpxOxmlMemo, HwpxOxmlParagraph, str]:
        """Create a memo and ensure it is visible by anchoring a MEMO field."""

        memo = self.add_memo(
            text,
            section=section,
            section_index=section_index,
            memo_shape_id_ref=memo_shape_id_ref,
            memo_id=memo_id,
            char_pr_id_ref=char_pr_id_ref,
            attributes=attributes,
        )

        target_paragraph = paragraph
        if target_paragraph is None:
            memo_section = memo.group.section
            if memo_section is None:
                raise ValueError("memo must belong to a section")
            paragraph_value = "" if paragraph_text is None else paragraph_text
            anchor_char = anchor_char_pr_id_ref or char_pr_id_ref
            target_paragraph = self.add_paragraph(
                paragraph_value,
                section=memo_section,
                char_pr_id_ref=anchor_char,
            )
        elif paragraph_text is not None:
            target_paragraph.text = paragraph_text

        field_value = self.attach_memo_field(
            target_paragraph,
            memo,
            field_id=field_id,
            author=author,
            created=created,
            number=number,
            char_pr_id_ref=anchor_char_pr_id_ref,
        )

        return memo, target_paragraph, field_value

    @property
    def paragraphs(self) -> List[HwpxOxmlParagraph]:
        """Return all paragraphs across every section."""
        return self._root.paragraphs

    @property
    def char_properties(self) -> dict[str, RunStyle]:
        """Return the resolved character style definitions available to the document."""

        return self._root.char_properties

    def char_property(self, char_pr_id_ref: int | str | None) -> RunStyle | None:
        """Return the style referenced by *char_pr_id_ref* if known."""

        return self._root.char_property(char_pr_id_ref)

    def ensure_run_style(
        self,
        *,
        bold: bool = False,
        italic: bool = False,
        underline: bool = False,
        base_char_pr_id: str | int | None = None,
    ) -> str:
        """Return a ``charPr`` identifier matching the requested flags."""

        return self._root.ensure_run_style(
            bold=bold,
            italic=italic,
            underline=underline,
            base_char_pr_id=base_char_pr_id,
        )

    def iter_runs(self) -> Iterator[HwpxOxmlRun]:
        """Yield every run element contained in the document."""

        for paragraph in self.paragraphs:
            for run in paragraph.runs:
                yield run

    def find_runs_by_style(
        self,
        *,
        text_color: str | None = None,
        underline_type: str | None = None,
        underline_color: str | None = None,
        char_pr_id_ref: str | int | None = None,
    ) -> List[HwpxOxmlRun]:
        """Return runs matching the requested style criteria."""

        matches: List[HwpxOxmlRun] = []
        target_char = str(char_pr_id_ref).strip() if char_pr_id_ref is not None else None

        for run in self.iter_runs():
            if target_char is not None:
                run_char = (run.char_pr_id_ref or "").strip()
                if run_char != target_char:
                    continue
            style = run.style
            if text_color is not None:
                if style is None or style.text_color() != text_color:
                    continue
            if underline_type is not None:
                if style is None or style.underline_type() != underline_type:
                    continue
            if underline_color is not None:
                if style is None or style.underline_color() != underline_color:
                    continue
            matches.append(run)
        return matches

    def replace_text_in_runs(
        self,
        search: str,
        replacement: str,
        *,
        text_color: str | None = None,
        underline_type: str | None = None,
        underline_color: str | None = None,
        char_pr_id_ref: str | int | None = None,
        limit: int | None = None,
    ) -> int:
        """Replace occurrences of *search* in runs matching the provided style filters."""

        if not search:
            raise ValueError("search must be a non-empty string")

        replacements = 0
        runs = self.find_runs_by_style(
            text_color=text_color,
            underline_type=underline_type,
            underline_color=underline_color,
            char_pr_id_ref=char_pr_id_ref,
        )

        for run in runs:
            remaining = None
            if limit is not None:
                remaining = limit - replacements
                if remaining <= 0:
                    break
            original_char_pr = run.char_pr_id_ref
            replaced_here = run.replace_text(
                search,
                replacement,
                count=remaining,
            )
            if replaced_here and original_char_pr is not None:
                # Ensure the run retains its original formatting reference even
                # if XML nodes were rewritten during substitution.
                run.char_pr_id_ref = original_char_pr
            replacements += replaced_here
            if limit is not None and replacements >= limit:
                break
        return replacements

    # ------------------------------------------------------------------
    # editing helpers
    def add_paragraph(
        self,
        text: str = "",
        *,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        para_pr_id_ref: str | int | None = None,
        style_id_ref: str | int | None = None,
        char_pr_id_ref: str | int | None = None,
        run_attributes: dict[str, str] | None = None,
        include_run: bool = True,
        **extra_attrs: str,
    ) -> HwpxOxmlParagraph:
        """Append a paragraph to the document and return it.

        Formatting references may be overridden via ``para_pr_id_ref``,
        ``style_id_ref`` and ``char_pr_id_ref``. Any additional keyword
        arguments are added as raw paragraph attributes.
        """
        return self._root.add_paragraph(
            text,
            section=section,
            section_index=section_index,
            para_pr_id_ref=para_pr_id_ref,
            style_id_ref=style_id_ref,
            char_pr_id_ref=char_pr_id_ref,
            run_attributes=run_attributes,
            include_run=include_run,
            **extra_attrs,
        )

    def add_table(
        self,
        rows: int,
        cols: int,
        *,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        width: int | None = None,
        height: int | None = None,
        border_fill_id_ref: str | int = "0",
        para_pr_id_ref: str | int | None = None,
        style_id_ref: str | int | None = None,
        char_pr_id_ref: str | int | None = None,
        run_attributes: dict[str, str] | None = None,
        **extra_attrs: str,
    ) -> HwpxOxmlTable:
        """Create a table in a new paragraph and return it."""

        paragraph = self.add_paragraph(
            "",
            section=section,
            section_index=section_index,
            para_pr_id_ref=para_pr_id_ref,
            style_id_ref=style_id_ref,
            char_pr_id_ref=char_pr_id_ref,
            include_run=False,
            **extra_attrs,
        )
        return paragraph.add_table(
            rows,
            cols,
            width=width,
            height=height,
            border_fill_id_ref=border_fill_id_ref,
            run_attributes=run_attributes,
            char_pr_id_ref=char_pr_id_ref,
        )

    def add_shape(
        self,
        shape_type: str,
        *,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        attributes: dict[str, str] | None = None,
        para_pr_id_ref: str | int | None = None,
        style_id_ref: str | int | None = None,
        char_pr_id_ref: str | int | None = None,
        run_attributes: dict[str, str] | None = None,
        **extra_attrs: str,
    ) -> HwpxOxmlInlineObject:
        """Insert an inline shape into a new paragraph."""

        paragraph = self.add_paragraph(
            "",
            section=section,
            section_index=section_index,
            para_pr_id_ref=para_pr_id_ref,
            style_id_ref=style_id_ref,
            char_pr_id_ref=char_pr_id_ref,
            include_run=False,
            **extra_attrs,
        )
        return paragraph.add_shape(
            shape_type,
            attributes=attributes,
            run_attributes=run_attributes,
            char_pr_id_ref=char_pr_id_ref,
        )

    def add_control(
        self,
        *,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        attributes: dict[str, str] | None = None,
        control_type: str | None = None,
        para_pr_id_ref: str | int | None = None,
        style_id_ref: str | int | None = None,
        char_pr_id_ref: str | int | None = None,
        run_attributes: dict[str, str] | None = None,
        **extra_attrs: str,
    ) -> HwpxOxmlInlineObject:
        """Insert a control inline object into a new paragraph."""

        paragraph = self.add_paragraph(
            "",
            section=section,
            section_index=section_index,
            para_pr_id_ref=para_pr_id_ref,
            style_id_ref=style_id_ref,
            char_pr_id_ref=char_pr_id_ref,
            include_run=False,
            **extra_attrs,
        )
        return paragraph.add_control(
            attributes=attributes,
            control_type=control_type,
            run_attributes=run_attributes,
            char_pr_id_ref=char_pr_id_ref,
        )

    def set_header_text(
        self,
        text: str,
        *,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        page_type: str = "BOTH",
    ) -> HwpxOxmlSectionHeaderFooter:
        """Ensure the requested section contains a header for *page_type* and set its text."""

        target_section = section
        if target_section is None and section_index is not None:
            target_section = self._root.sections[section_index]
        if target_section is None:
            if not self._root.sections:
                raise ValueError("document does not contain any sections")
            target_section = self._root.sections[-1]
        return target_section.properties.set_header_text(text, page_type=page_type)

    def set_footer_text(
        self,
        text: str,
        *,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        page_type: str = "BOTH",
    ) -> HwpxOxmlSectionHeaderFooter:
        """Ensure the requested section contains a footer for *page_type* and set its text."""

        target_section = section
        if target_section is None and section_index is not None:
            target_section = self._root.sections[section_index]
        if target_section is None:
            if not self._root.sections:
                raise ValueError("document does not contain any sections")
            target_section = self._root.sections[-1]
        return target_section.properties.set_footer_text(text, page_type=page_type)

    def remove_header(
        self,
        *,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        page_type: str = "BOTH",
    ) -> None:
        """Remove the header linked to *page_type* from the requested section if present."""

        target_section = section
        if target_section is None and section_index is not None:
            target_section = self._root.sections[section_index]
        if target_section is None:
            if not self._root.sections:
                return
            target_section = self._root.sections[-1]
        target_section.properties.remove_header(page_type=page_type)

    def remove_footer(
        self,
        *,
        section: HwpxOxmlSection | None = None,
        section_index: int | None = None,
        page_type: str = "BOTH",
    ) -> None:
        """Remove the footer linked to *page_type* from the requested section if present."""

        target_section = section
        if target_section is None and section_index is not None:
            target_section = self._root.sections[section_index]
        if target_section is None:
            if not self._root.sections:
                return
            target_section = self._root.sections[-1]
        target_section.properties.remove_footer(page_type=page_type)

    def save(
        self,
        path_or_stream: str | PathLike[str] | BinaryIO | None = None,
    ) -> str | PathLike[str] | BinaryIO | bytes | None:
        """Persist pending changes to *path_or_stream* or the original source."""
        updates = self._root.serialize()
        result = self._package.save(path_or_stream, updates)
        self._root.reset_dirty()
        return result
