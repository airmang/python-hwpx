"""Tests for paragraph remove, section add/remove, and namespace module."""

from __future__ import annotations

import io
import pytest

from hwpx import HwpxDocument
from hwpx.oxml.document import HwpxOxmlParagraph, HwpxOxmlSection


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

    def test_add_section_appends(self):
        doc = _new()
        assert len(doc.sections) >= 1
        initial_count = len(doc.sections)

        new_section = doc.add_section()
        assert len(doc.sections) == initial_count + 1
        assert new_section is doc.sections[-1]
        # New section has at least one paragraph
        assert len(new_section.paragraphs) >= 1

    def test_add_section_after(self):
        doc = _new()
        doc.add_section()
        assert len(doc.sections) >= 2

        mid = doc.add_section(after=0)
        assert len(doc.sections) >= 3
        assert doc.sections[1] is mid

    def test_remove_section_by_index(self):
        doc = _new()
        doc.add_section()
        count = len(doc.sections)
        assert count >= 2

        doc.remove_section(count - 1)
        assert len(doc.sections) == count - 1

    def test_remove_section_by_instance(self):
        doc = _new()
        new_sec = doc.add_section()
        count = len(doc.sections)

        doc.remove_section(new_sec)
        assert len(doc.sections) == count - 1

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
        new_sec.add_paragraph("in new section")

        path = tmp_path / "multi_sec.hwpx"
        doc.save_to_path(path)

        reopened = HwpxDocument.open(str(path))
        all_texts = [p.text for p in reopened.paragraphs]
        assert "in new section" in all_texts


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
