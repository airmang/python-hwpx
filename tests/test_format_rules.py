# SPDX-License-Identifier: Apache-2.0
"""Checking a document's formatting against a rule file (hwpx.tools.format_rules)."""

from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path

import pytest

from hwpx import HwpxDocument
from hwpx.errors import HwpxValueError
from hwpx.tools.format_rules import SUPPORTED_RULES, check_format, load_rules, main

CORPUS = Path(__file__).parent / "fixtures" / "hwpxlib_corpus"


def _document(build=None) -> bytes:
    doc = HwpxDocument.new()
    doc.add_paragraph("본문 첫 문단")
    if build is not None:
        build(doc)
    return doc.to_bytes()


def _rewrite(data: bytes, member: str, change) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as src, zipfile.ZipFile(out, "w") as dst:
        for info in src.infolist():
            payload = src.read(info.filename)
            if info.filename == member:
                changed = change(payload.decode("utf-8"))
                assert changed != payload.decode("utf-8"), "the rewrite changed nothing"
                payload = changed.encode("utf-8")
            dst.writestr(info, payload)
    return out.getvalue()


def _rules_of(report) -> list[str]:
    return [violation.rule for violation in report.violations]


def test_a_new_document_follows_rules_that_describe_it() -> None:
    report = check_format(
        _document(),
        {
            "charshape": {"fontsize": 1000, "ratio": 100, "spacing": 0, "bold": False, "underline": False},
            "parashape": {"horizontal": "양쪽 정렬", "linespacing": "글자에 따라", "linespacingvalue": 160,
                          "indent": 0, "outdent": 0, "spacing-paraup": 0, "spacing-parabottom": 0},
            "hyperlink": {"permission": False},
            "macro": {"permission": False},
        },
    )

    assert report.ok
    assert report.violations == ()
    assert report.unsupported_rules == ()
    assert "charshape.fontsize" in report.checked_rules


def test_font_size_outside_the_rule_is_reported_with_the_text() -> None:
    report = check_format(_document(), {"charshape": {"fontsize": {"min": 1100, "max": 1500}}})

    assert not report.ok
    assert _rules_of(report) == ["charshape.fontsize"]
    violation = report.violations[0]
    assert violation.actual == 1000
    assert violation.expected == {"min": 1100, "max": 1500}
    assert violation.text == "본문 첫 문단"
    assert (violation.section, violation.in_table) == (0, False)


def test_font_must_be_one_of_the_listed_faces() -> None:
    data = _document()
    with zipfile.ZipFile(io.BytesIO(data)) as package:
        header = package.read("Contents/header.xml").decode("utf-8")
    faces = set(re.findall(r'<hh:font id="\d+" face="([^"]+)"', header))

    assert check_format(data, {"charshape": {"font": sorted(faces)}}).ok
    report = check_format(data, {"charshape": {"font": ["없는글꼴"]}})
    assert _rules_of(report) == ["charshape.font"]
    assert report.violations[0].actual in faces


def test_only_runs_with_text_are_checked_for_character_shape() -> None:
    # The first paragraph of a new document holds the section settings and an empty run.
    report = check_format(_document(), {"charshape": {"fontsize": 1}})

    assert len(report.violations) == 1


def test_paragraph_shape_reads_the_first_line_value_as_indent_or_outdent() -> None:
    def hang(xml: str) -> str:
        return xml.replace('<hc:intent value="0"', '<hc:intent value="-2000"')

    data = _rewrite(_document(), "Contents/header.xml", hang)

    assert check_format(data, {"parashape": {"outdent": 2000, "indent": 0}}).ok
    assert set(_rules_of(check_format(data, {"parashape": {"outdent": 0}}))) == {"parashape.outdent"}


def test_alignment_and_line_spacing_accept_dvc_names_indices_and_file_names() -> None:
    data = _document()

    for spelling in ("양쪽 정렬", 0, "JUSTIFY"):
        assert check_format(data, {"parashape": {"horizontal": spelling}}).ok
    report = check_format(data, {"parashape": {"horizontal": "가운데 정렬", "linespacingvalue": {"min": 180, "max": 200}}})
    assert set(_rules_of(report)) == {"parashape.horizontal", "parashape.linespacingvalue"}
    assert {violation.actual for violation in report.violations} == {"JUSTIFY", 160}


def test_text_in_a_table_is_checked_and_marked_as_in_table() -> None:
    def build(doc: HwpxDocument) -> None:
        table = doc.add_table(1, 1)
        table.cell(0, 0).text = "칸 글"

    report = check_format(_document(build), {"charshape": {"fontsize": 1}, "table": {"treatAsChar": False}})

    in_table = [violation for violation in report.violations if violation.rule == "charshape.fontsize" and violation.text == "칸 글"]
    assert in_table and all(violation.in_table for violation in in_table)
    assert "table.treatAsChar" in _rules_of(report)


def test_nested_tables_are_reported_when_the_rule_forbids_them() -> None:
    rules = {"table": {"table-in-table": False}}
    flat = check_format(CORPUS / "reader_writer__SimpleTable.hwpx", rules)
    nested = check_format(CORPUS.parent / "exam" / "A_form.hwpx", rules)

    assert "table.table-in-table" not in _rules_of(flat)
    assert "table.table-in-table" in _rules_of(nested)
    assert all(violation.in_table for violation in nested.violations)


def test_hyperlinks_are_reported_when_not_permitted() -> None:
    def build(doc: HwpxDocument) -> None:
        doc.add_paragraph("앞 ").add_hyperlink("https://example.com", "여기")

    data = _document(build)

    assert check_format(data, {"hyperlink": {"permission": True}}).ok
    report = check_format(data, {"hyperlink": {"permission": False}})
    assert _rules_of(report) == ["hyperlink.permission"]
    assert "여기" in report.violations[0].text


def test_characters_outside_the_allowed_range_are_reported() -> None:
    def build(doc: HwpxDocument) -> None:
        doc.add_paragraph("이모지 \U0001F600 포함")

    report = check_format(_document(build), {"specialcharacter": {"minimum": 32, "maximum": 0xFFFF}})

    assert _rules_of(report) == ["specialcharacter.maximum"]
    assert report.violations[0].actual == "U+1F600"


def test_rules_this_checker_does_not_evaluate_are_listed_not_skipped() -> None:
    report = check_format(
        _document(),
        {"charshape": {"fontsize": 1000, "emboss": False}, "outlineshape": {"leveltype": []}, "style": {"permission": False}},
    )

    assert report.ok
    assert report.checked_rules == ("charshape.fontsize",)
    assert set(report.unsupported_rules) == {"charshape.emboss", "outlineshape", "style"}


@pytest.mark.parametrize(
    "rules",
    [
        {"charshape": {"fontsize": "big"}},
        {"charshape": {"fontsize": {"min": 5, "max": 1}}},
        {"charshape": {"bold": 1}},
        {"parashape": {"horizontal": "비스듬히"}},
        {"charshape": [1, 2]},
    ],
)
def test_a_malformed_rule_is_an_error_not_a_pass(rules: dict) -> None:
    with pytest.raises(HwpxValueError):
        check_format(_document(), rules)


def test_the_violation_list_is_bounded_and_says_so() -> None:
    def build(doc: HwpxDocument) -> None:
        for index in range(30):
            doc.add_paragraph(f"문단 {index}")

    report = check_format(_document(build), {"charshape": {"fontsize": 1}}, max_violations=10)

    assert len(report.violations) == 10
    assert report.truncated
    assert report.to_dict()["violationCount"] == 10


def test_every_supported_rule_name_is_a_dvc_rule_name() -> None:
    # Names copied from hancom-io/dvc Source/JsonModel.h (Apache-2.0); a typo here would silently check nothing.
    dvc = {
        "charshape": {"langtype", "fontsize", "font", "ratio", "spacing", "r-size", "bold", "italic", "underline",
                      "strikeout", "supscript", "subscript"},
        "parashape": {"horizontal", "margin-left", "margin-right", "indent", "outdent", "linespacing",
                      "linespacingvalue", "spacing-paraup", "spacing-parabottom"},
        "table": {"treatAsChar", "table-in-table"},
        "specialcharacter": {"minimum", "maximum"},
        "hyperlink": {"permission"},
        "macro": {"permission"},
    }
    assert {category: set(keys) for category, keys in SUPPORTED_RULES.items()} == dvc


def test_corpus_documents_are_checked_without_error() -> None:
    rules = {"charshape": {"fontsize": {"min": 1, "max": 100000}}, "parashape": {"linespacingvalue": {"min": 0, "max": 100000}}}
    for path in sorted(CORPUS.glob("*.hwpx"))[:25]:
        assert check_format(path, rules).ok, path.name


def test_command_line_reports_and_sets_the_exit_code(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    document = tmp_path / "doc.hwpx"
    document.write_bytes(_document())
    good = tmp_path / "good.json"
    good.write_text(json.dumps({"charshape": {"fontsize": 1000}}), encoding="utf-8")
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"charshape": {"fontsize": 1200}, "style": {"permission": False}}), encoding="utf-8")

    assert main([str(good), str(document)]) == 0
    assert "OK: 0 violation(s)" in capsys.readouterr().out
    assert main([str(bad), str(document), "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["unsupportedRules"] == ["style"]
    assert main([str(tmp_path / "missing.json"), str(document)]) == 2
    assert load_rules(good) == {"charshape": {"fontsize": 1000}}
