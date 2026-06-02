# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from pathlib import Path

import pytest
from lxml import etree

from hwpx.form_fill import (
    MISSING_CHAR_PR_ID_REF,
    fill_section_bytes,
    find_split_placeholders,
    heterogeneous_warnings,
)

# Clean-room reference metadata, ideas only:
# - chrisryugj/kordoc @ 31ec46a0a55cfa92d37b4a5ad34f4a5de9db4133, MIT:
#   HWPX text-node fill preserves original formatting; split text ranges can be
#   mapped with paragraph-level offsets.
# - sakada3/hwp-ops @ 8a5fd2ba82a4b6007d9c4eecf71a0b72e50a7a1e, Apache-2.0:
#   split-run placeholder scanning, charPrIDRef heterogeneity warnings, and
#   run-preserving fragment edits. No source code copied.

HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HS = "http://www.hancom.co.kr/hwpml/2011/section"

SAME_STYLE_SECTION = """
<hs:sec xmlns:hs="{hs}" xmlns:hp="{hp}">
  <hp:p>
    <hp:run charPrIDRef="3"><hp:t>안녕 {{{{na</hp:t></hp:run>
    <hp:run charPrIDRef="3"><hp:t>me</hp:t></hp:run>
    <hp:run charPrIDRef="3"><hp:t>}}}} 님</hp:t></hp:run>
  </hp:p>
</hs:sec>
""".format(hs=HS, hp=HP).encode()

MIXED_STYLE_SECTION = """
<hs:sec xmlns:hs="{hs}" xmlns:hp="{hp}">
  <hp:p>
    <hp:run charPrIDRef="3"><hp:t>{{{{na</hp:t></hp:run>
    <hp:run charPrIDRef="7"><hp:t>me}}}}</hp:t></hp:run>
  </hp:p>
</hs:sec>
""".format(hs=HS, hp=HP).encode()

PREFIX_SUFFIX_SECTION = """
<hs:sec xmlns:hs="{hs}" xmlns:hp="{hp}">
  <hp:p>
    <hp:run charPrIDRef="3"><hp:t>이름: {{{{na</hp:t></hp:run>
    <hp:run charPrIDRef="3"><hp:t>me}}}}</hp:t></hp:run>
    <hp:lineSegArray><hp:lineseg textpos="0"/></hp:lineSegArray>
    <hp:run charPrIDRef="9"><hp:t> 님</hp:t></hp:run>
  </hp:p>
</hs:sec>
""".format(hs=HS, hp=HP).encode()

SINGLE_RUN_SECTION = """
<hs:sec xmlns:hs="{hs}" xmlns:hp="{hp}">
  <hp:p><hp:run charPrIDRef="5"><hp:t>부서: {{{{dept}}}}</hp:t></hp:run></hp:p>
</hs:sec>
""".format(hs=HS, hp=HP).encode()

TWO_PLACEHOLDERS_SECTION = """
<hs:sec xmlns:hs="{hs}" xmlns:hp="{hp}">
  <hp:p>
    <hp:run charPrIDRef="1"><hp:t>{{{{first}}}}</hp:t></hp:run>
    <hp:run charPrIDRef="2"><hp:t> / {{{{se</hp:t></hp:run>
    <hp:run charPrIDRef="2"><hp:t>cond}}}}</hp:t></hp:run>
  </hp:p>
</hs:sec>
""".format(hs=HS, hp=HP).encode()

TWO_PLACEHOLDERS_ONE_TEXT_NODE_SECTION = """
<hs:sec xmlns:hs="{hs}" xmlns:hp="{hp}">
  <hp:p>
    <hp:run charPrIDRef="4"><hp:t>{{{{first}}}} and {{{{second}}}}</hp:t></hp:run>
  </hp:p>
</hs:sec>
""".format(hs=HS, hp=HP).encode()

COMMENTED_SECTION = """
<hs:sec xmlns:hs="{hs}" xmlns:hp="{hp}">
  <!-- generated comment should not affect local-name traversal -->
  <hp:p>
    <hp:run charPrIDRef="6"><hp:t>{{{{name}}}}</hp:t></hp:run>
  </hp:p>
</hs:sec>
""".format(hs=HS, hp=HP).encode()

NESTED_TABLE_SECTION = """
<hs:sec xmlns:hs="{hs}" xmlns:hp="{hp}">
  <hp:p>
    <hp:run charPrIDRef="1"><hp:t>outer {{{{outer}}}}</hp:t></hp:run>
    <hp:run charPrIDRef="1">
      <hp:tbl>
        <hp:tr>
          <hp:tc>
            <hp:subList>
              <hp:p><hp:run charPrIDRef="2"><hp:t>cell {{{{cell}}}}</hp:t></hp:run></hp:p>
            </hp:subList>
          </hp:tc>
        </hp:tr>
      </hp:tbl>
    </hp:run>
  </hp:p>
</hs:sec>
""".format(hs=HS, hp=HP).encode()

CROSS_NESTED_BOUNDARY_SECTION = """
<hs:sec xmlns:hs="{hs}" xmlns:hp="{hp}">
  <hp:p>
    <hp:run charPrIDRef="1"><hp:t>{{{{na</hp:t></hp:run>
    <hp:run charPrIDRef="1">
      <hp:tbl><hp:tr><hp:tc><hp:subList>
        <hp:p><hp:run charPrIDRef="2"><hp:t>me}}}}</hp:t></hp:run></hp:p>
      </hp:subList></hp:tc></hp:tr></hp:tbl>
    </hp:run>
  </hp:p>
</hs:sec>
""".format(hs=HS, hp=HP).encode()

MISSING_CHAR_REF_SECTION = """
<hs:sec xmlns:hs="{hs}" xmlns:hp="{hp}">
  <hp:p>
    <hp:run><hp:t>{{{{na</hp:t></hp:run>
    <hp:run charPrIDRef="3"><hp:t>me}}}}</hp:t></hp:run>
  </hp:p>
</hs:sec>
""".format(hs=HS, hp=HP).encode()

INLINE_PLACEHOLDER_SECTION = """
<hs:sec xmlns:hs="{hs}" xmlns:hp="{hp}">
  <hp:p>
    <hp:run charPrIDRef="1"><hp:t>{{{{na<hp:lineBreak/>me}}}}</hp:t></hp:run>
  </hp:p>
</hs:sec>
""".format(hs=HS, hp=HP).encode()


def _only(items):
    assert len(items) == 1
    return items[0]


def _section_text(section_bytes: bytes) -> str:
    root = etree.fromstring(section_bytes)
    return "".join(root.xpath(".//*[local-name()='t']/text()"))


def _run_char_refs(section_bytes: bytes) -> list[str | None]:
    root = etree.fromstring(section_bytes)
    return [run.get("charPrIDRef") for run in root.xpath(".//*[local-name()='run']")]


def _linesegarray_count(section_bytes: bytes) -> int:
    root = etree.fromstring(section_bytes)
    return sum(1 for element in root.iter() if etree.QName(element).localname.lower() == "linesegarray")


def test_finds_placeholder_split_across_runs() -> None:
    found = find_split_placeholders(SAME_STYLE_SECTION)
    target = _only(found)

    assert target.key == "{{name}}"
    assert target.split is True
    assert target.paragraph_index == 0
    assert target.start == 3
    assert target.end == 11
    assert target.charprid_refs == ("3",)
    assert len(target.fragments) == 3
    assert [fragment.run_index for fragment in target.fragments] == [0, 1, 2]


def test_single_run_placeholder_is_not_split() -> None:
    target = _only(find_split_placeholders(SINGLE_RUN_SECTION))

    assert target.key == "{{dept}}"
    assert target.split is False
    assert target.charprid_refs == ("5",)
    assert len(target.fragments) == 1


def test_finds_multiple_placeholders_in_one_paragraph() -> None:
    found = find_split_placeholders(TWO_PLACEHOLDERS_SECTION)

    assert [placeholder.key for placeholder in found] == ["{{first}}", "{{second}}"]
    assert [placeholder.split for placeholder in found] == [False, True]


def test_invalid_xml_raises_value_error() -> None:
    with pytest.raises(ValueError, match="invalid section XML"):
        find_split_placeholders(b"<hs:sec>")


def test_xml_comments_do_not_affect_traversal() -> None:
    target = _only(find_split_placeholders(COMMENTED_SECTION))

    assert target.key == "{{name}}"
    assert target.charprid_refs == ("6",)


def test_nested_table_paragraph_is_scanned_as_its_own_paragraph() -> None:
    found = find_split_placeholders(NESTED_TABLE_SECTION)

    assert [(placeholder.key, placeholder.paragraph_index) for placeholder in found] == [
        ("{{outer}}", 0),
        ("{{cell}}", 1),
    ]


def test_placeholder_does_not_span_into_nested_table_paragraph() -> None:
    assert find_split_placeholders(CROSS_NESTED_BOUNDARY_SECTION) == []


def test_warns_when_placeholder_crosses_multiple_charprid_refs() -> None:
    placeholders = find_split_placeholders(MIXED_STYLE_SECTION)
    warnings = heterogeneous_warnings(placeholders)

    warning = _only(warnings)
    assert warning.key == "{{name}}"
    assert warning.paragraph_index == 0
    assert warning.charprid_refs == ("3", "7")
    assert "charPrIDRef" in warning.message


def test_missing_charprid_ref_participates_in_heterogeneity_warning() -> None:
    placeholders = find_split_placeholders(MISSING_CHAR_REF_SECTION)
    warnings = heterogeneous_warnings(placeholders)

    warning = _only(warnings)
    assert warning.charprid_refs == (MISSING_CHAR_PR_ID_REF, "3")


def test_inline_placeholder_content_is_explicitly_unsupported() -> None:
    with pytest.raises(ValueError, match="inline hp:t placeholder content"):
        find_split_placeholders(INLINE_PLACEHOLDER_SECTION)


def test_fill_replaces_split_placeholder_preserving_first_run_ref() -> None:
    out, report = fill_section_bytes(PREFIX_SUFFIX_SECTION, {"{{name}}": "홍길동"})

    assert report.replacements == 1
    assert report.placeholders_found == 1
    assert report.missing_keys == ()
    assert _section_text(out) == "이름: 홍길동 님"
    assert "{{" not in _section_text(out)
    assert _run_char_refs(out) == ["3", "3", "9"]
    assert _linesegarray_count(out) == 0


def test_fill_preserves_unmapped_placeholder_and_reports_missing_key() -> None:
    out, report = fill_section_bytes(PREFIX_SUFFIX_SECTION, {})

    assert report.replacements == 0
    assert report.placeholders_found == 1
    assert report.missing_keys == ("{{name}}",)
    assert _section_text(out) == "이름: {{name}} 님"
    assert _run_char_refs(out) == ["3", "3", "9"]


def test_fill_handles_multiple_placeholders_from_right_to_left() -> None:
    out, report = fill_section_bytes(
        TWO_PLACEHOLDERS_SECTION,
        {"{{first}}": "하나", "{{second}}": "둘"},
    )

    assert report.replacements == 2
    assert _section_text(out) == "하나 / 둘"
    assert _run_char_refs(out) == ["1", "2", "2"]


def test_fill_handles_multiple_placeholders_in_same_text_node() -> None:
    out, report = fill_section_bytes(
        TWO_PLACEHOLDERS_ONE_TEXT_NODE_SECTION,
        {"{{first}}": "A", "{{second}}": "LONGER"},
    )

    assert report.replacements == 2
    assert _section_text(out) == "A and LONGER"
    assert _run_char_refs(out) == ["4"]


def test_fixture_split_run_placeholder_is_detected_and_explicitly_fillable() -> None:
    section_path = (
        Path(__file__).parent
        / "template_automation"
        / "fixtures"
        / "split-run-placeholder"
        / "package"
        / "Contents"
        / "section0.xml"
    )
    section_bytes = section_path.read_bytes()

    found = find_split_placeholders(section_bytes)
    assert any(placeholder.key == "{{NAME}}" and placeholder.split for placeholder in found)

    out, report = fill_section_bytes(section_bytes, {"{{NAME}}": "ALICE001"})
    assert report.replacements == 1
    assert "ALICE001" in _section_text(out)
    assert "{{NAME}}" not in _section_text(out)
