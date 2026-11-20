"""Sweep: whatever public call is refused, the document is as it was (exec7/rv4).

``test_refused_calls_leave_the_document_as_it_was`` pins the cases the final review of 7.0.0 found.
This one does not know the cases. It calls every public method and setter of the document root, its
namespaces and the objects they hand out, with arguments drawn from a pool of plausible and wrong
values, and whenever a call raises it compares the trees of every section, header and master page
and the images of the package with what they were before the call.

* A call refused with a typed error (an ``HwpxError`` with its ``code``) must have changed nothing.
  That is the contract, and the first run of this sweep found 46 kinds of call that broke it.
* A call that fails with a bare ``TypeError``/``ValueError``/``AttributeError`` -- a wrong *type*
  where a name or a number is written straight into XML -- should change nothing either. The ones
  that still do are listed in :data:`KNOWN_UNTYPED`; the list may only shrink.

The draw is seeded, so a failure names a call that fails again with the same seed.
"""

from __future__ import annotations

import inspect
import random
import warnings
from base64 import b64decode
from typing import Any

from lxml import etree

from hwpx import HwpxDocument
from hwpx.errors import HwpxError

PNG = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAAAAAA6fptVAAAACklEQVR4nGPYDQAAvQC8nHnAdAAAAABJRU5ErkJggg=="
)

#: ``target.method`` whose failure with an untyped error still leaves something behind: each writes
#: a value of the wrong type (an object where a name goes, bytes where a colour goes) into an element
#: it has already put in the tree. Take an entry out when its call checks first.
KNOWN_UNTYPED = frozenset({
    "cell.set_span",
    "ns.notes.add_memo",
    "ns.page.set_columns",
    "ns.page.set_endnote_shape",
    "ns.page.set_footnote_shape",
    "ns.page.set_grid",
    "ns.page.set_visibility",
    "ns.parts.set_document_options",
    "ns.styles.ensure_style",
    "ns.tracking.delete",
    "ns.tracking.insert",
    "paragraph.add_column_definition",
    "rect.set_draw_text",
    "section.add_memo",
})

_NAMESPACES = ("styles", "tables", "fields", "shapes", "media", "notes", "refs", "tracking", "page", "text", "parts")
_SKIPPED = frozenset({"save", "close", "to_bytes", "validate", "open", "new", "oxml", "package"})
_TRIALS = 18
_SEED = 20261120


def _seed_bytes() -> bytes:
    document = HwpxDocument.new()
    document.add_heading("제목", level=1)
    paragraph = document.add_paragraph("body text with words")
    paragraph.add_footnote("foot")
    paragraph.add_endnote("end")
    paragraph.add_bookmark("bm")
    document.notes.add_memo("memo", paragraph=document.add_paragraph("memo host"))
    table = document.add_table(2, 2)
    table.set_cell_text(0, 0, "cell")
    document.page.set_header(text="head")
    document.page.set_footer(text="foot")
    box = document.shapes.add_rectangle(paragraph=document.add_paragraph("box host"))
    box.set_draw_text("boxed")
    document.shapes.add_ruby("base", "rb", paragraph=document.add_paragraph("r"))
    document.refs.add_hyperlink("https://a.example", "link", paragraph=document.add_paragraph("l"))
    document.fields.add("f", paragraph=document.add_paragraph("f"))
    document.fields.add_check_box("cb", paragraph=document.add_paragraph("c"))
    document.shapes.add_equation("a+b", paragraph=document.add_paragraph("q"))
    document.add_picture(PNG, "png")
    document.tracking.insert(document.add_paragraph("tracked"), " ins", author="a")
    document.add_section()
    document.add_paragraph("second section", section=1)
    return document.to_bytes()


def _state(document: HwpxDocument) -> tuple[list[bytes], list[str]]:
    parts = [*document.oxml.sections, *document.oxml.headers, *document.oxml.master_pages]
    return [etree.tostring(part.element) for part in parts], sorted(str(item) for item in document.media.images)


def _handles(document: HwpxDocument) -> dict[str, Any]:
    paragraph = document.paragraphs[1]
    table = document.tables.all[0]
    handles: dict[str, Any] = {
        "doc": document, "paragraph": paragraph, "paragraph2": document.paragraphs[2], "table": table,
        "cell": table.cell(0, 0), "row": table.rows[0], "section": document.sections[0],
        "footnote": document.notes.footnotes[0], "memo": document.notes.memos[0],
        "header": document.page.header(), "ruby": document.shapes.rubies[0],
        "hyperlink": document.refs.hyperlinks[0], "bookmark": document.refs.bookmarks[0],
        "field": document.fields.all[0], "check_box": document.fields.check_boxes[0],
        "equation": document.shapes.equations[0], "picture": document.media.pictures[0],
        "run": paragraph.runs[0],
        "rect": next(shape for holder in document.paragraphs for shape in holder.shapes),
    }
    for name in _NAMESPACES:
        handles[f"ns.{name}"] = getattr(document, name)
    return handles


def _pool(handles: dict[str, Any]) -> list[Any]:
    plain: list[Any] = [
        None, 0, 1, -1, 2, 3, 7, 40, 1.5, -2.5, "", "x", "no such", "CENTER", "LEFT", "BOTH", "ODD", "#FF0000",
        "nope", "DIGIT", "number", "all", "body", True, False, b"x", PNG, "png", object(), (), [], {}, (0, 0),
        (1, 2, 3, 4), "A1:B2", "A1:Z9", [0], [5], {"children": [{"text": "t", "size": 37}, {"type": "bad"}]},
        [{"children": [{"text": "t", "size": 37}, {"type": "bad"}]}], [{"text": "ok"}], "FOOTNOTE", "A5", 50.0,
        {"x": 1}, ["x"], "https://b.example", "masterpage0", "9999",
    ]
    names = ("paragraph", "paragraph2", "table", "cell", "section", "footnote", "memo", "bookmark", "run")
    return plain + [handles[name] for name in names] + [[handles["paragraph"]], [handles["paragraph"], handles["paragraph2"]]]


def _members(obj: Any) -> list[tuple[str, inspect.Signature | None]]:
    """The public setters (signature ``None``) and methods of *obj*."""

    members: list[tuple[str, inspect.Signature | None]] = []
    for name in dir(type(obj)):
        if name.startswith("_") or name in _SKIPPED:
            continue
        static = inspect.getattr_static(type(obj), name)
        if isinstance(static, property):
            if static.fset is not None:
                members.append((name, None))
        elif callable(getattr(obj, name, None)):
            try:
                members.append((name, inspect.signature(getattr(obj, name))))
            except (TypeError, ValueError):
                continue
    return members


def _draw(signature: inspect.Signature, values: list[Any], handles: dict[str, Any], rng: random.Random) -> tuple[list[Any], dict[str, Any]]:
    args: list[Any] = []
    kwargs: dict[str, Any] = {}
    for name, parameter in signature.parameters.items():
        if parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
            continue
        required = parameter.default is parameter.empty
        if not required and rng.random() >= 0.35:
            continue
        value = rng.choice(values)
        if name in ("paragraph", "to", "anchor") and rng.random() < 0.6:
            value = handles["paragraph2"]
        if name == "table" and rng.random() < 0.7:
            value = handles["table"]
        if required and parameter.kind is not parameter.KEYWORD_ONLY:
            args.append(value)
        else:
            kwargs[name] = value
    return args, kwargs


def _sweep() -> tuple[list[str], set[str], int, int]:
    seed = _seed_bytes()
    rng = random.Random(_SEED)
    typed: list[str] = []
    untyped: set[str] = set()
    calls = refused = 0
    targets = sorted(set(_handles(HwpxDocument.open(seed))) - {"paragraph2"})  # the same kind as "paragraph"
    for target in targets:
        for name, signature in _members(_handles(HwpxDocument.open(seed))[target]):
            for _ in range(_TRIALS):
                document = HwpxDocument.open(seed)
                handles = _handles(document)
                values = _pool(handles)
                obj = handles[target]
                before = _state(document)
                if signature is None:
                    args, kwargs = [rng.choice(values)], {}
                else:
                    args, kwargs = _draw(signature, values, handles, rng)
                calls += 1
                try:
                    if signature is None:
                        setattr(obj, name, args[0])
                    else:
                        getattr(obj, name)(*args, **kwargs)
                except Exception as error:  # noqa: BLE001 - every refusal is the subject here
                    refused += 1
                    if _state(document) == before:
                        continue
                    if isinstance(error, HwpxError):
                        typed.append(f"{target}.{name}({args!r}, {kwargs!r}) -> {error.code}: {error}"[:400])
                    else:
                        untyped.add(f"{target}.{name}")
    return typed, untyped, calls, refused


def test_a_refused_public_call_changes_nothing() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        typed, untyped, calls, refused = _sweep()

    assert calls > 5000 and refused > calls // 2, (calls, refused)  # the sweep reaches refusals at all
    assert not typed, "refused with a typed error, and the document changed:\n" + "\n".join(typed[:20])
    assert untyped <= KNOWN_UNTYPED, (
        "these calls now leave something behind when they fail on a wrong type "
        f"(check the value before writing): {sorted(untyped - KNOWN_UNTYPED)}"
    )
