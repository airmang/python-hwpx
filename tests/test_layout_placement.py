"""The experimental placement API follows the existing page estimator."""
from pathlib import Path

from lxml import etree

from hwpx import HwpxDocument
from hwpx.experimental import estimate_layout, estimate_pages
from hwpx.layout.line_cache import write_line_caches

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HH = "{http://www.hancom.co.kr/hwpml/2011/head}"


def _saved_lines(paragraph, starts=(0,), heights=None, *, top=0, spacing=600, width=40000):
    """Give *paragraph* the layout cache a document saved by Hancom carries: a line starting at each of *starts*
    (text positions as Hancom counts them, an object taking 8), each as tall as *heights* says (1000 otherwise),
    the first *top* down. Where the next paragraph's first line goes."""

    for old in paragraph.findall(f"{HP}linesegarray"):
        paragraph.remove(old)
    array = etree.SubElement(paragraph, f"{HP}linesegarray")
    for start, height in zip(starts, heights or (1000,) * len(starts)):
        etree.SubElement(array, f"{HP}lineseg", textpos=str(start), vertpos=str(top), textheight=str(height),
                         vertsize=str(height), baseline=str(height * 85 // 100), spacing=str(spacing), horzpos="0",
                         horzsize=str(width), flags="393216")
        top += height + spacing
    return top


def _declared_rows(table, height):
    """Make every row of *table* as tall as its cells declare, *height*, and the table as tall as its rows (as
    Hancom saves hp:sz)."""

    for cell in table.element.iter(f"{HP}tc"):
        cell.find(f"{HP}cellSz").set("height", str(height))
    table.element.find(f"{HP}sz").set("height", str(height * len(table.element.findall(f"{HP}tr"))))


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
    headers = [area for area in layout.areas if area.kind == "header"]
    assert [area.page for area in headers] == list(range(layout.estimate.pages))  # on every page of its section
    for area in headers:  # the room above the body, as tall as the header margin; its lines are not laid out
        body = layout.pages[area.page].body
        assert (area.x, area.top + area.height, area.width) == (body[0], body[1], body[2]) and area.height > 0
        assert [line.text for line in area.lines] == ["머리말 내용"] and area.unavailable == ()


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
    assert placed.unavailable == () and placed.moved is False
    assert [(row.page, row.row) for row in placed.rows] == [(0, 0), (0, 1), (0, 2)]
    assert sum(row.height for row in placed.rows) == int(table.element.find(f"{HP}sz").get("height"))
    # the table is all its line holds: its rows stand from the line's top, at the line's start
    line, = next(item for item in layout.paragraphs if item.paragraph == placed.paragraph).lines
    tall = placed.rows[0].height
    assert [(row.top, row.x) for row in placed.rows] == [(line.top, 0), (line.top + tall, 0), (line.top + 2 * tall, 0)]
    merged, neighbor = placed.rows[0].cells
    assert (merged.row, merged.column, merged.row_span) == (0, 0, 2)
    assert merged.height == placed.rows[0].height + placed.rows[1].height
    assert (neighbor.x, neighbor.top) == (merged.width, 0)
    # a cell sets its line in the middle of its height: the merged cell has a row's height more room
    assert merged.lines[0].top - neighbor.lines[0].top == (merged.height - neighbor.height) // 2 > 0
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
    assert all(row.cells[0].lines == () for row in outer_placed.rows)  # text is not all the cell holds
    holding = [(row.page, line.paragraph, line.text, line.tables)
               for row in outer_placed.rows for line in row.cells[0].lines_with_tables if line.tables]
    assert holding == [(1, 71, None, (inner_placed.table,))]
    assert [(row.page, row.row) for row in inner_placed.rows] == [(1, 0), (1, 1)]
    assert inner_placed.moved is None  # a table in a cell has no anchor line of its own in the body
    shown = ["".join(line.text for line in row.cells[0].lines_with_tables if line.text) for row in outer_placed.rows]
    assert shown[0].startswith("칸을 여는 문단") and shown[1].endswith("안쪽 표 다음 문단")
    assert "".join(line.text for row in inner_placed.rows for line in row.cells[0].lines) == (
        "안쪽 표의 첫 행안쪽 표의 둘째 행")


def test_a_table_among_cached_lines_stands_on_the_line_holding_its_place():
    doc = HwpxDocument.new(empty_first_line=True)
    body = estimate_layout(doc).pages[0].body[3]
    before, after = "표보다 앞선 글", "표를 지난 글"
    paragraph = doc.add_paragraph(before)
    table = paragraph.add_table(2, 2)
    table.cell(0, 0).text = "글 가운데 놓인 표"
    paragraph.add_run(after)
    tall = (body - 1200) // 2
    _declared_rows(table, tall)
    # the lines as saved: the text before the table, the table (8 places in the cache), the text after it
    _saved_lines(paragraph.element, (0, len(before), len(before) + 8), (1000, 2 * tall, 1000))

    layout = estimate_layout(doc)
    assert layout.estimate == estimate_pages(doc)
    lines = layout.paragraphs[-1].lines
    assert [line.position.page for line in lines] == [0, 1, 2]  # the table's line does not fit under the first
    assert [(line.text, line.source) for line in lines] == [(before, "cache"), ("", "cache"), (after, "cache")]
    placed, = layout.tables
    assert [(row.page, row.row, row.height) for row in placed.rows] == [(1, 0, tall), (1, 1, tall)]
    assert placed.moved is True  # among text, where it stands on its line is not laid out
    assert placed.unavailable == ("inline table origin not measured", "table left edge not measured")
    assert all((row.top, row.x) == (None, None) for row in placed.rows)
    assert "".join(line.text for line in placed.rows[0].cells[0].lines) == "글 가운데 놓인 표"


def test_a_table_among_the_cached_lines_of_a_cell_is_named_on_its_line():
    doc = HwpxDocument.new()
    outer = doc.add_paragraph("").add_table(1, 1)
    before, after = "칸 안에서 표보다 앞선 글", "표를 지난 글"
    paragraph = outer.cell(0, 0).paragraphs[0]
    paragraph.text = before
    inner = paragraph.add_table(1, 2)
    inner.cell(0, 1).text = "칸 속에 든 표"
    paragraph.add_run(after)
    _declared_rows(outer, 8000)
    _declared_rows(inner, 3000)
    _saved_lines(paragraph.element, (0, len(before)), (1000, 3000))
    for cell_paragraph in inner.element.iter(f"{HP}p"):
        _saved_lines(cell_paragraph)

    layout = estimate_layout(doc)
    assert layout.estimate == estimate_pages(doc)
    outer_placed, inner_placed = layout.tables
    cell, = outer_placed.rows[0].cells
    assert cell.lines == () and "the cell holds tables: its lines are in lines_with_tables" in cell.unavailable
    assert [(line.text, line.source, line.tables) for line in cell.lines_with_tables] == [
        (before, "cache", ()), (None, "cache", (inner_placed.table,))]
    assert cell.lines_with_tables[1].text_start == len(before)  # the line's range stays, its text is not text alone
    assert [(row.page, row.height) for row in inner_placed.rows] == [(0, 3000)]
    assert "".join(line.text for line in inner_placed.rows[0].cells[1].lines) == "칸 속에 든 표"


def test_a_table_placed_on_the_paper_keeps_its_rows_where_its_band_stands():
    doc = HwpxDocument.new()
    doc.add_paragraph("종이 위 자리에 놓인 표가 있는 쪽")
    table = doc.add_paragraph("").add_table(2, 2)
    table.cell(1, 1).text = "종이 위의 표"
    table.element.set("textWrap", "TOP_AND_BOTTOM")
    table.element.find(f"{HP}pos").attrib.update({
        "treatAsChar": "0", "flowWithText": "0", "vertRelTo": "PAPER", "vertAlign": "TOP", "vertOffset": "30000",
        "horzRelTo": "PAPER", "horzAlign": "LEFT", "horzOffset": "8504",
    })
    doc.add_paragraph("표와 겹치지 않는 문단")

    layout = estimate_layout(doc)
    assert layout.estimate == estimate_pages(doc)
    placed, = layout.tables
    first, second = placed.rows
    assert (first.page, first.top, second.page, second.top) == (0, 30000, 0, 30000 + first.height)
    assert placed.moved is False and placed.unavailable == ()
    assert "".join(line.text for line in second.cells[1].lines) == "종이 위의 표"


def test_a_square_wrapped_table_beside_cached_lines_stands_at_its_band():
    doc = HwpxDocument.new(empty_first_line=True)
    paragraph = doc.add_paragraph("")
    table = paragraph.add_table(2, 1)
    table.cell(0, 0).text = "글 옆에 선 표"
    table.element.attrib.update({"textWrap": "SQUARE", "textFlow": "BOTH_SIDES"})
    table.element.find(f"{HP}sz").set("width", "12000")
    for cell in table.element.iter(f"{HP}tc"):
        cell.find(f"{HP}cellSz").set("width", "12000")
    table.element.find(f"{HP}pos").attrib.update({
        "treatAsChar": "0", "flowWithText": "1", "vertRelTo": "PARA", "vertAlign": "TOP", "vertOffset": "0",
        "horzRelTo": "COLUMN", "horzAlign": "RIGHT", "horzOffset": "0",
    })
    _declared_rows(table, 2500)
    text = "표 곁을 따라 흐르는 글 " * 9
    paragraph.add_run(text)
    third = len(text) // 3
    _saved_lines(paragraph.element, (0, 8 + third, 8 + 2 * third), width=28000)  # as broken beside the table

    layout = estimate_layout(doc)
    assert layout.estimate == estimate_pages(doc)
    lines = layout.paragraphs[-1].lines
    assert [line.source for line in lines] == ["cache"] * 3
    placed, = layout.tables
    assert [(row.page, row.top, row.height) for row in placed.rows] == [
        (0, lines[0].top, 2500), (0, lines[0].top + 2500, 2500)]
    assert placed.unavailable == ()


def test_a_table_gone_on_whole_to_the_next_page_is_placed_at_its_top():
    doc = HwpxDocument.new()
    body = estimate_layout(doc).pages[0].body[3]
    for _ in range((body - 12000) // 1600):
        doc.add_paragraph("앞 쪽을 채우는 문단")
    paragraph = doc.add_paragraph("표를 지닌 문단")
    table = paragraph.add_table(3, 1)
    table.element.attrib.update({"textWrap": "TOP_AND_BOTTOM", "pageBreak": "NONE"})
    table.element.find(f"{HP}pos").attrib.update({
        "treatAsChar": "0", "flowWithText": "1", "vertRelTo": "PARA", "vertAlign": "TOP", "vertOffset": "0",
        "horzRelTo": "COLUMN", "horzAlign": "LEFT", "horzOffset": "0",
    })
    _declared_rows(table, 6000)

    layout = estimate_layout(doc)
    assert layout.estimate == estimate_pages(doc)
    assert layout.estimate.pages == 2
    assert [line.position.page for line in layout.paragraphs[-1].lines] == [0]  # its line stays
    placed, = layout.tables
    top = layout.pages[1].body[1]
    assert [(row.page, row.top) for row in placed.rows] == [(1, top), (1, top + 6000), (1, top + 12000)]
    assert placed.moved is True and placed.split is None and placed.unavailable == ()


def test_a_table_the_layout_does_not_place_says_why():
    doc = HwpxDocument.new()
    floating = doc.add_paragraph("").add_table(1, 1)
    floating.element.set("textWrap", "IN_FRONT_OF_TEXT")
    floating.element.find(f"{HP}pos").attrib.update({"treatAsChar": "0", "vertRelTo": "PARA", "horzRelTo": "PARA"})
    doc.page.set_header(text="머리말")
    header = next(doc.sections[0].element.iter(f"{HP}header"))
    held = doc.add_paragraph("").add_table(1, 1)
    moved = held.element.getparent()
    header.find(f"{HP}subList/{HP}p").append(moved)  # the run holding the table, into the header's paragraph

    layout = estimate_layout(doc)
    assert layout.estimate == estimate_pages(doc)
    reasons = {reason for placed in layout.tables if not placed.rows for reason in placed.unavailable}
    assert reasons == {
        "a table in front of or behind the text takes no room in the layout: its place is not computed",
        "a table in a header: what a header holds is not placed row by row",
    }


def test_an_unsplit_table_left_before_its_line_is_not_placed():
    doc = HwpxDocument.new()
    body = estimate_layout(doc).pages[0].body[3]
    for _ in range((body - 19000) // 1600):
        doc.add_paragraph("쪽의 앞을 채우는 문단")
    paragraph = doc.add_paragraph("")
    table = paragraph.add_table(3, 1)
    table.element.attrib.update({"textWrap": "TOP_AND_BOTTOM", "pageBreak": "NONE"})
    table.element.find(f"{HP}sz").set("width", "15000")
    for cell in table.element.iter(f"{HP}tc"):
        cell.find(f"{HP}cellSz").set("width", "15000")
    _declared_rows(table, 6200)
    table.element.find(f"{HP}pos").attrib.update({
        "treatAsChar": "0", "flowWithText": "1", "vertRelTo": "PARA", "vertAlign": "TOP", "vertOffset": "0",
        "horzRelTo": "COLUMN", "horzAlign": "LEFT", "horzOffset": "0",
    })
    beside = doc.shapes.add_rectangle(8000, 4000, paragraph=paragraph, treat_as_char=False)
    beside.element.set("textWrap", "TOP_AND_BOTTOM")
    beside.element.find(f"{HP}pos").attrib.update({
        "flowWithText": "1", "vertRelTo": "PARA", "vertAlign": "TOP", "vertOffset": "0",
        "horzRelTo": "COLUMN", "horzAlign": "RIGHT", "horzOffset": "0",
    })
    doc.add_paragraph("표 다음 문단")

    layout = estimate_layout(doc)
    assert layout.estimate == estimate_pages(doc)
    # the two objects fit at the foot of the first page; the paragraph's line has no room below them
    anchor = next(item for item in layout.paragraphs if item.paragraph == layout.tables[0].paragraph)
    assert [line.position.page for line in anchor.lines] == [1]
    placed, = layout.tables
    assert placed.rows == () and placed.moved is None
    assert placed.unavailable == (
        "a table set not to split is left on the page before its paragraph's line: the layout does not follow it "
        "going on with that line",)

    table.element.set("pageBreak", "CELL")  # one that may split is where the layout leaves it
    again, = estimate_layout(doc).tables
    assert [row.page for row in again.rows] == [0, 0, 0] and again.unavailable == ()


def test_cell_lines_stand_where_the_cell_sets_them():
    doc = HwpxDocument.new()
    table = doc.add_paragraph("").add_table(1, 3)
    for index, where in enumerate(("TOP", "CENTER", "BOTTOM")):
        cell = table.cell(0, index)
        cell.text = "한 줄짜리 칸"
        cell.element.find(f"{HP}subList").set("vertAlign", where)
    _declared_rows(table, 6000)

    layout = estimate_layout(doc)
    assert layout.estimate == estimate_pages(doc)
    at_top, centred, at_foot = (cell.lines[0] for cell in layout.tables[0].rows[0].cells)
    margin = at_top.top  # the cell's top margin, the same as its bottom one
    assert 0 < margin < 1000 and all(cell.unavailable == () for cell in layout.tables[0].rows[0].cells)
    assert at_foot.top == 6000 - margin - at_foot.height
    assert centred.top == margin + (6000 - 2 * margin - centred.height) // 2
    assert all(line.x is not None and line.width is not None for line in (at_top, centred, at_foot))


def test_a_split_cell_set_at_its_top_starts_each_part_below_its_top_margin():
    def split_cell(where):
        doc = HwpxDocument.new()
        table = doc.add_paragraph("").add_table(1, 1)
        table.element.find(f"{HP}pos").set("treatAsChar", "0")
        table.element.set("pageBreak", "CELL")
        table.cell(0, 0).text = "쪽을 넘도록 길게 이어 쓰는 칸의 글 " * 300
        table.cell(0, 0).element.find(f"{HP}subList").set("vertAlign", where)
        layout = estimate_layout(doc)
        assert layout.estimate == estimate_pages(doc) and layout.estimate.pages > 2
        return [row.cells[0] for row in layout.tables[0].rows]

    parts = split_cell("TOP")
    margin = parts[0].lines[0].top
    for part in parts:
        tops = [line.top for line in part.lines]
        assert tops[0] == margin and part.unavailable == ()
        assert all(below - above == tops[1] - tops[0] for above, below in zip(tops, tops[1:]))

    for part in split_cell("CENTER"):  # where Hancom stands the lines of each part is not laid out
        assert all(line.top is None and line.text for line in part.lines)
        assert part.unavailable == ("cell line tops not measured: the cell is split over pages and not set at its top",)


def test_a_table_placed_from_its_column_keeps_its_left_edge():
    for align, expected in (("LEFT", lambda room: 1000), ("CENTER", lambda room: (room - 15000) // 2 + 1000),
                            ("RIGHT", lambda room: room - 15000 - 1000)):
        doc = HwpxDocument.new()
        table = doc.add_paragraph("").add_table(2, 1)
        table.element.set("textWrap", "TOP_AND_BOTTOM")
        table.element.find(f"{HP}sz").set("width", "15000")
        for cell in table.element.iter(f"{HP}tc"):
            cell.find(f"{HP}cellSz").set("width", "15000")
        table.element.find(f"{HP}pos").attrib.update({
            "treatAsChar": "0", "flowWithText": "1", "vertRelTo": "PARA", "vertAlign": "TOP", "vertOffset": "0",
            "horzRelTo": "COLUMN", "horzAlign": align, "horzOffset": "1000",
        })

        layout = estimate_layout(doc)
        assert layout.estimate == estimate_pages(doc)
        placed, = layout.tables
        room, = layout.pages[0].column_areas[0].widths
        assert [row.x for row in placed.rows] == [expected(room)] * 2 and placed.unavailable == ()


def test_a_table_alone_on_its_line_follows_the_paragraph_alignment():
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("")
    table = paragraph.add_table(1, 1)
    table.element.find(f"{HP}sz").set("width", "12000")
    table.element.find(f"{HP}tr/{HP}tc/{HP}cellSz").set("width", "12000")
    shape = next(item for item in doc.parts.headers[0].element.iter(f"{HH}paraPr")
                 if item.get("id") == paragraph.element.get("paraPrIDRef"))

    def left_edge(horizontal):
        shape.find(f"{HH}align").set("horizontal", horizontal)
        layout = estimate_layout(doc)
        assert layout.estimate == estimate_pages(doc)
        (row,), line = layout.tables[0].rows, layout.paragraphs[-1].lines[0]
        assert row.top == line.top and layout.tables[0].unavailable == ()
        return row.x, layout.pages[0].column_areas[0].widths[0]

    assert left_edge("JUSTIFY")[0] == 0
    centred, room = left_edge("CENTER")
    assert centred == (room - 12000) / 2
    assert left_edge("RIGHT")[0] == room - 12000

    table.element.find(f"{HP}sz").set("width", str(room + 600))  # wider than its line, not set left
    table.element.find(f"{HP}tr/{HP}tc/{HP}cellSz").set("width", str(room + 600))
    wide, = estimate_layout(doc).tables
    assert wide.rows[0].x is None and wide.rows[0].top is not None
    assert wide.unavailable == ("table left edge not measured",)


def test_a_table_in_a_text_box_stands_on_the_page_of_its_box():
    doc = HwpxDocument.new()
    body = estimate_layout(doc).pages[0].body[3]
    for _ in range(body // 1600 + 3):
        doc.add_paragraph("글상자를 둘째 쪽으로 미는 문단")
    box = doc.shapes.add_rectangle(20000, 9000, paragraph=doc.add_paragraph(""), treat_as_char=True)
    box.set_draw_text("글상자에 적은 글")
    table = next(iter(box.iter_paragraphs())).paragraph.add_table(2, 1)
    table.cell(1, 0).text = "글상자 속의 표"

    layout = estimate_layout(doc)
    assert layout.estimate == estimate_pages(doc)
    placed, = layout.tables
    drawing, = layout.objects
    assert drawing.page == 1 and [row.page for row in placed.rows] == [1, 1]
    assert placed.unavailable == ("table origin in its text box not measured", "table left edge not measured")
    assert "".join(line.text for line in placed.rows[1].cells[0].lines) == "글상자 속의 표"


def test_a_table_in_front_of_the_text_placed_on_the_paper_keeps_its_place():
    doc = HwpxDocument.new()
    table = doc.add_paragraph("").add_table(2, 2)
    table.element.set("textWrap", "IN_FRONT_OF_TEXT")
    position = table.element.find(f"{HP}pos")
    position.attrib.update({
        "treatAsChar": "0", "flowWithText": "0", "vertRelTo": "PAPER", "vertAlign": "TOP", "vertOffset": "40000",
        "horzRelTo": "PAPER", "horzAlign": "LEFT", "horzOffset": "12000",
    })

    layout = estimate_layout(doc)
    assert layout.estimate == estimate_pages(doc)
    placed, = layout.tables
    first, second = placed.rows
    assert (first.page, first.top, second.top) == (0, 40000, 40000 + first.height) and placed.unavailable == ()
    assert first.x == 12000 - layout.pages[0].body[0]  # from the column's left edge

    position.attrib.update({"vertRelTo": "PARA", "flowWithText": "1"})  # from its paragraph: not computed
    floating, = estimate_layout(doc).tables
    assert floating.rows == () and floating.unavailable == (
        "a table in front of or behind the text takes no room in the layout: its place is not computed",)


def test_an_object_alone_on_its_line_has_its_rectangle():
    doc = HwpxDocument.new(empty_first_line=True)
    paragraph = doc.add_paragraph("")
    doc.shapes.add_rectangle(12000, 7200, paragraph=paragraph, treat_as_char=True)
    shape = next(item for item in doc.parts.headers[0].element.iter(f"{HH}paraPr")
                 if item.get("id") == paragraph.element.get("paraPrIDRef"))

    def rectangle(horizontal):
        shape.find(f"{HH}align").set("horizontal", horizontal)
        layout = estimate_layout(doc)
        assert layout.estimate == estimate_pages(doc)
        placed, = layout.objects
        line, = layout.paragraphs[-1].lines
        assert (placed.wrap, placed.page, placed.top, placed.unavailable) == ("AS_CHARACTER", 0, line.top, ())
        assert (placed.width, placed.height) == (12000, 7200) and line.height == 7200
        return placed.x - layout.pages[0].body[0], layout.pages[0].column_areas[0].widths[0]

    assert rectangle("JUSTIFY")[0] == 0
    centred, room = rectangle("CENTER")
    assert centred == (room - 12000) // 2
    assert rectangle("RIGHT")[0] == room - 12000


def _object_among(before, after="", horizontal=None, *, cached=None):
    """A document whose last paragraph holds *before*, a 6000 x 5000 rectangle set as a character, then *after*,
    aligned *horizontal* (the paragraph shape's own when None); *cached*: the saved lines' starts. Its layout."""

    doc = HwpxDocument.new(empty_first_line=True)
    paragraph = doc.add_paragraph(before)
    doc.shapes.add_rectangle(6000, 5000, paragraph=paragraph, treat_as_char=True)
    if after:
        paragraph.add_run(after)
    if horizontal is not None:
        shape = next(item for item in doc.parts.headers[0].element.iter(f"{HH}paraPr")
                     if item.get("id") == paragraph.element.get("paraPrIDRef"))
        shape.find(f"{HH}align").set("horizontal", horizontal)
    if cached is not None:
        _saved_lines(paragraph.element, cached, width=estimate_layout(doc).pages[0].body[2])
    layout = estimate_layout(doc)
    assert layout.estimate == estimate_pages(doc)
    return layout


def test_an_object_among_text_stands_past_the_text_before_it_on_its_line():
    left = estimate_layout(HwpxDocument.new()).pages[0].body[0]

    def x(before, after="", horizontal="LEFT"):
        layout = _object_among(before, after, horizontal)
        placed, = layout.objects
        line, = layout.paragraphs[-1].lines
        assert (placed.page, placed.top, placed.width, placed.height) == (0, line.top, 6000, 5000)
        assert line.height == 5000 and placed.unavailable == ()
        return placed.x - left

    assert x("") == 0
    one = x("가가")
    assert one > 0 and x("가가가가") == 2 * one  # past the characters before it, as the layout measures them
    assert x("가가", " 가가", "JUSTIFY") == one  # its paragraph's last line: set as if left
    room = estimate_layout(HwpxDocument.new()).pages[0].body[2]
    centred, right = x("가가", "가가", "CENTER"), x("가가", "가가", "RIGHT")
    assert abs((right - one) - 2 * (centred - one)) <= 1  # moved by the room the line leaves, or half of it
    assert right - one == room - (2 * one + 6000)


def test_an_object_among_text_says_why_its_line_does_not_place_it():
    layout = _object_among("가가", " ", "CENTER")
    assert layout.objects[0].x is None
    assert layout.objects[0].unavailable == (
        ("object set as a character on a line set centred or right that ends in spaces or automatic spacing: whether "
         "Hancom counts them is not laid out"),)
    assert _object_among("", "가가", "DISTRIBUTE").objects[0].x is not None  # at its line's start
    spread, = _object_among("가가", "가가", "DISTRIBUTE").objects
    assert spread.x is None and spread.unavailable == (
        ("object set as a character on a line spread across its room (justified but the last, or distributed): "
         "where Hancom adds the room is not laid out"),)


def test_an_object_among_saved_lines_stands_past_the_text_before_it_on_its_own_line():
    left = estimate_layout(HwpxDocument.new()).pages[0].body[0]
    first = _object_among("가", "가", "LEFT").objects[0].x - left
    # the lines as saved: two characters, then the third character, the object (8 places) and the last one
    placed, = _object_among("가가가", "가", "LEFT", cached=(0, 2)).objects
    lines = _object_among("가가가", "가", "LEFT", cached=(0, 2)).paragraphs[-1].lines
    assert [line.source for line in lines] == ["cache", "cache"]
    assert placed.x - left == first  # past the one character before it on the second line
    assert placed.top is None and placed.unavailable == (
        "object set as a character on a line taller than it: where it stands up and down the line is not laid out",)
    spread, = _object_among("가가", "가", "JUSTIFY", cached=(0, 10)).objects  # on the first of two lines
    assert spread.x is None and spread.unavailable[0].startswith("object set as a character on a line spread")


def test_an_object_among_the_saved_lines_of_a_cell_stands_on_its_cell_line():
    doc = HwpxDocument.new()
    table = doc.add_paragraph("").add_table(1, 2)
    paragraph = table.cell(0, 1).paragraphs[0]
    paragraph.text = "가가"
    doc.shapes.add_rectangle(3000, 1000, paragraph=paragraph, treat_as_char=True)
    paragraph.add_run("가")
    _saved_lines(paragraph.element, (0,), (1000,), width=18000)

    layout = estimate_layout(doc)
    assert layout.estimate == estimate_pages(doc)
    placed, = layout.objects
    row, = layout.tables[0].rows
    cell = row.cells[1]
    line, = cell.lines
    assert (line.height, line.source) == (1000, "cache")
    assert (placed.page, placed.unavailable) == (row.page, ())
    assert placed.top == row.top + cell.top + line.top  # the line as tall as the object
    pen = placed.x - (layout.pages[0].body[0] + row.x + cell.x + line.x)
    first = _object_among("가가", "가", "LEFT").objects[0].x - layout.pages[0].body[0]
    assert pen == first  # past the two characters before it, measured as in the body
    # a hanging indent: the saved first line has the cell's whole room (in whole layout units), the layout's too
    shape = next(item for item in doc.parts.headers[0].element.iter(f"{HH}paraPr")
                 if item.get("id") == paragraph.element.get("paraPrIDRef"))
    for intent in shape.iter("{http://www.hancom.co.kr/hwpml/2011/core}intent"):
        intent.set("value", "-2000")
    inner = cell.width - 2 * line.x
    _saved_lines(paragraph.element, (0,), (1000,), width=inner - inner % 4)
    indented = estimate_layout(doc)
    assert indented.estimate == estimate_pages(doc)
    assert (indented.objects[0].x, indented.objects[0].unavailable) == (placed.x, ())


def test_members_of_a_group_stand_where_the_group_holds_them():
    from hwpx.oxml import ContainerMember

    doc = HwpxDocument.new()
    doc.shapes.add_container([ContainerMember.rect(0, 0, 5000, 3000), ContainerMember.ellipse(6000, 1000, 4000, 4000)],
                             paragraph=doc.add_paragraph(""))
    layout = estimate_layout(doc)
    assert layout.estimate == estimate_pages(doc)
    group, first, second = layout.objects
    assert group.kind == "container" and None not in (group.x, group.top) and group.unavailable == ()
    assert (first.page, first.x - group.x, first.top - group.top, first.width, first.height) == (0, 0, 0, 5000, 3000)
    assert (second.x - group.x, second.top - group.top, second.width, second.height) == (6000, 1000, 4000, 4000)
    assert first.unavailable == second.unavailable == ()


def test_objects_held_by_a_cell_or_a_text_box_stand_on_its_page():
    doc = HwpxDocument.new()
    body = estimate_layout(doc).pages[0].body[3]
    for _ in range(body // 1600 + 3):
        doc.add_paragraph("둘째 쪽으로 미는 문단")
    table = doc.add_paragraph("").add_table(1, 1)
    doc.shapes.add_rectangle(3000, 2000, paragraph=table.cell(0, 0).paragraphs[0], treat_as_char=True)
    box = doc.shapes.add_rectangle(20000, 9000, paragraph=doc.add_paragraph(""), treat_as_char=True)
    box.set_draw_text("글상자에 적은 글")
    doc.shapes.add_rectangle(2000, 1000, paragraph=next(iter(box.iter_paragraphs())).paragraph, treat_as_char=True)

    layout = estimate_layout(doc)
    assert layout.estimate == estimate_pages(doc)
    in_cell, holder, in_box = layout.objects
    assert (in_cell.page, in_cell.x, in_cell.top) == (1, None, None)
    assert in_cell.unavailable == ("object set as a character: its line has no horizontal origin or width",)
    assert holder.page == 1 and holder.top is not None  # its line holding an object keeps no text:
    assert holder.unavailable == ("a text box holding a table or a drawing: what it holds besides its text is not placed",)
    assert len(holder.lines) == 1 and holder.lines[0].text is None
    assert (in_box.page, in_box.top) == (1, None)
    assert in_box.unavailable == ("an object in a text box: its place in the box is not laid out",)
    assert all((item.width, item.height) != (None, None) for item in layout.objects)


def test_a_footer_hidden_on_a_page_is_not_given_there():
    doc = HwpxDocument.new()
    doc.page.set_footer(text="꼬리말에 적은 글")
    body = estimate_layout(doc).pages[0].body[3]
    for _ in range(2 * (body // 1600) + 3):
        doc.add_paragraph("세 쪽을 채우는 문단")

    def footer_pages():
        layout = estimate_layout(doc)
        assert layout.estimate == estimate_pages(doc) and layout.estimate.pages == 3
        footers = [area for area in layout.areas if area.kind == "footer"]
        for area in footers:
            body_box = layout.pages[area.page].body
            assert (area.x, area.top, area.width) == (body_box[0], body_box[1] + body_box[3], body_box[2])
            line, = area.lines
            assert area.unavailable == () and (line.text, line.source, line.height) == ("꼬리말에 적은 글", "engine", 1000)
            assert line.top + line.height == area.top + area.height  # set at the foot of its room, as its text says
            assert tuple(vars(line.position).values()) == (area.page, 0, line.top - body_box[1])
        return [area.page for area in footers]

    assert footer_pages() == [0, 1, 2]
    hiding = etree.SubElement(etree.SubElement(doc.sections[0].element.findall(f"{HP}p")[-1].find(f"{HP}run"),
                                               f"{HP}ctrl"), f"{HP}pageHiding")
    hiding.attrib.update({"hideHeader": "0", "hideFooter": "1", "hideMasterPage": "0", "hideBorder": "0",
                          "hideFill": "0", "hidePageNum": "0"})
    assert footer_pages() == [0, 1]  # the last paragraph hides it on its page
    next(doc.sections[0].element.iter(f"{HP}footer")).set("applyPageType", "ODD")
    odd, = [area for area in estimate_layout(doc).areas if area.kind == "footer"]
    assert odd.page is None and odd.unavailable == (
        "footer for odd or even pages: the layout does not count page numbers (hp:startNum, hp:newNum)",)


def test_header_lines_stand_in_its_room_as_its_text_sets_them():
    doc = HwpxDocument.new()
    doc.page.set_header(text="머리말에 적은 글")
    doc.add_paragraph("본문")
    sub_list = next(doc.sections[0].element.iter(f"{HP}header")).find(f"{HP}subList")

    def header():
        layout = estimate_layout(doc)
        assert layout.estimate == estimate_pages(doc)
        area, = [area for area in layout.areas if area.kind == "header"]
        return area

    area = header()
    line, = area.lines
    assert (area.top + area.height, area.unavailable) == (layout_body_top(doc), ())
    assert (line.top, line.text, line.x, line.width) == (area.top, "머리말에 적은 글", 0, area.width)  # at its top
    sub_list.set("vertAlign", "CENTER")
    assert header().lines[0].top == area.top + (area.height - 1000) // 2
    for _ in range(6):
        etree.SubElement(sub_list, f"{HP}p", attrib=dict(sub_list.find(f"{HP}p").attrib))
        sub_list[-1].append(etree.fromstring(etree.tostring(sub_list.find(f"{HP}p").find(f"{HP}run"))))
    taller = header()
    assert taller.lines == () and taller.unavailable == (
        "header text taller than its room: where Hancom sets it is not laid out",)


def layout_body_top(doc):
    return estimate_layout(doc).pages[0].body[1]


def test_text_box_lines_stand_in_the_box_as_its_text_sets_them():
    doc = HwpxDocument.new()
    box = doc.shapes.add_rectangle(20000, 9000, paragraph=doc.add_paragraph(""), treat_as_char=True)
    box.set_draw_text("글상자에 적은 글")
    layout = estimate_layout(doc)
    assert layout.estimate == estimate_pages(doc)
    placed, = layout.objects
    line, = placed.lines
    margin = 283  # the box's text margins as written
    assert placed.unavailable == () and (line.text, line.source, line.height) == ("글상자에 적은 글", "engine", 1000)
    assert (line.x, line.width) == (margin, 20000 - 2 * margin)
    assert line.top == margin + (9000 - 2 * margin - 1000) // 2  # centred, as its text says
