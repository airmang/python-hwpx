"""The experimental placement API follows the existing page estimator."""
from lxml import etree

from hwpx import HwpxDocument
from hwpx.experimental import estimate_layout, estimate_pages

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HH = "{http://www.hancom.co.kr/hwpml/2011/head}"


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
