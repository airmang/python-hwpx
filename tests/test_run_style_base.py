"""A requested character shape is its base shape with the requested changes."""

from __future__ import annotations

from hwpx.document import HwpxDocument


def _shape(document: HwpxDocument, char_pr_id: str | None) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    style = document.oxml.char_property(char_pr_id)
    assert style is not None
    return dict(style.attributes), {name: dict(values) for name, values in style.child_attributes.items()}


def test_bold_on_a_run_keeps_its_size_color_and_font() -> None:
    document = HwpxDocument.new()
    red = document.styles.ensure_run(size=16, color="#FF0000")
    run = document.add_paragraph("").add_run("글", char_pr_id_ref=red)

    run.bold = True

    attributes, children = _shape(document, run.char_pr_id_ref)
    assert run.bold is True
    assert attributes["height"] == "1600"
    assert attributes["textColor"] == "#FF0000"
    assert children["fontRef"] == _shape(document, red)[1]["fontRef"]


def test_italic_and_underline_on_a_run_keep_its_size_and_each_other() -> None:
    document = HwpxDocument.new()
    small = document.styles.ensure_run(size=8)
    run = document.add_paragraph("").add_run("글", char_pr_id_ref=small)

    run.italic = True
    run.underline = True

    attributes, children = _shape(document, run.char_pr_id_ref)
    assert attributes["height"] == "800"
    assert "italic" in children
    assert children["underline"]["type"] != "NONE"


def test_a_run_given_only_a_size_keeps_the_other_formatting_of_the_first_shape() -> None:
    # A new document holds a 16 pt shape with a heading colour; a run asking for
    # 16 pt alone must not pick that one up.
    document = HwpxDocument.new()
    first_attributes, first_children = _shape(document, "0")

    run = document.add_paragraph("").add_run("글", size=16)

    attributes, children = _shape(document, run.char_pr_id_ref)
    assert attributes["height"] == "1600"
    assert attributes["textColor"] == first_attributes["textColor"]
    assert children["fontRef"] == first_children["fontRef"]


def test_a_named_base_is_built_on_even_when_another_shape_has_the_requested_values() -> None:
    document = HwpxDocument.new()
    document.styles.ensure_run(bold=True, size=20, color="#00AA00")
    small = document.styles.ensure_run(size=8)

    bold_small = document.styles.ensure_run(bold=True, base_char_pr_id=small)

    attributes, children = _shape(document, bold_small)
    assert attributes["height"] == "800"
    assert attributes["textColor"] == "#000000"
    assert "bold" in children


def test_a_size_change_on_a_base_keeps_its_bold_italic_and_underline() -> None:
    document = HwpxDocument.new()
    base = document.styles.ensure_run(bold=True, italic=True, underline=True, size=12)

    for smaller in (
        document.styles.ensure_run(size=9, base_char_pr_id=base),
        document.oxml.ensure_run_style(size=9, base_char_pr_id=base),
    ):
        attributes, children = _shape(document, smaller)
        assert attributes["height"] == "900"
        assert "bold" in children and "italic" in children
        assert children["underline"]["type"] != "NONE"


def test_a_derived_shape_keeps_the_strikeout_of_its_base() -> None:
    document = HwpxDocument.new()
    struck = document.styles.ensure_run(strike=True)
    run = document.add_paragraph("").add_run("글", char_pr_id_ref=struck)

    run.bold = True

    _, children = _shape(document, run.char_pr_id_ref)
    assert children["strikeout"]["shape"] == "SOLID"


def test_a_request_that_changes_nothing_gives_the_base_itself() -> None:
    document = HwpxDocument.new()
    height = _shape(document, "0")[0]["height"]

    assert document.styles.ensure_run() == "0"
    assert document.styles.ensure_run(size=int(height) / 100) == "0"
    assert document.styles.ensure_run(bold=True, size=14) == document.styles.ensure_run(bold=True, size=14)
