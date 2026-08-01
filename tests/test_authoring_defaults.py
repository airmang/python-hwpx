from __future__ import annotations

import io

from hwpx import HwpxDocument

import pytest

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def _roundtrip(doc: HwpxDocument) -> HwpxDocument:
    buffer = io.BytesIO()
    doc.save_to_stream(buffer)
    buffer.seek(0)
    return HwpxDocument.open(buffer)


class TestTableHancomDefaults:
    """add_table defaults measured from real Hancom gold documents
    (specs/056-authoring-fidelity-audit)."""

    def test_cell_padding_matches_hancom(self) -> None:
        doc = HwpxDocument.new()
        table = doc.add_table(2, 2)
        margin = table.cell(0, 0).element.find(f"{HP}cellMargin")
        assert dict(margin.attrib) == {
            "left": "510", "right": "510", "top": "141", "bottom": "141",
        }
        in_margin = table.element.find(f"{HP}inMargin")
        assert in_margin.get("left") == "510" and in_margin.get("top") == "141"

    def test_default_width_fills_the_text_body(self) -> None:
        doc = HwpxDocument.new()
        table = doc.add_table(2, 3)
        properties = doc.sections[0].properties
        body = (
            properties.page_size.width
            - properties.page_margins.left
            - properties.page_margins.right
            - properties.page_margins.gutter
        )
        assert int(table.element.find(f"{HP}sz").get("width")) == body

    def test_nested_default_width_fits_the_parent_cell(self) -> None:
        doc = HwpxDocument.new()
        outer = doc.add_table(2, 2)
        cell = outer.cell(0, 0)
        cell_width = int(cell.element.find(f"{HP}cellSz").get("width"))
        pad = sum(
            int(cell.element.find(f"{HP}cellMargin").get(side))
            for side in ("left", "right")
        )
        inner = cell.paragraphs[0].add_table(2, 2)
        inner_width = int(inner.element.find(f"{HP}sz").get("width"))
        assert inner_width == cell_width - pad
        assert inner_width > 0

    def test_explicit_width_still_wins(self) -> None:
        doc = HwpxDocument.new()
        table = doc.add_table(1, 2, width=12345)
        assert table.element.find(f"{HP}sz").get("width") == "12345"


class TestListParaPrDoesNotLeak:
    def test_plain_paragraph_after_bullet_returns_to_body_text(self) -> None:
        doc = HwpxDocument.new()
        bullets = doc.ensure_numbering(kind="bullet")
        doc.add_paragraph("글머리표", para_pr_id_ref=bullets[0])
        after = doc.add_paragraph("일반 본문")
        assert after.element.get("paraPrIDRef") != bullets[0]

    def test_plain_paragraph_after_numbered_returns_to_body_text(self) -> None:
        doc = HwpxDocument.new()
        nums = doc.ensure_numbering(kind="numbered")
        doc.add_paragraph("첫째", para_pr_id_ref=nums[0])
        after = doc.add_paragraph("일반 본문")
        assert after.element.get("paraPrIDRef") != nums[0]

    def test_explicit_list_para_pr_still_continues_the_list(self) -> None:
        doc = HwpxDocument.new()
        bullets = doc.ensure_numbering(kind="bullet")
        doc.add_paragraph("첫 항목", para_pr_id_ref=bullets[0])
        second = doc.add_paragraph("둘째 항목", para_pr_id_ref=bullets[0])
        assert second.element.get("paraPrIDRef") == bullets[0]

    def test_ordinary_formatting_still_inherits(self) -> None:
        doc = HwpxDocument.new()
        styled = doc.add_paragraph("본문", para_pr_id_ref="0")
        after = doc.add_paragraph("이어지는 본문")
        assert after.element.get("paraPrIDRef") == styled.element.get("paraPrIDRef")


class TestBorderSurface:
    def test_border_type_emits_and_dedupes(self) -> None:
        doc = HwpxDocument.new()
        dashed = doc.ensure_border_fill(
            border_type="DASH", border_color="#0000FF", border_width="0.4 mm"
        )
        assert doc.ensure_border_fill(
            border_type="DASH", border_color="#0000FF", border_width="0.4 mm"
        ) == dashed
        solid = doc.ensure_border_fill(border_color="#0000FF", border_width="0.4 mm")
        assert solid != dashed

    def test_border_type_outside_owpml_vocabulary_rejected(self) -> None:
        doc = HwpxDocument.new()
        with pytest.raises(ValueError):
            doc.ensure_border_fill(border_type="ZIGZAG")

    def test_set_cell_border_fill_points_one_cell(self) -> None:
        doc = HwpxDocument.new()
        table = doc.add_table(1, 2)
        dashed = doc.ensure_border_fill(border_type="DASH")
        table.set_cell_border_fill(0, 1, dashed)
        reopened = _roundtrip(doc)
        cells = list(reopened.sections[0].element.iter(f"{HP}tc"))
        assert cells[1].get("borderFillIDRef") == dashed
        assert cells[0].get("borderFillIDRef") != dashed


class TestHyperlinkConvention:
    """Real-corpus dominant styling: blue #0000FF text + blue BOTTOM underline."""

    def test_display_run_gets_blue_underline_by_default(self) -> None:
        doc = HwpxDocument.new()
        doc.add_hyperlink("https://example.com", "링크")
        reopened = _roundtrip(doc)
        HPNS = HP
        HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
        link_run = None
        for section in reopened.sections:
            for p in section.paragraphs:
                runs = p._run_elements()
                for i, run in enumerate(runs):
                    if run.find(f"{HPNS}ctrl/{HPNS}fieldBegin") is not None:
                        link_run = runs[i + 1]
        assert link_run is not None
        char_id = link_run.get("charPrIDRef")
        char_props = {
            el.get("id"): el
            for header in reopened.headers
            for el in header._char_properties_element()
        }
        cp = char_props[char_id]
        assert cp.get("textColor") == "#0000FF"
        underline = cp.find(f"{HH}underline")
        assert underline.get("type") == "BOTTOM"
        assert underline.get("color") == "#0000FF"

    def test_explicit_char_pr_overrides_convention(self) -> None:
        doc = HwpxDocument.new()
        doc.add_hyperlink("https://example.com", "링크", char_pr_id_ref="0")
        HPNS = HP
        found = None
        for section in doc.sections:
            for p in section.paragraphs:
                runs = p._run_elements()
                for i, run in enumerate(runs):
                    if run.find(f"{HPNS}ctrl/{HPNS}fieldBegin") is not None:
                        found = runs[i + 1]
        assert found is not None
        assert found.get("charPrIDRef") == "0"


class TestRunStyleExtensions:
    """5.4.0 additions — every parameter was render-verified on real Hancom
    in the fidelity audit before gaining an API surface."""

    def test_extended_styles_emit_expected_xml(self) -> None:
        doc = HwpxDocument.new()
        wave = doc.ensure_run_style(underline_shape="WAVE", underline_color="#009900")
        ratio = doc.ensure_run_style(ratio=200)
        spacing = doc.ensure_run_style(letter_spacing=30)
        shadow = doc.ensure_run_style(shadow="#999999")
        sup = doc.ensure_run_style(script="sup")
        double_strike = doc.ensure_run_style(strike_shape="DOUBLE_SLIM")
        assert len({wave, ratio, spacing, shadow, sup, double_strike}) == 6

        HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
        char_props = {
            el.get("id"): el
            for header in doc.headers
            for el in header._char_properties_element()
        }
        underline = char_props[wave].find(f"{HH}underline")
        assert underline.get("shape") == "WAVE"
        assert underline.get("color") == "#009900"
        assert underline.get("type") != "NONE"
        assert char_props[ratio].find(f"{HH}ratio").get("hangul") == "200"
        assert char_props[spacing].find(f"{HH}spacing").get("hangul") == "30"
        assert char_props[shadow].find(f"{HH}shadow").get("type") == "DROP"
        assert char_props[sup].find(f"{HH}relSz").get("hangul") == "67"
        assert char_props[sup].find(f"{HH}offset").get("hangul") == "-30"
        assert char_props[double_strike].find(f"{HH}strikeout").get("shape") == "DOUBLE_SLIM"

    def test_extended_styles_are_idempotent(self) -> None:
        doc = HwpxDocument.new()
        first = doc.ensure_run_style(ratio=200, letter_spacing=30)
        assert doc.ensure_run_style(ratio=200, letter_spacing=30) == first

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"underline_shape": "SQUIGGLE"},
            {"strike_shape": "NOISE"},
            {"ratio": 5},
            {"ratio": 900},
            {"letter_spacing": -80},
            {"script": "middle"},
        ],
    )
    def test_out_of_vocabulary_values_rejected(self, kwargs: dict) -> None:
        doc = HwpxDocument.new()
        with pytest.raises(ValueError):
            doc.ensure_run_style(**kwargs)

    def test_sub_script_offsets_downward(self) -> None:
        # 실한컴 렌더 실측(600dpi): offset 양수=아래, 음수=위. 감사 battery1의
        # "+30=위첨자 픽셀 정확" 판정은 오독이었다(픽셀 재검증으로 정정).
        doc = HwpxDocument.new()
        sub = doc.ensure_run_style(script="sub")
        HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
        char_props = {
            el.get("id"): el
            for header in doc.headers
            for el in header._char_properties_element()
        }
        assert char_props[sub].find(f"{HH}offset").get("hangul") == "30"
