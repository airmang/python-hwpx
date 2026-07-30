from __future__ import annotations

import io
from pathlib import Path

from hwpx import HwpxDocument
from hwpx.tools.package_validator import validate_editor_open_safety

import pytest

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
DATA = Path(__file__).parent / "data"


def _roundtrip(doc: HwpxDocument) -> HwpxDocument:
    buffer = io.BytesIO()
    doc.save_to_stream(buffer)
    buffer.seek(0)
    return HwpxDocument.open(buffer)


def _field_begin(doc: HwpxDocument, name: str):
    for section in doc.sections:
        for fb in section.element.iter(f"{HP}fieldBegin"):
            if fb.get("name") == name:
                return fb
    raise AssertionError(f"fieldBegin not found: {name}")


class TestGoldContractShape:
    """The emitted XML must match the real-Hancom CLICKHERE gold pair
    (specs/053-formfield-authoring/evidence/p0/clickhere-contract.md)."""

    def test_field_begin_attributes(self) -> None:
        doc = HwpxDocument.new()
        doc.add_form_field("성명", prompt="이름 입력", memo="도움말")
        fb = _field_begin(doc, "성명")
        assert fb.get("type") == "CLICK_HERE"
        assert fb.get("editable") == "1"
        assert fb.get("dirty") == "0"
        assert fb.get("zorder") == "-1"
        assert fb.get("metaTag") == ""
        assert fb.get("id") and fb.get("fieldid")

    def test_command_serialization_counts_characters(self) -> None:
        # Korean + spaces inside values: lengths are UTF-16 character counts.
        doc = HwpxDocument.new()
        doc.add_form_field("f", prompt="안내 문", memo="m 1")
        fb = _field_begin(doc, "f")
        params = {
            p.get("name"): (p.text or "")
            for p in fb.find(f"{HP}parameters")
        }
        payload = "Direction:wstring:4:안내 문 HelpState:wstring:3:m 1 "
        assert params["Command"] == f"Clickhere:set:{len(payload)}:{payload} "
        assert params["Direction"] == "안내 문"
        assert params["HelpState"] == "m 1"
        assert params["Prop"] == "9"
        command_param = fb.find(f"{HP}parameters/{HP}stringParam[@name='Command']")
        assert command_param.get(
            "{http://www.w3.org/XML/1998/namespace}space"
        ) == "preserve"

    def test_param_count_omits_empty_entries(self) -> None:
        doc = HwpxDocument.new()
        doc.add_form_field("only_name")
        fb = _field_begin(doc, "only_name")
        parameters = fb.find(f"{HP}parameters")
        assert parameters.get("cnt") == "2"
        names = [p.get("name") for p in parameters]
        assert names == ["Prop", "Command"]

    def test_prompt_run_is_red_italic_and_field_end_pairs(self) -> None:
        doc = HwpxDocument.new()
        doc.add_form_field("f", prompt="누르세요")
        fb = _field_begin(doc, "f")
        paragraph = fb.getparent().getparent().getparent()
        runs = [child for child in paragraph if child.tag == f"{HP}run"]
        begin_index = next(
            i for i, run in enumerate(runs)
            if run.find(f"{HP}ctrl/{HP}fieldBegin") is not None
        )
        prompt_run = runs[begin_index + 1]
        assert prompt_run.find(f"{HP}t").text == "누르세요"
        char_pr = doc.headers[0].element.find(
            f".//{HH}charPr[@id='{prompt_run.get('charPrIDRef')}']"
        )
        assert char_pr.get("textColor", "").upper() == "#FF0000"
        assert char_pr.find(f"{HH}italic") is not None
        end_run = runs[begin_index + 2]
        fe = end_run.find(f"{HP}ctrl/{HP}fieldEnd")
        assert fe.get("beginIDRef") == fb.get("id")
        assert fe.get("fieldid") == fb.get("fieldid")
        assert end_run.find(f"{HP}t") is not None

    def test_no_prompt_run_when_prompt_empty(self) -> None:
        doc = HwpxDocument.new()
        doc.add_form_field("bare")
        fb = _field_begin(doc, "bare")
        paragraph = fb.getparent().getparent().getparent()
        runs = [child for child in paragraph if child.tag == f"{HP}run"]
        begin_index = next(
            i for i, run in enumerate(runs)
            if run.find(f"{HP}ctrl/{HP}fieldBegin") is not None
        )
        assert runs[begin_index + 1].find(f"{HP}ctrl/{HP}fieldEnd") is not None


class TestRoundTrip:
    """Created fields must be consumed by the standard list/fill APIs with no
    special-casing, across a save/reopen boundary."""

    def test_create_save_reopen_list(self) -> None:
        doc = HwpxDocument.new()
        created = doc.add_form_field("부서", prompt="부서 입력", memo="조직명")
        assert created["name"] == "부서"
        assert created["prompt"] == "부서 입력"
        assert created["memo"] == "조직명"
        assert created["is_placeholder"] is True
        assert created["has_end"] is True

        reopened = _roundtrip(doc)
        fields = reopened.list_form_fields()
        assert [f["name"] for f in fields] == ["부서"]
        field = fields[0]
        assert field["dirty"] == "0"
        assert field["is_placeholder"] is True
        assert field["current_value"] == "부서 입력"

    def test_fill_swaps_placeholder_style_and_sets_dirty(self) -> None:
        doc = HwpxDocument.new()
        doc.add_form_field("성명", prompt="이름 입력")
        reopened = _roundtrip(doc)
        response = reopened.fill_form_field("홍길동", name="성명")
        assert response["ok"] is True
        field = response["field"]
        assert field["current_value"] == "홍길동"
        assert field["dirty"] == "1"
        assert field["is_placeholder"] is False

        fb = _field_begin(reopened, "성명")
        paragraph = fb.getparent().getparent().getparent()
        runs = [child for child in paragraph if child.tag == f"{HP}run"]
        begin_index = next(
            i for i, run in enumerate(runs)
            if run.find(f"{HP}ctrl/{HP}fieldBegin") is not None
        )
        # value run must carry the surrounding style, not the red prompt style
        assert (
            runs[begin_index + 1].get("charPrIDRef")
            == runs[begin_index].get("charPrIDRef")
        )

        final = _roundtrip(reopened)
        assert final.list_form_fields()[0]["current_value"] == "홍길동"

    def test_field_in_table_cell(self) -> None:
        doc = HwpxDocument.new()
        table = doc.add_table(2, 2)
        cell_paragraph = table.cell(0, 0).paragraphs[0]
        doc.add_form_field("셀필드", prompt="셀 입력", paragraph=cell_paragraph)
        reopened = _roundtrip(doc)
        fields = reopened.list_form_fields()
        assert [f["name"] for f in fields] == ["셀필드"]
        reopened.fill_form_field("값123", name="셀필드")
        assert reopened.list_form_fields()[0]["current_value"] == "값123"

    def test_multiple_fields_pair_independently(self) -> None:
        doc = HwpxDocument.new()
        doc.add_form_field("a", prompt="가")
        doc.add_form_field("b")
        doc.add_form_field("c", prompt="다", memo="m")
        reopened = _roundtrip(doc)
        fields = reopened.list_form_fields()
        assert [f["name"] for f in fields] == ["a", "b", "c"]
        assert all(f["has_end"] for f in fields)
        begin_ids = {f["id"] for f in fields}
        assert len(begin_ids) == 3

    def test_open_safety(self) -> None:
        doc = HwpxDocument.new()
        doc.add_form_field("f", prompt="입력")
        buffer = io.BytesIO()
        doc.save_to_stream(buffer)
        report = validate_editor_open_safety(buffer.getvalue())
        assert report.ok, report


class TestValidation:
    def test_blank_name_rejected(self) -> None:
        doc = HwpxDocument.new()
        with pytest.raises(ValueError):
            doc.add_form_field("   ")

    def test_illegal_control_chars_sanitized(self) -> None:
        doc = HwpxDocument.new()
        created = doc.add_form_field("ok", prompt="안내\x00문")
        assert created["prompt"] == "안내문"


class TestHancomGoldFixtures:
    """Reader regression against real Hancom-authored CLICKHERE documents
    (P0 gold pair, Hancom 12.0.0.3288)."""

    def test_gold_empty_reads_prompt_memo_placeholder(self) -> None:
        doc = HwpxDocument.open(DATA / "clickhere_gold_empty.hwpx")
        (field,) = doc.list_form_fields()
        assert field["name"] == "NAMETEXT_THREE"
        assert field["field_type"] == "CLICK_HERE"
        assert field["prompt"] == "DIRTEXT_ONE"
        assert field["memo"] == "MEMOTEXT_TWO"
        assert field["dirty"] == "0"
        assert field["is_placeholder"] is True
        assert field["current_value"] == "DIRTEXT_ONE"

    def test_gold_filled_reads_value_not_placeholder(self) -> None:
        doc = HwpxDocument.open(DATA / "clickhere_gold_filled.hwpx")
        (field,) = doc.list_form_fields()
        assert field["current_value"] == "FILLED_VALUE_X"
        assert field["dirty"] == "1"
        assert field["is_placeholder"] is False
