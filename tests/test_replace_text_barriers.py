"""``doc.text.replace`` does not join text on the two sides of a tab or a line break.

Hancom reads a tab or a line break as a character of its own, so "사<tab/>과" is not "사과";
highlight marks inside the text still do not split a word.
"""

from __future__ import annotations

from hwpx.document import HwpxDocument
from hwpx.oxml.namespaces import HP


def test_a_tab_between_the_letters_is_not_a_match() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("탭사\t과 그리고 사과")

    count = document.text.replace("사과", "배")

    assert count == 1
    assert paragraph.text == "탭사\t과 그리고 배"


def test_a_line_break_between_the_letters_is_not_a_match() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("")
    text = paragraph.runs[0].element.find(f"{HP}t")
    text.text = "사"
    line_break = text.makeelement(f"{HP}lineBreak", {})
    line_break.tail = "과"
    text.append(line_break)

    assert document.text.replace("사과", "배") == 0
    assert text.text == "사" and line_break.tail == "과"


def test_a_highlighted_word_is_still_one_word() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("앞 사과 뒤")
    document.text.highlight(paragraph, "사과")

    count = document.text.replace("사과", "배")

    assert count == 1
    assert "배" in paragraph.text and "사과" not in paragraph.text


def test_limit_still_counts_across_the_stretches_of_a_run() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("사과\t사과\t사과")

    count = document.text.replace("사과", "배", limit=2)

    assert count == 2
    assert paragraph.text == "배\t배\t사과"


def test_replace_leaves_xml_comment_text_alone() -> None:
    """An XML comment inside ``hp:t`` is not text: its content is neither searched
    nor rewritten, and the text on both sides of it still matches as one stretch."""
    import io
    import warnings
    import zipfile

    from hwpx import HwpxDocument

    document = HwpxDocument.new()
    document.add_paragraph("사과 주스")
    source = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(document.to_bytes())) as zin, zipfile.ZipFile(source, "w") as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename == "Contents/section0.xml":
                data = data.replace("사과 주스".encode(), "사<!-- 사과 -->과 주스".encode(), 1)
                assert "<!-- 사과 -->".encode() in data
            zout.writestr(info, data)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        commented = HwpxDocument.open(source.getvalue())
    count = commented.text.replace("사과", "배", everywhere=True)
    comments = [node.text for node in commented.sections[0].element.iter() if not isinstance(node.tag, str)]
    assert comments == [" 사과 "]
    assert count == 1
    # the edited section saves; the comment is not content and is not written back
    with zipfile.ZipFile(io.BytesIO(commented.to_bytes())) as package:
        section = package.read("Contents/section0.xml").decode("utf-8")
    assert "<hp:t>배 주스</hp:t>" in section


def test_an_edited_section_with_xml_comments_saves() -> None:
    """Real documents carry XML comments inside table rows. Editing such a
    section used to fail to save (xml.etree cannot write lxml comment nodes)."""
    import io
    import warnings
    import zipfile

    from hwpx import HwpxDocument

    document = HwpxDocument.new()
    table = document.add_table(2, 2)
    table.set_cell_text(0, 0, "가")
    source = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(document.to_bytes())) as zin, zipfile.ZipFile(source, "w") as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename == "Contents/section0.xml":
                data = data.replace(b"<hp:tr>", b"<hp:tr><!-- row note --><?note row?>", 1)
            zout.writestr(info, data)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        commented = HwpxDocument.open(source.getvalue())
        commented.add_paragraph("추가")
        reopened = HwpxDocument.open(commented.to_bytes())
    assert "가" in reopened.text.plain() and "추가" in reopened.text.plain()
