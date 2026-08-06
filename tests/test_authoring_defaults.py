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


class TestCharacterFormatResidual:
    """cycle-6.3 트레인 ⑩ — 감사 갭 #8(문자 서식 의미 요소 잔여).

    `outline`/`emboss`/`engrave`는 스키마 어휘로 검증했다(Header XML
    schema.xml:901-978). `script`의 실요소 병행은 hwpxlib 실코퍼스
    (error__20250808 문서, charPr id=513)에서 실한컴이 위첨자 토글로 쓴
    charPr에 `<hh:supscript/>`가 있음을 직접 관찰해 반영했다 — 이 트레인은
    실한컴 렌더 왕복까지는 하지 못했다(데모 파일로 별도 기록).
    """

    HH = "{http://www.hancom.co.kr/hwpml/2011/head}"

    def test_outline_emits_type(self) -> None:
        doc = HwpxDocument.new()
        outlined = doc.styles.ensure_run(outline="SOLID")
        cp = doc.oxml.headers[0]._char_properties_element().find(
            f"{self.HH}charPr[@id='{outlined}']"
        )
        assert cp.find(f"{self.HH}outline").get("type") == "SOLID"

    def test_outline_out_of_vocabulary_rejected(self) -> None:
        doc = HwpxDocument.new()
        with pytest.raises(ValueError):
            doc.styles.ensure_run(outline="ZIGZAG")

    def test_outline_none_is_settable_explicitly(self) -> None:
        doc = HwpxDocument.new()
        cleared = doc.styles.ensure_run(outline="NONE")
        cp = doc.oxml.headers[0]._char_properties_element().find(
            f"{self.HH}charPr[@id='{cleared}']"
        )
        assert cp.find(f"{self.HH}outline").get("type") == "NONE"

    def test_emboss_and_engrave_emit_flag_elements(self) -> None:
        doc = HwpxDocument.new()
        embossed = doc.styles.ensure_run(emboss=True)
        engraved = doc.styles.ensure_run(engrave=True)
        assert embossed != engraved
        headers = doc.oxml.headers
        char_props_el = headers[0]._char_properties_element()
        emboss_cp = char_props_el.find(f"{self.HH}charPr[@id='{embossed}']")
        engrave_cp = char_props_el.find(f"{self.HH}charPr[@id='{engraved}']")
        assert emboss_cp.find(f"{self.HH}emboss") is not None
        assert emboss_cp.find(f"{self.HH}engrave") is None
        assert engrave_cp.find(f"{self.HH}engrave") is not None
        assert engrave_cp.find(f"{self.HH}emboss") is None

    def test_script_pairs_real_flag_element_with_existing_offset_approximation(
        self,
    ) -> None:
        doc = HwpxDocument.new()
        sup = doc.styles.ensure_run(script="sup")
        sub = doc.styles.ensure_run(script="sub")
        char_props_el = doc.oxml.headers[0]._char_properties_element()
        sup_cp = char_props_el.find(f"{self.HH}charPr[@id='{sup}']")
        sub_cp = char_props_el.find(f"{self.HH}charPr[@id='{sub}']")
        # 기존 계약(파괴 금지): relSz=67, offset 부호는 그대로.
        assert sup_cp.find(f"{self.HH}relSz").get("hangul") == "67"
        assert sup_cp.find(f"{self.HH}offset").get("hangul") == "-30"
        assert sub_cp.find(f"{self.HH}offset").get("hangul") == "30"
        # 신규: 실요소가 병행 방출된다.
        assert sup_cp.find(f"{self.HH}supscript") is not None
        assert sup_cp.find(f"{self.HH}subscript") is None
        assert sub_cp.find(f"{self.HH}subscript") is not None
        assert sub_cp.find(f"{self.HH}supscript") is None

    def test_residual_extensions_are_idempotent(self) -> None:
        doc = HwpxDocument.new()
        first = doc.styles.ensure_run(outline="DASH", emboss=True)
        again = doc.styles.ensure_run(outline="DASH", emboss=True)
        assert first == again
        sup_first = doc.styles.ensure_run(script="sup")
        sup_again = doc.styles.ensure_run(script="sup")
        assert sup_first == sup_again

    def test_read_side_exposes_residual_flags(self) -> None:
        doc = HwpxDocument.new()
        sup = doc.styles.ensure_run(script="sup")
        outlined = doc.styles.ensure_run(outline="THICK")
        embossed = doc.styles.ensure_run(emboss=True)
        engraved = doc.styles.ensure_run(engrave=True)
        assert doc.styles.char_property(sup).is_superscript() is True
        assert doc.styles.char_property(sup).is_subscript() is False
        assert doc.styles.char_property(outlined).outline_type() == "THICK"
        assert doc.styles.char_property(embossed).is_emboss() is True
        assert doc.styles.char_property(engraved).is_engrave() is True

    def test_residual_flags_survive_roundtrip(self) -> None:
        doc = HwpxDocument.new()
        sub = doc.styles.ensure_run(script="sub")
        outlined = doc.styles.ensure_run(outline="DOT")
        embossed = doc.styles.ensure_run(emboss=True)
        doc.add_paragraph("아래첨자", char_pr_id_ref=sub)
        doc.add_paragraph("외곽선", char_pr_id_ref=outlined)
        doc.add_paragraph("양각", char_pr_id_ref=embossed)
        reopened = _roundtrip(doc)
        assert reopened.styles.char_property(sub).is_subscript() is True
        assert reopened.styles.char_property(outlined).outline_type() == "DOT"
        assert reopened.styles.char_property(embossed).is_emboss() is True
