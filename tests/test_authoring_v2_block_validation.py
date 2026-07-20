"""Characterization tests for hwpx.authoring._validate_v2_block.

Pins the issue codes produced for every block type and every branch
(required-field guards and computed-field checks) ahead of a complexity
refactor (S-088 P3). These tests must pass unchanged before and after
the refactor -- the goal is a pure decomposition, not a behavior change.
"""

from __future__ import annotations

from hwpx import validate_document_plan

DOCUMENT_PLAN_V2_SCHEMA_VERSION = "hwpx.document_plan.v2"


def _plan(blocks: list) -> dict:
    return {
        "schemaVersion": DOCUMENT_PLAN_V2_SCHEMA_VERSION,
        "sections": [{"blocks": blocks}],
    }


def _codes(blocks: list) -> set[str]:
    report = validate_document_plan(_plan(blocks))
    return {issue.code for issue in report.issues}


def test_block_not_object():
    assert "block_not_object" in _codes(["not-a-mapping"])


def test_unsupported_block_type():
    assert "unsupported_block_type" in _codes([{"type": "bogus"}])


def test_heading_missing_text():
    assert "missing_text" in _codes([{"type": "heading"}])
    assert "missing_text" in _codes([{"type": "heading", "text": "   "}])


def test_heading_ok():
    assert _codes([{"type": "heading", "text": "제목"}]) == set()


def test_image_missing_path():
    assert "missing_text" in _codes([{"type": "image"}])


def test_image_ok():
    assert _codes([{"type": "image", "path": "img.png"}]) == set()


def test_image_grid_missing_images_not_list():
    assert "missing_image_grid_images" in _codes([{"type": "image_grid"}])
    assert "missing_image_grid_images" in _codes([{"type": "image_grid", "images": []}])


def test_image_grid_missing_image_path():
    assert "missing_image_path" in _codes(
        [{"type": "image_grid", "images": [{"caption": "no path"}]}]
    )


def test_image_grid_ok():
    assert (
        _codes([{"type": "imageGrid", "images": [{"path": "a.png"}]}]) == set()
    )


def test_bullets_missing_items():
    for type_name in ("bullets", "bullet", "numbered_list", "numberedList"):
        assert "missing_list_items" in _codes([{"type": type_name}])


def test_bullets_ok():
    assert _codes([{"type": "bullets", "items": ["one"]}]) == set()


def test_table_missing_content():
    assert "missing_table_content" in _codes([{"type": "table"}])


def test_table_ok_with_header_only():
    assert _codes([{"type": "table", "header": ["a"]}]) == set()


def test_table_ok_with_rows_only():
    assert _codes([{"type": "table", "rows": [["a"]]}]) == set()


def test_toc_invalid_native_flag():
    assert "invalid_native_flag" in _codes([{"type": "toc", "native": "yes"}])


def test_toc_ok():
    assert _codes([{"type": "toc"}]) == set()


def test_approval_box_ok_no_required_fields():
    # approval_box has no required-field guard branch.
    assert _codes([{"type": "approval_box"}]) == set()
    assert _codes([{"type": "approvalBox"}]) == set()


# -- computed-field dispatch per block type ---------------------------------


def test_heading_computed_field_error():
    assert "unknown_computed_field" in _codes(
        [{"type": "heading", "text": "{{ bogus() }}"}]
    )


def test_paragraph_computed_field_error_in_text_and_runs():
    assert "unknown_computed_field" in _codes(
        [{"type": "paragraph", "text": "{{ bogus() }}"}]
    )
    assert "unknown_computed_field" in _codes(
        [
            {
                "type": "paragraph",
                "text": "ok",
                "children": [{"text": "{{ bogus() }}"}],
            }
        ]
    )
    # 'runs' is accepted when 'children' is absent.
    assert "unknown_computed_field" in _codes(
        [
            {
                "type": "paragraph",
                "text": "ok",
                "runs": [{"text": "{{ bogus() }}"}],
            }
        ]
    )


def test_bullets_computed_field_error():
    assert "unknown_computed_field" in _codes(
        [{"type": "bullets", "items": ["{{ bogus() }}"]}]
    )


def test_table_computed_field_error_in_header_and_rows():
    assert "unknown_computed_field" in _codes(
        [{"type": "table", "header": ["{{ bogus() }}"]}]
    )
    assert "unknown_computed_field" in _codes(
        [{"type": "table", "header": ["a"], "rows": [["{{ bogus() }}"]]}]
    )


def test_image_grid_computed_field_error_in_caption():
    assert "unknown_computed_field" in _codes(
        [
            {
                "type": "image_grid",
                "images": [{"path": "a.png", "caption": "{{ bogus() }}"}],
            }
        ]
    )


def test_approval_box_computed_field_error_in_labels_and_delegated():
    assert "unknown_computed_field" in _codes(
        [{"type": "approval_box", "labels": ["{{ bogus() }}"]}]
    )
    assert "unknown_computed_field" in _codes(
        [{"type": "approval_box", "delegated": "{{ bogus() }}"}]
    )


def test_toc_computed_field_error_in_title_and_entries():
    assert "unknown_computed_field" in _codes(
        [{"type": "toc", "title": "{{ bogus() }}"}]
    )
    assert "unknown_computed_field" in _codes(
        [{"type": "toc", "entries": [{"text": "{{ bogus() }}"}]}]
    )
