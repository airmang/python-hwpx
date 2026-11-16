# SPDX-License-Identifier: Apache-2.0
"""7.0 이름 정리: 6.x 에 나간 이름을 바꾸거나 지우면 새 자리를 알려 준다.

안내 표는 :mod:`hwpx._removed_names` 하나다(이름 :data:`NAMES`, 인자 :data:`ARGUMENTS`).
표의 줄은 그 이름을 바꾸는 묶음이 이름을 바꾸기 전에도 적혀 있을 수 있다 — 그동안은 아무
일도 하지 않는다. 아래 표 검사는 줄마다 "아직 그대로(대기)"이거나 "부르면 안내가 난다"
둘 중 하나임을 본다. 묶음이 이름을 바꾸면 그 줄의 안내가 그대로 검사된다.

이 파일은 저장 동사 넷을 합친 ``doc.save`` (D4), ``from_package`` → ``open(package)``,
루트 ``add_*`` 인자(D2·D8·D11), ``paragraphs``/``sections`` tuple 도 본다.
"""

from __future__ import annotations

import importlib
import inspect
import io
import sys
import types
import zipfile
from pathlib import Path

import pytest

import hwpx
import hwpx.model as model
from hwpx import HwpxDocument, MutationReport, QualityPolicy, VisualCompleteReport
from hwpx import _removed_names as hints
from hwpx._document.ns import NAMESPACES
from hwpx._document._units import _line_width_mm_to_hwp_units
from hwpx.errors import HwpxAttributeError, HwpxTypeError, HwpxValueError, SaveError
from hwpx.objects import Alignment
from hwpx.opc.package import HwpxPackage

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7V\x8b\xb2\x00\x00\x00\x00IEND\xaeB`\x82"
)
_NAMESPACE_BY_PATH = {cls._path: (attribute, cls) for attribute, cls in NAMESPACES.items()}
_SENTINEL = object()


# --------------------------------------------------------------------------
# 표 ① 이름: 줄마다 대기 중이거나, 부르면 안내가 난다


def _name_rows() -> list[tuple[str, str]]:
    return sorted((owner, name) for owner, rows in hints.NAMES.items() for name in rows)


def _owner_target(owner: str):
    if owner == "doc":
        return HwpxDocument
    if owner in _NAMESPACE_BY_PATH:
        return _NAMESPACE_BY_PATH[owner][1]
    return hints._resolve_owner(owner)


def _still_there(target: object, name: str) -> bool:
    if isinstance(target, types.ModuleType):
        return name in vars(target)
    return inspect.getattr_static(target, name, _SENTINEL) is not _SENTINEL


@pytest.mark.parametrize(("owner", "name"), _name_rows())
def test_a_name_row_is_pending_or_names_the_new_place(owner: str, name: str) -> None:
    entry = hints.NAMES[owner][name]
    target = _owner_target(owner)
    if _still_there(target, name):
        assert owner != "doc", f"루트 {name} 는 7.0에서 지웠다"
        return  # 그 이름을 바꾸는 묶음이 아직 바꾸지 않았다: 안내는 대기 중이다
    document = HwpxDocument.new()
    if owner == "doc":
        holder: object = document
    elif owner in _NAMESPACE_BY_PATH:
        holder = getattr(document, _NAMESPACE_BY_PATH[owner][0])
    elif isinstance(target, types.ModuleType):
        holder = target
    else:
        holder = object.__new__(target)
    expected = hints.RemovedNameImportError if isinstance(target, types.ModuleType) else HwpxAttributeError
    with pytest.raises(expected) as raised:
        getattr(holder, name)
    error = raised.value
    assert error.code == ("document-name-moved" if entry.moving else "document-name-removed")
    assert error.context["replacement"] == entry.replacement
    assert "7.0" in str(error)
    if entry.hint:
        assert entry.hint in str(error)
    if not isinstance(target, types.ModuleType):
        assert not hasattr(holder, name)


def test_every_owner_in_the_table_is_a_class_or_module_the_hooks_reach() -> None:
    for owner in hints.NAMES:
        target = _owner_target(owner)
        assert isinstance(target, (type, types.ModuleType)), owner
        if isinstance(target, types.ModuleType) or owner == "doc" or owner in _NAMESPACE_BY_PATH:
            continue
        assert getattr(target.__getattr__, "__hwpx_hint__", False), f"{owner} 에 안내 훅이 없다"


def test_the_public_names_are_the_hwpx_model_aliases() -> None:
    for alias in model.__all__:
        cls = getattr(model, alias)
        if isinstance(cls, type) and cls.__module__.startswith("hwpx.oxml"):
            assert hints.public_name(cls) == alias


# --------------------------------------------------------------------------
# 표 ② 인자: 옛 키워드마다 대기 중이거나, 주면 새 키워드를 알려 준다


def _argument_rows() -> list[tuple[str, str]]:
    rows = []
    for caller, rule in hints.ARGUMENTS.items():
        rows.extend((caller, old) for old in rule.renamed)
        rows.extend((caller, f"<position>{name}") for name in rule.keyword_only)
    return sorted(rows)


def _callable_for(caller: str, document: HwpxDocument):
    owner, _, method = caller.rpartition(".")
    if owner == "doc":
        return getattr(document, method), False
    if owner in _NAMESPACE_BY_PATH:
        return getattr(getattr(document, _NAMESPACE_BY_PATH[owner][0]), method), False
    if owner.startswith("hwpx."):
        return getattr(importlib.import_module(owner), method), False
    return getattr(hints._resolve_owner(owner), method), True  # unbound: the guard runs before self is used


@pytest.mark.parametrize(("caller", "old"), _argument_rows())
def test_an_argument_row_is_pending_or_names_the_new_argument(caller: str, old: str) -> None:
    document = HwpxDocument.new()
    function, unbound = _callable_for(caller, document)
    parameters = inspect.signature(function).parameters
    rule = hints.ARGUMENTS[caller]
    if old.startswith("<position>"):
        name = old[len("<position>"):]
        if parameters[name].kind is not inspect.Parameter.KEYWORD_ONLY:
            return  # still positional: pending
        positional = [p for p in parameters.values() if p.kind in hints._POSITIONAL]
        args = [None] * (len(positional) + 1)
        with pytest.raises(HwpxTypeError) as raised:
            function(*args)
        assert raised.value.code == "hwpx-argument-removed"
        assert raised.value.context["argument"] == name
        assert rule.hint in str(raised.value)
        return
    if old in parameters:
        return  # the old keyword is still the method's own: pending
    if caller.startswith("hwpx.") and not getattr(function, "__hwpx_guard__", None):
        pytest.fail(f"{caller}: 모듈 함수에는 @rejects_removed_arguments(caller={caller!r}) 를 단다")
    args = [None] if unbound else []
    with pytest.raises(HwpxTypeError) as raised:
        function(*args, **{old: _SENTINEL})
    error = raised.value
    assert error.code == "hwpx-argument-removed"
    assert error.context["argument"] == old
    assert error.context["replacement"] == rule.renamed[old]
    assert rule.hint in str(error)


def test_every_argument_row_names_an_existing_method() -> None:
    document = HwpxDocument.new()
    for caller in hints.ARGUMENTS:
        function, _ = _callable_for(caller, document)
        assert callable(function), caller


# --------------------------------------------------------------------------
# 장치: 표에 줄을 더하면 안내가 난다(묶음·모델·값 형식·모듈·인자·위치 인자)


@pytest.fixture
def extra_rows(monkeypatch: pytest.MonkeyPatch):
    def add(owner: str, name: str, entry: hints.Removed) -> None:
        monkeypatch.setitem(hints.NAMES, owner, {**hints.NAMES.get(owner, {}), name: entry})

    return add


def test_a_namespace_row_answers_through_the_namespace(extra_rows) -> None:
    extra_rows("doc.styles", "old_style_reader", hints._gone("doc.styles.get(...)", "doc.styles.old_style_reader()는 없어졌다"))
    styles = HwpxDocument.new().styles
    with pytest.raises(HwpxAttributeError) as raised:
        styles.old_style_reader  # noqa: B018
    assert raised.value.code == "document-name-removed"
    assert raised.value.context["owner"] == "doc.styles"
    assert not hasattr(styles, "old_style_reader")


def test_a_model_row_answers_on_its_class_and_subclasses(extra_rows) -> None:
    extra_rows("InlineObject", "old_reader", hints._gone("InlineObject.new_reader", "old_reader 는 new_reader 다"))
    document = HwpxDocument.new()
    picture = document.add_picture(PNG, "png")
    assert isinstance(picture, model.InlineObject)
    with pytest.raises(HwpxAttributeError) as raised:
        picture.old_reader  # noqa: B018
    assert raised.value.context["owner"] == "InlineObject"
    assert getattr(picture, "old_reader", None) is None
    with pytest.raises(AttributeError) as plain:
        picture.no_such_name  # noqa: B018
    assert not isinstance(plain.value, HwpxAttributeError)


def test_a_property_that_fails_inside_keeps_its_own_error(extra_rows) -> None:
    extra_rows("Paragraph", "text", hints._gone("Paragraph.other", "text 는 바뀌었다"))

    class Broken(model.Paragraph):  # type: ignore[misc]
        @property
        def text(self) -> str:  # type: ignore[override]
            raise AttributeError("the real reason")

    paragraph = HwpxDocument.new().add_paragraph("x")
    paragraph.__class__ = Broken
    with pytest.raises(AttributeError, match="the real reason"):
        paragraph.text  # noqa: B018


def test_a_value_type_row_answers_on_a_slotted_class(extra_rows) -> None:
    from hwpx.oxml.header import Font

    extra_rows("Font", "old_face", hints._gone("Font.face", "Font.old_face 는 face 다", kind="property"))
    font = object.__new__(Font)
    with pytest.raises(HwpxAttributeError, match="Font.old_face 는 face 다"):
        font.old_face  # noqa: B018


def test_a_module_row_answers_an_import(monkeypatch: pytest.MonkeyPatch, extra_rows) -> None:
    module = types.ModuleType("hwpx._hint_probe")
    monkeypatch.setitem(sys.modules, module.__name__, module)
    extra_rows(module.__name__, "OldThing", hints._gone("NewThing", "OldThing 는 7.0에서 NewThing 이다"))
    hints._install_module_hook(module)
    with pytest.raises(ImportError, match="OldThing 는 7.0에서 NewThing 이다") as raised:
        exec(f"from {module.__name__} import OldThing", {})
    assert raised.value.code == "document-name-removed"  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        module.something_else  # noqa: B018


def test_an_argument_row_guards_renamed_keyword_only_and_xml_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    def add_thing(text: str, *, paragraph: object = None, new_width: int = 0) -> tuple[str, object, int]:
        return text, paragraph, new_width

    monkeypatch.setitem(
        hints.ARGUMENTS,
        "doc.things.add_thing",
        hints._args("doc.things.add_thing(text, p, old_width=) → (text, paragraph=p, new_width=)",
                    keyword_only=("paragraph",), xml_attributes=True, old_width="new_width"),
    )
    guarded = hints.guard_arguments(add_thing, "doc.things.add_thing")
    assert inspect.signature(guarded) == inspect.signature(add_thing)
    assert guarded("t", paragraph=1, new_width=2) == ("t", 1, 2)
    with pytest.raises(HwpxTypeError) as renamed:
        guarded("t", old_width=3)
    assert renamed.value.context["replacement"] == "new_width"
    with pytest.raises(HwpxTypeError) as positional:
        guarded("t", object())
    assert positional.value.context["argument"] == "paragraph"
    with pytest.raises(HwpxTypeError) as xml:
        guarded("t", pageBreak="1")
    assert xml.value.context["xmlAttribute"] is True
    assert {renamed.value.code, positional.value.code, xml.value.code} == {"hwpx-argument-removed"}


def test_a_row_for_an_argument_the_method_still_takes_changes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    def keeps(*, old_width: int = 0) -> int:
        return old_width

    monkeypatch.setitem(hints.ARGUMENTS, "doc.things.keeps", hints._args("…", old_width="new_width"))
    assert hints.guard_arguments(keeps, "doc.things.keeps") is keeps


# --------------------------------------------------------------------------
# 루트: 저장 동사·from_package·add_* 인자·tuple


@pytest.mark.parametrize("name", ["save_to_path", "save_to_stream", "save_report", "from_package"])
def test_a_removed_root_name_points_at_its_7_0_place(name: str) -> None:
    document = HwpxDocument.new()
    with pytest.raises(HwpxAttributeError) as raised:
        getattr(document, name)
    assert raised.value.code == "document-name-removed"
    assert raised.value.context["replacement"] == hints.NAMES["doc"][name].replacement
    assert hints.NAMES["doc"][name].hint in str(raised.value)
    assert "migration-7.0.md" in (raised.value.suggestion or "")
    assert not hasattr(document, name)


def test_from_package_on_the_class_points_at_open() -> None:
    with pytest.raises(HwpxAttributeError, match=r"HwpxDocument\.open\(package\)"):
        HwpxDocument.from_package  # noqa: B018
    assert not hasattr(HwpxDocument, "from_package")
    with pytest.raises(AttributeError) as plain:
        HwpxDocument.no_such_name  # noqa: B018
    assert not isinstance(plain.value, HwpxAttributeError)


def test_open_takes_an_open_package() -> None:
    package = HwpxPackage.open(HwpxDocument.new().to_bytes())
    document = HwpxDocument.open(package)
    assert document.package is package
    document.add_paragraph("패키지에서 연 문서")
    assert "패키지에서 연 문서" in HwpxDocument.open(document.to_bytes()).text.plain()


@pytest.mark.parametrize(
    ("call", "argument", "replacement"),
    [
        (lambda d: d.add_picture(PNG, "png", line_width=33), "line_width", "line_width_mm"),
        (lambda d: d.add_picture(PNG, "png", align="CENTER"), "align", "alignment"),
        (lambda d: d.add_picture(PNG, "png", run_attributes={}), "run_attributes", None),
        (lambda d: d.add_paragraph("x", run_attributes={}), "run_attributes", None),
        (lambda d: d.add_table(1, 1, run_attributes={}), "run_attributes", None),
        (lambda d: d.add_paragraph("x", pageBreak="1"), "pageBreak", None),
        (lambda d: d.add_heading("x", columnBreak="1"), "columnBreak", None),
        (lambda d: d.add_table(1, 1, pageBreak="1"), "pageBreak", None),
        (lambda d: d.add_picture(PNG, "png", pageBreak="1"), "pageBreak", None),
    ],
)
def test_a_removed_root_argument_is_named_and_nothing_is_added(call, argument: str, replacement) -> None:
    document = HwpxDocument.new()
    before = (len(document.paragraphs), len(document.media.images))
    with pytest.raises(HwpxTypeError) as raised:
        call(document)
    assert raised.value.code == "hwpx-argument-removed"
    assert raised.value.context["argument"] == argument
    assert raised.value.context["replacement"] == replacement
    assert (len(document.paragraphs), len(document.media.images)) == before


def test_a_picture_line_width_in_mm_writes_the_hwpunit_6x_wrote() -> None:
    assert _line_width_mm_to_hwp_units(0.12) == 33  # the 6.x default line_width=33
    assert _line_width_mm_to_hwp_units(0.5) == 141  # what Hancom keeps for 0.5 mm
    document = HwpxDocument.new()
    picture = document.add_picture(PNG, "png", line_color="#000000")
    assert picture.element.find("{http://www.hancom.co.kr/hwpml/2011/paragraph}lineShape").get("width") == "33"
    centred = document.add_picture(PNG, "png", alignment=Alignment.CENTER)
    assert isinstance(centred, model.Picture)
    for bad in (-1, True, "0.12 mm", float("nan")):
        with pytest.raises(HwpxValueError) as raised:
            document.add_picture(PNG, "png", line_width_mm=bad)
        assert raised.value.code == "shape-picture-border-value"


def test_the_raw_shape_escape_hatches_still_take_xml_attributes() -> None:
    document = HwpxDocument.new()
    with pytest.warns(UserWarning):
        shape = document.shapes.add_raw("rect", pageBreak="1")
    assert shape.paragraph.element.get("pageBreak") == "1"


def test_paragraphs_and_sections_are_tuples() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("하나")
    assert isinstance(document.paragraphs, tuple)
    assert isinstance(document.sections, tuple)
    assert document.paragraphs[-1].text == "하나"


# --------------------------------------------------------------------------
# doc.save (D4)


def test_save_to_a_path_returns_the_receipt(tmp_path: Path) -> None:
    document = HwpxDocument.new()
    document.add_paragraph("경로")
    target = tmp_path / "out.hwpx"
    report = document.save(target)
    assert isinstance(report, MutationReport)
    assert report.path == str(target) and report.ok and report.quality is None
    assert "quality" not in report.to_dict()
    assert HwpxDocument.open(target).text.plain().strip() == "경로"


def test_save_to_a_stream_writes_hwpx_and_reports_no_path() -> None:
    document = HwpxDocument.new()
    document.add_paragraph("스트림")
    stream = io.BytesIO()
    report = document.save(stream)
    assert report.path is None
    assert zipfile.is_zipfile(io.BytesIO(stream.getvalue()))


def test_save_picks_the_format_from_the_name_or_the_argument(tmp_path: Path) -> None:
    document = HwpxDocument.new()
    document.add_paragraph("한글 5.0")
    signature = b"\xd0\xcf\x11\xe0"
    with pytest.warns(UserWarning):
        document.save(tmp_path / "a.hwp")
    assert (tmp_path / "a.hwp").read_bytes()[:4] == signature
    stream = io.BytesIO()
    document.save(stream, format="hwp")
    assert stream.getvalue()[:4] == signature
    document.save(tmp_path / "b.hwpx", format="hwpx")
    assert (tmp_path / "b.hwpx").read_bytes()[:2] == b"PK"
    with pytest.raises(HwpxValueError) as raised:
        document.save(io.BytesIO(), format="docx")  # type: ignore[arg-type]
    assert raised.value.code == "save-format-unsupported"


@pytest.mark.parametrize("target", [None, 3, b"out.hwpx"])
def test_save_refuses_a_target_that_is_neither_a_path_nor_a_stream(target: object) -> None:
    with pytest.raises(HwpxTypeError) as raised:
        HwpxDocument.new().save(target)  # type: ignore[arg-type]
    assert raised.value.code == "save-target-invalid-type"


def test_save_with_a_passing_quality_gate_carries_its_report(tmp_path: Path) -> None:
    document = HwpxDocument.new()
    document.add_paragraph("품질")
    policy = QualityPolicy.transparent().with_(require_reference_integrity=True)
    report = document.save(tmp_path / "q.hwpx", quality=policy)
    assert isinstance(report.quality, VisualCompleteReport) and report.quality.ok
    assert report.to_dict()["quality"] == report.quality.to_dict()
    assert report.quality.output_path == str(tmp_path / "q.hwpx")


def test_a_refused_quality_gate_writes_nothing_and_hands_the_report_over(tmp_path: Path) -> None:
    document = HwpxDocument.new()
    document.add_paragraph("엄격")
    target = tmp_path / "strict.hwpx"
    with pytest.raises(SaveError) as raised:
        document.save(target, quality=QualityPolicy.strict())  # no render oracle: not visually verified
    error = raised.value
    assert error.code == "quality-gate-failed"
    assert isinstance(error.report, VisualCompleteReport) and not error.report.ok
    assert error.context["errors"] == [str(item) for item in error.report.errors]
    assert not target.exists()


def test_save_has_the_signature_the_spec_froze() -> None:
    parameters = inspect.signature(HwpxDocument.save).parameters
    assert list(parameters) == ["self", "target", "format", "mode", "fallback", "quality", "pipeline"]
    assert [parameters[name].default for name in ("format", "mode", "fallback", "quality", "pipeline")] == [
        None, "auto", "error", None, None]
    assert parameters["pipeline"].kind is inspect.Parameter.KEYWORD_ONLY
    assert hasattr(hwpx, "MutationReport") and not hasattr(HwpxDocument, "save_to_path")


# --------------------------------------------------------------------------
# 문단·런·서식·개체 모델 (WP3): add_* 반환, 쓰기 속성, 선 굵기 mm, 수식 글자 크기


_HP_NS = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def test_paragraph_add_returns_the_value_its_reader_gives() -> None:
    from hwpx.objects import Bookmark, CheckBox, FormField, Highlight, Hyperlink, NumberRestart, PageHiding

    document = HwpxDocument.new()
    paragraph = document.add_paragraph("표시할 글")
    mark = paragraph.add_bookmark("갈피")
    assert isinstance(mark, Bookmark) and mark == document.refs.bookmarks[0]
    assert paragraph.bookmarks == (mark,)
    link = paragraph.add_hyperlink("https://example.com", "누리집")
    assert isinstance(link, Hyperlink) and link == paragraph.hyperlinks[0] and link.text == "누리집"
    field = paragraph.add_form_field("성명", prompt="이름")
    assert isinstance(field, FormField) and field.name == "성명" and field.prompt == "이름"
    assert (field.field_id, field.location) == (document.fields.all[0].field_id, document.fields.all[0].location)
    box = paragraph.add_check_box("동의")
    assert isinstance(box, CheckBox) and box.element is document.fields.check_boxes[0].element
    assert box.index == 0 and box.section is document.sections[0]
    assert isinstance(paragraph.add_highlight(color="#FFFF00", match="표시"), Highlight)
    restart = paragraph.add_number_restart(number=3)
    assert restart == NumberRestart(kind="PAGE", number=3, paragraph=paragraph)
    hiding = paragraph.add_page_hiding(header=True)
    assert isinstance(hiding, PageHiding) and hiding.header and not hiding.footer
    field.value = "홍길동"  # the value is the live form field's
    assert document.fields.all[0].value == "홍길동"


def test_a_paragraph_reads_its_many_as_tuples() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("글")
    paragraph.add_rectangle(1000, 1000)
    for name in ("runs", "tables", "shapes", "footnotes", "endnotes", "bookmarks"):
        assert isinstance(getattr(paragraph, name), tuple), name
    box = paragraph.shapes[0]
    text = box.set_draw_text("글상자", vertical_alignment="TOP")
    assert isinstance(text.paragraphs, tuple)
    added = text.add_paragraph("둘째", para_pr_id_ref=0)
    assert added.para_pr_id_ref == "0" and text.paragraphs[-1].text == "둘째"
    caption = box.set_caption("그림 1", full_size=True)
    assert caption.full_size is True and isinstance(caption.paragraphs, tuple)


def test_object_values_are_written_through_their_properties() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("")
    shape = paragraph.add_rectangle(2000, 1000, line_width_mm=0.5)
    shape.z_order, shape.rotation, shape.description = 3, 30, "사각형"
    assert (shape.z_order, shape.rotation, shape.description) == (3, 30, "사각형")
    assert shape.attributes.get("zOrder") == "3"
    for setter in ("set_z_order", "set_rotation", "set_description", "get_attribute"):
        assert not hasattr(shape, setter)
    equation = paragraph.add_equation("{a} over {b}", font_size=12.0, width=3000)
    assert (equation.font_size, equation.width) == (12.0, 3000)
    assert equation.element.get("baseUnit") == "1200"
    equation.script = "x+y"
    assert equation.script == "x+y" and not hasattr(equation, "set_script")
    picture = paragraph.add_picture(document.media.add_image(PNG, "png"), width=6000, height=6000)
    picture.crop = (1000, 0, 0, 0)
    assert picture.crop == (1000, 0, 0, 0) and not hasattr(picture, "set_crop")


@pytest.mark.parametrize(("millimetres", "units"), [(0.12, "33"), (0.5, "141"), (0.25, "70"), (1.0, "283"), (0, "0")])
def test_a_line_width_in_mm_writes_and_reads_back(millimetres: float, units: str) -> None:
    document = HwpxDocument.new()
    shape = document.add_paragraph("").add_line(line_width_mm=millimetres)
    assert shape.element.find(f"{_HP_NS}lineShape").get("width") == units
    assert shape.line_width_mm == millimetres
    shape.line_width_mm = shape.line_width_mm  # what it reads, written back, is what it was
    assert shape.element.find(f"{_HP_NS}lineShape").get("width") == units


def test_set_position_spells_its_frames_out() -> None:
    document = HwpxDocument.new()
    shape = document.add_paragraph("").add_rectangle(1000, 1000, treat_as_char=False)
    shape.set_position(horizontal_relative_to="PAPER", vertical_relative_to="PAGE",
                       horizontal_alignment="CENTER", vertical_alignment="TOP")
    position = shape.element.find(f"{_HP_NS}pos")
    assert [position.get(name) for name in ("horzRelTo", "vertRelTo", "horzAlign", "vertAlign")] == [
        "PAPER", "PAGE", "CENTER", "TOP"]
    with pytest.raises(HwpxValueError) as raised:
        shape.set_position(vertical_alignment="MIDDLE")
    assert raised.value.code == "shape-position-frame"
    assert raised.value.context["argument"] == "vertical_alignment"


def test_run_style_reads_are_properties() -> None:
    document = HwpxDocument.new()
    style = document.styles.char_property(document.styles.ensure_run(color="#FF0000", underline=True))
    assert style is not None
    assert style.color == "#FF0000" and style.underline_type == "BOTTOM"
    assert (style.superscript, style.subscript, style.emboss, style.engrave) == (False, False, False, False)
    assert style.matches(text_color="#FF0000", underline_type="BOTTOM")
    run = document.add_paragraph("글").runs[-1]
    assert "text" in run.content_kinds and isinstance(run.content_kinds, frozenset)


def test_header_border_fills_read_as_values() -> None:
    from hwpx.objects import BorderFillInfo

    document = HwpxDocument.new()
    header = document.oxml.headers[0]
    infos = header.border_fills
    assert infos and all(isinstance(info, BorderFillInfo) for info in infos.values())
    first = next(iter(infos))
    assert header.border_fill(first) == infos[first] == document.styles.border_fill(first)


def test_the_equation_converters_are_not_in_hwpx_experimental() -> None:
    import hwpx.experimental

    for name in ("latex_to_eqedit", "estimate_equation_size", "UnsupportedLatexError"):
        assert name not in hwpx.experimental.__all__
        with pytest.raises(hwpx.MovedToSubmodule, match=f"from hwpx.equation import {name}"):
            getattr(hwpx.experimental, name)
    from hwpx.equation import estimate_equation_size

    assert estimate_equation_size("{a} over {b}", font_size=11.0) == estimate_equation_size("{a} over {b}")

# --------------------------------------------------------------------------
# 값 형식 (WP5b): 구역은 객체, 배치·정렬은 풀어 쓴 이름, D15 형식은 hwpx.objects 에서도


def test_form_objects_and_places_read_their_section_as_an_object() -> None:
    document = HwpxDocument.new()
    paragraph = document.add_paragraph("양식")
    box = paragraph.add_check_box("동의")
    radio = document.fields.add_radio_button("예", group="물음")
    section = document.sections[0]
    assert box.section is section and radio.section is section
    assert all(edit.section is section for edit in (document.fields.add_edit_box("칸"),))
    assert document.sections.index(box.section) == 0
    place = next(document.text.iter_paragraphs())
    assert place.section is section and place.to_dict()["section"] == 0
    match = document.text.find("양식")[0]
    assert match.section is section and match.to_dict()["section"] == 0
    master = document.parts.add_master_page()
    master.add_paragraph("바탕")
    assert next(p for p in document.text.iter_paragraphs(where="master_page")).section is None


def test_object_position_and_numbering_levels_spell_their_names_out() -> None:
    document = HwpxDocument.new()
    shape = document.add_paragraph("").add_rectangle(4000, 2000)
    shape.set_position(treat_as_char=False, horizontal_relative_to="PAPER", vertical_alignment="TOP")
    position = shape.position
    assert (position.horizontal_relative_to, position.vertical_alignment) == ("PAPER", "TOP")
    assert position.to_dict()["horizontalRelativeTo"] == "PAPER"
    numbering_id = next(iter(document.styles.numberings), None) or document.styles.add_numbering(["^1."]).id
    level = document.styles.numbering(numbering_id).levels[0]
    assert isinstance(level.alignment, Alignment) and level.to_dict()["alignment"] == str(level.alignment)


def test_the_d15_types_are_the_implementation_classes_under_hwpx_objects() -> None:
    import hwpx.objects as objects
    from hwpx.oxml.header import Font, ParagraphProperty
    from hwpx.oxml.run import RunStyle
    from hwpx.oxml.table import HwpxTableGridPosition

    assert (objects.Font, objects.ParagraphProperty, objects.RunStyle) == (Font, ParagraphProperty, RunStyle)
    assert objects.GridPosition is HwpxTableGridPosition
    assert "GridPosition" in dir(objects) and "PictureRef" not in objects.__all__
    document = HwpxDocument.new()
    table = document.add_table(1, 1)
    assert isinstance(table.cell_map[0][0], objects.GridPosition)


def test_page_text_direction_reads_the_words_a_cell_reads() -> None:
    document = HwpxDocument.new()
    document.page.set_text_direction("VERTICAL", vertical_header_footer=True)
    assert document.page.text_direction() == "VERTICAL" and document.page.vertical_header_footer() is True
    cell = document.add_table(1, 1).cell(0, 0)
    cell.text_direction = "VERTICAL"
    assert type(cell.text_direction) is type(document.page.text_direction()) is str


def test_a_container_member_takes_its_line_width_in_mm() -> None:
    from hwpx.objects import ContainerMember

    member = ContainerMember.rect(0, 0, 1000, 1000)
    assert member.element.find(".//{*}lineShape").get("width") == "33"  # 0.12 mm, as 6.x's default "33"
    thick = ContainerMember.text_box(0, 0, 1000, 1000, "x", line_width_mm=0.5, vertical_alignment="TOP")
    assert thick.element.find(".//{*}lineShape").get("width") == "141"
    with pytest.raises(HwpxTypeError) as raised:
        ContainerMember.line(0, 0, 10, 10, line_width="33")
    assert raised.value.context["replacement"] == "line_width_mm"


def test_a_bullet_head_reads_its_alignment() -> None:
    from hwpx.oxml.header import BulletParaHead

    head = BulletParaHead("^1.", 1, 1, Alignment.LEFT, None, None, None, None, None)
    assert head.alignment == "LEFT"
    with pytest.raises(HwpxAttributeError) as raised:
        head.align  # noqa: B018
    assert raised.value.context["replacement"] == "BulletParaHead.alignment"


def test_add_master_page_reference_tells_the_new_keyword() -> None:
    """6.12 took ``id_ref=``; 7.0 names it ``master_page_id=`` and the old keyword says so."""
    document = HwpxDocument.new()
    properties = document.oxml.sections[0].properties
    with pytest.raises(TypeError) as caught:
        properties.add_master_page_reference(id_ref="masterpage0")
    assert "master_page_id" in str(caught.value)
