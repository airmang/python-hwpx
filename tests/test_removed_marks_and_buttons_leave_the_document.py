"""A bookmark or a form control taken out of the document changes itself only (exec7/rv3).

#800 set the rule for objects taken out of the document: an edit of the object's own text or value is
allowed and writes nothing on the document's side. Two paths still wrote there: renaming a removed
bookmark re-pointed the document's hyperlinks at a bookmark that is not in it, and checking a radio
button whose paragraph was removed unchecked the buttons of its group that are.
"""

from __future__ import annotations

from hwpx import HwpxDocument


def _opened(document: HwpxDocument) -> HwpxDocument:
    return HwpxDocument.open(document.to_bytes())


def test_renaming_a_removed_bookmark_leaves_the_links_and_the_bytes() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("keep")
    paragraph.add_hyperlink("#old", "jump")
    paragraph.add_bookmark("old")
    document = _opened(document)
    mark = document.refs.bookmarks[0]
    mark.remove()
    before = document.to_bytes()

    renamed = mark.rename("new")

    assert renamed.name == "new"  # its own name
    assert document.to_bytes() == before
    assert _opened(document).paragraphs[-1].hyperlinks[0].url == "#old"


def test_checking_a_removed_radio_button_leaves_its_group_and_the_bytes() -> None:
    document = HwpxDocument.new()
    document.fields.add_radio_button("Live", group="g", checked=True)
    removed_paragraph = document.add_paragraph("remove")
    document.fields.add_radio_button("Gone", group="g", paragraph=removed_paragraph)
    document = _opened(document)
    gone = next(button for button in document.fields.radio_buttons if button.caption == "Gone")
    next(paragraph for paragraph in document.paragraphs if paragraph.text.startswith("remove")).remove()
    before = document.to_bytes()

    gone.checked = True

    assert gone.checked is True  # its own value
    assert document.to_bytes() == before
    assert [button.checked for button in _opened(document).fields.radio_buttons] == [True]


def test_changing_a_removed_check_box_or_edit_box_leaves_the_bytes() -> None:
    document = HwpxDocument.new()
    removed_paragraph = document.add_paragraph("remove")
    document.fields.add_check_box("확인", paragraph=removed_paragraph)
    document.fields.add_edit_box("old", paragraph=removed_paragraph)
    document.add_paragraph("keep")
    document = _opened(document)
    check, edit = document.fields.check_boxes[0], document.fields.edit_boxes[0]
    next(paragraph for paragraph in document.paragraphs if paragraph.text.startswith("remove")).remove()
    before = document.to_bytes()

    check.checked = True
    edit.text = "new"

    assert (check.checked, edit.text) == (True, "new")
    assert document.to_bytes() == before


def test_removing_a_taken_out_copy_of_a_field_bookmark_leaves_the_one_in_the_document() -> None:
    """A copy keeps the id of the field it was copied from. Removing the copy's bookmark after the copy
    left the document looked for the end by that id in the document's sections and took the end of the
    bookmark that is there."""

    from lxml.etree import SubElement

    from hwpx.oxml.namespaces import HP

    document = HwpxDocument.new()
    begin, end = (document.add_paragraph(text) for text in ("begin", "end"))
    for paragraph, tag, attributes in ((begin, "fieldBegin", {"id": "13", "type": "BOOKMARK", "name": "span"}),
                                       (end, "fieldEnd", {"beginIDRef": "13"})):
        SubElement(SubElement(paragraph.runs[0].element, HP + "ctrl"), HP + tag, attributes)
    copy = begin.copy_to(document.add_section().paragraphs[0])
    stale = copy.bookmarks[0]
    copy.remove()
    before = document.to_bytes()

    stale.remove()

    assert document.to_bytes() == before
    saved = _opened(document)
    assert [bookmark.name for bookmark in saved.refs.bookmarks] == ["span"]
    assert len(saved.sections[0].element.findall(".//{*}fieldEnd[@beginIDRef='13']")) == 1


def test_a_bookmark_taken_out_of_a_plain_elementtree_section_renames_itself_only() -> None:
    import xml.etree.ElementTree as ET

    from hwpx.model import Section
    from hwpx.oxml.namespaces import HP, HS

    root = ET.Element(HS + "sec")
    paragraph = ET.fromstring(
        f'<p xmlns="{HP[1:-1]}"><run><ctrl><bookmark name="a"/></ctrl>'
        '<ctrl><fieldBegin type="HYPERLINK" name="#a"/></ctrl></run></p>'
    )
    root.append(paragraph)
    section = Section("section0.xml", root)
    view = section.paragraphs[0]
    mark = view.bookmarks[0]
    paragraph.find(".//{*}ctrl").remove(mark.element)
    section.reset_dirty()

    mark.rename("gone")

    assert (view.hyperlinks[0].url, section.dirty) == ("#a", False)
