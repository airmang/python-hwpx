# SPDX-License-Identifier: Apache-2.0
"""Small API holes found in the 7.0 coverage check, and their kin.

- ``doc.fields.add`` / ``add_check_box`` take ``paragraph=`` as a number, as every other
  ``paragraph=`` does (it raised ``AttributeError: 'int' object has no attribute ...``).
- :func:`typing.get_type_hints` resolves every public method of every namespace (a
  tool-schema builder calls it; the annotations named types imported only for type checkers).
- A public method given an argument of the wrong type fails with a typed
  :class:`~hwpx.errors.HwpxError` that is also the builtin a caller would catch, never a bare
  ``TypeError``/``AttributeError`` from deep inside it.
- An equation or chart is never written 0 wide or 0 high.
"""

from __future__ import annotations

import inspect
import subprocess
import sys
import textwrap
import typing

import pytest

from hwpx import HwpxDocument
from hwpx._document.ns import NAMESPACES
from hwpx.errors import HwpxError, HwpxLookupError, HwpxTypeError, HwpxValueError

_CHART = (
    b'<c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart">'
    b"<c:chart><c:plotArea><c:pieChart/></c:plotArea></c:chart></c:chartSpace>"
)


def _doc() -> HwpxDocument:
    document = HwpxDocument.new()
    document.add_paragraph("첫 문단")
    document.add_paragraph("둘째 문단")
    return document


# -- fields.add / add_check_box(paragraph=<int>) -------------------------------------------


def test_form_field_goes_into_the_numbered_paragraph() -> None:
    document = _doc()
    target = document.paragraphs[1]
    before = len(document.paragraphs)

    document.fields.add("성명", paragraph=1)

    assert len(document.paragraphs) == before
    assert any(element.tag.endswith("}fieldBegin") for element in target.element.iter())
    reopened = HwpxDocument.open(document.to_bytes())
    assert [f.name for f in reopened.fields.all] == ["성명"]


def test_check_box_goes_into_the_numbered_paragraph_of_a_section() -> None:
    document = _doc()
    target = document.sections[0].paragraphs[-1]

    box = document.fields.add_check_box("동의", paragraph=-1, section=0)

    assert box.paragraph.element is target.element


@pytest.mark.parametrize("method", ["add", "add_check_box"])
def test_paragraph_number_out_of_range_or_wrong_type_is_typed(method: str) -> None:
    document = _doc()
    add = getattr(document.fields, method)
    with pytest.raises(HwpxLookupError) as missing:
        add("x", paragraph=99)
    assert missing.value.code == "paragraph-not-found"
    with pytest.raises(HwpxTypeError) as wrong:
        add("x", paragraph="1")
    assert wrong.value.code == "paragraph-invalid-type"


def test_paragraph_argument_annotations_take_an_int() -> None:
    for method in ("add", "add_check_box"):
        annotation = inspect.signature(getattr(NAMESPACES["fields"], method)).parameters["paragraph"].annotation
        assert "int" in str(annotation)


# -- typing.get_type_hints -------------------------------------------------------------------


def _public_callables():
    for attribute, namespace in NAMESPACES.items():
        for cls in inspect.getmro(namespace):
            if cls is object:
                continue
            for name, member in vars(cls).items():
                if name.startswith("_") and name != "__getitem__":
                    continue
                function = member.fget if isinstance(member, property) else member
                if callable(function):
                    yield f"doc.{attribute}.{name}", function


@pytest.mark.parametrize(("label", "function"), list(_public_callables()), ids=lambda value: value if isinstance(value, str) else "")
def test_every_namespace_method_has_resolvable_type_hints(label: str, function: object) -> None:
    typing.get_type_hints(function)


def test_resolving_hints_resolves_to_the_real_classes() -> None:
    from hwpx.form_fit import FitPolicy
    from hwpx.tools.table_navigation import TableMapResult

    hints = typing.get_type_hints(NAMESPACES["fields"].fill)
    assert FitPolicy in typing.get_args(hints["fit_policy"])
    assert typing.get_type_hints(NAMESPACES["tables"].map)["return"] is TableMapResult
    assert typing.get_type_hints(NAMESPACES["styles"].document.fget)["return"] is HwpxDocument


def test_namespaces_still_load_no_tools_or_form_fit_module() -> None:
    code = textwrap.dedent(
        """
        import sys
        from hwpx import HwpxDocument
        document = HwpxDocument.new()
        for name in ("styles", "tables", "fields", "shapes", "media", "notes", "refs",
                     "tracking", "page", "text", "parts"):
            getattr(document, name)
        print(sorted(m for m in sys.modules if m.startswith(("hwpx.tools", "hwpx.form_fit"))))
        """
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "[]"


# -- equation and chart size -----------------------------------------------------------------


@pytest.mark.parametrize("size", [(0, 0), (0, 500), (500, 0), 5, (1, 2, 3), "10,10", (1.5, 2)])
def test_equation_size_must_be_two_positive_ints(size: object) -> None:
    document = _doc()
    count = len(document.paragraphs)
    with pytest.raises(HwpxValueError) as caught:
        document.shapes.add_equation("a over b", size=size)  # type: ignore[arg-type]
    assert caught.value.code == "shape-size-value"
    assert len(document.paragraphs) == count  # refused before a paragraph is added
    if isinstance(size, tuple) and len(size) == 2:
        with pytest.raises(HwpxValueError):
            document.paragraphs[0].add_equation("a over b", width=size[0], height=size[1])  # type: ignore[arg-type]


def test_explicit_equation_size_is_still_written() -> None:
    document = _doc()
    equation = document.shapes.add_equation("a over b", size=(2000, 1000))
    assert (equation.width, equation.height) == (2000, 1000)


def test_chart_refuses_a_zero_size_before_writing_its_part() -> None:
    document = _doc()
    parts = set(document.package.part_names())
    count = len(document.paragraphs)
    with pytest.raises(HwpxValueError) as caught:
        document.shapes.add_chart(_CHART, size=(0, 0))
    assert caught.value.code == "shape-size-value"
    assert set(document.package.part_names()) == parts
    assert len(document.paragraphs) == count


@pytest.mark.parametrize("chart_xml", [{"a": 1}, 1, None, ["<c:chartSpace/>"]])
def test_chart_xml_of_the_wrong_type_is_typed(chart_xml: object) -> None:
    document = _doc()
    parts = set(document.package.part_names())
    with pytest.raises(HwpxTypeError) as caught:
        document.shapes.add_chart(chart_xml)  # type: ignore[arg-type]
    assert caught.value.context["argument"] == "chart_xml"
    assert set(document.package.part_names()) == parts


def test_paragraph_add_chart_reference_is_checked() -> None:
    document = _doc()
    with pytest.raises(HwpxTypeError):
        document.paragraphs[0].add_chart(1)  # type: ignore[arg-type]
    with pytest.raises(HwpxValueError) as caught:
        document.paragraphs[0].add_chart("  ")
    assert caught.value.code == "shape-chart-reference-empty"


# -- wrong-typed arguments: a typed error that is also the builtin -----------------------------


def _png() -> bytes:
    return bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000d4944415478da63f8ffff3f0005fe02fea7d6a4a40000000049454e44ae426082"
    )


_WRONG_TYPES = {
    "paragraph.text = 1": lambda d: setattr(d.paragraphs[0], "text", 1),
    "paragraph.add_run(dict)": lambda d: d.paragraphs[0].add_run({"a": 1}),
    "paragraph.add_equation(1)": lambda d: d.paragraphs[0].add_equation(1),
    "paragraph.add_equation('')": lambda d: d.paragraphs[0].add_equation(" "),
    "paragraph.add_table('2', 2)": lambda d: d.paragraphs[0].add_table("2", 2),
    "paragraph.add_table(0, 2)": lambda d: d.paragraphs[0].add_table(0, 2),
    "paragraph.add_hyperlink(1, 't')": lambda d: d.paragraphs[0].add_hyperlink(1, "t"),
    "paragraph.add_hyperlink('', 't')": lambda d: d.paragraphs[0].add_hyperlink("", "t"),
    "paragraph.add_bookmark(1)": lambda d: d.paragraphs[0].add_bookmark(1),
    "paragraph.style = object()": lambda d: setattr(d.paragraphs[0], "style", object()),
    "paragraph.style = True": lambda d: setattr(d.paragraphs[0], "style", True),
    "table.cell('a', 0)": lambda d: d.add_table(2, 2).cell("a", 0),
    "cell.text = 5": lambda d: setattr(d.add_table(2, 2).cell(0, 0), "text", 5),
    "cell.set_size(width='a')": lambda d: d.add_table(2, 2).cell(0, 0).set_size(width="a"),
    "cell.add_paragraph(dict)": lambda d: d.add_table(2, 2).cell(0, 0).add_paragraph({"a": 1}),
    "table.set_column_widths('ab')": lambda d: d.add_table(2, 2).set_column_widths("ab"),
    "table.set_column_widths([1])": lambda d: d.add_table(2, 2).set_column_widths([1]),
    "text.replace(1, 'b')": lambda d: d.text.replace(1, "b"),
    "text.replace('a', 1)": lambda d: d.text.replace("첫", 1),
    "text.highlight(0, 1)": lambda d: d.text.highlight(0, 1),
    "text.apply_changes([])": lambda d: d.text.apply_changes([]),
    "text.outline(max_chars='a')": lambda d: d.text.outline(max_chars="a"),
    "fields.add(1)": lambda d: d.fields.add(1),
    "fields.add(prompt=1)": lambda d: d.fields.add("n", prompt=1),
    "fields.add_check_box(1)": lambda d: d.fields.add_check_box(1),
    "shapes.add_equation(1)": lambda d: d.shapes.add_equation(1),
    "notes.add_footnote(1)": lambda d: d.notes.add_footnote(1),
    "notes.add_memo(1)": lambda d: d.notes.add_memo(1),
    "refs.add_bookmark(1)": lambda d: d.refs.add_bookmark(1),
    "refs.add_bookmark('')": lambda d: d.refs.add_bookmark(""),
    "refs.add_hyperlink(1, 't')": lambda d: d.refs.add_hyperlink(1, "t"),
    "page.set_header(text=1)": lambda d: d.page.set_header(text=1),
    "page.set_columns('2')": lambda d: d.page.set_columns("2"),
    "tracking.insert(0, 1)": lambda d: d.tracking.insert(0, 1),
    "tables['a']": lambda d: d.tables["a"],
    "add_section(after='a')": lambda d: d.add_section(after="a"),
    "add_section(after=9)": lambda d: d.add_section(after=9),
    "save(123)": lambda d: d.save(123),
}


@pytest.mark.parametrize("label", sorted(_WRONG_TYPES))
def test_a_wrong_argument_fails_typed_and_catchable(label: str) -> None:
    document = _doc()
    with pytest.raises(HwpxError) as caught:
        _WRONG_TYPES[label](document)
    error = caught.value
    assert isinstance(error, (TypeError, ValueError, LookupError))
    assert error.code
    assert error.suggestion


def test_text_of_the_wrong_type_carries_the_paragraph_text_code() -> None:
    document = _doc()
    with pytest.raises(HwpxTypeError) as caught:
        document.paragraphs[0].text = 1  # type: ignore[assignment]
    assert caught.value.code == "paragraph-text-invalid-type"
    assert document.paragraphs[0].text == "첫 문단"  # refused before the old text went
    run = next(run for run in document.paragraphs[0].runs if run.text)
    with pytest.raises(HwpxTypeError):
        run.text = 1  # type: ignore[assignment]
    assert run.text == "첫 문단"


def test_bookmark_and_link_still_take_a_name() -> None:
    document = _doc()
    document.refs.add_bookmark("표1", paragraph=0)
    document.refs.add_hyperlink("#표1", "표 1로", paragraph=1)
    reopened = HwpxDocument.open(document.to_bytes())
    assert [b.name for b in reopened.refs.bookmarks] == ["표1"]
    assert [h.url for h in reopened.refs.hyperlinks] == ["#표1"]
