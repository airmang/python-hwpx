"""Tests for paragraph remove, section add/remove, and namespace module."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from hwpx import HwpxDocument, validate_editor_open_safety
from hwpx.opc.package import HwpxPackageError
from hwpx.oxml.namespaces import HP, tag_local_name


def _new() -> HwpxDocument:
    return HwpxDocument.new()


# =========================================================================
# Paragraph removal
# =========================================================================


class TestParagraphRemove:
    """Tests for HwpxOxmlParagraph.remove() and related helpers."""

    def test_remove_paragraph_by_instance(self):
        doc = _new()
        doc.add_paragraph("first")
        doc.add_paragraph("second")
        doc.add_paragraph("third")
        section = doc.sections[0]
        paras = section.paragraphs
        # There is a default empty paragraph + 3 added = 4 total (skeleton may vary)
        initial_count = len(paras)
        assert initial_count >= 3

        # Remove the paragraph containing "second"
        target = [p for p in section.paragraphs if p.text == "second"]
        assert len(target) == 1
        target[0].remove()

        remaining_texts = [p.text for p in section.paragraphs]
        assert "second" not in remaining_texts
        assert len(section.paragraphs) == initial_count - 1

    def test_remove_paragraph_by_index(self):
        doc = _new()
        doc.add_paragraph("alpha")
        doc.add_paragraph("beta")
        section = doc.sections[0]
        count_before = len(section.paragraphs)
        assert count_before >= 2

        # Remove last paragraph by index
        section.remove_paragraph(count_before - 1)
        assert len(section.paragraphs) == count_before - 1

    def test_remove_last_paragraph_raises(self):
        doc = _new()
        section = doc.sections[0]
        # Keep removing until only one remains
        while len(section.paragraphs) > 1:
            section.paragraphs[-1].remove()

        assert len(section.paragraphs) == 1
        with pytest.raises(ValueError, match="최소 하나"):
            section.paragraphs[0].remove()

    def test_remove_paragraph_bad_index_raises(self):
        doc = _new()
        section = doc.sections[0]
        with pytest.raises(IndexError):
            section.remove_paragraph(999)

    def test_document_remove_paragraph(self):
        """Test the high-level HwpxDocument.remove_paragraph() method."""
        doc = _new()
        doc.add_paragraph("keep")
        doc.add_paragraph("remove_me")
        section = doc.sections[0]
        paras = section.paragraphs
        target = [p for p in paras if p.text == "remove_me"]
        assert target
        doc.remove_paragraph(target[0])

        remaining = [p.text for p in section.paragraphs]
        assert "remove_me" not in remaining

    def test_document_remove_paragraph_by_index(self):
        doc = _new()
        doc.add_paragraph("A")
        doc.add_paragraph("B")
        section = doc.sections[0]
        count = len(section.paragraphs)
        # Remove last paragraph by index through document-level method
        doc.remove_paragraph(count - 1, section=section)
        assert len(section.paragraphs) == count - 1

    def test_remove_paragraph_roundtrip(self, tmp_path):
        """Paragraph removal persists through save/open cycle."""
        doc = _new()
        doc.add_paragraph("stays")
        doc.add_paragraph("goes_away")
        section = doc.sections[0]
        target = [p for p in section.paragraphs if p.text == "goes_away"]
        assert target
        target[0].remove()

        path = tmp_path / "remove_para.hwpx"
        doc.save_to_path(path)

        reopened = HwpxDocument.open(str(path))
        texts = [p.text for p in reopened.paragraphs]
        assert "goes_away" not in texts
        assert "stays" in texts


# =========================================================================
# Section add / remove
# =========================================================================


class TestSectionManagement:
    """Tests for add_section() and remove_section()."""

    @staticmethod
    def _layout(section):
        first_run = section.element.find(f"{HP}p/{HP}run")
        assert first_run is not None
        section_properties = first_run.find(f"{HP}secPr")
        assert section_properties is not None
        page_properties = section_properties.find(f"{HP}pagePr")
        assert page_properties is not None
        margin = page_properties.find(f"{HP}margin")
        assert margin is not None
        column_properties = first_run.find(f"{HP}ctrl/{HP}colPr")
        assert column_properties is not None
        return first_run, section_properties, page_properties, margin, column_properties

    @staticmethod
    def _section_mutation_state(doc: HwpxDocument) -> tuple:
        root = doc._root
        return (
            tuple(section.part_name for section in root.sections),
            tuple(ET.tostring(section.element) for section in root.sections),
            ET.tostring(root._manifest),
            tuple(ET.tostring(header.element) for header in root.headers),
            root._manifest_dirty,
        )

    def test_add_section_appends(self):
        doc = _new()
        assert len(doc.sections) >= 1
        initial_count = len(doc.sections)
        source_xml = ET.tostring(doc.sections[-1].element)

        new_section = doc.add_section()
        assert len(doc.sections) == initial_count + 1
        assert new_section is doc.sections[-1]
        assert doc.headers[0].element.get("secCnt") == str(initial_count + 1)
        # New section has at least one paragraph
        assert len(new_section.paragraphs) >= 1
        assert ET.tostring(doc.sections[-2].element) == source_xml

        first_run, section_properties, page_properties, margin, column_properties = (
            self._layout(new_section)
        )
        assert int(page_properties.get("width", "0")) > 0
        assert int(page_properties.get("height", "0")) > 0
        assert margin.attrib == doc.sections[-2].properties._margin_element().attrib
        assert column_properties.get("colCount") == "1"
        assert [tag_local_name(child.tag) for child in first_run[1]] == ["colPr"]
        assert section_properties.get("masterPageCnt") == "0"
        assert section_properties.find(f"{HP}header") is None
        assert section_properties.find(f"{HP}footer") is None
        assert section_properties.find(f"{HP}headerApply") is None
        assert section_properties.find(f"{HP}footerApply") is None
        assert section_properties.find(f"{HP}masterPage") is None
        assert section_properties.find(f"{HP}presentation") is None
        assert [tag_local_name(child.tag) for child in first_run] == [
            "secPr",
            "ctrl",
            "t",
        ]

    def test_add_section_after(self, tmp_path):
        doc = _new()
        second = doc.add_section()
        doc.sections[0].paragraphs[0].text = "first"
        second.paragraphs[0].text = "second"
        doc.sections[0].properties.set_page_size(width=60000, height=90000)
        doc.sections[0].properties.set_page_margins(left=7000, right=7100)
        second.properties.set_page_size(width=70000, height=100000)
        assert len(doc.sections) >= 2

        mid = doc.add_section(after=0)
        assert len(doc.sections) >= 3
        assert doc.sections[1] is mid
        assert doc.headers[0].element.get("secCnt") == "3"
        _, _, page_properties, margin, _ = self._layout(mid)
        assert page_properties.get("width") == "60000"
        assert page_properties.get("height") == "90000"
        assert margin.get("left") == "7000"
        assert margin.get("right") == "7100"
        mid.paragraphs[0].text = "middle"

        path = tmp_path / "inserted-section.hwpx"
        doc.save_to_path(path)
        reopened = HwpxDocument.open(path)
        assert [section.paragraphs[0].text for section in reopened.sections] == [
            "first",
            "middle",
            "second",
        ]

    def test_add_section_after_negative_index_uses_same_anchor_for_layout_and_order(
        self,
    ):
        doc = _new()
        second = doc.add_section()
        doc.sections[0].properties.set_page_size(width=60000, height=90000)
        second.properties.set_page_size(width=70000, height=100000)

        appended = doc.add_section(after=-1)

        assert doc.sections[-1] is appended
        _, _, page_properties, _, _ = self._layout(appended)
        assert page_properties.get("width") == "70000"
        assert page_properties.get("height") == "100000"

    @pytest.mark.parametrize("after", [2, -3])
    def test_add_section_rejects_out_of_range_anchor_atomically(self, after):
        doc = _new()
        doc.add_section()
        before = self._section_mutation_state(doc)

        with pytest.raises(IndexError, match="section index"):
            doc.add_section(after=after)

        assert self._section_mutation_state(doc) == before

    def test_add_section_does_not_copy_header_footer_stories(self):
        doc = _new()
        first = doc.sections[0]
        first_header = doc.set_header_text("first header", section=first)
        first_footer = doc.set_footer_text("first footer", section=first)

        second = doc.add_section()
        assert second.properties.get_header("BOTH") is None
        assert second.properties.get_footer("BOTH") is None
        assert not any(
            tag_local_name(element.tag) in {"header", "footer"}
            for element in second.element.iter()
        )

        second_header = doc.set_header_text("second header", section=second)
        second_footer = doc.set_footer_text("second footer", section=second)
        assert first_header.element.get("id") != second_header.element.get("id")
        assert first_footer.element.get("id") != second_footer.element.get("id")
        assert first.properties.get_header("BOTH").text == "first header"
        assert first.properties.get_footer("BOTH").text == "first footer"
        assert second.properties.get_header("BOTH").text == "second header"
        assert second.properties.get_footer("BOTH").text == "second footer"

    def test_add_section_fails_closed_without_renderable_layout(self):
        doc = _new()
        first_run, section_properties, _, _, _ = self._layout(doc.sections[0])
        section_properties.remove(section_properties.find(f"{HP}pagePr"))
        column_control = first_run.find(f"{HP}ctrl")
        assert column_control is not None
        first_run.remove(column_control)
        before = self._section_mutation_state(doc)

        with pytest.raises(ValueError, match="no existing section has positive"):
            doc.add_section()
        assert self._section_mutation_state(doc) == before

    @pytest.mark.parametrize("container_name", ["manifest", "spine"])
    @pytest.mark.parametrize("operation", ["add", "remove"])
    def test_section_mutation_fails_closed_without_manifest_container(
        self,
        container_name,
        operation,
    ):
        doc = _new()
        doc.add_section()
        manifest_root = doc._root._manifest
        namespace = doc._root._OPF_NS
        container = manifest_root.find(f"{{{namespace}}}{container_name}")
        assert container is not None
        manifest_root.remove(container)
        before = self._section_mutation_state(doc)

        with pytest.raises(ValueError, match=f"opf:{container_name}"):
            if operation == "add":
                doc.add_section()
            else:
                doc.remove_section(1)

        assert self._section_mutation_state(doc) == before

    def test_remove_section_by_index(self):
        doc = _new()
        doc.add_section()
        count = len(doc.sections)
        assert count >= 2

        doc.remove_section(count - 1)
        assert len(doc.sections) == count - 1
        assert doc.headers[0].element.get("secCnt") == str(count - 1)

    def test_remove_section_by_instance(self):
        doc = _new()
        new_sec = doc.add_section()
        count = len(doc.sections)

        doc.remove_section(new_sec)
        assert len(doc.sections) == count - 1
        assert doc.headers[0].element.get("secCnt") == str(count - 1)

    def test_remove_section_resolves_relative_manifest_href(self):
        doc = _new()
        removed = doc.add_section()
        manifest, spine = doc._root._manifest_section_containers()
        namespace = doc._root._OPF_NS
        target = next(
            item
            for item in manifest.findall(f"{{{namespace}}}item")
            if item.get("id") == "section1"
        )
        target.set("href", "section1.xml")

        doc.remove_section(removed)

        assert all(
            item.get("id") != "section1"
            for item in manifest.findall(f"{{{namespace}}}item")
        )
        assert all(
            itemref.get("idref") != "section1"
            for itemref in spine.findall(f"{{{namespace}}}itemref")
        )
        assert doc.headers[0].element.get("secCnt") == "1"

    def test_remove_last_section_raises(self):
        doc = _new()
        # Remove extra sections to get to 1
        while len(doc.sections) > 1:
            doc.remove_section(len(doc.sections) - 1)

        assert len(doc.sections) == 1
        with pytest.raises(ValueError, match="최소 하나"):
            doc.remove_section(0)

    def test_remove_section_bad_index_raises(self):
        doc = _new()
        doc.add_section()  # ensure 2+ sections
        with pytest.raises(IndexError):
            doc.remove_section(999)

    def test_remove_section_not_in_document_raises(self):
        doc1 = _new()
        doc2 = _new()
        foreign_section = doc2.sections[0]
        doc1.add_section()  # ensure doc1 has 2+ sections
        with pytest.raises(ValueError, match="속하지 않"):
            doc1.remove_section(foreign_section)

    def test_add_section_with_content_roundtrip(self, tmp_path):
        """Added sections with content survive save/open."""
        doc = _new()
        new_sec = doc.add_section()
        new_sec.paragraphs[0].text = "in new section"

        path = tmp_path / "multi_sec.hwpx"
        doc.save_to_path(path)

        reopened = HwpxDocument.open(str(path))
        all_texts = [p.text for p in reopened.paragraphs]
        assert "in new section" in all_texts
        first_run, _, page_properties, _, _ = self._layout(reopened.sections[1])
        assert int(page_properties.get("width", "0")) > 0
        assert int(page_properties.get("height", "0")) > 0
        assert [tag_local_name(child.tag) for child in first_run][:2] == [
            "secPr",
            "ctrl",
        ]

    def test_open_safety_rejects_header_section_count_mismatch(self):
        doc = _new()
        doc.add_section()
        assert validate_editor_open_safety(doc.to_bytes()).ok

        doc.headers[0].element.set("secCnt", "1")
        doc.headers[0].mark_dirty()
        with pytest.raises(
            HwpxPackageError,
            match="secCnt does not match resolved section count",
        ):
            doc.to_bytes()


# =========================================================================
# Namespace module
# =========================================================================


class TestNamespaceModule:
    """Verify that the shared namespace module exists and exposes constants."""

    def test_namespace_constants_importable(self):
        from hwpx.oxml.namespaces import HP_NS, HP, HH_NS, HH, HC_NS, HC

        assert "paragraph" in HP_NS
        assert HP.startswith("{")
        assert "head" in HH_NS
        assert HH.startswith("{")
        assert "core" in HC_NS
        assert HC.startswith("{")
