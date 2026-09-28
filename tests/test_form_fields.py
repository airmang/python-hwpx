from __future__ import annotations

from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError
from hwpx.tools.package_validator import validate_editor_open_safety


HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HANCOM_SAVED = Path(__file__).parent / "fixtures" / "hancom_saved"
SPANNING = HANCOM_SAVED / "form_fields_spanning_before.hwpx"
SPANNING_FILLED = HANCOM_SAVED / "form_fields_spanning_after.hwpx"
SPANNING_VALUES = {"본문": "새 값 1", "칸": "새 값 2", "붙음": "새 값 3", "한줄": "새 값 4"}
NO_END = HANCOM_SAVED / "form_field_no_end_before.hwpx"
NESTED = HANCOM_SAVED / "nested_field_saved.hwpx"
VALUE_SHAPES = {"파랑": "새 파랑", "굵게": "새 굵게", "같음": "새 같음", "안내": "새 안내"}
NO_END_FILLED = HANCOM_SAVED / "form_field_no_end_after.hwpx"


def _append(parent, tag: str, attrs: dict[str, str] | None = None):
    child = parent.makeelement(tag, attrs or {})
    parent.append(child)
    return child


def _add_click_here_field(
    doc: HwpxDocument,
    *,
    name: str = "일시",
    prompt: str = "회의 일시",
    value: str = "입력하세요",
) -> None:
    paragraph = doc.add_paragraph("", include_run=False)
    p = paragraph.element
    begin_run = _append(p, f"{HP}run", {"charPrIDRef": "0"})
    ctrl = _append(begin_run, f"{HP}ctrl", {"type": "FORM", "id": "ctrl-date"})
    field_begin = _append(
        ctrl,
        f"{HP}fieldBegin",
        {
            "id": "field-date",
            "fieldid": "field-date",
            "type": "ClickHere",
            "name": name,
            "prompt": prompt,
        },
    )
    parameters = _append(field_begin, f"{HP}parameters", {"count": "2"})
    _append(parameters, f"{HP}stringParam", {"name": "FieldName"}).text = name
    _append(parameters, f"{HP}stringParam", {"name": "Instruction"}).text = prompt

    text_run = _append(p, f"{HP}run", {"charPrIDRef": "0"})
    _append(text_run, f"{HP}t").text = value
    end_run = _append(p, f"{HP}run", {"charPrIDRef": "0"})
    end_ctrl = _append(end_run, f"{HP}ctrl")
    _append(end_ctrl, f"{HP}fieldEnd", {"beginIDRef": "field-date", "fieldid": "field-date"})
    _append(p, f"{HP}lineSegArray")
    paragraph.section.mark_dirty()


def test_list_form_fields_reports_name_prompt_and_current_value() -> None:
    doc = HwpxDocument.new()
    _add_click_here_field(doc)

    fields = doc.list_form_fields()

    assert len(fields) == 1
    assert fields[0].field_id == "field-date"
    assert fields[0].name == "일시"
    # instruction/control_type were 5.x aliases absorbed into prompt/field_type
    # (design §2.3) — the check below covers the same underlying value.
    assert fields[0].prompt == "회의 일시"
    assert fields[0].value == "입력하세요"
    assert fields[0].field_type == "ClickHere"
    assert fields[0].has_end is True


def test_fill_form_field_preserves_run_formatting_and_open_safety(tmp_path: Path) -> None:
    path = tmp_path / "form-field.hwpx"
    doc = HwpxDocument.new()
    _add_click_here_field(doc)

    result = doc.fill_form_field("2026-06-11 10:00", name="일시")
    doc.save_to_path(path)

    # No `ok` key: reaching a FieldFillResult at all means the fill succeeded
    # (fail-closed raise on a hard fit failure instead, design §2.4).
    assert result.before == "입력하세요"
    assert result.after == "2026-06-11 10:00"
    assert result.style_preserved is True
    assert validate_editor_open_safety(path.read_bytes()).ok is True

    reopened = HwpxDocument.open(path)
    fields = reopened.list_form_fields()
    assert fields[0].value == "2026-06-11 10:00"
    paragraph = reopened.paragraphs[fields[0].location.paragraph_index]
    assert paragraph.element.find(f"{HP}lineSegArray") is None


def test_fill_form_field_rejects_memo_and_hyperlink_fields() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("", include_run=False)
    p = paragraph.element
    for field_type in ("MEMO", "HYPERLINK"):
        run = _append(p, f"{HP}run", {"charPrIDRef": "0"})
        ctrl = _append(run, f"{HP}ctrl", {"type": field_type})
        _append(ctrl, f"{HP}fieldBegin", {"id": field_type.lower(), "type": field_type})
    paragraph.section.mark_dirty()

    assert doc.list_form_fields() == ()  # list_form_fields now returns a tuple (design §2.5)


def _paragraph_marks(doc: HwpxDocument) -> list[str]:
    """Every paragraph (body and cells, in document order): its text with [B] and [E] for field begins
    and ends and [표] for a table."""
    marks = []
    for section in doc.sections:
        for paragraph in section.element.iter(f"{HP}p"):
            parts = []
            for run in paragraph.findall(f"{HP}run"):
                for child in run:
                    tag = child.tag.rsplit("}", 1)[-1]
                    if tag == "t":
                        parts.append("".join(child.itertext()))
                    elif tag == "ctrl":
                        parts += ["[B]"] * len(child.findall(f"{HP}fieldBegin"))
                        parts += ["[E]"] * len(child.findall(f"{HP}fieldEnd"))
                    elif tag == "tbl":
                        parts.append("[표]")
            marks.append("".join(parts))
    return marks


def test_a_field_running_over_paragraphs_reads_all_its_content() -> None:
    doc = HwpxDocument.open(SPANNING.read_bytes())
    fields = {field.name: field for field in doc.fields.all}

    assert all(field.has_end for field in fields.values())
    assert fields["본문"].value == "첫 줄\n가운데 문단\n\n끝 앞"  # the paragraph holding the table is empty
    assert fields["칸"].value == "칸 첫 줄\n칸 가운데\n칸 끝 앞"
    assert fields["붙음"].value == "\n"
    assert fields["한줄"].value == "안의 글"


def test_fields_running_over_paragraphs_fill_as_hancom_does() -> None:
    """Four fields filled by Hancom: over a paragraph and a table, over a cell's three paragraphs, over a
    paragraph break, and within one paragraph. The paragraphs inside a field go; its end and the rest of
    the end's paragraph join the begin's paragraph, which keeps its shape."""
    doc = HwpxDocument.open(SPANNING.read_bytes())
    begin = next(p for p in doc.paragraphs if "앞 글" in p.text)
    shape = begin.element.get("paraPrIDRef")
    for name, value in SPANNING_VALUES.items():
        doc.fields.fill(value, name=name)
    hancom = HwpxDocument.open(SPANNING_FILLED.read_bytes())

    assert _paragraph_marks(doc) == _paragraph_marks(hancom)
    assert [field.value for field in doc.fields.all] == list(SPANNING_VALUES.values())
    assert next(p for p in doc.paragraphs if "앞 글" in p.text).element.get("paraPrIDRef") == shape


def test_filling_a_field_drops_the_fields_inside_it_as_hancom_does() -> None:
    """Hancom saved a paragraph holding the field 바깥 ("바깥 앞 ", the field 안쪽, " 바깥 뒤") and filled 바깥:
    the value took the whole content, and 안쪽 went with it."""
    doc = HwpxDocument.open(NESTED.read_bytes())
    hancom = HwpxDocument.open((HANCOM_SAVED / "nested_field_outer.hwpx").read_bytes())
    assert "바깥 앞 [B]안쪽 값[E] 바깥 뒤" in "".join(_paragraph_marks(doc))

    doc.fields.fill("새 바깥 값", name="바깥")

    assert _paragraph_marks(doc) == _paragraph_marks(hancom)
    assert [field.name for field in doc.fields.all] == [field.name for field in hancom.fields.all] == ["바깥", "따로"]


def test_filling_the_field_inside_keeps_the_field_around_it() -> None:
    doc = HwpxDocument.open(NESTED.read_bytes())
    hancom = HwpxDocument.open((HANCOM_SAVED / "nested_field_inner.hwpx").read_bytes())

    doc.fields.fill("새 안쪽 값", name="안쪽")

    assert _paragraph_marks(doc) == _paragraph_marks(hancom)
    assert [(field.name, field.value) for field in doc.fields.all] == [
        ("바깥", "바깥 앞 새 안쪽 값 바깥 뒤"),
        ("안쪽", "새 안쪽 값"),
        ("따로", "따로 값"),
    ]


def _value_shapes(doc: HwpxDocument) -> dict[str, set[str]]:
    """Each field's name and the shapes of the runs holding its text."""
    shapes: dict[str, set[str]] = {}
    for paragraph in doc.sections[0].element.iter(f"{HP}p"):
        name = None
        for run in paragraph.findall(f"{HP}run"):
            for child in run:
                begin = child.find(f"{HP}fieldBegin")
                if begin is not None:
                    name = begin.get("name")
                elif child.find(f"{HP}fieldEnd") is not None:
                    name = None
                elif name and child.tag == f"{HP}t" and "".join(child.itertext()):
                    shapes.setdefault(name, set()).add(run.get("charPrIDRef"))
    return shapes


def test_a_value_takes_the_shape_of_the_field_begin_as_hancom_writes_it() -> None:
    """Hancom saved four fields whose begin and end sit in runs of shape 0: 파랑 holding a value in a blue run,
    굵게 one in a bold run, 같음 one in a run of shape 0, and 안내 its prompt. It filled all four: every value
    took the shape of the run holding the field's begin."""
    doc = HwpxDocument.open((HANCOM_SAVED / "field_value_shape_saved.hwpx").read_bytes())
    hancom = HwpxDocument.open((HANCOM_SAVED / "field_value_shape_filled.hwpx").read_bytes())
    assert _value_shapes(doc)["파랑"] != {"0"} and _value_shapes(doc)["굵게"] != {"0"}

    results = [doc.fields.fill(value, name=name) for name, value in VALUE_SHAPES.items()]

    assert _value_shapes(doc) == _value_shapes(hancom) == {name: {"0"} for name in VALUE_SHAPES}
    assert [field.value for field in doc.fields.all] == list(VALUE_SHAPES.values())
    assert [result.style_preserved for result in results] == [False, False, True, False]


def test_fill_refuses_a_field_without_an_end() -> None:
    doc = HwpxDocument.new()
    paragraph = doc.add_paragraph("")
    doc.fields.add(name="끝없음", paragraph=paragraph)
    end = next(paragraph.element.iter(f"{HP}fieldEnd"))
    end.getparent().getparent().remove(end.getparent())
    before = _paragraph_marks(doc)

    assert doc.fields.all[0].has_end is False
    with pytest.raises(HwpxValueError) as raised:
        doc.fields.fill("값", name="끝없음")
    assert raised.value.code == "field-end-missing"
    assert _paragraph_marks(doc) == before


def test_hancom_leaves_a_field_without_an_end_as_it_was() -> None:
    """Hancom was asked to fill 본문, a field whose end is missing, with "새 값 1" and saved the document as it
    was; python-hwpx refuses the same fill."""
    before, after = (HwpxDocument.open(path.read_bytes()) for path in (NO_END, NO_END_FILLED))

    assert _paragraph_marks(after) == _paragraph_marks(before)
    assert [(field.name, field.has_end) for field in before.fields.all] == [("본문", False)]
    with pytest.raises(HwpxValueError) as raised:
        before.fields.fill("새 값 1", name="본문")
    assert raised.value.code == "field-end-missing"


HWPXLIB = Path(__file__).parent / "fixtures" / "hwpxlib_corpus"


def test_a_prompt_kept_only_in_the_command_string_is_the_placeholder() -> None:
    doc = HwpxDocument.open((HWPXLIB / "tool__finder__TestFinder.hwpx").read_bytes())

    assert [(field.name, field.prompt, field.is_placeholder) for field in doc.fields.all][:2] == [
        ("필드1", "필드1", True),
        ("필드2", "필드2", True),
    ]


def test_filling_a_command_prompt_field_drops_the_prompt_style() -> None:
    """The prompt run is red; the value takes the field's own character shape, and the field's parameters stay
    as they were."""
    doc = HwpxDocument.open((HWPXLIB / "tool__textextractor__Table.hwpx").read_bytes())
    begin = next(b for b in doc.sections[0].element.iter(f"{HP}fieldBegin") if b.get("name") == "날짜")
    begin_style = begin.getparent().getparent().get("charPrIDRef")
    parameters = [(p.get("name"), p.text) for p in begin.find(f"{HP}parameters")]

    doc.fields.fill("2026-09-28", name="날짜")

    value = next(t for t in doc.sections[0].element.iter(f"{HP}t") if (t.text or "") == "2026-09-28")
    assert value.getparent().get("charPrIDRef") == begin_style
    assert [(p.get("name"), p.text) for p in begin.find(f"{HP}parameters")] == parameters
    assert begin.get("dirty") == "1"


def _field_text_nodes_of(doc: HwpxDocument, name: str):
    begin = next(b for b in doc.sections[0].element.iter(f"{HP}fieldBegin") if b.get("name") == name)
    paragraph = begin.getparent().getparent().getparent()
    return [t for t in paragraph.iter(f"{HP}t")]


def test_a_line_break_in_a_field_value_is_written_as_hp_line_break() -> None:
    doc = HwpxDocument.new()
    doc.fields.add("주소", prompt="주소", paragraph=doc.add_paragraph(""))

    result = doc.fields.fill("서울\r\n종로구\n1번지", name="주소")

    [text] = [t for t in _field_text_nodes_of(doc, "주소") if "".join(t.itertext())]
    assert text.text == "서울"
    assert [(child.tag, child.tail) for child in text] == [(f"{HP}lineBreak", "종로구"), (f"{HP}lineBreak", "1번지")]
    assert result.field.value == "서울\n종로구\n1번지"


def test_filling_a_field_drops_the_line_breaks_of_its_old_value() -> None:
    doc = HwpxDocument.new()
    doc.fields.add("주소", prompt="주소", paragraph=doc.add_paragraph(""))
    doc.fields.fill("서울", name="주소")
    [text] = [t for t in _field_text_nodes_of(doc, "주소") if "".join(t.itertext())]
    line_break = text.makeelement(f"{HP}lineBreak", {})  # as Hancom saves a two-line value
    text.append(line_break)
    line_break.tail = "종로구"

    result = doc.fields.fill("부산", name="주소")

    assert not any(t.findall(f"{HP}lineBreak") for t in _field_text_nodes_of(doc, "주소"))
    assert result.field.value == "부산"


def test_a_field_value_line_break_matches_what_hancom_saves() -> None:
    """Hancom opened a document whose field 주소 held "서울", a raw newline and "종로구", and saved the
    newline as hp:lineBreak; python-hwpx now writes the same."""
    hancom = HwpxDocument.open((HANCOM_SAVED / "form_field_line_break.hwpx").read_bytes())
    [saved] = [t for t in _field_text_nodes_of(hancom, "주소") if (t.text or "").startswith("서울")]
    assert (saved.text, [(child.tag, child.tail) for child in saved]) == ("서울", [(f"{HP}lineBreak", "종로구")])
    assert [(field.name, field.value) for field in hancom.fields.all] == [("주소", "서울\n종로구")]

    doc = HwpxDocument.new()
    doc.fields.add("주소", prompt="주소", paragraph=doc.add_paragraph("주소: "))
    doc.fields.fill("서울\n종로구", name="주소")
    [written] = [t for t in _field_text_nodes_of(doc, "주소") if (t.text or "").startswith("서울")]
    assert (written.text, [(child.tag, child.tail) for child in written]) == ("서울", [(f"{HP}lineBreak", "종로구")])


def _unnamed_field_document() -> HwpxDocument:
    doc = HwpxDocument.new()
    doc.fields.add("이름", prompt="이름", paragraph=doc.add_paragraph(""))
    doc.fields.add("임시", prompt="날짜", paragraph=doc.add_paragraph(""))
    unnamed = next(b for b in doc.sections[0].element.iter(f"{HP}fieldBegin") if b.get("name") == "임시")
    unnamed.set("name", "")  # Hancom keeps an unnamed click-here field with name=""
    return doc


def test_an_unnamed_field_is_left_out_of_the_field_list() -> None:
    doc = _unnamed_field_document()

    assert [field.name for field in doc.fields.all] == ["이름"]


def test_an_unnamed_field_is_not_found_by_name_but_by_index() -> None:
    doc = _unnamed_field_document()
    unnamed = next(b for b in doc.sections[0].element.iter(f"{HP}fieldBegin") if b.get("name") == "")

    for name in (unnamed.get("id"), "날짜"):  # neither its id nor its prompt is a name
        with pytest.raises(HwpxValueError) as raised:
            doc.fields.fill("2026-09-28", name=name)
        assert raised.value.code == "field-not-found"

    result = doc.fields.fill("2026-09-28", field_index=1)
    assert result.field.name == ""
    assert result.field.value == "2026-09-28"


def test_hancom_lists_and_fills_only_the_named_field() -> None:
    """Hancom saved a document with a field 이름 and a field whose name is empty, before and after it was
    asked to fill 이름 with 홍길동 and the unnamed field, by its id, with a date: its field list held
    이름 alone, and only 이름 was filled."""
    before = HwpxDocument.open((HANCOM_SAVED / "form_field_unnamed_before.hwpx").read_bytes())
    after = HwpxDocument.open((HANCOM_SAVED / "form_field_unnamed_after.hwpx").read_bytes())

    assert [field.name for field in before.fields.all] == ["이름"]
    assert [(field.name, field.value) for field in after.fields.all] == [("이름", "홍길동")]
    unnamed = [b for b in after.sections[0].element.iter(f"{HP}fieldBegin") if b.get("name") == ""]
    assert len(unnamed) == 1 and unnamed[0].get("dirty") != "1"
