"""The experimental placement API gives each tab of a line where the text after it starts."""

from hwpx import HwpxDocument
from hwpx.experimental import TabPlacement, estimate_layout, estimate_pages
from tests.test_layout_placement import HH, _saved_lines

#: The paragraph's own stops (mm) and the fills Hancom draws across them.
_STOPS = [{"pos_mm": 20, "type": "RIGHT", "leader": "DOT"}, {"pos_mm": 50, "type": "CENTER", "leader": "DASH"},
          {"pos_mm": 80, "type": "DECIMAL"}, {"pos_mm": 100, "type": "LEFT", "leader": "SOLID"}]


def _mm(value: float) -> int:
    return round(value * 7200 / 25.4)


def _layout(doc):
    layout = estimate_layout(doc)
    assert layout.estimate == estimate_pages(doc)  # tracing the tabs leaves the estimate alone
    return layout


def _width(text: str) -> float:
    """How wide the layout lays *text* out in a new document's body, measured by the tab before it."""

    doc = HwpxDocument.new()
    doc.add_paragraph(f"\t{text}")
    doc.styles.apply_paragraph_format(paragraph=doc.paragraphs[-1], tab_stops=[{"pos_mm": 100, "type": "RIGHT"}])
    tab, = _layout(doc).paragraphs[-1].lines[0].tabs
    return _mm(100) - tab.x


def _align(doc, paragraph, horizontal):
    shape = next(item for item in doc.parts.headers[0].element.iter(f"{HH}paraPr")
                 if item.get("id") == paragraph.element.get("paraPrIDRef"))
    shape.find(f"{HH}align").set("horizontal", horizontal)


def test_a_tab_reaches_the_paragraph_stop_its_text_takes():
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("가\t나나\t다다\t1.25\t라")
    doc.styles.apply_paragraph_format(paragraph=paragraph, tab_stops=_STOPS)
    line, = _layout(doc).paragraphs[-1].lines
    assert len(line.tabs) == 4 and all(tab.unavailable == () for tab in line.tabs)
    right, centre, decimal, left = line.tabs
    assert [tab.stop for tab in line.tabs] == ["RIGHT", "CENTER", "DECIMAL", "LEFT"]
    assert [tab.leader for tab in line.tabs] == ["DOT", "DASH", "NONE", "SOLID"]
    two = _width("나나")
    assert right.x == _mm(20) - two  # the text after it ends at the stop
    assert centre.x == _mm(50) - two / 2  # centred on it
    assert decimal.x == _mm(80) - _width("1")  # its full stop at it
    assert left.x == _mm(100)  # starts there
    assert right.start == _width("가") and right.start < right.x  # the tab starts where the text before it ends
    assert centre.start == right.x + two and left.start > decimal.x


def test_a_tab_without_a_stop_of_its_paragraph_reaches_the_next_default_stop():
    doc = HwpxDocument.new()
    doc.add_paragraph("가가\t나\t\t다")
    line, = _layout(doc).paragraphs[-1].lines
    first, second, third = line.tabs
    assert {tab.stop for tab in line.tabs} == {"DEFAULT"} and {tab.leader for tab in line.tabs} == {"NONE"}
    step = first.x
    assert step > _width("가가") and (second.x, third.x) == (2 * step, 3 * step)
    assert third.start == second.x  # the second tab ends where the third starts


def test_an_automatic_stop_at_the_line_end_takes_the_text_to_it():
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("가\t나")
    doc.styles.apply_paragraph_format(paragraph=paragraph, auto_tab_right=True)
    line, = _layout(doc).paragraphs[-1].lines
    tab, = line.tabs
    assert (tab.stop, tab.leader, tab.x) == ("RIGHT", "NONE", line.x + line.width - _width("나"))


def test_tabs_move_as_the_alignment_moves_the_line():
    def tabs(horizontal):
        doc = HwpxDocument.new()
        paragraph = doc.add_paragraph("가\t나")
        _align(doc, paragraph, horizontal)
        line, = _layout(doc).paragraphs[-1].lines
        return line.tabs[0], line.width

    left, room = tabs("LEFT")
    used = left.x + _width("나")
    assert tabs("JUSTIFY")[0] == left  # its paragraph's last line: set as if left
    assert tabs("CENTER")[0].x == left.x + (room - used) / 2
    right = tabs("RIGHT")[0]
    assert (right.x, right.start) == (left.x + room - used, left.start + room - used)


def test_a_tab_on_a_line_hancom_spreads_says_why_it_has_no_place():
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("가\t" + "나" * 60)
    _align(doc, paragraph, "JUSTIFY")
    first, *rest = _layout(doc).paragraphs[-1].lines
    tab, = first.tabs
    assert (tab.x, tab.start, tab.stop) == (None, None, None) and tab.unavailable == (
        "tab on a line spread across its room (justified but the last, or distributed): where Hancom adds the room "
        "is not laid out",)
    assert rest and all(line.tabs == () for line in rest)
    _align(doc, paragraph, "DISTRIBUTE")
    assert _layout(doc).paragraphs[-1].lines[1].tabs == ()  # a line without a tab has none


def test_a_tab_on_a_saved_line_reaches_where_the_layout_measures_it():
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("가가\t나")
    engine, = _layout(doc).paragraphs[-1].lines
    _saved_lines(paragraph.element, width=engine.width)
    saved, = _layout(doc).paragraphs[-1].lines
    assert saved.source == "cache" and engine.source == "engine" and saved.tabs == engine.tabs


def test_cell_text_box_and_header_lines_give_their_tabs_from_their_own_edge():
    doc = HwpxDocument.new()
    doc.page.set_header(text="머리\t말")
    doc.add_paragraph("칸\t글")
    table = doc.add_paragraph("").add_table(1, 2)
    table.cell(0, 1).paragraphs[0].text = "칸\t글"
    box = doc.shapes.add_rectangle(20000, 6000, paragraph=doc.add_paragraph(""), treat_as_char=True)
    box.set_draw_text("칸\t글")
    layout = _layout(doc)
    body, = [paragraph.lines[0] for paragraph in layout.paragraphs if paragraph.lines[0].text == "칸\t글"]
    step = body.tabs[0].x
    cell_line, = layout.tables[0].rows[0].cells[1].lines
    box_line, = layout.objects[0].lines
    header, = [area for area in layout.areas if area.kind == "header"]
    for line in (cell_line, box_line, header.lines[0]):
        tab, = line.tabs
        assert tab.unavailable == () and tab.stop == "DEFAULT"
        assert tab.x == line.x + step  # the default stops counted from the edge the line's room starts at
    assert cell_line.x > 0 and box_line.x > 0 and header.lines[0].x == 0


def test_every_tab_of_a_line_has_its_place_or_says_why():
    doc = HwpxDocument.new()
    for text in ("가\t나", "\t", "가\t\t나\t", "\t가" * 20):
        doc.add_paragraph(text)
    layout = _layout(doc)
    for paragraph in layout.paragraphs:
        for line in paragraph.lines:
            assert len(line.tabs) == (line.text or "").count("\t")
            for tab in line.tabs:
                assert isinstance(tab, TabPlacement)
                assert (tab.x is None) == bool(tab.unavailable)


def test_a_line_without_text_or_tabs_keeps_none():
    doc = HwpxDocument.new()
    doc.add_paragraph("가나다")
    layout = _layout(doc)
    assert all(line.tabs == () for paragraph in layout.paragraphs for line in paragraph.lines)
