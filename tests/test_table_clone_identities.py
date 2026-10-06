"""Content cloning must not silently duplicate native identities or local references."""

import io
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from hwpx import HwpxDocument
from hwpx.table_patch import apply_table_ops

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


@pytest.mark.parametrize("op,reference", [("insert_column_by_clone", "ref_col"), ("insert_row_by_clone", "ref_row")])
@pytest.mark.parametrize("content", [
    '<hp:rect id="10" instid="10"/>',
    '<hp:pic id="11"/>',
    '<hp:equation id="12"/>',
    '<hp:fieldBegin id="13" fieldid="13"/>',
    '<hp:fieldEnd beginIDRef="13" fieldid="13"/>',
    '<hp:bookmark name="target"/>',
    '<hp:subList linkListIDRef="42"/>',
    '<hp:connectLine subjectIDRef="42"/>',
])
def test_local_identities_and_references_are_refused_without_mutation(op: str, reference: str, content: str) -> None:
    document = HwpxDocument.new()
    document.add_table(rows=2, cols=2)
    source = document.to_bytes()
    # Inject into the serialized input so the clone guard is tested independently of
    # the object-authoring/save checks (some examples are deliberately incomplete).
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(source)) as archive, zipfile.ZipFile(output, "w") as target:
        for info in archive.infolist():
            data = archive.read(info.filename)
            if info.filename == "Contents/section0.xml":
                root = etree.fromstring(data)
                run = next(root.iter(HP + "tbl")).find(f"{HP}tr/{HP}tc/{HP}subList/{HP}p/{HP}run")
                run.append(etree.fromstring(f'<wrapper xmlns:hp="{HP[1:-1]}">{content}</wrapper>')[0])
                data = etree.tostring(root)
            target.writestr(info, data)
    source = output.getvalue()

    result = apply_table_ops(source, [{"op": op, "table_index": 0, reference: 0, "count": 2}])

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
def test_hancom_saved_cell_picture_is_refused_for_content_cloning(op: str, reference: str) -> None:
    source = (Path(__file__).parent / "fixtures" / "hancom_saved" /
              "pages_cell_picture_as_character_alone.hwpx").read_bytes()
    result = apply_table_ops(source, [{"op": op, "table_index": 0, reference: 1 if reference == "ref_col" else 0}])

    assert not result.ok
    assert result.data == source
    assert "local identities or references" in str(result.skipped)
