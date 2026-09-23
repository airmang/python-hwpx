from __future__ import annotations

import io
import zipfile
from pathlib import Path

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError
from hwpx.tools.package_validator import validate_editor_open_safety

import pytest

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
FIXTURES = Path(__file__).parent / "fixtures"
GOLD_HANCOM = FIXTURES / "hwpxlib_corpus" / "error__20230426__HwpxTest1.hwpx"

CHART_HEAD = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>'
    '<c:chartSpace xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart">'
    "<c:chart><c:plotArea><c:layout/>"
)
PIE_CHARTML = (
    CHART_HEAD
    + '<c:pieChart><c:varyColors val="1"/><c:ser><c:idx val="0"/><c:order val="0"/>'
    '<c:cat><c:strRef><c:f>Sheet1!$A$2:$A$3</c:f><c:strCache><c:ptCount val="2"/>'
    '<c:pt idx="0"><c:v>A</c:v></c:pt><c:pt idx="1"><c:v>B</c:v></c:pt></c:strCache></c:strRef></c:cat>'
    '<c:val><c:numRef><c:f>Sheet1!$B$2:$B$3</c:f><c:numCache><c:formatCode>General</c:formatCode>'
    '<c:ptCount val="2"/><c:pt idx="0"><c:v>60</c:v></c:pt><c:pt idx="1"><c:v>40</c:v></c:pt>'
    "</c:numCache></c:numRef></c:val></c:ser></c:pieChart>"
    "</c:plotArea></c:chart></c:chartSpace>"
)


SERIES = (
    '<c:ser><c:idx val="0"/><c:order val="0"/>'
    '<c:cat><c:strRef><c:f>Sheet1!$A$2:$A$3</c:f><c:strCache><c:ptCount val="2"/>'
    '<c:pt idx="0"><c:v>A</c:v></c:pt><c:pt idx="1"><c:v>B</c:v></c:pt></c:strCache></c:strRef></c:cat>'
    '<c:val><c:numRef><c:f>Sheet1!$B$2:$B$3</c:f><c:numCache><c:formatCode>General</c:formatCode>'
    '<c:ptCount val="2"/><c:pt idx="0"><c:v>60</c:v></c:pt><c:pt idx="1"><c:v>40</c:v></c:pt>'
    "</c:numCache></c:numRef></c:val></c:ser>"
)
AX_IDS = '<c:axId val="111"/><c:axId val="222"/>'
AXES = (
    '<c:catAx><c:axId val="111"/><c:scaling><c:orientation val="minMax"/></c:scaling>'
    '<c:delete val="0"/><c:axPos val="b"/><c:crossAx val="222"/></c:catAx>'
    '<c:valAx><c:axId val="222"/><c:scaling><c:orientation val="minMax"/></c:scaling>'
    '<c:delete val="0"/><c:axPos val="l"/><c:crossAx val="111"/></c:valAx>'
)


def _line_chartml(ax_ids: str = "", axes: str = "") -> str:
    return _chartml("lineChart", '<c:grouping val="standard"/>', ax_ids, axes)


def _chartml(kind: str, head: str = "", ax_ids: str = "", axes: str = "") -> str:
    return (
        CHART_HEAD + f"<c:{kind}>" + head + SERIES + ax_ids + f"</c:{kind}>"
        + axes + "</c:plotArea></c:chart></c:chartSpace>"
    )


AXIS_KINDS = {
    "barChart": '<c:barDir val="col"/><c:grouping val="clustered"/>',
    "lineChart": '<c:grouping val="standard"/>',
    "areaChart": '<c:grouping val="standard"/>',
    "scatterChart": '<c:scatterStyle val="lineMarker"/>',
    "radarChart": '<c:radarStyle val="marker"/>',
    "bubbleChart": "",
}


def _roundtrip(doc: HwpxDocument) -> tuple[HwpxDocument, bytes]:
    buffer = io.BytesIO()
    doc.save_to_stream(buffer)
    payload = buffer.getvalue()
    return HwpxDocument.open(io.BytesIO(payload)), payload


def _anchors(doc: HwpxDocument):
    found = []
    for section in doc.sections:
        found.extend(section.element.iter(f"{HP}chart"))
    return found


class TestGoldContractShape:
    """The emitted anchor must match the real-Hancom chart contract
    (specs/055-chart-authoring/evidence/p0/chart-contract.md)."""

    def test_anchor_attributes_and_part(self) -> None:
        doc = HwpxDocument.new()
        doc.add_chart(PIE_CHARTML)
        (anchor,) = _anchors(doc)
        assert anchor.get("chartIDRef") == "Chart/chart1.xml"
        assert anchor.get("numberingType") == "PICTURE"
        assert anchor.get("textWrap") == "SQUARE"
        assert anchor.get("id")
        local_names = [child.tag.rsplit("}", 1)[-1] for child in anchor]
        assert local_names == ["sz", "pos", "outMargin"]
        assert anchor.find(f"{HP}pos").get("treatAsChar") == "0"

    def test_part_written_verbatim_and_unregistered(self) -> None:
        doc = HwpxDocument.new()
        doc.add_chart(PIE_CHARTML)
        _reopened, payload = _roundtrip(doc)
        with zipfile.ZipFile(io.BytesIO(payload)) as package:
            assert package.read("Chart/chart1.xml") == PIE_CHARTML.encode("utf-8")
            hpf = package.read("Contents/content.hpf").decode("utf-8")
        # Real Hancom registers chart parts in no manifest (gold contract).
        assert "chart1" not in hpf

    def test_part_paths_allocate_sequentially(self) -> None:
        doc = HwpxDocument.new()
        doc.add_chart(PIE_CHARTML)
        doc.add_chart(PIE_CHARTML)
        refs = [anchor.get("chartIDRef") for anchor in _anchors(doc)]
        assert refs == ["Chart/chart1.xml", "Chart/chart2.xml"]

    def test_inline_placement(self) -> None:
        doc = HwpxDocument.new()
        doc.add_chart(PIE_CHARTML, treat_as_char=True, size=(20000, 12000))
        (anchor,) = _anchors(doc)
        assert anchor.get("textWrap") == "TOP_AND_BOTTOM"
        pos = anchor.find(f"{HP}pos")
        assert pos.get("treatAsChar") == "1"
        sz = anchor.find(f"{HP}sz")
        assert (sz.get("width"), sz.get("height")) == ("20000", "12000")


class TestSelfRoundtrip:
    def test_reopen_keeps_anchor_and_part_bytes(self) -> None:
        doc = HwpxDocument.new()
        doc.add_chart(PIE_CHARTML)
        reopened, _payload = _roundtrip(doc)
        (anchor,) = _anchors(reopened)
        assert anchor.get("chartIDRef") == "Chart/chart1.xml"
        # patch-grade resave must keep the chart part byte-identical
        _again, payload2 = _roundtrip(reopened)
        with zipfile.ZipFile(io.BytesIO(payload2)) as package:
            assert package.read("Chart/chart1.xml") == PIE_CHARTML.encode("utf-8")

    def test_chart_in_table_cell(self) -> None:
        doc = HwpxDocument.new()
        table = doc.add_table(2, 2)
        cell_paragraph = table.cell(0, 0).paragraphs[0]
        doc.add_chart(PIE_CHARTML, paragraph=cell_paragraph)
        reopened, _payload = _roundtrip(doc)
        (anchor,) = _anchors(reopened)
        ancestors = []
        parent = anchor.getparent()
        while parent is not None:
            ancestors.append(parent.tag.rsplit("}", 1)[-1])
            parent = parent.getparent()
        assert "tc" in ancestors

    def test_byte_preservation_of_unrelated_parts(self) -> None:
        doc = HwpxDocument.open(GOLD_HANCOM)
        with zipfile.ZipFile(GOLD_HANCOM) as package:
            before = {name: package.read(name) for name in package.namelist()}
        doc.add_chart(PIE_CHARTML)
        buffer = io.BytesIO()
        doc.save_to_stream(buffer)
        with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as package:
            after = {name: package.read(name) for name in package.namelist()}
        changed = {
            name for name in before if name in after and before[name] != after[name]
        }
        assert changed <= {"Contents/section0.xml"}
        # The gold file already carries Chart/chart1.xml — ours must not clobber it.
        assert after["Chart/chart1.xml"] == before["Chart/chart1.xml"]
        assert _anchors(HwpxDocument.open(io.BytesIO(buffer.getvalue())))[-1].get(
            "chartIDRef"
        ) == "Chart/chart2.xml"

    def test_open_safety(self) -> None:
        doc = HwpxDocument.new()
        doc.add_chart(PIE_CHARTML)
        buffer = io.BytesIO()
        doc.save_to_stream(buffer)
        report = validate_editor_open_safety(buffer.getvalue())
        assert report.ok, report

    def test_gold_fixture_anchor_still_reads(self) -> None:
        doc = HwpxDocument.open(GOLD_HANCOM)
        anchors = _anchors(doc)
        assert anchors
        assert anchors[0].get("chartIDRef") == "Chart/chart1.xml"


class TestValidation:
    def test_empty_chartml_rejected(self) -> None:
        doc = HwpxDocument.new()
        with pytest.raises(ValueError):
            doc.add_chart("   ")

    def test_malformed_xml_rejected_before_any_write(self) -> None:
        doc = HwpxDocument.new()
        with pytest.raises(ValueError):
            doc.add_chart("<c:chartSpace")
        assert _anchors(doc) == []
        buffer = io.BytesIO()
        doc.save_to_stream(buffer)
        with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as package:
            assert not [n for n in package.namelist() if n.startswith("Chart/")]

    def test_wrong_root_rejected(self) -> None:
        doc = HwpxDocument.new()
        with pytest.raises(ValueError, match="chartSpace"):
            doc.add_chart("<not-a-chart/>")

    # An axis-less line chart crashes Hancom's page render and every save;
    # the same chart with c:catAx/c:valAx renders.
    def test_line_chart_without_axes_rejected_before_any_write(self) -> None:
        doc = HwpxDocument.new()
        with pytest.raises(HwpxValueError) as caught:
            doc.add_chart(_line_chartml())
        assert caught.value.code == "shape-chart-axes-missing"
        assert caught.value.suggestion
        assert _anchors(doc) == []
        buffer = io.BytesIO()
        doc.save_to_stream(buffer)
        with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as package:
            assert not [n for n in package.namelist() if n.startswith("Chart/")]

    def test_line_chart_naming_undefined_axes_rejected(self) -> None:
        doc = HwpxDocument.new()
        with pytest.raises(HwpxValueError) as caught:
            doc.add_chart(_line_chartml(ax_ids=AX_IDS))
        assert caught.value.code == "shape-chart-axes-missing"
        assert caught.value.context["axIds"] == ["111", "222"]
        assert caught.value.context["chartKind"] == "lineChart"

    def test_line_chart_with_axes_accepted(self) -> None:
        doc = HwpxDocument.new()
        doc.add_chart(_line_chartml(ax_ids=AX_IDS, axes=AXES))
        assert len(_anchors(doc)) == 1

    # Without axes Hancom draws a bar chart with no bars and crashes on the
    # other kinds that need axes.
    @pytest.mark.parametrize("kind", sorted(AXIS_KINDS))
    def test_chart_kinds_that_need_axes_are_rejected_without_them(self, kind: str) -> None:
        doc = HwpxDocument.new()
        with pytest.raises(HwpxValueError) as caught:
            doc.add_chart(_chartml(kind, AXIS_KINDS[kind]))
        assert caught.value.code == "shape-chart-axes-missing"
        assert caught.value.context["chartKind"] == kind
        assert _anchors(doc) == []

    def test_bar_chart_with_axes_accepted(self) -> None:
        doc = HwpxDocument.new()
        doc.add_chart(_chartml("barChart", AXIS_KINDS["barChart"], AX_IDS, AXES))
        assert len(_anchors(doc)) == 1

    # A 3-D chart without a series axis names it with an axis id of 0.
    def test_a_zero_axis_id_stands_for_no_axis(self) -> None:
        doc = HwpxDocument.new()
        doc.add_chart(_chartml("bar3DChart", AXIS_KINDS["barChart"], AX_IDS + '<c:axId val="0"/>', AXES))
        assert len(_anchors(doc)) == 1

    def test_a_zero_axis_id_does_not_count_as_one_of_the_two_axes(self) -> None:
        doc = HwpxDocument.new()
        with pytest.raises(HwpxValueError) as caught:
            doc.add_chart(_chartml("barChart", AXIS_KINDS["barChart"], '<c:axId val="111"/><c:axId val="0"/>', AXES))
        assert caught.value.code == "shape-chart-axes-missing"

    @pytest.mark.parametrize("kind", ["pieChart", "doughnutChart"])
    def test_charts_without_axes_by_design_are_accepted(self, kind: str) -> None:
        doc = HwpxDocument.new()
        doc.add_chart(_chartml(kind, '<c:varyColors val="1"/>'))
        assert len(_anchors(doc)) == 1
