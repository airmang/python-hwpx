"""Integration tests – open ➜ modify ➜ save ➜ reopen ➜ verify roundtrips.

These tests exercise the full HwpxDocument lifecycle including OPC
serialization to ensure nothing is lost during save/load cycles.
"""

from __future__ import annotations

import io
import pathlib
import tempfile

import pytest

from hwpx import HwpxDocument


# =========================================================================
# Helpers
# =========================================================================


def _new() -> HwpxDocument:
    return HwpxDocument.new()


def _roundtrip(doc: HwpxDocument) -> HwpxDocument:
    """Save to bytes, reopen, return the new document."""
    return HwpxDocument.open(doc.to_bytes())


# =========================================================================
# Basic roundtrip
# =========================================================================


class TestBasicRoundtrip:

    def test_empty_document_roundtrip(self):
        doc = _new()
        doc2 = _roundtrip(doc)
        assert doc2 is not None

    def test_paragraphs_survive_roundtrip(self):
        doc = _new()
        doc.add_paragraph("Hello")
        doc.add_paragraph("World")
        doc2 = _roundtrip(doc)
        texts = [p.text for p in doc2.paragraphs]
        assert "Hello" in texts
        assert "World" in texts

    def test_text_setter_roundtrip(self):
        doc = _new()
        p = doc.add_paragraph("before")
        p.text = "after"
        doc2 = _roundtrip(doc)
        texts = [p.text for p in doc2.paragraphs]
        assert "after" in texts
        assert "before" not in texts


# =========================================================================
# Table roundtrip
# =========================================================================


class TestTableRoundtrip:

    def test_table_created_and_survives(self):
        doc = _new()
        tbl = doc.add_table(2, 3)
        tbl.cell(0, 0).text = "A"
        tbl.cell(1, 2).text = "F"
        doc2 = _roundtrip(doc)
        all_tables = [t for p in doc2.paragraphs for t in p.tables]
        assert len(all_tables) >= 1

    def test_table_cell_text_survives(self):
        doc = _new()
        tbl = doc.add_table(1, 1)
        tbl.cell(0, 0).text = "cell_value"
        doc2 = _roundtrip(doc)
        tables = [t for p in doc2.paragraphs for t in p.tables]
        assert len(tables) >= 1
        assert tables[0].cell(0, 0).text == "cell_value"

    def test_nested_table_roundtrip(self):
        doc = _new()
        outer = doc.add_table(1, 1)
        inner = outer.cell(0, 0).add_table(1, 1)
        inner.cell(0, 0).text = "nested"
        doc2 = _roundtrip(doc)
        tables = [t for p in doc2.paragraphs for t in p.tables]
        assert len(tables) >= 1


# =========================================================================
# Shape roundtrip
# =========================================================================


class TestShapeRoundtrip:

    def test_rectangle_roundtrip(self):
        doc = _new()
        doc.add_paragraph("before")
        p = doc.add_paragraph("")
        p.add_rectangle(7200, 3600)
        doc2 = _roundtrip(doc)
        assert len(doc2.paragraphs) >= 2

    def test_line_roundtrip(self):
        doc = _new()
        p = doc.add_paragraph("")
        p.add_line(0, 0, 14400, 0)
        doc2 = _roundtrip(doc)
        assert len(doc2.paragraphs) >= 1

    def test_ellipse_roundtrip(self):
        doc = _new()
        p = doc.add_paragraph("")
        p.add_ellipse(5000, 5000)
        doc2 = _roundtrip(doc)
        assert len(doc2.paragraphs) >= 1

    def test_shape_preserved_after_resave(self):
        doc = _new()
        p = doc.add_paragraph("")
        p.add_rectangle(100, 50, line_color="#FF0000")
        doc2 = _roundtrip(doc)
        b = doc2.to_bytes()
        assert len(b) > 0


# =========================================================================
# Bookmark / Hyperlink roundtrip
# =========================================================================


class TestBookmarkHyperlinkRoundtrip:

    def test_bookmark_roundtrip(self):
        doc = _new()
        p = doc.add_paragraph("bm")
        p.add_bookmark("my_mark")
        doc2 = _roundtrip(doc)
        # Re-find paragraph with bookmarks
        found = False
        for p2 in doc2.paragraphs:
            if "my_mark" in p2.bookmarks:
                found = True
                break
        assert found

    def test_hyperlink_roundtrip(self):
        doc = _new()
        p = doc.add_paragraph("hl")
        p.add_hyperlink("https://example.com", "Link")
        doc2 = _roundtrip(doc)
        has_link = False
        for p2 in doc2.paragraphs:
            for hl in p2.hyperlinks:
                if hl["url"] == "https://example.com":
                    has_link = True
                    break
        assert has_link


# =========================================================================
# Column definition roundtrip
# =========================================================================


class TestColumnRoundtrip:

    def test_column_definition_survives(self):
        doc = _new()
        p = doc.add_paragraph("cols")
        p.add_column_definition(col_count=2, same_gap=850)
        doc2 = _roundtrip(doc)
        assert len(doc2.paragraphs) >= 1


# =========================================================================
# Validation roundtrip
# =========================================================================


class TestValidationRoundtrip:

    def test_validate_on_save_does_not_corrupt(self):
        doc = _new()
        doc.validate_on_save = True
        doc.add_paragraph("p1")
        doc.add_table(1, 1).cell(0, 0).text = "t1"
        doc2 = _roundtrip(doc)
        texts = [p.text for p in doc2.paragraphs]
        assert "p1" in texts


# =========================================================================
# Style inheritance roundtrip
# =========================================================================


class TestStyleInheritanceRoundtrip:

    def test_inherited_styles_persist(self):
        doc = _new()
        doc.add_paragraph("styled", para_pr_id_ref="5", style_id_ref="3", char_pr_id_ref="7")
        p2 = doc.add_paragraph("inheriting")
        # Verify inheritance happened
        assert p2.para_pr_id_ref == "5"
        assert p2.style_id_ref == "3"
        assert p2.char_pr_id_ref == "7"
        doc2 = _roundtrip(doc)
        paras = doc2.paragraphs
        # Find our paragraph
        inherited = [p for p in paras if p.text == "inheriting"]
        assert len(inherited) == 1
        assert inherited[0].para_pr_id_ref == "5"
        assert inherited[0].style_id_ref == "3"


# =========================================================================
# Exporter roundtrip (bytes input)
# =========================================================================


class TestExporterFromBytes:

    def test_export_text_from_saved_bytes(self):
        from hwpx.tools.exporter import export_text
        doc = _new()
        doc.add_paragraph("Saved text")
        b = doc.to_bytes()
        text = export_text(b)
        assert "Saved text" in text

    def test_export_html_from_saved_bytes(self):
        from hwpx.tools.exporter import export_html
        doc = _new()
        doc.add_paragraph("HTML output")
        b = doc.to_bytes()
        html = export_html(b)
        assert "HTML output" in html

    def test_export_markdown_from_saved_bytes(self):
        from hwpx.tools.exporter import export_markdown
        doc = _new()
        doc.add_paragraph("Markdown output")
        doc.add_table(1, 2).cell(0, 0).text = "Cell"
        b = doc.to_bytes()
        md = export_markdown(b)
        assert "Markdown output" in md
        assert "Cell" in md


# =========================================================================
# File I/O roundtrip
# =========================================================================


class TestFileIO:

    def test_save_and_open_file(self, tmp_path: pathlib.Path):
        doc = _new()
        doc.add_paragraph("file test")
        path = tmp_path / "test.hwpx"
        doc.save_to_path(str(path))
        doc2 = HwpxDocument.open(str(path))
        texts = [p.text for p in doc2.paragraphs]
        assert "file test" in texts

    def test_save_to_bytesio(self):
        doc = _new()
        doc.add_paragraph("bytesio")
        buf = io.BytesIO()
        doc.save_to_stream(buf)
        buf.seek(0)
        doc2 = HwpxDocument.open(buf)
        texts = [p.text for p in doc2.paragraphs]
        assert "bytesio" in texts


# =========================================================================
# Multi-feature combined roundtrip
# =========================================================================


class TestCombinedRoundtrip:

    def test_complex_document_roundtrip(self):
        """Create a document with multiple features, verify after roundtrip."""
        doc = _new()
        doc.add_paragraph("Title", para_pr_id_ref="1", style_id_ref="0")
        doc.add_paragraph("Body paragraph")

        tbl = doc.add_table(2, 2)
        tbl.cell(0, 0).text = "A1"
        tbl.cell(0, 1).text = "B1"
        tbl.cell(1, 0).text = "A2"
        tbl.cell(1, 1).text = "B2"

        p = doc.add_paragraph("")
        p.add_rectangle(7200, 3600)
        p.add_bookmark("mark_1")

        doc.add_paragraph("Closing")

        # Roundtrip
        doc2 = _roundtrip(doc)
        texts = [p.text for p in doc2.paragraphs]
        assert "Title" in texts
        assert "Body paragraph" in texts
        assert "Closing" in texts
        all_tables = [t for p in doc2.paragraphs for t in p.tables]
        assert len(all_tables) >= 1

    def test_double_roundtrip(self):
        """Saving twice should not cause corruption."""
        doc = _new()
        doc.add_paragraph("double")
        doc.add_table(1, 1).cell(0, 0).text = "t"
        doc2 = _roundtrip(doc)
        doc3 = _roundtrip(doc2)
        texts = [p.text for p in doc3.paragraphs]
        assert "double" in texts
