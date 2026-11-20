# SPDX-License-Identifier: Apache-2.0
"""What the README, the guides and the errors tell a reader holds when they do it.

Each test is a thing a reader was told and that did not hold before 7.0.0 went out:

* the save the README names for reference checking refused every document, and gave no reason;
* writing the 6.x name of a header's page type was accepted and did nothing;
* ``doc.fields.fill(None, ...)`` put the word "None" in the form;
* a highlight running across two runs came out of the text extractor with two ends for one begin;
* the install command in a "moved to python-hwpx-automation" error kept an installed 7.x companion
  and pulled python-hwpx back to 6.x;
* ``doc.tables.map()`` numbers tables as ``doc.tables.with_nested`` does, which the pages did not say;
* the comparison page's count of the document object's members was not the measured one;
* the release notes body sat 120 bytes under GitHub's limit, in a step that runs after the upload.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

from hwpx import HwpxDocument, QualityPolicy
from hwpx.errors import HwpxAttributeError, HwpxTypeError, SaveError
from hwpx.tools.text_extractor import AnnotationOptions, TextExtractor

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


# -- the quality gate ---------------------------------------------------------------------------


def test_a_policy_that_needs_a_render_says_so_when_it_refuses(tmp_path: Path) -> None:
    document = HwpxDocument.new()
    document.add_paragraph("엄격")
    target = tmp_path / "strict.hwpx"
    with pytest.raises(SaveError) as raised:
        document.save(target, quality=QualityPolicy.strict())
    error = raised.value
    assert error.code == "quality-gate-failed" and not target.exists()
    assert error.context["errors"] == []  # nothing is wrong with the document
    assert "require_visual_complete" in str(error) and "RENDER_ORACLE_UNAVAILABLE" in str(error)
    assert "QualityPolicy(require_visual_complete=False)" in (error.suggestion or "")


def test_the_policy_the_readme_names_saves_and_checks_references(tmp_path: Path) -> None:
    policy = QualityPolicy(require_visual_complete=False)
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("참조")
    report = document.save(tmp_path / "ok.hwpx", quality=policy)
    assert report.quality is not None and report.quality.ok

    paragraph.runs[-1].element.set("charPrIDRef", "987654")  # a character shape the header does not have
    with pytest.raises(SaveError) as raised:
        document.save(tmp_path / "bad.hwpx", quality=policy)
    assert "REFERENCE_INTEGRITY_FAILED" in str(raised.value)
    assert not (tmp_path / "bad.hwpx").exists()


@pytest.mark.parametrize("readme", ["README.md", "README_EN.md", "docs/usage.md"])
def test_no_page_sends_the_reader_to_the_policy_that_cannot_pass(readme: str) -> None:
    assert "QualityPolicy.strict())" not in (ROOT / readme).read_text(encoding="utf-8")


# -- a removed name is refused when written, too ------------------------------------------------


def test_writing_the_6x_name_of_a_headers_page_type_is_refused() -> None:
    document = HwpxDocument.new()
    header = document.page.set_header(text="머리말")
    with pytest.raises(HwpxAttributeError) as raised:
        header.apply_page_type = "ODD"  # 6.x: wrote applyPageType. 7.0 before this: kept aside, wrote nothing
    assert "page_type" in str(raised.value)
    assert "apply_page_type" not in vars(header)
    header.page_type = "ODD"
    reopened = HwpxDocument.open(document.to_bytes())
    assert [h.page_type for h in reopened.page.headers()] == ["ODD"]


# -- a field value ------------------------------------------------------------------------------


def test_filling_a_field_with_none_is_refused_and_leaves_the_field() -> None:
    document = HwpxDocument.new()
    document.fields.add("연락처", prompt="적으세요", paragraph=document.add_paragraph("연락처: "))
    before = document.to_bytes()
    with pytest.raises(HwpxTypeError):
        document.fields.fill(None, name="연락처")  # type: ignore[arg-type]
    assert document.to_bytes() == before
    document.fields.fill("", name="연락처")  # the way to empty it
    document.fields.fill(120, name="연락처")  # type: ignore[arg-type]  # a number is still written as its digits
    assert "120" in HwpxDocument.open(document.to_bytes()).text.plain()


# -- highlight markers --------------------------------------------------------------------------


def _marked(path: Path) -> str:
    with TextExtractor(str(path)) as extractor:
        return extractor.extract_text(annotations=AnnotationOptions(highlight="markers"))


def test_a_highlight_across_two_runs_has_one_begin_and_one_end() -> None:
    text = _marked(FIXTURES / "hancom_saved" / "highlight_across_runs.hwpx")
    assert "앞부[HIGHLIGHT color=#FFFF00]분글자굵은부[/HIGHLIGHT]분글자뒷부분글자" in text
    assert text.count("[HIGHLIGHT") == text.count("[/HIGHLIGHT]") == 1


def test_highlight_markers_pair_up_in_every_document_hangul_saved() -> None:
    checked = 0
    for path in sorted((FIXTURES / "hancom_saved").glob("*highlight*.hwpx")):
        text = _marked(path)
        assert text.count("[HIGHLIGHT") == text.count("[/HIGHLIGHT]"), path.name
        depth = 0
        for token in text.replace("[/HIGHLIGHT]", "\0E").replace("[HIGHLIGHT", "\0B").split("\0")[1:]:
            depth += 1 if token.startswith("B") else -1
            assert depth >= 0, path.name  # never an end before its begin
        checked += 1
    assert checked >= 1


def test_a_highlight_made_here_across_runs_pairs_up(tmp_path: Path) -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("앞부분")
    paragraph.add_run("굵은부분", bold=True)
    paragraph.add_run("뒷부분")
    document.text.highlight_span(paragraph, 2, paragraph, 6, color="#00FF00")  # from one run into the next
    path = tmp_path / "made.hwpx"
    document.save(path)
    text = _marked(path)
    assert "[HIGHLIGHT color=#00FF00]분굵은부[/HIGHLIGHT]" in text
    assert text.count("[HIGHLIGHT") == text.count("[/HIGHLIGHT]") == 1


# -- the install command an error gives ---------------------------------------------------------

_INSTALL = 'pip install -U "python-hwpx-automation>=8"'


def test_every_moved_message_gives_the_command_that_upgrades_the_companion() -> None:
    import hwpx
    from hwpx import _moved_modules, _removed_names

    assert _moved_modules.COMPANION_INSTALL == _removed_names.AUTOMATION_INSTALL == _INSTALL
    document = HwpxDocument.new()
    with pytest.raises(HwpxAttributeError) as moved_method:
        document.tables.find_cell_by_label("성명")
    assert _INSTALL in str(moved_method.value)
    with pytest.raises(ImportError) as moved_name:
        hwpx.HwpxMarkdownConverter
    assert _INSTALL in str(moved_name.value)
    with pytest.raises(ImportError) as moved_module:
        importlib.import_module("hwpx.tools.markdown_import")
    assert _INSTALL in str(moved_module.value)


def test_no_shipped_text_gives_the_bare_install_command() -> None:
    bare = "pip install python-hwpx-automation"
    for path in sorted((ROOT / "src" / "hwpx").rglob("*.py")):
        assert bare not in path.read_text(encoding="utf-8"), path
    for name in ("README.md", "README_EN.md", "docs/usage.md"):
        assert bare not in (ROOT / name).read_text(encoding="utf-8"), name
    guide = (ROOT / "docs" / "migration-7.0.md").read_text(encoding="utf-8")
    assert f"\n{_INSTALL} " in guide  # the command the guide gives; it names the bare one only to warn of it


# -- table numbers ------------------------------------------------------------------------------


def test_the_table_map_numbers_tables_as_with_nested_does() -> None:
    document = HwpxDocument.open(str(FIXTURES / "m2_corpus" / "form_002.hwpx"))
    mapped = document.tables.map()["tables"]
    nested = document.tables.with_nested
    assert len(mapped) == len(nested) > len(document.tables)  # the form has tables inside cells
    for index, entry in enumerate(mapped):
        assert entry["table_index"] == index
        assert (entry["rows"], entry["cols"]) == (nested[index].row_count, nested[index].column_count)
    # the same number means another table in doc.tables, which leaves nested tables out
    assert (mapped[1]["rows"], mapped[1]["cols"]) != (document.tables[1].row_count, document.tables[1].column_count)
    for name in ("README.md", "README_EN.md", "docs/usage.md"):
        assert "doc.tables.with_nested[table_index]" in (ROOT / name).read_text(encoding="utf-8"), name


# -- the measured comparison --------------------------------------------------------------------


def _script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_the_comparison_page_gives_the_measured_size_of_the_document_object() -> None:
    import json

    measured = _script("measure_control_surfaces").measure_ours()
    recorded = json.loads((ROOT / "docs" / "control-surfaces.json").read_text(encoding="utf-8"))["ours"]
    assert recorded["total"] == measured["total"]
    assert sorted(recorded["methods"] + recorded["properties"] + recorded["other"]) == sorted(
        measured["methods"] + measured["properties"] + measured["other"]
    )
    page = (ROOT / "docs" / "comparison-python-docx.md").read_text(encoding="utf-8")
    assert f"| 공개 멤버 수 | **19** | **29** | **{measured['total']}** |" in page


# -- the release notes --------------------------------------------------------------------------


def _release_notes_step() -> str:
    yaml = pytest.importorskip("yaml")
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8"))
    step = next(
        step
        for job in workflow["jobs"].values()
        for step in job["steps"]
        if str(step.get("name", "")).startswith("Extract latest changelog")
    )
    return step["run"].split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]


@pytest.mark.parametrize("lines", [3, 6000])
def test_the_release_notes_fit_githubs_limit_counted_in_bytes(tmp_path: Path, lines: int) -> None:
    body = "".join(f"- 고친 것 {index}: 한글로 적은 한 줄이다.\n" for index in range(lines))
    (tmp_path / "CHANGELOG.md").write_text(
        f"# Changelog\n\n## [9.9.9] - 2030-01-01\n\n{body}\n## [9.9.8] - 2029-01-01\n\n- 앞 판\n", encoding="utf-8"
    )
    subprocess.run(
        [sys.executable, "-c", _release_notes_step()],
        cwd=tmp_path, check=True, env={**os.environ, "GITHUB_REF_NAME": "v9.9.9"},
    )
    notes = (tmp_path / "release_notes.md").read_text(encoding="utf-8")
    assert notes.startswith("## [9.9.9] - 2030-01-01") and "앞 판" not in notes
    assert len(notes.encode("utf-8")) <= 110_000 < 125_000
    if lines == 3:
        assert notes.count("- 고친 것") == 3 and "CHANGELOG.md" not in notes
    else:
        assert notes.rstrip().endswith("([9.9.9] - 2030-01-01)")
        assert "https://github.com/airmang/python-hwpx/blob/v9.9.9/CHANGELOG.md" in notes
        assert notes.count("- 고친 것") > 1000  # cut at a line end, most of it kept


def test_the_current_release_notes_fit() -> None:
    script = _release_notes_step()
    subprocess.run([sys.executable, "-c", script], cwd=ROOT, check=True, env={**os.environ, "GITHUB_REF_NAME": "main"})
    notes = ROOT / "release_notes.md"
    try:
        assert len(notes.read_bytes()) <= 110_000
    finally:
        notes.unlink()


# -- a note in a document without the note style ------------------------------------------------


@pytest.mark.parametrize("name", ["exam/A_form.hwpx", "hwpxlib_corpus/error__20230728__test.hwpx", "m3_gongmun_gold/seoul_sihaengmun.hwpx"])
def test_a_note_points_at_shapes_the_document_has(name: str) -> None:
    """``add_footnote``/``add_endnote`` on a document with no style named 각주/미주 wrote the template's
    fixed ids: a style the document does not have (the exam form), or another style (an outline level)."""

    from hwpx.tools.id_integrity import check_id_integrity

    document = HwpxDocument.open(str(FIXTURES / name))
    assert not check_id_integrity(document).dangling
    host = next(paragraph for paragraph in document.paragraphs if paragraph.text.strip())
    head = "{http://www.hancom.co.kr/hwpml/2011/head}"
    styles = {style.get("id"): style.get("name") for header in document.oxml.headers for style in header.element.iter(f"{head}style")}
    for add, wanted in ((host.add_footnote, "각주"), (host.add_endnote, "미주")):
        note = add("검토")
        body = note.element.find(".//{http://www.hancom.co.kr/hwpml/2011/paragraph}p")
        assert body is not None
        used = styles[body.get("styleIDRef")]  # a style the header has
        assert used == wanted if wanted in styles.values() else not used.startswith("개요")
    assert not check_id_integrity(document).dangling
    assert not check_id_integrity(HwpxDocument.open(document.to_bytes())).dangling
