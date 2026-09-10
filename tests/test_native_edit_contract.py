"""Native edit contracts anchored to externally authored inputs."""

from copy import deepcopy
from pathlib import Path
import zipfile
from lxml import etree
import pytest
from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError
from hwpx.form_fit import FitPolicy
from hwpx.form_fit.apply import fit_cell_text
from hwpx.form_fit.measure import resolve_slot_metrics

CORPUS = Path(__file__).parent / "fixtures/hwpxlib_corpus"
HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def fingerprint(node):
    return (
        node.tag,
        dict(node.attrib),
        node.text,
        node.tail,
        [fingerprint(c) for c in node],
    )


def test_floating_shape_preserves_other_fields_and_parts(tmp_path):
    source = CORPUS / "reader_writer__SimpleRectangle.hwpx"
    with HwpxDocument.open(source) as doc:
        shape = doc.paragraphs[0].shapes[0]
        expected = deepcopy(shape.element)
        expected.find(HP + "pos").set("horzOffset", "-100")
        expected.find(HP + "pos").set("vertOffset", "14000")
        shape.set_position(horizontal_offset=-100, vertical_offset=14000)
        assert fingerprint(shape.element) == fingerprint(expected)
        output = tmp_path / "position.hwpx"
        doc.save_to_path(output, mode="patch", fallback="error")
    with HwpxDocument.open(output) as doc:
        assert fingerprint(doc.paragraphs[0].shapes[0].element) == fingerprint(expected)
    with zipfile.ZipFile(source) as old, zipfile.ZipFile(output) as new:
        assert [n for n in old.namelist() if old.read(n) != new.read(n)] == [
            "Contents/section0.xml"
        ]


@pytest.mark.parametrize("bad", [True, 2.5, "200", 2**31, -(2**31) - 1])
def test_position_refuses_invalid_value_before_mutation(bad):
    with HwpxDocument.open(CORPUS / "reader_writer__SimpleRectangle.hwpx") as doc:
        shape = doc.paragraphs[0].shapes[0]
        before = etree.tostring(shape.element)
        with pytest.raises(HwpxValueError, match="integer"):
            shape.set_position(horizontal_offset=bad, vertical_offset=0)
        assert etree.tostring(shape.element) == before


@pytest.mark.parametrize("missing", [False, True])
def test_position_refuses_inline_or_missing_anchor(missing):
    with HwpxDocument.open(CORPUS / "reader_writer__SimpleRectangle.hwpx") as doc:
        shape = doc.paragraphs[0].shapes[0]
        position = shape.element.find(HP + "pos")
        if missing:
            shape.element.remove(position)
        else:
            position.set("treatAsChar", "1")
        before = etree.tostring(shape.element)
        with pytest.raises(HwpxValueError, match="floating"):
            shape.set_position(horizontal_offset=0, vertical_offset=0)
        assert etree.tostring(shape.element) == before


@pytest.mark.parametrize(
    "kind,old_text", [("header", "머리말 테스트"), ("footer", "꼬리말")]
)
def test_native_story_preserves_empty_paragraphs_without_new_mirror(
    kind, old_text, tmp_path
):
    with HwpxDocument.open(CORPUS / "reader_writer__HeaderFooter.hwpx") as doc:
        props = doc.sections[0].properties
        story = getattr(props, "get_" + kind)()
        assert story.text == old_text
        expected = deepcopy(doc.sections[0].element)
        for text in expected.iter(HP + "t"):
            if text.text == old_text:
                text.text = "검토 완료"
                paragraph = text.getparent().getparent()
                for child in list(paragraph):
                    if child.tag in {HP + "linesegarray", HP + "lineSegArray"}:
                        paragraph.remove(child)
        story.set_simple_text_preserving("검토 완료")
        assert not props.element.findall(HP + kind)
        assert fingerprint(doc.sections[0].element) == fingerprint(expected)
        output = tmp_path / f"{kind}.hwpx"
        doc.save_to_path(output, mode="patch", fallback="error")
    with HwpxDocument.open(output) as doc:
        assert getattr(doc.sections[0].properties, "get_" + kind)().text == "검토 완료"


def test_native_story_refuses_duplicates_and_rich_controls():
    with HwpxDocument.open(CORPUS / "reader_writer__HeaderFooter.hwpx") as doc:
        story = doc.sections[0].properties.headers[0]
        parent = story.element.getparent()
        duplicate = deepcopy(story.element)
        parent.append(duplicate)
        before = etree.tostring(doc.sections[0].element)
        with pytest.raises(HwpxValueError, match="ambiguous"):
            story.set_simple_text_preserving("금지")
        assert etree.tostring(doc.sections[0].element) == before
        parent.remove(duplicate)
        etree.SubElement(story.element.find(".//" + HP + "run"), HP + "ctrl")
        before = etree.tostring(doc.sections[0].element)
        with pytest.raises(HwpxValueError, match="rich"):
            story.set_simple_text_preserving("금지")
        assert etree.tostring(doc.sections[0].element) == before


def test_real_cell_inherits_table_margins_and_reports_height_risk():
    source = Path(__file__).parent / "fixtures/m2_corpus/gov_donation_report_form.hwpx"
    with HwpxDocument.open(source) as doc:
        cell = next(
            c
            for p in doc.sections[0].paragraphs
            for t in p.tables
            for row in t.rows
            for c in row.cells
            if not c.text.strip()
        )
        assert cell.element.get("hasMargin") == "0"
        slot = resolve_slot_metrics(cell, doc)
        assert slot.available_width == pytest.approx((3140 - 1020) * 0.93)
        assert (
            slot.available_height is None
        )  # inherited padding leaves less than one line
        assert slot.height_unavailable
        result = fit_cell_text(
            cell,
            "김민준",
            FitPolicy(mode="wrap_then_shrink", overflow="fail", min_font_pt=8),
            document=doc,
        )
        assert result.lines >= 2
        assert any("height" in warning for warning in result.warnings)


def test_explicit_cell_margin_overrides_table():
    with HwpxDocument.open(CORPUS / "reader_writer__SimpleTable.hwpx") as doc:
        cell = doc.tables.all[0].cell(0, 0)
        cell.element.set("hasMargin", "1")
        margin = cell.element.find(HP + "cellMargin")
        margin.set("left", "111")
        margin.set("right", "222")
        assert resolve_slot_metrics(cell, doc).available_width == pytest.approx(
            (cell.width - 333) * 0.93
        )


@pytest.mark.parametrize("selector", [{"name": "필드1234"}, {"field_id": "1080328314"}])
def test_empty_field_same_run_inserts_inside_controls(selector, tmp_path):
    source = CORPUS / "error__20231219__test1.hwpx"
    with HwpxDocument.open(source) as doc:
        original = deepcopy(doc.sections[0].element)
        begin = next(original.iter(HP + "fieldBegin"))
        begin.set("dirty", "1")
        control = begin.getparent()
        run = control.getparent()
        text = etree.Element(HP + "t")
        text.text = "확인 완료"
        run.insert(list(run).index(control) + 1, text)
        for cache in list(run.getparent().iter(HP + "linesegarray")):
            cache.getparent().remove(cache)
        result = doc.fields.fill("확인 완료", **selector)
        assert result.after == "확인 완료"
        assert fingerprint(doc.sections[0].element) == fingerprint(original)
        output = tmp_path / "field.hwpx"
        doc.save_to_path(output, mode="patch", fallback="error")
    with HwpxDocument.open(output) as doc:
        field = next(f for f in doc.fields.all if f.name == "필드1234")
        assert field.value == "확인 완료"


def test_cloned_paragraph_ids_are_distinct_and_do_not_collide(tmp_path):
    from hwpx.plan import apply_edit_plan

    source = CORPUS / "error__20250523__프로젝트 계획서.hwpx"
    output = tmp_path / "rows.hwpx"
    with HwpxDocument.open(source) as doc:
        original_ids = {
            p.get("id") for s in doc.sections for p in s.element.iter(HP + "p")
        }
        reference = deepcopy(doc.tables.all[1].rows[6].element)
    result = apply_edit_plan(
        {
            "schemaVersion": "hwpx.edit-plan/v1",
            "source": str(source),
            "output": str(output),
            "steps": [
                {
                    "id": "rows",
                    "op": "apply_table_ops",
                    "args": {
                        "ops": [
                            {
                                "op": "insert_row_by_clone",
                                "table_index": 1,
                                "ref_row": 6,
                                "count": 2,
                            }
                        ]
                    },
                }
            ],
        }
    )
    assert result.ok
    with HwpxDocument.open(output) as doc:
        ids = []
        for index in (7, 8):
            clone = deepcopy(doc.tables.all[1].rows[index].element)
            for new, old in zip(
                clone.iter(HP + "p"), reference.iter(HP + "p"), strict=True
            ):
                ids.append(new.get("id"))
                new.set("id", old.get("id"))
            for addr in clone.iter(HP + "cellAddr"):
                assert addr.get("rowAddr") == str(index)
                addr.set("rowAddr", "6")
            assert fingerprint(clone) == fingerprint(reference)
        assert len(ids) == len(set(ids))
        assert not original_ids.intersection(ids)


def test_border_edit_preserves_external_feature_switch_requirements(tmp_path):
    source = Path(__file__).parent / "fixtures/m2_corpus/public_official_table.hwpx"
    with zipfile.ZipFile(source) as z:
        before = etree.fromstring(z.read("Contents/header.xml"))
    requirements = [n.get(HP + "required-namespace") for n in before.iter(HP + "case")]
    assert "http://www.hancom.co.kr/hwpml/2016/paragraph" in requirements
    with HwpxDocument.open(source) as doc:
        border = doc.styles.ensure_border_fill(
            border_color="#0055AA", border_type="SOLID"
        )
        doc.tables.all[0].set_cell_border_fill(0, 0, border)
        output = tmp_path / "border.hwpx"
        doc.save_to_path(output, mode="patch", fallback="error")
    with zipfile.ZipFile(output) as z:
        after = etree.fromstring(z.read("Contents/header.xml"))
    assert [
        n.get(HP + "required-namespace") for n in after.iter(HP + "case")
    ] == requirements


def test_namespace_normalization_preserves_uri_text_comments_and_attributes():
    from hwpx.opc.xml_utils import normalize_hwpml_namespaces

    old = b"http://www.hancom.co.kr/hwpml/2016/paragraph"
    data = (
        b'<p xmlns="'
        + old
        + b'" note="xmlns:fake=\''
        + old
        + b'\'" required="'
        + old
        + b'">'
        + old
        + b'<!-- xmlns="'
        + old
        + b'" --><![CDATA[xmlns="'
        + old
        + b'"]]></p>'
    )
    expected = data.replace(
        b'<p xmlns="' + old + b'"',
        b'<p xmlns="http://www.hancom.co.kr/hwpml/2011/paragraph"',
        1,
    )
    assert normalize_hwpml_namespaces(data) == expected


def test_cell_border_only_edit_preserves_fill_width_and_shared_style(tmp_path):
    source = Path(__file__).parent / "fixtures/m2_corpus/public_official_table.hwpx"
    with HwpxDocument.open(source) as doc:
        tables = []

        def walk(paragraphs):
            for p in paragraphs:
                for t in p.tables:
                    tables.append(t)
                    for row in t.rows:
                        for cell in row.cells:
                            walk(cell.paragraphs)

        walk(doc.paragraphs)
        table = tables[10]
        cell = table.cell(0, 2)
        base = cell.element.get("borderFillIDRef")
        header = doc.oxml.headers[0]
        HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
        container = next(header.element.iter(HH + "borderFills"))
        before = deepcopy(next(n for n in container if n.get("id") == base))
        table.set_cell_borders(0, 2, color="#0055aa", line_type="SOLID")
        new_id = cell.element.get("borderFillIDRef")
        assert new_id != base
        wanted = deepcopy(before)
        wanted.set("id", new_id)
        for name in ["leftBorder", "rightBorder", "topBorder", "bottomBorder"]:
            wanted.find(HH + name).set("color", "#0055AA")
            wanted.find(HH + name).set("type", "SOLID")
        assert fingerprint(
            next(n for n in container if n.get("id") == new_id)
        ) == fingerprint(wanted)
        assert fingerprint(
            next(n for n in container if n.get("id") == base)
        ) == fingerprint(before)
        count = len(container)
        table.set_cell_borders(0, 2, color="#0055AA", line_type="SOLID")
        assert len(container) == count and cell.element.get("borderFillIDRef") == new_id
        before_bad = (
            etree.tostring(header.element),
            etree.tostring(doc.sections[0].element),
        )
        for kwargs in [{"color": "bad"}, {"color": "#112233", "line_type": "bad"}]:
            with pytest.raises(HwpxValueError) as exc:
                table.set_cell_borders(0, 2, **kwargs)
            assert (
                exc.value.code == "cell-border-edit-unsupported"
                and exc.value.suggestion
            )
            assert (
                etree.tostring(header.element),
                etree.tostring(doc.sections[0].element),
            ) == before_bad
        output = tmp_path / "border-only.hwpx"
        doc.save_to_path(output, mode="patch", fallback="error")
    with zipfile.ZipFile(output) as z:
        reopened = etree.fromstring(z.read("Contents/header.xml"))
        assert fingerprint(
            next(n for n in reopened.iter(HH + "borderFill") if n.get("id") == new_id)
        ) == fingerprint(wanted)
