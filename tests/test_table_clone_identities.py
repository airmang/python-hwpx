"""Content cloning numbers what it copies as Hancom numbers what it pastes, and refuses
what points into another part or definition."""

import io
import re
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.table_patch import TableStructureError, _clone_content, _fresh_ids, _number_clones, apply_table_ops

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HP_NS = HP[1:-1]
HANCOM_SAVED = Path(__file__).parent / "fixtures" / "hancom_saved"


@pytest.mark.parametrize("content", [
    "<hp:subList linkListIDRef = '42'/>",
    '<hp:subList linkListNextIDRef="42"/>',
    "<hp:chart chartIDRef = '3'/>",
    '<hp:header id="1" applyPageType="BOTH"/>',
    '<hp:footer id="1" applyPageType="BOTH"/>',
])
def test_content_pointing_into_another_part_or_definition_is_refused(content: str) -> None:
    fragment = '<hp:p id="1">' + content + '</hp:p>'
    with pytest.raises(TableStructureError, match="local identities or references"):
        _clone_content(fragment, _fresh_ids(fragment, None))


def _with_cell_content(content: str, *, rectangle: bool = False) -> bytes:
    """A new document whose first table's first cell run holds *content* (injected into the
    serialized input, so the clone is tested apart from the object-authoring checks), after a
    rectangle drawn in that cell when *rectangle*."""
    document = HwpxDocument.new()
    table = document.add_table(rows=2, cols=2)
    if rectangle:
        table.cell(0, 0).paragraphs[0].add_rectangle(width=2000, height=1000)
    source = document.to_bytes()
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(source)) as archive, zipfile.ZipFile(output, "w") as target:
        for info in archive.infolist():
            data = archive.read(info.filename)
            if info.filename == "Contents/section0.xml":
                root = etree.fromstring(data)
                run = next(root.iter(HP + "tbl")).find(f"{HP}tr/{HP}tc/{HP}subList/{HP}p/{HP}run")
                for child in etree.fromstring(f'<wrapper xmlns:hp="{HP_NS}">{content}</wrapper>'):
                    run.append(child)
                data = etree.tostring(root)
            target.writestr(info, data)
    return output.getvalue()


def _section(data: bytes) -> etree._Element:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return etree.fromstring(archive.read("Contents/section0.xml"))


def _first_column_cells(data: bytes, op: str) -> list[etree._Element]:
    table = next(_section(data).iter(HP + "tbl"))
    cells = [tc for tc in table.iter(HP + "tc")]
    return [tc for tc in cells if (tc.find(HP + "cellAddr").get("colAddr" if op == "insert_row_by_clone" else "rowAddr")
                                   == "0")]


_FIELDS = (
    '<hp:ctrl><hp:fieldBegin id="13" type="CLICK_HERE" name="성명" fieldid="627272811" zorder="-1"/></hp:ctrl>'
    '<hp:t>홍길동</hp:t>'
    '<hp:ctrl><hp:fieldEnd beginIDRef="13" fieldid="627272811"/></hp:ctrl>'
    '<hp:ctrl><hp:bookmark name="target"/></hp:ctrl>'
)


@pytest.mark.parametrize("op,reference", [("insert_column_by_clone", "ref_col"), ("insert_row_by_clone", "ref_row")])
def test_a_clone_numbers_its_objects_and_fields_as_hancom_pastes_them(op: str, reference: str) -> None:
    source = _with_cell_content(_FIELDS, rectangle=True)
    numbers_before = {node.get(name) for node in _section(source).iter() for name in ("id", "instid")} - {None, ""}
    rect_before = next(_section(source).iter(HP + "rect"))

    result = apply_table_ops(source, [{"op": op, "table_index": 0, reference: 0, "count": 2}])

    assert result.ok, result.skipped
    original, *copies = _first_column_cells(result.data, op)[:3]
    rect = original.find(f".//{HP}rect")
    assert [rect.get(name) for name in ("id", "instid", "zOrder")] == [rect_before.get(name) for name in
                                                                      ("id", "instid", "zOrder")]
    fresh = []
    for cell in copies:
        rect = cell.find(f".//{HP}rect")
        begin, end = cell.find(f".//{HP}fieldBegin"), cell.find(f".//{HP}fieldEnd")
        fresh += [rect.get("id"), rect.get("instid"), begin.get("id")]
        # Hancom's paste keeps a field's fieldid and name, its end following the new id, and a
        # bookmark's name.
        assert end.get("beginIDRef") == begin.get("id")
        assert (begin.get("fieldid"), begin.get("name"), begin.get("zorder")) == ("627272811", "성명", "-1")
        assert cell.find(f".//{HP}bookmark").get("name") == "target"
    assert len(set(fresh)) == len(fresh) and not set(fresh) & numbers_before
    # Above the document's own stacking order, as Hancom stacks a paste.
    assert sorted(int(cell.find(f".//{HP}rect").get("zOrder")) for cell in copies) == [1, 2]


def test_a_copied_connector_loses_its_ends_and_shapes_get_two_fresh_numbers() -> None:
    content = ('<hp:p id="1"><hp:run><hp:connectLine id="20" instid="21" zOrder="4">'
               '<hp:startPt subjectIDRef="10"/><hp:endPt subjectIDRef="10"/></hp:connectLine></hp:run></hp:p>')
    copied = _number_clones(_clone_content(content, _fresh_ids(content, None)), content)

    assert re.findall(r'subjectIDRef="(\d+)"', copied) == ["0", "0"]
    line = re.search(r"<hp:connectLine\b[^>]*>", copied).group(0)
    numbers = re.findall(r'\b(?:id|instid)="(\d+)"', line)
    assert len(set(numbers)) == 2 and not set(numbers) & {"1", "20", "21"}
    assert 'zOrder="5"' in line


def test_a_copied_group_numbers_the_group_and_keeps_its_shapes_ids() -> None:
    """Hancom saves the shapes of a group with zOrder 0 and ids of 0 or shared within the group;
    only the group and each shape's instid carry numbers, so a copy renumbers just those."""
    content = ('<hp:p id="1"><hp:run><hp:container id="40" zOrder="3" groupLevel="0" instid="41">'
               '<hp:rect id="0" zOrder="0" groupLevel="1" instid="42"/>'
               '<hp:rect id="2" zOrder="0" groupLevel="1" instid="43"/>'
               '<hp:rect id="2" zOrder="0" groupLevel="1" instid="44"/></hp:container></hp:run></hp:p>')
    copied = _number_clones(_clone_content(content, _fresh_ids(content, None)), content)

    group = re.search(r"<hp:container\b[^>]*>", copied).group(0)
    shapes = re.findall(r"<hp:rect\b[^>]*>", copied)
    assert 'zOrder="4"' in group and not set(re.findall(r'\b(?:id|instid)="(\d+)"', group)) & {"40", "41"}
    assert [re.search(r'\sid="(\d+)"', shape).group(1) for shape in shapes] == ["0", "2", "2"]
    assert all('zOrder="0"' in shape for shape in shapes)
    instids = [re.search(r'instid="(\d+)"', shape).group(1) for shape in shapes]
    assert len(set(instids)) == 3 and not set(instids) & {"0", "2", "42", "43", "44"}


_MEMO = (
    '<hp:ctrl><hp:fieldBegin id="30" type="MEMO" name="" editable="1" dirty="0" zorder="1" fieldid="623209829" metaTag="">'
    '<hp:parameters cnt="4" name=""><hp:stringParam name="Command">MEMO/65535/1/1955991296/31284124//\\;;</hp:stringParam>'
    '<hp:stringParam name="ID">memo1</hp:stringParam><hp:integerParam name="Number">1</hp:integerParam>'
    '<hp:stringParam name="MemoShapeIDRef">65535</hp:stringParam></hp:parameters>'
    '<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="TOP" linkListIDRef="0" linkListNextIDRef="0"'
    ' textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0"><hp:p id="0" paraPrIDRef="0" styleIDRef="0" pageBreak="0"'
    ' columnBreak="0" merged="0"><hp:run charPrIDRef="0"><hp:t>메모 글</hp:t></hp:run></hp:p></hp:subList>'
    '</hp:fieldBegin></hp:ctrl><hp:t>표시</hp:t><hp:ctrl><hp:fieldEnd beginIDRef="30" fieldid="623209829"/></hp:ctrl>'
)


def test_a_cloned_memo_takes_the_next_memo_number() -> None:
    """Hancom drops the range end of a memo numbered like another (memos_same_number), and
    gives a pasted memo the next number in its Number, zorder, ID and command."""
    source = _with_cell_content(_MEMO)

    result = apply_table_ops(source, [{"op": "insert_row_by_clone", "table_index": 0, "ref_row": 0, "count": 2}])

    assert result.ok, result.skipped
    memos = []
    for begin in _section(result.data).iter(HP + "fieldBegin"):
        params = {p.get("name"): p.text for p in begin.find(HP + "parameters")}
        memos.append((begin.get("zorder"), params["Number"], params["ID"], params["Command"].split("/")[2]))
        assert begin.find(f"{HP}subList//{HP}t").text == "메모 글"
    assert memos == [("1", "1", "memo1", "1"), ("2", "2", "memo2", "2"), ("3", "3", "memo3", "3")]
    ends = [end.get("beginIDRef") for end in _section(result.data).iter(HP + "fieldEnd")]
    assert ends == [begin.get("id") for begin in _section(result.data).iter(HP + "fieldBegin")]
    assert len(set(ends)) == 3


@pytest.mark.parametrize("content", [
    '<hp:subList linkListIDRef="42"/>',
    '<hp:chart chartIDRef="3"/>',
])
def test_a_refused_clone_leaves_the_document_as_it_was(content: str) -> None:
    source = _with_cell_content(content)

    result = apply_table_ops(source, [{"op": "insert_row_by_clone", "table_index": 0, "ref_row": 0, "count": 2}])

    assert not result.ok
    assert result.data == source
    assert "local identities or references" in str(result.skipped)


def test_blank_columns_keep_the_original_object_and_do_not_duplicate_it() -> None:
    document = HwpxDocument.new()
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).paragraphs[0].add_rectangle(width=2000, height=1000)
    source = document.to_bytes()
    result = apply_table_ops(source, [
        {"op": "insert_column_by_clone", "table_index": 0, "ref_col": 0, "count": 2, "blank": True},
    ])

    assert result.ok, result.skipped
    with zipfile.ZipFile(io.BytesIO(source)) as archive:
        original = next(etree.fromstring(archive.read("Contents/section0.xml")).iter(HP + "rect"))
    with zipfile.ZipFile(io.BytesIO(result.data)) as archive:
        rectangles = list(etree.fromstring(archive.read("Contents/section0.xml")).iter(HP + "rect"))
    assert len(rectangles) == 1
    assert etree.tostring(rectangles[0]) == etree.tostring(original)


@pytest.mark.parametrize("op,reference", [("insert_column_by_clone", "ref_col"), ("insert_row_by_clone", "ref_row")])
def test_hancom_saved_cell_picture_is_cloned_with_its_own_numbers(op: str, reference: str) -> None:
    source = (HANCOM_SAVED / "pages_cell_picture_as_character_alone.hwpx").read_bytes()
    result = apply_table_ops(source, [{"op": op, "table_index": 0, reference: 1 if reference == "ref_col" else 0}])

    assert result.ok, result.skipped
    pictures = list(_section(result.data).iter(HP + "pic"))
    before = list(_section(source).iter(HP + "pic"))
    assert len(pictures) == len(before) + 1
    numbers = [n for pic in pictures for n in (pic.get("id"), pic.get("instid"))]
    assert len(set(numbers)) == len(numbers) - sum(pic.get("id") == pic.get("instid") for pic in before)
    image = [pic.find(".//{http://www.hancom.co.kr/hwpml/2011/core}img").get("binaryItemIDRef") for pic in pictures]
    assert len(set(image)) == 1  # the copy shows the same image, as Hancom's paste does
    assert HwpxDocument.open(result.data).tables
