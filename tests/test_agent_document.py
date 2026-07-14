from __future__ import annotations

import json
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.agent.document import HwpxAgentDocument
from hwpx.agent.model import AgentContractError
from hwpx.oxml.namespaces import HP

REVISION = "sha256:" + "a" * 64


def _build_semantic_document() -> HwpxDocument:
    document = HwpxDocument.new()
    first = document.sections[0].paragraphs[0]
    first.element.set("id", "101")
    first.text = "수행 평가 계획"
    second = document.add_paragraph("설명 문단")
    second.element.set("id", "102")
    second.add_rectangle(width=7200, height=3600, fill_color="#FFFFFF")
    second.add_footnote("근거 각주")
    table = document.add_table(2, 2)
    table.element.set("id", "201")
    table.rows[0].cells[0].text = "항목"
    table.rows[0].cells[1].text = "내용"
    table.rows[1].cells[0].text = "평가"
    table.rows[1].cells[1].text = "프로젝트"
    document.sections[0].add_memo("검토 메모", memo_id="301", attributes={"author": "검토자"})

    field_run = second.element.makeelement(f"{HP}run", {"charPrIDRef": "0"})
    control = field_run.makeelement(f"{HP}ctrl", {"type": "FORM"})
    field_run.append(control)
    second.element.append(field_run)
    field_begin = control.makeelement(
        f"{HP}fieldBegin",
        {"id": "field-1", "fieldName": "담당자", "type": "FORM", "editable": "true"},
    )
    control.append(field_begin)
    second.section.mark_dirty()

    mystery = second.runs[0].element.makeelement(f"{HP}mysteryObject", {})
    second.runs[0].element.append(mystery)
    second.section.mark_dirty()
    return document


def test_projection_covers_semantic_kinds_without_raw_leakage() -> None:
    with _build_semantic_document() as document:
        agent = HwpxAgentDocument.from_document(document, revision=REVISION)
        payload = agent.get("/", depth=8, child_limit=200).to_dict()
        kinds = {record.kind for record in agent.records}

    assert {
        "document",
        "section",
        "paragraph",
        "run",
        "table",
        "row",
        "cell",
        "form-field",
        "shape",
        "memo",
        "footnote",
    } <= kinds
    assert payload["coverage"]["unsupportedChildren"] == 0
    body = next(
        node for node in agent.records if node.kind == "paragraph" and node.attributes.get("id") == "102"
    )
    assert body.unsupported_child_count == 1
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "<hp:" not in serialized
    assert "namespaceUri" not in serialized
    assert "packagePath" not in serialized


def test_projection_and_form_api_cover_fields_nested_in_table_cells() -> None:
    with HwpxDocument.new() as document:
        table = document.add_table(1, 1)
        table.element.set("id", "nested-table")
        paragraph = table.rows[0].cells[0].paragraphs[0]
        paragraph.text = "승인 담당: "

        begin_run = paragraph.element.makeelement(f"{HP}run", {"charPrIDRef": "0"})
        begin_ctrl = begin_run.makeelement(f"{HP}ctrl", {})
        begin_ctrl.append(
            begin_ctrl.makeelement(
                f"{HP}fieldBegin",
                {
                    "id": "nested-field",
                    "fieldid": "nested-field-native",
                    "name": "표셀담당",
                    "type": "CLICK_HERE",
                    "editable": "1",
                },
            )
        )
        begin_run.append(begin_ctrl)
        paragraph.element.append(begin_run)
        paragraph.add_run("교육과정부장")
        end_run = paragraph.element.makeelement(f"{HP}run", {"charPrIDRef": "0"})
        end_ctrl = end_run.makeelement(f"{HP}ctrl", {})
        end_ctrl.append(
            end_ctrl.makeelement(
                f"{HP}fieldEnd",
                {"beginIDRef": "nested-field", "fieldid": "nested-field-native"},
            )
        )
        end_run.append(end_ctrl)
        paragraph.element.append(end_run)
        paragraph.section.mark_dirty()

        fields = document.list_form_fields()
        agent = HwpxAgentDocument.from_document(document, revision=REVISION)
        projected = [record for record in agent.records if record.kind == "form-field"]

    assert [field["name"] for field in fields] == ["표셀담당"]
    assert fields[0]["current_value"] == "교육과정부장"
    assert len(projected) == 1
    assert projected[0].summary["name"] == "표셀담당"
    assert "/table" in projected[0].path and "/cell[1]/" in projected[0].path


def test_paths_are_deterministic_across_save_and_reopen(tmp_path: Path) -> None:
    first_path = tmp_path / "first.hwpx"
    second_path = tmp_path / "second.hwpx"
    with _build_semantic_document() as document:
        document.save_to_path(first_path)
    with HwpxAgentDocument.open(first_path) as first:
        paths_before = [record.path for record in first.records]
        first.document.save_to_path(second_path)
    with HwpxAgentDocument.open(second_path) as second:
        paths_after = [record.path for record in second.records]

    assert paths_after == paths_before


def test_duplicate_native_ids_become_positional_and_id_path_is_ambiguous() -> None:
    with HwpxDocument.new() as document:
        first = document.sections[0].paragraphs[0]
        second = document.add_paragraph("둘")
        first.element.set("id", "duplicate")
        second.element.set("id", "duplicate")
        agent = HwpxAgentDocument.from_document(document, revision=REVISION)
        paragraphs = [record for record in agent.records if record.kind == "paragraph"]

        assert [record.stability for record in paragraphs[:2]] == ["positional", "positional"]
        with pytest.raises(AgentContractError) as error:
            agent.resolve_record('/section[1]/paragraph[@id="duplicate"]')
        assert error.value.code == "ambiguous_target"


def test_get_depth_child_limits_and_coverage_are_exact() -> None:
    with HwpxDocument.new() as document:
        for index in range(5):
            document.add_paragraph(f"문단 {index}")
        agent = HwpxAgentDocument.from_document(document, revision=REVISION)
        section = agent.get("/section[1]", depth=1, child_limit=2)

        assert len(section.children) == 2
        assert section.child_count == 6
        assert section.truncated_child_count == 4
        assert (
            len(section.children)
            + section.unsupported_child_count
            + section.truncated_child_count
            == section.child_count
        )


def test_query_normalization_filtering_revision_and_truncation() -> None:
    with HwpxDocument.new() as document:
        document.sections[0].paragraphs[0].text = "수행   평가"
        document.add_paragraph("수행 평가")
        document.add_paragraph("기타")
        agent = HwpxAgentDocument.from_document(document, revision=REVISION)

        result = agent.query('paragraph:contains("수행 평가")', limit=1)
        assert len(result.nodes) == 1
        assert result.truncated is True
        with pytest.raises(AgentContractError) as error:
            agent.query("paragraph", limit=5, expected_revision="sha256:" + "b" * 64)
        assert error.value.code == "stale_revision"


@pytest.mark.parametrize(
    ("kwargs", "target"),
    [
        ({"depth": 9}, "depth"),
        ({"child_limit": 0}, "childLimit"),
    ],
)
def test_projection_resource_limits_fail_closed(kwargs: dict[str, int], target: str) -> None:
    with HwpxDocument.new() as document:
        agent = HwpxAgentDocument.from_document(document, revision=REVISION)
        with pytest.raises(AgentContractError) as error:
            agent.get("/", **kwargs)
        assert error.value.target == target
