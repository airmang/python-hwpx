from __future__ import annotations

from pathlib import Path

from hwpx import HwpxDocument


def _form() -> tuple[HwpxDocument, object]:
    document = HwpxDocument.new()
    table = document.add_table(3, 4)
    table.cell(0, 0).text = "성  명"
    table.cell(0, 2).text = "주    소"
    table.cell(1, 0).text = "연락처:"
    table.cell(1, 1).text = "010-0000-0000"
    table.cell(2, 0).text = "프로젝트 이름"
    return document, table


def test_a_label_is_found_however_it_is_spaced() -> None:
    document, table = _form()

    result = document.tables.fill_by_path(
        {"성명 > right": "홍길동", "주소 > right": "서울", "프로젝트이름 > right": "가", "연 락 처 > right": "02"}
    )

    assert result["failed"] == []
    assert table.cell(0, 1).text == "홍길동"
    assert table.cell(0, 3).text == "서울"
    assert table.cell(2, 1).text == "가"
    assert table.cell(1, 1).text == "02"
    assert document.tables.find_cell_by_label("성명")["count"] == 1


def test_a_two_line_label_is_found_by_either_line_unless_a_whole_cell_matches() -> None:
    document = HwpxDocument.new()
    table = document.add_table(2, 2)
    table.cell(0, 0).text = "성  명"
    table.cell(0, 0).add_paragraph("Name")
    table.cell(1, 0).text = "학번"
    table.cell(1, 0).add_paragraph("Student No.")

    by_korean = document.tables.fill_by_path({"성명 > right": "홍길동"})
    by_english = document.tables.fill_by_path({"student no. > right": "2026"})
    whole = document.tables.find_cell_by_label("성명 Name")

    assert by_korean["failed"] == [] and by_english["failed"] == []
    assert table.cell(0, 1).text == "홍길동"
    assert table.cell(1, 1).text == "2026"
    assert whole["count"] == 1

    # A cell that is exactly the label wins over a cell that only has it on one line.
    other = document.add_table(1, 2)
    other.cell(0, 0).text = "Name"
    matches = document.tables.find_cell_by_label("Name")
    assert matches["count"] == 1
    assert matches["matches"][0]["table_index"] == 1


def _two_people() -> tuple[HwpxDocument, object, object]:
    document = HwpxDocument.new()
    document.add_paragraph("1. 신청인")
    first = document.add_table(1, 2)
    first.cell(0, 0).text = "성명"
    document.add_paragraph("2. 보호자")
    second = document.add_table(1, 2)
    second.cell(0, 0).text = "성 명"
    return document, first, second


def test_an_ambiguous_label_lists_its_candidates_and_a_number_picks_one() -> None:
    document, first, second = _two_people()

    refused = document.tables.fill_by_path({"성명 > right": "홍길동"})

    assert refused["applied_count"] == 0
    failure = refused["failed"][0]
    assert failure["reason"] == "ambiguous label"
    assert [(c["table_index"], c["row"], c["col"], c["selector"]) for c in failure["candidates"]] == [
        (0, 0, 0, "성명[1]"),
        (1, 0, 0, "성명[2]"),
    ]
    assert first.cell(0, 1).text == "" and second.cell(0, 1).text == ""

    picked = document.tables.fill_by_path({"성명[2] > right": "김보호", "성명 [1] > right": "홍길동"})

    assert picked["failed"] == []
    assert first.cell(0, 1).text == "홍길동"
    assert second.cell(0, 1).text == "김보호"


def test_an_occurrence_past_the_last_match_is_refused_and_a_literal_bracket_label_still_works() -> None:
    document, first, _second = _two_people()

    too_far = document.tables.fill_by_path({"성명[3] > right": "x"})
    missing = document.tables.fill_by_path({"없는이름표[1] > right": "x"})

    assert too_far["failed"] == [{"path": "성명[3] > right", "reason": "label occurrence out of range: 3 of 2"}]
    assert missing["failed"] == [{"path": "없는이름표[1] > right", "reason": "label not found"}]

    literal = document.add_table(1, 2)
    literal.cell(0, 0).text = "항목[1]"
    result = document.tables.fill_by_path({"항목[1] > right": "값"})
    assert result["failed"] == []
    assert literal.cell(0, 1).text == "값"
    assert first.cell(0, 1).text == ""


def test_form_slots_lists_each_blank_once_with_a_path_that_fills_it() -> None:
    document, table = _form()
    table.cell(2, 2).text = "비고"

    listed = document.tables.form_slots()

    assert listed["count"] == len(listed["slots"])
    by_target = {(slot["target_cell"]["row"], slot["target_cell"]["col"]): slot for slot in listed["slots"]}
    assert by_target[(0, 1)]["path"] == "성 명 > right"
    assert by_target[(0, 3)]["path"] == "주 소 > right"
    assert by_target[(2, 1)]["path"] == "프로젝트 이름 > right"
    assert by_target[(2, 3)]["path"] == "비고 > right"
    # (1, 1) already has a value. (1, 2) sits beside that value: the list reads structure and
    # leaves it to the caller whether a cell with text is a label. (1, 3) has no text beside it.
    assert (1, 1) not in by_target
    assert by_target[(1, 2)]["label"] == "010-0000-0000"
    assert (1, 3) not in by_target

    values = {slot["path"]: f"값{number}" for number, slot in enumerate(listed["slots"])}
    result = document.tables.fill_by_path(values)

    assert result["failed"] == []
    for (row, col), slot in by_target.items():
        assert table.cell(row, col).text == values[slot["path"]]
    remaining = {
        (slot["target_cell"]["row"], slot["target_cell"]["col"])
        for slot in document.tables.form_slots()["slots"]
    }
    assert not remaining & set(by_target)


def test_form_slots_numbers_repeated_labels_and_skips_cells_that_hold_objects() -> None:
    document, first, second = _two_people()
    holder = document.add_table(1, 2)
    holder.cell(0, 0).text = "첨부"
    holder.cell(0, 1).add_table(1, 1)

    slots = document.tables.form_slots()["slots"]

    assert [slot["path"] for slot in slots if slot["label"].replace(" ", "") == "성명"] == [
        "성명[1] > right",
        "성 명[2] > right",
    ]
    assert all(slot["label"] != "첨부" for slot in slots)

    result = document.tables.fill_by_path({slot["path"]: "값" for slot in slots if slot["path"]})
    assert result["failed"] == []
    assert first.cell(0, 1).text == "값" and second.cell(0, 1).text == "값"


def test_a_label_that_cannot_be_a_path_is_listed_without_one() -> None:
    document = HwpxDocument.new()
    table = document.add_table(1, 2)
    table.cell(0, 0).text = "< 보 기 >"
    colon = document.add_table(1, 2)
    colon.cell(0, 0).text = ":"

    slot, colon_slot = document.tables.form_slots()["slots"]

    assert slot["path"] is None
    assert colon_slot["path"] is None
    assert (slot["table_index"], slot["target_cell"]["row"], slot["target_cell"]["col"]) == (0, 0, 1)


def test_filled_form_survives_save_and_reopen(tmp_path: Path) -> None:
    document, _table = _form()
    slots = document.tables.form_slots()["slots"]
    document.tables.fill_by_path({slot["path"]: "값" for slot in slots})
    target = tmp_path / "filled.hwpx"
    document.save_to_path(target)

    with HwpxDocument.open(target) as reopened:
        for slot in slots:
            cell = slot["target_cell"]
            assert reopened.tables[0].cell(cell["row"], cell["col"]).text == "값"


def test_paths_are_resolved_before_any_value_is_written() -> None:
    document = HwpxDocument.new()
    table = document.add_table(1, 3)
    table.cell(0, 0).text = "가"
    table.cell(0, 1).text = "나"

    # "가 > right" overwrites the cell that reads "나"; "나 > right" still means the cell it named.
    result = document.tables.fill_by_path({"가 > right": "값1", "나 > right": "값2", "값1 > right": "x"})

    assert [entry["path"] for entry in result["applied"]] == ["가 > right", "나 > right"]
    assert result["failed"] == [{"path": "값1 > right", "reason": "label not found"}]
    assert table.cell(0, 1).text == "값1"
    assert table.cell(0, 2).text == "값2"


def test_filling_many_slots_reads_the_tables_once(monkeypatch) -> None:
    from hwpx.tools import table_navigation

    document = HwpxDocument.new()
    table = document.add_table(40, 2)
    for row in range(40):
        table.cell(row, 0).text = f"항목{row}"
    built = []
    original = table_navigation._LabelIndex.__init__

    def counting(self, tables):
        built.append(1)
        original(self, tables)

    monkeypatch.setattr(table_navigation._LabelIndex, "__init__", counting)

    slots = document.tables.form_slots()["slots"]
    result = document.tables.fill_by_path({slot["path"]: "값" for slot in slots})

    assert result["applied_count"] == 40
    assert len(built) == 2  # one for the listing, one for the whole fill


def test_form_slots_leaves_out_spacer_cells_and_says_how_wide_a_blank_is() -> None:
    document = HwpxDocument.new()
    table = document.add_table(1, 3)
    table.cell(0, 0).text = "연계유형"
    for col, width in ((1, 600), (2, 20000)):  # about 2 mm and 70 mm
        table.cell(0, col).element.find(
            "{http://www.hancom.co.kr/hwpml/2011/paragraph}cellSz"
        ).set("width", str(width))

    assert document.tables.form_slots()["slots"] == []

    every = document.tables.form_slots(min_width_mm=0)["slots"]
    assert [(slot["target_cell"]["col"], slot["width_mm"]) for slot in every] == [(1, 2.1)]
    # The path still reaches the narrow cell when the caller means it.
    assert document.tables.fill_by_path({every[0]["path"]: "v"})["failed"] == []


def test_fit_policy_measures_each_value_and_refuses_what_does_not_fit() -> None:
    from hwpx.form_fit import FitPolicy

    document = HwpxDocument.new()
    table = document.add_table(2, 2)
    table.cell(0, 0).text = "성명"
    table.cell(1, 0).text = "주소"
    long_value = "서울특별시 종로구 세종대로 209 정부서울청사 별관 3층 민원실 " * 20

    result = document.tables.fill_by_path(
        {"성명 > right": "홍길동", "주소 > right": long_value},
        fit=FitPolicy(mode="fail_on_overflow"),
    )

    assert [entry["path"] for entry in result["applied"]] == ["성명 > right"]
    assert result["applied"][0]["fit"]["ok"] is True
    assert result["failed"][0]["reason"] == "value does not fit"
    assert result["failed"][0]["fit"]["ok"] is False
    assert table.cell(0, 1).text == "홍길동"
    assert table.cell(1, 1).text == ""

    plain = document.tables.fill_by_path({"주소 > right": long_value})
    assert plain["failed"] == [] and "fit" not in plain["applied"][0]
    assert table.cell(1, 1).text == long_value
