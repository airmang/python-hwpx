"""The experimental placement API follows the existing page estimator."""
from pathlib import Path

from lxml import etree

from hwpx import HwpxDocument
from hwpx.experimental import estimate_layout, estimate_pages
from hwpx.layout.line_cache import write_line_caches

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HH = "{http://www.hancom.co.kr/hwpml/2011/head}"


def _saved_lines(paragraph, lines=1, *, top=0, height=1000, spacing=600, width=40000):
    """Give *paragraph* the layout cache a document saved by Hancom carries: *lines* lines of *height*, the first
    *top* down its cell, the text cut evenly between them. Where the next paragraph's first line goes."""

    for old in paragraph.findall(f"{HP}linesegarray"):
        paragraph.remove(old)
    array = etree.SubElement(paragraph, f"{HP}linesegarray")
    length = sum(len(text.text or "") for text in paragraph.iter(f"{HP}t") if text.getparent().getparent() is paragraph)
    for line in range(lines):
        etree.SubElement(array, f"{HP}lineseg", textpos=str(line * (length // lines)),
                         vertpos=str(top + line * (height + spacing)), textheight=str(height), vertsize=str(height),
                         baseline=str(height * 85 // 100), spacing=str(spacing), horzpos="0", horzsize=str(width),
                         flags="393216")
    return top + lines * (height + spacing)


def test_preserves_the_estimate_and_reports_engine_text_ranges():
    doc = HwpxDocument.new()
    text = "둘째 줄에도 들어갈 문장🙂 " * 400
    doc.add_paragraph(text)

    layout = estimate_layout(doc)
    assert layout.estimate == estimate_pages(doc)
    assert len(layout.pages) == layout.estimate.pages > 1
    paragraph = layout.paragraphs[-1]
    assert tuple(line.position for line in paragraph.lines) == layout.estimate.lines[-1]
    assert len({line.position.page for line in paragraph.lines}) > 1
    assert "".join(line.text for line in paragraph.lines) == text
    for previous, following in zip(paragraph.lines, paragraph.lines[1:]):
        assert previous.text_end == following.text_start
    for line in paragraph.lines:
        assert line.source == "engine"
        assert line.height > 0
        assert line.width > 0
        assert line.top == layout.pages[line.position.page].body[1] + line.position.vertpos
    assert (paragraph.lines[-1].text_end - paragraph.lines[0].text_start) > len(text)


def test_reads_cache_text_positions_and_horizontal_metrics():
    doc = HwpxDocument.new(empty_first_line=True)
    paragraph = doc.add_paragraph("가나다라마바사아자차카타파하" * 8)
    array = etree.SubElement(paragraph.element, f"{HP}linesegarray")
    for start, top in [(0, 0), (37, 1600), (74, 3200)]:
        etree.SubElement(array, f"{HP}lineseg", textpos=str(start), vertpos=str(top), textheight="1000",
                         vertsize="1000", spacing="600", horzpos="400", horzsize="42520")

    placement = estimate_layout(doc).paragraphs[-1]
    assert [(line.text_start, line.text_end) for line in placement.lines] == [(0, 37), (37, 74), (74, 112)]
    assert [line.text for line in placement.lines] == [paragraph.text[:37], paragraph.text[37:74], paragraph.text[74:]]
    assert all((line.x, line.width, line.source) == (400, 42520, "cache") for line in placement.lines)


def test_carries_an_estimator_decline_without_partial_geometry():
    doc = HwpxDocument.new()
    header = doc.parts.headers[0].element
    compat = next(header.iter(f"{HH}compatibleDocument"), None)
    if compat is None:
        compat = etree.SubElement(header, f"{HH}compatibleDocument")
    compat.set("targetProgram", "MS_WORD")

    layout = estimate_layout(doc)
    assert layout.estimate == estimate_pages(doc)
    assert layout.estimate.pages is None
    assert layout.estimate.unsupported
    assert layout.pages == layout.paragraphs == ()


def test_a_wrapped_line_reports_both_pieces_and_their_ranges():
    doc = HwpxDocument.new()
    anchor = doc.add_paragraph("")
    rectangle = doc.shapes.add_rectangle(12000, 7200, paragraph=anchor, treat_as_char=False)
    rectangle.element.set("textWrap", "SQUARE")
    rectangle.element.set("textFlow", "BOTH_SIDES")
    position = rectangle.element.find(f"{HP}pos")
    position.attrib.update({"horzRelTo": "COLUMN", "horzAlign": "LEFT", "horzOffset": "10000",
                            "vertRelTo": "PARA", "vertOffset": "0"})
    text = "도형 양옆에 놓이는 문장 " * 30
    doc.add_paragraph(text)

    layout = estimate_layout(doc)
    assert layout.estimate == estimate_pages(doc)
    first, second, *rest = layout.paragraphs[-1].lines
    assert first.top == second.top
    assert (first.x, first.width, second.x, second.width) == (0, 10000, 22000, 20520)
    assert first.text_end == second.text_start
    assert "".join(line.text for line in (first, second, *rest)) == text


def test_an_inline_table_retains_its_rows_merged_cells_and_measured_text():
    doc = HwpxDocument.new()
    table = doc.add_paragraph("").add_table(3, 2)
    table.merge_cells(0, 0, 1, 0)
    table.cell(0, 0).text = "합친 칸 🙂"
    table.cell(0, 1).text = "나란한 칸"
    table.cell(2, 0).text = "마지막 행"

    layout = estimate_layout(doc)
    assert layout.estimate == estimate_pages(doc)
    placed, = layout.tables
    assert [(row.page, row.row) for row in placed.rows] == [(0, 0), (0, 1), (0, 2)]
    merged, neighbor = placed.rows[0].cells
    assert (merged.row_span, merged.column_span) == (2, 1)
    assert merged.height == placed.rows[0].height + placed.rows[1].height
    assert neighbor.x == merged.width
    assert "".join(line.text for line in merged.lines) == "합친 칸 🙂"


def test_row_breaks_repeat_the_header_on_the_actual_continuation_page():
    doc = HwpxDocument.new()
    table = doc.add_paragraph("").add_table(52, 2)
    table.element.find(f"{HP}pos").set("treatAsChar", "0")
    table.element.attrib.update({"pageBreak": "TABLE", "repeatHeader": "1"})
    for row in range(52):
        table.cell(row, 0).text = f"확인 {row + 1}"
    table.cell(0, 0).element.set("header", "1")
    table.cell(0, 1).element.set("header", "1")

    layout = estimate_layout(doc)
    assert layout.estimate == estimate_pages(doc)
    assert layout.estimate.pages > 1
    placed, = layout.tables
    assert placed.split == "rows"
    assert [row.row for row in placed.rows if not row.repeated] == list(range(52))
    repeated = [row for row in placed.rows if row.repeated]
    assert [(row.page, row.row) for row in repeated] == [(page, 0) for page in range(1, layout.estimate.pages)]
    assert all(row.top == layout.pages[row.page].body[1] for row in repeated)


def test_split_row_reports_cell_line_slices():
    doc = HwpxDocument.new()
    table = doc.add_paragraph("").add_table(1, 1)
    table.element.find(f"{HP}pos").set("treatAsChar", "0")
    table.element.set("pageBreak", "CELL")
    text = "다음 쪽으로 계속되는 칸 문장 🙂 " * 420
    table.cell(0, 0).text = text

    layout = estimate_layout(doc)
    assert layout.estimate == estimate_pages(doc)
    placed, = layout.tables
    assert placed.split == "cell-lines"
    assert len(placed.rows) > 1 and all(row.row == 0 for row in placed.rows)
    assert [(before.line_end, after.line_start) for before, after in zip(placed.rows, placed.rows[1:])] == [
        (row.line_start, row.line_start) for row in placed.rows[1:]
    ]
    assert "".join(line.text for row in placed.rows for cell in row.cells for line in cell.lines) == text


def test_nested_inline_table_keeps_its_own_rows_in_the_parent_cell_page():
    doc = HwpxDocument.new()
    outer = doc.add_paragraph("").add_table(1, 1)
    inner = outer.cell(0, 0).paragraphs[0].add_table(2, 1)
    inner.cell(1, 0).text = "안쪽 표"

    layout = estimate_layout(doc)
    assert layout.estimate == estimate_pages(doc)
    outer_placement, inner_placement = layout.tables
    assert len(outer_placement.rows) == 1
    assert [row.page for row in inner_placement.rows] == [0, 0]
    assert "".join(line.text for line in inner_placement.rows[1].cells[0].lines) == "안쪽 표"


def test_merged_cell_continues_with_the_same_source_and_remaining_lines():
    doc = HwpxDocument.new()
    table = doc.add_paragraph("").add_table(3, 2)
    table.element.find(f"{HP}pos").set("treatAsChar", "0")
    table.merge_cells(0, 0, 1, 0)
    text = "병합 칸 내용 " * 200
    table.cell(0, 0).text = text

    layout = estimate_layout(doc)
    assert layout.estimate == estimate_pages(doc)
    placed, = layout.tables
    assert placed.split == "cell-lines"
    first, continued = [cell for row in placed.rows for cell in row.cells if cell.source_index == 0]
    assert first.line_start == 0 and first.line_end == continued.line_start
    assert "".join(line.text for cell in (first, continued) for line in cell.lines) == text


def test_blank_table_anchor_and_runs_preserve_native_character_positions():
    doc = HwpxDocument.new()
    table_anchor = doc.add_paragraph("")
    table_anchor.add_table(1, 1)
    paragraph = doc.add_paragraph("보통 🙂")
    marked = paragraph.add_run("굵게", bold=True)

    layout = estimate_layout(doc)
    assert layout.estimate == estimate_pages(doc)
    anchor, styled = layout.paragraphs[-2:]
    # The first body paragraph also carries the section and column controls.
    assert (anchor.lines[0].text_start, anchor.lines[0].text_end, anchor.lines[0].text) == (0, 24, "")
    line, = styled.lines
    assert line.text == "보통 🙂굵게"
    assert [text for _, text in line.runs] == ["보통 🙂", "굵게"]
    assert line.runs[-1][0] == marked.element.get("charPrIDRef")


def test_square_object_rectangle_and_note_areas_use_final_frames():
    doc = HwpxDocument.new()
    anchor = doc.add_paragraph("")
    rectangle = doc.shapes.add_rectangle(12000, 7200, paragraph=anchor, treat_as_char=False)
    rectangle.element.set("textWrap", "SQUARE")
    rectangle.element.find(f"{HP}pos").attrib.update({
        "horzRelTo": "COLUMN", "horzAlign": "LEFT", "horzOffset": "10000",
        "vertRelTo": "PARA", "vertOffset": "0",
    })
    paragraph = doc.add_paragraph("주석의 닻")
    doc.notes.add_footnote("각주 내용", paragraph=paragraph)
    doc.notes.add_endnote("미주 내용", paragraph=paragraph)
    doc.page.set_header(text="머리말 내용")

    layout = estimate_layout(doc)
    assert layout.estimate == estimate_pages(doc)
    obj, = layout.objects
    assert (obj.page, obj.x, obj.width, obj.height) == (0, layout.pages[0].body[0] + 10000, 12000, 7200)
    assert obj.top is not None and not obj.unavailable
    positioned = {area.kind: area for area in layout.areas}
    for kind, expected in (("footNote", "각주 내용"), ("endNote", "미주 내용")):
        area = positioned[kind]
        assert area.page is not None and area.top is not None
        assert "".join(line.text for line in area.lines) == expected
    assert positioned["header"].top is None and positioned["header"].unavailable


def test_cached_square_picture_keeps_its_moved_page_separate_from_its_anchor():
    path = Path(__file__).parent / "fixtures/hancom_saved/pages_square_picture_moved_to_the_next_page.hwpx"
    layout = estimate_layout(path)
    assert layout.estimate == estimate_pages(path)
    picture, = layout.objects
    anchor = next(item for item in layout.paragraphs
                  if (item.section, item.paragraph) == (picture.section, picture.paragraph))
    assert anchor.lines[0].position.page == 0
    assert picture.page == 1 and picture.top == layout.pages[1].body[1]
    assert (picture.width, picture.height) == (20000, 27112)


def _merged_table_with_saved_lines():
    """An inline table with a cell merged over rows in which every paragraph keeps a layout cache: the layout
    takes such a table as tall as it was saved (hp:sz), without asking for its rows."""

    doc = HwpxDocument.new()
    table = doc.add_paragraph("").add_table(3, 2)
    table.merge_cells(0, 0, 1, 0)
    table.cell(0, 0).text = "두 행을 합친 칸"
    table.cell(0, 1).text = "곁에 놓인 칸"
    table.cell(2, 0).text = "맨 아래 행"
    assert write_line_caches(doc).written
    assert all(paragraph.find(f"{HP}linesegarray") is not None for paragraph in table.element.iter(f"{HP}p"))
    return doc, table


def test_an_inline_table_laid_out_as_tall_as_it_was_saved_keeps_its_rows():
    doc, table = _merged_table_with_saved_lines()

    layout = estimate_layout(doc)
    assert layout.estimate == estimate_pages(doc)
    placed, = layout.tables
    assert placed.unavailable == ("inline table origin not measured",)
    assert [(row.page, row.row) for row in placed.rows] == [(0, 0), (0, 1), (0, 2)]
    assert sum(row.height for row in placed.rows) == int(table.element.find(f"{HP}sz").get("height"))
    merged, neighbor = placed.rows[0].cells
    assert (merged.row, merged.column, merged.row_span) == (0, 0, 2)
    assert merged.height == placed.rows[0].height + placed.rows[1].height
    assert (neighbor.x, neighbor.top) == (merged.width, 0)
    assert [(line.text, line.source) for line in merged.lines] == [("두 행을 합친 칸", "cache")]
    assert [line.text for row in placed.rows for cell in row.cells for line in cell.lines if line.text] == [
        "두 행을 합친 칸", "곁에 놓인 칸", "맨 아래 행"]


def test_rows_that_do_not_add_up_to_the_saved_height_are_placed_without_heights():
    doc, table = _merged_table_with_saved_lines()
    size = table.element.find(f"{HP}sz")
    size.set("height", str(int(size.get("height")) + 700))  # drawn taller than the row model makes it

    layout = estimate_layout(doc)
    assert layout.estimate == estimate_pages(doc)
    placed, = layout.tables
    assert [(row.page, row.row, row.top, row.height) for row in placed.rows] == [
        (0, 0, None, None), (0, 1, None, None), (0, 2, None, None)]
    reason, = [why for why in placed.unavailable if why.startswith("row heights not measured")]
    for cell in (cell for row in placed.rows for cell in row.cells):
        assert (cell.top, cell.height) == (None, None) and reason in cell.unavailable
        assert cell.x is not None and cell.width is not None
    assert "".join(line.text for line in placed.rows[0].cells[0].lines) == "두 행을 합친 칸"


def test_a_nested_table_stands_on_the_page_of_the_cell_line_holding_it():
    doc = HwpxDocument.new()
    outer = doc.add_paragraph("").add_table(1, 1)
    outer.element.find(f"{HP}pos").set("treatAsChar", "0")
    outer.element.set("pageBreak", "CELL")
    cell = outer.cell(0, 0)
    cell.paragraphs[0].text = "칸을 여는 문단"
    for number in range(70):
        cell.add_paragraph(f"쪽을 넘기려고 쌓는 문단 {number + 2}")
    inner = cell.add_paragraph("").add_table(2, 1)
    inner.cell(0, 0).text = "안쪽 표의 첫 행"
    inner.cell(1, 0).text = "안쪽 표의 둘째 행"
    cell.add_paragraph("안쪽 표 다음 문단")
    top = 0
    for paragraph in cell.element.findall(f"{HP}subList/{HP}p"):
        top = _saved_lines(paragraph, top=top)
    for paragraph in inner.element.iter(f"{HP}p"):
        _saved_lines(paragraph)

    layout = estimate_layout(doc)
    assert layout.estimate == estimate_pages(doc)
    assert layout.estimate.pages == 2
    outer_placed, inner_placed = layout.tables
    assert outer_placed.split == "cell-lines"
    first, second = outer_placed.rows
    assert (first.page, second.page) == (0, 1) and first.line_end == second.line_start
    holding = [(row.page, line.paragraph, line.text, line.tables)
               for row in outer_placed.rows for line in row.cells[0].lines if line.tables]
    assert holding == [(1, 71, None, (inner_placed.table,))]
    assert [(row.page, row.row) for row in inner_placed.rows] == [(1, 0), (1, 1)]
    assert inner_placed.moved is None  # a table in a cell has no anchor line of its own in the body
    shown = ["".join(line.text for line in row.cells[0].lines if line.text) for row in outer_placed.rows]
    assert shown[0].startswith("칸을 여는 문단") and shown[1].endswith("안쪽 표 다음 문단")
    assert "".join(line.text for row in inner_placed.rows for line in row.cells[0].lines) == (
        "안쪽 표의 첫 행안쪽 표의 둘째 행")
