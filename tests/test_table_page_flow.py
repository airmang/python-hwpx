from __future__ import annotations

from hwpx.document import HwpxDocument

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def test_table_treat_as_char_is_explicit_and_persists() -> None:
    with HwpxDocument.new() as document:
        table = document.add_table(2, 1)
        assert table.treat_as_char is True
        original_height = table.height
        table.set_treat_as_char(False)
        assert table.treat_as_char is False
        reopened = HwpxDocument.open(document.to_bytes())
        try:
            assert reopened.tables.all[0].treat_as_char is False
            assert reopened.tables.all[0].height == original_height
        finally:
            reopened.close()


def test_a_new_table_row_is_as_tall_as_its_text() -> None:
    # As a new Hancom table: the cell height is 282 and the row grows to its text.
    with HwpxDocument.new() as document:
        table = document.add_table(3, 2)
        heights = {cell.get("height") for cell in table.element.iter(f"{HP}cellSz")}
        assert heights == {"282"}
        assert table.height == 3 * 282


def test_a_table_that_fits_the_page_stays_inline() -> None:
    with HwpxDocument.new() as document:
        assert document.add_table(10, 3).treat_as_char is True


def test_a_table_taller_than_the_page_flows_across_pages() -> None:
    # 60 rows of at least one 10 pt line plus the cell margins do not fit the
    # 232 mm body of the default A4 page; Hancom never breaks an inline table.
    with HwpxDocument.new() as document:
        table = document.add_table(60, 3)
        assert table.treat_as_char is False
        assert table.element.get("pageBreak") == "CELL"


def test_given_row_heights_count_toward_the_page() -> None:
    with HwpxDocument.new() as document:
        assert document.add_table(20, 2, height=20 * 3600).treat_as_char is False
        assert document.add_table(15, 2, height=15 * 3600).treat_as_char is True


def test_the_page_as_drawn_decides() -> None:
    # 40 one-line rows fit a portrait page body but not a landscape one.
    with HwpxDocument.new() as document:
        assert document.add_table(40, 2).treat_as_char is True
        document.page.setup(orientation="LANDSCAPE")
        assert document.add_table(40, 2).treat_as_char is False
