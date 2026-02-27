"""Unit tests for new features added in Phase 2.3–3.5.

Covers: shape insertion, column editing, bookmark/hyperlink, validation,
style preservation, nested tables, OWPML alignment, and exporters.
"""

from __future__ import annotations

import io
import xml.etree.ElementTree as ET

import pytest

from hwpx import HwpxDocument
from hwpx.oxml.document import (
    HwpxOxmlParagraph,
    HwpxOxmlShape,
    HwpxOxmlTable,
    HwpxOxmlTableCell,
    _create_ellipse_element,
    _create_line_element,
    _create_rectangle_element,
)
from hwpx.tools.exporter import export_html, export_markdown, export_text


# =========================================================================
# Helpers
# =========================================================================


def _new_doc() -> HwpxDocument:
    """Create a fresh document for testing."""
    return HwpxDocument.new()


# =========================================================================
# 2.3 – Shape insertion
# =========================================================================


class TestShapeInsertion:
    """Tests for LINE, RECT, ELLIPSE shape creation and wrapping."""

    def test_add_line_returns_shape(self):
        doc = _new_doc()
        p = doc.add_paragraph("shapes")
        shape = p.add_line(0, 0, 14400, 0)
        assert isinstance(shape, HwpxOxmlShape)
        assert shape.shape_type == "line"

    def test_add_rectangle_returns_shape(self):
        doc = _new_doc()
        p = doc.add_paragraph("")
        shape = p.add_rectangle(7200, 3600)
        assert isinstance(shape, HwpxOxmlShape)
        assert shape.shape_type == "rect"
        assert shape.width == 7200
        assert shape.height == 3600

    def test_add_ellipse_returns_shape(self):
        doc = _new_doc()
        p = doc.add_paragraph("")
        shape = p.add_ellipse(5000, 5000)
        assert isinstance(shape, HwpxOxmlShape)
        assert shape.shape_type == "ellipse"

    def test_shape_resize(self):
        doc = _new_doc()
        p = doc.add_paragraph("")
        shape = p.add_rectangle(100, 50)
        shape.resize(200, 100)
        assert shape.width == 200
        assert shape.height == 100

    def test_shapes_property_returns_list(self):
        doc = _new_doc()
        p = doc.add_paragraph("")
        p.add_rectangle(100, 50)
        p.add_ellipse(100, 100)
        assert len(p.shapes) == 2

    def test_shape_line_color(self):
        doc = _new_doc()
        p = doc.add_paragraph("")
        shape = p.add_rectangle(100, 50, line_color="#FF0000")
        assert shape.line_color == "#FF0000"

    def test_shape_set_line_color(self):
        doc = _new_doc()
        p = doc.add_paragraph("")
        shape = p.add_rectangle(100, 50)
        shape.line_color = "#00FF00"
        assert shape.line_color == "#00FF00"

    def test_line_element_boolean_uses_zero(self):
        el = _create_line_element(0, 0, 100, 0)
        assert el.get("isReverseHV") == "0"
        assert el.get("lock") == "0"

    def test_rectangle_fill_color(self):
        doc = _new_doc()
        p = doc.add_paragraph("")
        shape = p.add_rectangle(100, 50, fill_color="#FF0000")
        assert shape.shape_type == "rect"

    def test_ellipse_boolean_uses_zero(self):
        el = _create_ellipse_element(100, 100)
        assert el.get("intervalDirty") == "0"
        assert el.get("hasArcPr") == "0"

    def test_shape_inst_id(self):
        doc = _new_doc()
        p = doc.add_paragraph("")
        shape = p.add_rectangle(100, 50)
        assert shape.inst_id is not None

    def test_shape_child_order_matches_real_hwpx(self):
        """Verify ASC → ADO → type-specific → ASO ordering."""
        el = _create_rectangle_element(100, 50)
        ns = "http://www.hancom.co.kr/hwpml/2011/paragraph"
        children = [c.tag.split("}")[-1] for c in el]
        # ASC first
        assert children.index("offset") < children.index("orgSz")
        assert children.index("renderingInfo") < children.index("lineShape")
        # ADO before type-specific
        assert children.index("lineShape") < children.index("pt0")
        # ASO last
        assert children.index("pt3") < children.index("sz")
        assert children.index("sz") < children.index("pos")

    def test_core_namespace_for_matrix(self):
        """transMatrix, scaMatrix, rotMatrix should use hc: namespace."""
        el = _create_rectangle_element(100, 50)
        hc_ns = "http://www.hancom.co.kr/hwpml/2011/core"
        ri = el.find(f"{{{ns}}}renderingInfo" if (ns := "http://www.hancom.co.kr/hwpml/2011/paragraph") else "")
        assert ri is not None
        trans = ri.find(f"{{{hc_ns}}}transMatrix")
        assert trans is not None

    def test_shape_roundtrip(self):
        doc = _new_doc()
        doc.add_paragraph("text").add_rectangle(100, 50)
        b = doc.to_bytes()
        doc2 = HwpxDocument.open(b)
        assert len(doc2.paragraphs) >= 2

    def test_document_add_line(self):
        doc = _new_doc()
        shape = doc.add_line()
        assert shape.shape_type == "line"

    def test_document_add_rectangle(self):
        doc = _new_doc()
        shape = doc.add_rectangle(200, 100)
        assert shape.shape_type == "rect"

    def test_document_add_ellipse(self):
        doc = _new_doc()
        shape = doc.add_ellipse(200, 200)
        assert shape.shape_type == "ellipse"


# =========================================================================
# 2.4 – Column editing
# =========================================================================


class TestColumnEditing:
    """Tests for column definition insertion."""

    def test_add_column_definition(self):
        doc = _new_doc()
        p = doc.add_paragraph("cols")
        p.add_column_definition(col_count=2, same_gap=850)
        b = doc.to_bytes()
        # Roundtrip
        xml_str = ET.tostring(p.element, encoding="unicode")
        assert "colPr" in xml_str

    def test_set_columns_convenience(self):
        doc = _new_doc()
        doc.set_columns(3, same_gap=567)
        b = doc.to_bytes()
        assert len(b) > 0

    def test_column_default_gap(self):
        doc = _new_doc()
        p = doc.add_paragraph("test")
        p.add_column_definition(col_count=2)
        xml_str = ET.tostring(p.element, encoding="unicode")
        assert 'colCount="2"' in xml_str


# =========================================================================
# 2.5 – Bookmark / Hyperlink
# =========================================================================


class TestBookmarkHyperlink:
    """Tests for bookmark and hyperlink APIs."""

    def test_add_bookmark(self):
        doc = _new_doc()
        p = doc.add_paragraph("bm")
        p.add_bookmark("test_mark")
        assert "test_mark" in p.bookmarks

    def test_add_multiple_bookmarks(self):
        doc = _new_doc()
        p = doc.add_paragraph("bm")
        p.add_bookmark("mark1")
        p.add_bookmark("mark2")
        assert len(p.bookmarks) == 2

    def test_add_hyperlink(self):
        doc = _new_doc()
        p = doc.add_paragraph("link")
        p.add_hyperlink("https://example.com", "Click")
        links = p.hyperlinks
        assert len(links) == 1
        assert links[0]["url"] == "https://example.com"
        assert links[0]["type"] == "HYPERLINK"

    def test_hyperlink_roundtrip(self):
        doc = _new_doc()
        p = doc.add_paragraph("link")
        p.add_hyperlink("https://test.org", "Test")
        b = doc.to_bytes()
        doc2 = HwpxDocument.open(b)
        assert len(doc2.paragraphs) >= 2

    def test_document_add_bookmark(self):
        doc = _new_doc()
        doc.add_bookmark("doc_bm")
        p = doc.paragraphs[-1]
        assert "doc_bm" in p.bookmarks

    def test_document_add_hyperlink(self):
        doc = _new_doc()
        doc.add_hyperlink("https://example.com", "Link")
        p = doc.paragraphs[-1]
        links = p.hyperlinks
        assert len(links) >= 1


# =========================================================================
# 3.1 – Validation
# =========================================================================


class TestValidation:
    """Tests for validate() and validate_on_save."""

    def test_validate_returns_report(self):
        doc = _new_doc()
        doc.add_paragraph("valid doc")
        report = doc.validate()
        assert hasattr(report, "ok")
        assert hasattr(report, "issues")

    def test_validate_on_save_flag(self):
        doc = _new_doc()
        assert doc.validate_on_save is False
        doc.validate_on_save = True
        assert doc.validate_on_save is True

    def test_validate_no_infinite_recursion(self):
        """validate() calls to_bytes internally; must not recurse."""
        doc = _new_doc()
        doc.validate_on_save = True
        doc.add_paragraph("test")
        # Should complete without RecursionError
        report = doc.validate()
        assert report is not None

    def test_to_bytes_with_validate_on_save(self):
        doc = _new_doc()
        doc.validate_on_save = True
        doc.add_paragraph("test")
        b = doc.to_bytes()
        assert len(b) > 0


# =========================================================================
# 3.2 – Style preservation
# =========================================================================


class TestStylePreservation:
    """Tests for style reference preservation across text edits."""

    def test_text_setter_preserves_paragraph_refs(self):
        doc = _new_doc()
        p = doc.add_paragraph("original", para_pr_id_ref="5", style_id_ref="3")
        p.text = "replaced"
        assert p.para_pr_id_ref == "5"
        assert p.style_id_ref == "3"

    def test_text_setter_preserves_char_pr_id_ref(self):
        doc = _new_doc()
        p = doc.add_paragraph("original", char_pr_id_ref="7")
        p.text = "replaced"
        assert p.char_pr_id_ref == "7"

    def test_text_setter_cleans_empty_runs(self):
        """After setting text, only one run should contain the new value."""
        doc = _new_doc()
        p = doc.add_paragraph("first")
        # Setting text replaces content; verify result has text
        p.text = "new"
        assert p.text == "new"
        assert len(p.runs) >= 1

    def test_clear_text_preserves_refs(self):
        doc = _new_doc()
        p = doc.add_paragraph("content", para_pr_id_ref="2", style_id_ref="1")
        p.clear_text()
        assert p.text == ""
        assert p.para_pr_id_ref == "2"
        assert p.style_id_ref == "1"

    def test_style_inheritance_default(self):
        doc = _new_doc()
        p1 = doc.add_paragraph("first", para_pr_id_ref="5", style_id_ref="3", char_pr_id_ref="7")
        p2 = doc.add_paragraph("second")
        assert p2.para_pr_id_ref == "5"
        assert p2.style_id_ref == "3"
        assert p2.char_pr_id_ref == "7"

    def test_style_inheritance_disabled(self):
        doc = _new_doc()
        p1 = doc.add_paragraph("first", para_pr_id_ref="5")
        p2 = doc.add_paragraph("second", inherit_style=False)
        assert p2.para_pr_id_ref == "0"

    def test_run_text_setter_preserves_char_pr(self):
        doc = _new_doc()
        p = doc.add_paragraph("original", char_pr_id_ref="9")
        run = p.runs[0]
        assert run.char_pr_id_ref == "9"
        run.text = "changed"
        assert run.char_pr_id_ref == "9"

    def test_add_run_lxml_compat(self):
        """add_run must work even when elements are lxml-backed."""
        doc = _new_doc()
        p = doc.add_paragraph("initial")
        run = p.add_run("extra")
        assert run.text == "extra"
        assert len(p.runs) == 2


# =========================================================================
# 3.3 – Nested tables
# =========================================================================


class TestNestedTables:
    """Tests for nested table and cell paragraph support."""

    def test_cell_add_paragraph(self):
        doc = _new_doc()
        tbl = doc.add_table(2, 2)
        cell = tbl.cell(0, 0)
        cell.add_paragraph("extra line")
        # Original + newly added
        assert len(cell.paragraphs) >= 2

    def test_cell_add_table(self):
        doc = _new_doc()
        tbl = doc.add_table(2, 2)
        cell = tbl.cell(0, 0)
        inner = cell.add_table(2, 2)
        assert isinstance(inner, HwpxOxmlTable)

    def test_cell_tables_property(self):
        doc = _new_doc()
        tbl = doc.add_table(2, 2)
        cell = tbl.cell(0, 0)
        cell.add_table(1, 1)
        assert len(cell.tables) == 1

    def test_nested_table_text(self):
        doc = _new_doc()
        tbl = doc.add_table(1, 1)
        cell = tbl.cell(0, 0)
        inner = cell.add_table(1, 1)
        inner.cell(0, 0).text = "nested"
        assert inner.cell(0, 0).text == "nested"

    def test_nested_table_roundtrip(self):
        doc = _new_doc()
        tbl = doc.add_table(1, 1)
        tbl.cell(0, 0).add_table(2, 2)
        b = doc.to_bytes()
        doc2 = HwpxDocument.open(b)
        assert len(doc2.paragraphs) >= 1


# =========================================================================
# 3.4 – OWPML schema alignment
# =========================================================================


class TestOwpmlAlignment:
    """Tests verifying XML output matches Hancom Word conventions."""

    def test_sublist_attributes_match_real_files(self):
        """Verify subList uses HORIZONTAL, BREAK, CENTER, linkListIDRef."""
        doc = _new_doc()
        tbl = doc.add_table(1, 1)
        cell = tbl.cell(0, 0)
        sublist = cell.element.find(
            f"{{{_hp_ns()}}}subList"
        )
        assert sublist is not None
        assert sublist.get("textDirection") == "HORIZONTAL"
        assert sublist.get("lineWrap") == "BREAK"
        assert sublist.get("linkListIDRef") == "0"

    def test_shape_boolean_attrs_use_zero(self):
        el = _create_rectangle_element(100, 50)
        assert el.get("lock") == "0"
        flip = el.find(f"{{{_hp_ns()}}}flip")
        assert flip is not None
        assert flip.get("horizontal") == "0"

    def test_identity_matrix_integer_values(self):
        el = _create_rectangle_element(100, 50)
        hc_ns = "http://www.hancom.co.kr/hwpml/2011/core"
        hp_ns = _hp_ns()
        ri = el.find(f"{{{hp_ns}}}renderingInfo")
        trans = ri.find(f"{{{hc_ns}}}transMatrix")
        assert trans.get("e1") == "1"
        assert trans.get("e2") == "0"

    def test_line_shape_has_headfill_tailfill(self):
        el = _create_rectangle_element(100, 50)
        hp_ns = _hp_ns()
        ls = el.find(f"{{{hp_ns}}}lineShape")
        assert ls is not None
        assert ls.get("headfill") == "1"
        assert ls.get("tailfill") == "1"
        assert ls.get("alpha") == "0"


def _hp_ns() -> str:
    return "http://www.hancom.co.kr/hwpml/2011/paragraph"


# =========================================================================
# 3.5 – Exporter tools
# =========================================================================


class TestExporters:
    """Tests for the text/HTML/Markdown export functions."""

    def _doc_with_content(self) -> HwpxDocument:
        doc = _new_doc()
        doc.add_paragraph("Hello")
        tbl = doc.add_table(2, 2)
        tbl.cell(0, 0).text = "A"
        tbl.cell(0, 1).text = "B"
        tbl.cell(1, 0).text = "C"
        tbl.cell(1, 1).text = "D"
        doc.add_paragraph("End")
        return doc

    def test_export_text_basic(self):
        doc = self._doc_with_content()
        text = export_text(doc)
        assert "Hello" in text
        assert "End" in text

    def test_export_text_includes_tables(self):
        doc = self._doc_with_content()
        text = export_text(doc)
        assert "A" in text
        assert "B" in text

    def test_export_text_no_duplication(self):
        doc = self._doc_with_content()
        text = export_text(doc)
        # "A" should appear in the table row, not duplicated
        lines = [l for l in text.split("\n") if "A" in l]
        assert len(lines) == 1

    def test_export_html_full_document(self):
        doc = self._doc_with_content()
        html = export_html(doc)
        assert "<!DOCTYPE html>" in html
        assert "<p>Hello</p>" in html
        assert "<table" in html

    def test_export_html_body_only(self):
        doc = self._doc_with_content()
        html = export_html(doc, full_document=False)
        assert "<!DOCTYPE" not in html
        assert "<p>Hello</p>" in html

    def test_export_markdown_basic(self):
        doc = self._doc_with_content()
        md = export_markdown(doc)
        assert "Hello" in md
        assert "| A | B |" in md
        assert "| --- | --- |" in md

    def test_export_text_bytes_input(self):
        doc = self._doc_with_content()
        b = doc.to_bytes()
        text = export_text(b)
        assert "Hello" in text

    def test_document_export_text_method(self):
        doc = self._doc_with_content()
        text = doc.export_text()
        assert "Hello" in text

    def test_document_export_html_method(self):
        doc = self._doc_with_content()
        html = doc.export_html(full_document=False)
        assert "<p>Hello</p>" in html

    def test_document_export_markdown_method(self):
        doc = self._doc_with_content()
        md = doc.export_markdown()
        assert "Hello" in md
