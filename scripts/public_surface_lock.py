#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""공개 표면 잠금 — ``tests/data/public_surface.json`` 을 만들고 설치본과 견준다.

파일 하나가 공개 표면의 모든 층을 잠근다.

- ``top``        ``hwpx.__all__`` 의 이름(함수는 서명까지)
- ``root``       ``HwpxDocument`` 의 공개 멤버와 지원 dunder 4개(``__init__``·``__repr__``·
                 ``__enter__``·``__exit__``)
- ``namespaces`` 묶음 11개(``doc.styles`` …)의 멤버. ``doc.styles``·``doc.tables`` 처럼
                 꺼내기·세기를 받는 묶음은 그 dunder(``__getitem__`` 등)도 잠근다
- ``model``      ``hwpx.model`` 클래스마다 계약 멤버(``members``, 서명까지)와 계약 밖 공개
                 이름(``internal``, 이름만 — minor에서 바뀔 수 있는 구현 세부)
- ``objects``    ``hwpx.objects`` 값 형식의 필드(이름·형식, 순서), 멤버, enum 값
- ``module``     모듈 경로로 가져오는 stable 이름(``MODULE_NAMES``,
                 docs/stable-api.md 「7.0: 엔진의 공개 읽기」와 오류·수식 모듈)

멤버마다 종류(method/property …), 인자 ``[이름, 종류(P/PO/K/V/VK), 기본값 있음]``, 속성의 쓰기
가능 여부, 반환 표기(따옴표를 떼고 ``HwpxOxml*`` 구현 이름을 ``hwpx.model`` 이름으로 바꾼 글)를
적는다. 인자의 형식 표기는 견주지 않는다.

명령::

    # 설치본이 잠금과 같은지 본다. 같으면 0, 다르면 1(무엇이 어떻게 다른지와 고치는 명령을 적는다)
    python scripts/public_surface_lock.py check

    # 의도한 변경이면 잠금을 다시 만든다. 바뀐 것마다 tests/data/public_surface_changes.jsonl 에 한 줄
    python scripts/public_surface_lock.py check --update --reason "WP3: Paragraph.add_* 인자 이름"
    #   깨지는 변경(지우기·이름 바꾸기·서명 바꾸기)은 패키지 메이저가 잠금의 메이저보다 클 때만 받는다.
    #   다음 메이저를 만드는 동안에는 --allow-major-break(잠금의 major를 패키지 메이저 + 1로 적는다)
    #   계약(model)의 이름을 바꿨으면 새 이름을 계약에 올린다: --contract Table.cell_map
    #   계약에서 내리면: --internal Document.char_property

    # git 병합 뒤(충돌이 났든, 저절로 커밋됐든): 손으로 합치지 않는다. 두 쪽의 계약 분류를 세 갈래로
    # 합쳐 병합된 코드에서 다시 만든다. 두 쪽이 각자 장부에 적은 변경은 그대로 받고, 어느 쪽 잠금에도
    # 없던 변경(잠금을 다시 만들지 않은 가지, 이 잠금 전에 갈라진 가지)은 --reason이 있어야 받는다.
    # 성공 0, 받을 수 없거나 문서의 잠금 표 밖에 충돌이 남았으면 1.
    python scripts/public_surface_lock.py rebuild [--reason "<가지>: <무엇을 왜>"] [--allow-major-break]

    python scripts/public_surface_lock.py diff old.json new.json [--json out.json]
    python scripts/public_surface_lock.py live --out surface.json
    python scripts/public_surface_lock.py counts

``check --update`` 와 ``rebuild`` 는 docs/stable-api.md 의 잠금 표(표시 사이)도 다시 쓴다.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as _dt
import enum
import functools
import importlib
import inspect
import json
import re
import subprocess
import sys
import warnings
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / "tests" / "data" / "public_surface.json"
LEDGER = ROOT / "tests" / "data" / "public_surface_changes.jsonl"
DOC = ROOT / "docs" / "stable-api.md"

SCHEMA = "python-hwpx.public-surface/v1"
SCRIPT = "scripts/public_surface_lock.py"
UPDATE_HINT = f'python {SCRIPT} check --update --reason "<무엇을 왜>"'

#: 루트가 계약으로 내놓는 dunder(6.0 루트 예산 35에 들어간다).
ROOT_DUNDERS = frozenset({"__init__", "__repr__", "__enter__", "__exit__"})
#: 묶음이 꺼내기·세기를 받으면 그것도 계약이다(``doc.tables[0]``, ``len(doc.styles)``).
NAMESPACE_DUNDERS = frozenset({"__getitem__", "__iter__", "__len__", "__contains__"})
#: 이 모듈에서 온 멤버는 파이썬의 것이라 잠그지 않는다(버전마다 다르다).
FOREIGN_MODULES = frozenset({"builtins", "enum", "abc"})

#: 모듈 경로로 가져오는 stable 이름. ``None`` 이면 그 모듈의 ``__all__`` 전부다.
#: docs/stable-api.md 「7.0: 엔진의 공개 읽기」(+ 수식 변환, 오류 모듈).
MODULE_NAMES: dict[str, tuple[str, ...] | None] = {
    "hwpx.tools.exporter": ("ListLabels", "NoteLabels", "number_text", "NUMBER_TEXT_FORMATS", "table_grid_text"),
    "hwpx.oxml.run": ("text_element_content",),
    "hwpx.oxml.paragraph_heading": ("heading_outline_level", "outline_style_level", "paragraph_heading"),
    "hwpx.oxml.hyperlink_form": ("hyperlink_target",),
    "hwpx.oxml.table_sizes": ("cell_margins_of",),
    "hwpx.oxml.section_format": ("PAGE_PORTRAIT", "PAGE_LANDSCAPE"),
    "hwpx.oxml.namespaces": ("HP", "HH", "HC", "HS", "qn", "tag_local_name"),
    "hwpx.opc.security": None,
    "hwpx.form_fit": (
        "char_advance",
        "estimate_text_width",
        "indented_widths",
        "text_style_from_refs",
        "TextStyle",
        "resolve_slot_metrics",
        "SlotMetrics",
        "FitEngine",
        "FitPolicy",
        "FitResult",
    ),
    "hwpx.equation": (
        "latex_to_eqedit",
        "eqedit_to_latex",
        "estimate_equation_size",
        "UnsupportedLatexError",
        "EquationConversionError",
    ),
    "hwpx.errors": None,
}

_KIND = {
    inspect.Parameter.POSITIONAL_ONLY: "PO",
    inspect.Parameter.POSITIONAL_OR_KEYWORD: "P",
    inspect.Parameter.VAR_POSITIONAL: "V",
    inspect.Parameter.KEYWORD_ONLY: "K",
    inspect.Parameter.VAR_KEYWORD: "VK",
}


# --------------------------------------------------------------------------------------------- 표기


_LITERAL = re.compile(r"Literal\[[^\]]*\]")
_MODULE_PREFIX = re.compile(r"\b(?:[a-z_][a-z0-9_]*\.)+(?=[A-Za-z_])")
_HELD = re.compile(r"\x00(\d+)\x00")


def _split_top(text: str) -> list[str]:
    parts, depth, start = [], 0, 0
    for index, char in enumerate(text):
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(text[start:index].strip())
            start = index + 1
    parts.append(text[start:].strip())
    return parts


def _unwrap_unions(text: str) -> str:
    """``Optional[X]`` → ``X | None``, ``Union[A, B]`` → ``A | B`` (어느 깊이에서나).

    ``from __future__ import annotations`` 가 없는 모듈의 표기는 파이썬 버전마다 다르게
    찍힌다(3.10 ``typing.Optional[int]``, 3.14 ``int | None``). 한 모양으로 맞춘다.
    """

    match = re.search(r"\b(Optional|Union)\[", text)
    while match:
        depth, end = 0, None
        for index in range(match.end() - 1, len(text)):
            if text[index] == "[":
                depth += 1
            elif text[index] == "]":
                depth -= 1
                if depth == 0:
                    end = index
                    break
        if end is None:
            return text
        inner = [_unwrap_unions(part) for part in _split_top(text[match.end() : end])]
        if match.group(1) == "Optional":
            inner.append("None")
        text = text[: match.start()] + " | ".join(inner) + text[end + 1 :]
        match = re.search(r"\b(Optional|Union)\[", text)
    return text


@functools.lru_cache(maxsize=1)
def _model_aliases() -> tuple[tuple[str, str], ...]:
    """구현 이름 → 공개 이름(``HwpxOxmlParagraph`` → ``Paragraph``). ``hwpx.model``·``hwpx.objects``가
    다른 이름으로 다시 내보내는 클래스만."""

    import hwpx.model as model
    import hwpx.objects as objects

    pairs = set()
    for module in (model, objects):
        for public in module.__all__:
            implementation = getattr(getattr(module, public), "__name__", public)
            if implementation != public:
                pairs.add((implementation, public))
    return tuple(sorted(pairs, key=lambda pair: (-len(pair[0]), pair)))


def normalize_annotation(annotation: Any) -> str | None:
    """표기를 사용자가 읽는 글로: 따옴표·모듈 경로를 떼고 구현 이름을 ``hwpx.model`` 이름으로."""

    if annotation is None or annotation is inspect.Parameter.empty or annotation is inspect.Signature.empty:
        return None
    if isinstance(annotation, str):
        text = annotation
    elif isinstance(annotation, type) and not hasattr(annotation, "__origin__"):
        text = annotation.__qualname__
    else:
        text = repr(annotation)
    text = text.strip()
    held: list[str] = []

    def _hold(match: re.Match[str]) -> str:
        held.append(match.group(0))
        return f"\x00{len(held) - 1}\x00"

    text = _LITERAL.sub(_hold, text)
    text = text.replace("'", "").replace('"', "")
    text = _MODULE_PREFIX.sub("", text)
    text = re.sub(r"\bNoneType\b", "None", text)
    text = _unwrap_unions(text)
    for implementation, public in _model_aliases():
        text = re.sub(rf"\b{implementation}\b", public, text)
    text = text.replace("ET.Element", "Element")
    return _HELD.sub(lambda match: held[int(match.group(1))], text)


# --------------------------------------------------------------------------------------------- 실측


def _params(func: Callable[..., Any], *, bound: bool) -> tuple[list[list[Any]] | None, str | None]:
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return None, None
    parameters = list(signature.parameters.values())
    if bound and parameters and parameters[0].kind in (
        inspect.Parameter.POSITIONAL_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    ):
        parameters = parameters[1:]
    rows = [[p.name, _KIND[p.kind], p.default is not inspect.Parameter.empty] for p in parameters]
    return rows, normalize_annotation(signature.return_annotation)


def _owner(cls: type, name: str) -> type | None:
    for klass in cls.__mro__:
        if name in vars(klass):
            return klass
    return None


def _field_names(cls: type) -> set[str]:
    """dataclass 필드 이름(밑줄 없는 것). 기본값 없는 필드는 클래스 속성이 아니라 ``dir`` 에 안 보인다."""

    if not dataclasses.is_dataclass(cls):
        return set()
    return {f.name for f in dataclasses.fields(cls) if not f.name.startswith("_")}


def _member(cls: type, name: str) -> dict[str, Any] | None:
    entry: dict[str, Any]
    if name in _field_names(cls) and not isinstance(inspect.getattr_static(cls, name, None), property):
        # ``Paragraph.section`` 처럼 기본값 없는 dataclass 필드(인스턴스 속성)
        entry = {"kind": "attribute"}
        text = normalize_annotation(next(f.type for f in dataclasses.fields(cls) if f.name == name))
        if text:
            entry["returns"] = text
        return entry
    owner = _owner(cls, name)
    if owner is None or owner.__module__ in FOREIGN_MODULES:
        return None
    static = vars(owner)[name]
    if isinstance(static, property):
        entry = {"kind": "property", "settable": static.fset is not None}
        if static.fget is not None:
            _, returns = _params(static.fget, bound=True)
            if returns:
                entry["returns"] = returns
        return entry
    if isinstance(static, functools.cached_property):
        entry = {"kind": "property", "settable": False}
        _, returns = _params(static.func, bound=True)
        if returns:
            entry["returns"] = returns
        return entry
    fields = {f.name: f for f in dataclasses.fields(cls)} if dataclasses.is_dataclass(cls) else {}
    if name in fields:
        entry = {"kind": "attribute"}
        text = normalize_annotation(fields[name].type)
        if text:
            entry["returns"] = text
        return entry
    if isinstance(static, (classmethod, staticmethod)):
        entry = {"kind": type(static).__name__}
        params, returns = _params(static.__func__, bound=isinstance(static, classmethod))
    elif inspect.isfunction(static) or inspect.ismethoddescriptor(static) or inspect.isbuiltin(static):
        entry = {"kind": "method"}
        params, returns = _params(static, bound=True)
    else:
        return {"kind": "attribute", "returns": type(static).__name__}
    if params is not None:
        entry["params"] = params
    if returns:
        entry["returns"] = returns
    return entry


def _members(cls: type, *, dunders: Iterable[str] = (), skip: Iterable[str] = ()) -> dict[str, Any]:
    wanted = set(dunders)
    skipped = set(skip)
    out: dict[str, Any] = {}
    for name in sorted(dir(cls)):
        if name in skipped or (name.startswith("_") and name not in wanted):
            continue
        entry = _member(cls, name)
        if entry is not None:
            out[name] = entry
    return out


def _public_names(cls: type) -> set[str]:
    return {name for name in dir(cls) if not name.startswith("_")} | _field_names(cls)


def _enum_values(cls: type[enum.Enum]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for member in cls:
        value = member.value
        values[member.name] = value if isinstance(value, (str, int, float, bool)) or value is None else repr(value)
    return values


def _class_entry(cls: type, *, init: bool) -> dict[str, Any]:
    """enum은 값, dataclass는 필드(이름·형식, 순서)와 멤버, 그 밖의 클래스는 멤버.

    ``init`` 이면 클래스가 스스로 정의한 ``__init__`` 의 서명도 잠근다(모듈 수준 클래스는 사용자가
    만든다). dataclass의 ``__init__`` 은 필드가 말해 준다. 예외는 바탕 클래스도 잠근다
    (``except ValueError`` 가 계속 잡아야 한다).
    """

    if issubclass(cls, enum.Enum):
        return {"kind": "enum", "values": _enum_values(cls)}
    if dataclasses.is_dataclass(cls):
        every = dataclasses.fields(cls)
        return {
            "kind": "dataclass",
            "fields": [[f.name, normalize_annotation(f.type)] for f in every if not f.name.startswith("_")],
            "members": _members(cls, skip={f.name for f in every}),
        }
    entry: dict[str, Any] = {"kind": "class"}
    if issubclass(cls, BaseException):
        entry["bases"] = [klass.__name__ for klass in cls.__mro__[1:] if klass is not object]
    entry["members"] = _members(cls, dunders=("__init__",) if init else ())
    return entry


def _value_entry(value: Any) -> dict[str, Any]:
    if inspect.isclass(value):
        return _class_entry(value, init=True)
    if callable(value):
        params, returns = _params(value, bound=False)
        entry: dict[str, Any] = {"kind": "function"}
        if params is not None:
            entry["params"] = params
        if returns:
            entry["returns"] = returns
        return entry
    return {"kind": "constant", "type": type(value).__name__}


def _objects_entry(value: Any) -> dict[str, Any]:
    if not inspect.isclass(value):
        return {"kind": "constant", "type": type(value).__name__}
    return _class_entry(value, init=False)


def build_live(contract: Mapping[str, Iterable[str]], *, major: int | None = None) -> dict[str, Any]:
    """설치본의 공개 표면. ``contract`` 는 ``hwpx.model`` 클래스마다 계약 멤버 이름이다."""

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return _build_live(contract, major)


def _build_live(contract: Mapping[str, Iterable[str]], major: int | None) -> dict[str, Any]:
    import hwpx
    import hwpx.model as model
    import hwpx.objects as objects
    from hwpx._document.ns import NAMESPACES
    from hwpx.document import HwpxDocument

    lock: dict[str, Any] = {"schemaVersion": SCHEMA, "major": package_major() if major is None else major}

    top: dict[str, Any] = {}
    for name in sorted(hwpx.__all__):
        try:
            value = getattr(hwpx, name)
        except Exception:  # noqa: BLE001 — 옮겨 간 이름은 오류로 자리를 알려 준다
            top[name] = {"kind": "missing"}
            continue
        # 최상위 클래스는 이름만 잠근다(HwpxDocument는 root 층이 따로 잠근다).
        top[name] = {"kind": "class"} if inspect.isclass(value) else _value_entry(value)
    lock["top"] = top

    lock["root"] = _members(HwpxDocument, dunders=ROOT_DUNDERS)

    lock["namespaces"] = {
        name: _members(cls, dunders=NAMESPACE_DUNDERS, skip=("document",)) for name, cls in NAMESPACES.items()
    }

    classes: dict[str, Any] = {}
    for name in sorted(model.__all__):
        cls = getattr(model, name)
        wanted = set(contract.get(name, ()))
        public = _public_names(cls)
        members = {}
        for member_name in sorted(public & wanted):
            entry = _member(cls, member_name)
            if entry is not None:
                members[member_name] = entry
        classes[name] = {"members": members, "internal": sorted(public - set(members))}
    lock["model"] = classes

    lock["objects"] = {name: _objects_entry(getattr(objects, name)) for name in sorted(objects.__all__)}

    modules: dict[str, Any] = {}
    for module_name, names in MODULE_NAMES.items():
        module = importlib.import_module(module_name)
        listed = list(getattr(module, "__all__", ())) if names is None else list(names)
        entries: dict[str, Any] = {}
        for name in sorted(listed):
            entries[name] = _value_entry(getattr(module, name)) if hasattr(module, name) else {"kind": "missing"}
        modules[module_name] = entries
    lock["module"] = modules
    return lock


def package_major() -> int:
    import hwpx

    head = str(hwpx.__version__).split(".", 1)[0]
    return int(head) if head.isdigit() else 0


def package_version() -> str:
    import hwpx

    return str(hwpx.__version__)


def contract_of(lock: Mapping[str, Any]) -> dict[str, set[str]]:
    return {name: set(entry.get("members", {})) for name, entry in lock.get("model", {}).items()}


# --------------------------------------------------------------------------------------------- 견주기


@dataclasses.dataclass
class Changes:
    """잠금 둘의 차이. ``breaking`` 은 부르는 코드를 깨는 것, ``additive`` 는 더하기만 하는 것,
    ``other`` 는 부르는 코드에 닿지 않는 것(계약 밖 이름, 반환 표기만 생기거나 없어짐)."""

    breaking: list[str] = dataclasses.field(default_factory=list)
    additive: list[str] = dataclasses.field(default_factory=list)
    other: list[str] = dataclasses.field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.breaking or self.additive or self.other)

    def items(self) -> list[tuple[str, str]]:
        return (
            [("breaking", x) for x in self.breaking]
            + [("additive", x) for x in self.additive]
            + [("other", x) for x in self.other]
        )


_LABEL = {"breaking": "깨짐", "additive": "더함", "other": "기타"}


def _params_change(path: str, old: list[list[Any]], new: list[list[Any]], out: Changes) -> None:
    old_positional = [p[0] for p in old if p[1] in ("PO", "P")]
    new_positional = [p[0] for p in new if p[1] in ("PO", "P")]
    if new_positional[: len(old_positional)] != old_positional:
        out.breaking.append(f"{path}: 위치 인자 {old_positional} -> {new_positional}")
    new_by_name = {p[0]: p for p in new}
    old_by_name = {p[0]: p for p in old}
    for name, kind, has_default in old:
        now = new_by_name.get(name)
        if now is None:
            out.breaking.append(f"{path}: 인자 없어짐 {name}")
            continue
        if has_default and not now[2]:
            out.breaking.append(f"{path}: 인자 {name}의 기본값 없어짐")
        elif now[2] and not has_default:
            out.additive.append(f"{path}: 인자 {name}에 기본값 생김")
        if kind != now[1]:
            widened = (kind, now[1]) in {("K", "P"), ("PO", "P")}
            (out.additive if widened else out.breaking).append(f"{path}: 인자 {name}의 종류 {kind} -> {now[1]}")
    for name, kind, has_default in new:
        if name in old_by_name:
            continue
        if kind in ("V", "VK") or has_default:
            out.additive.append(f"{path}: 인자 생김 {name}")
        else:
            out.breaking.append(f"{path}: 반드시 줘야 하는 인자 생김 {name}")


def _value_names(entry: Mapping[str, Any]) -> dict[str, Any]:
    values = entry.get("values")
    if isinstance(values, dict):
        return dict(values)
    return {value: None for value in values or ()}


def _entry_change(path: str, old: Mapping[str, Any], new: Mapping[str, Any], out: Changes) -> None:
    if old.get("kind") != new.get("kind"):
        out.breaking.append(f"{path}: 종류 {old.get('kind')} -> {new.get('kind')}")
        return
    if old.get("params") is not None and new.get("params") is not None:
        _params_change(path, old["params"], new["params"], out)
    if old.get("settable") and new.get("settable") is False:
        out.breaking.append(f"{path}: 쓰기 없어짐")
    elif old.get("settable") is False and new.get("settable"):
        out.additive.append(f"{path}: 쓰기 생김")
    old_returns, new_returns = old.get("returns"), new.get("returns")
    if old_returns and new_returns and old_returns != new_returns:
        out.breaking.append(f"{path}: 반환 {old_returns} -> {new_returns}")
    elif old_returns and not new_returns:
        out.other.append(f"{path}: 반환 표기 없어짐 ({old_returns})")
    elif new_returns and not old_returns:
        out.other.append(f"{path}: 반환 표기 생김 ({new_returns})")
    if "type" in old and "type" in new and old["type"] != new["type"]:
        out.breaking.append(f"{path}: 값의 형식 {old['type']} -> {new['type']}")
    if "bases" in old and "bases" in new:
        gone = [b for b in old["bases"] if b not in new["bases"]]
        came = [b for b in new["bases"] if b not in old["bases"]]
        if gone:
            out.breaking.append(f"{path}: 바탕 클래스 없어짐 {gone}")
        if came:
            out.additive.append(f"{path}: 바탕 클래스 생김 {came}")
    if "values" in old and "values" in new:
        old_values, new_values = _value_names(old), _value_names(new)
        gone = [v for v in old_values if v not in new_values]
        came = [v for v in new_values if v not in old_values]
        if gone:
            out.breaking.append(f"{path}: 값 없어짐 {gone}")
        if came:
            out.additive.append(f"{path}: 값 생김 {came}")
        for name, value in old_values.items():
            if name in new_values and value is not None and new_values[name] is not None and value != new_values[name]:
                out.breaking.append(f"{path}.{name}: 값 {value!r} -> {new_values[name]!r}")
    if "fields" in old and "fields" in new:
        old_fields = {f[0]: f[1] for f in old["fields"]}
        new_fields = {f[0]: f[1] for f in new["fields"]}
        gone = [f for f in old_fields if f not in new_fields]
        came = [f for f in new_fields if f not in old_fields]
        if gone:
            out.breaking.append(f"{path}: 필드 없어짐 {gone}")
        if came:
            out.additive.append(f"{path}: 필드 생김 {came}")
        kept_old = [f for f in old_fields if f in new_fields]
        kept_new = [f for f in new_fields if f in old_fields]
        if kept_old != kept_new:
            out.breaking.append(f"{path}: 필드 순서 {kept_old} -> {kept_new}")
        for name in kept_old:
            if old_fields[name] and new_fields[name] and old_fields[name] != new_fields[name]:
                out.breaking.append(f"{path}.{name}: 필드 형식 {old_fields[name]} -> {new_fields[name]}")
    if "members" in old and "members" in new:
        _map_change(path, old["members"], new["members"], out)


def _map_change(path: str, old: Mapping[str, Any], new: Mapping[str, Any], out: Changes) -> None:
    for name, entry in old.items():
        if name not in new:
            out.breaking.append(f"{path}.{name}: 없어짐")
        else:
            _entry_change(f"{path}.{name}", entry, new[name], out)
    for name in new:
        if name not in old:
            out.additive.append(f"{path}.{name}: 생김")


def compare(old: Mapping[str, Any], new: Mapping[str, Any]) -> Changes:
    """``old`` 에서 ``new`` 로 무엇이 바뀌었나. 잠금에 적힌 것은 하나도 빼지 않고 견준다."""

    out = Changes()
    old_top, new_top = old.get("top", {}), new.get("top", {})
    for name, entry in old_top.items():
        if name not in new_top:
            out.breaking.append(f"hwpx.{name}: __all__에서 없어짐")
        else:
            _entry_change(f"hwpx.{name}", entry, new_top[name], out)
    out.additive += [f"hwpx.{name}: __all__에 생김" for name in new_top if name not in old_top]

    _map_change("doc", old.get("root", {}), new.get("root", {}), out)
    old_ns, new_ns = old.get("namespaces", {}), new.get("namespaces", {})
    for name in sorted(set(old_ns) | set(new_ns)):
        if name not in new_ns:
            out.breaking.append(f"doc.{name}: 묶음 없어짐")
        elif name not in old_ns:
            out.additive.append(f"doc.{name}: 묶음 생김")
        else:
            _map_change(f"doc.{name}", old_ns[name], new_ns[name], out)

    old_model, new_model = old.get("model", {}), new.get("model", {})
    for name in sorted(set(old_model) | set(new_model)):
        path = f"model.{name}"
        if name not in new_model:
            out.breaking.append(f"{path}: hwpx.model에서 없어짐")
            continue
        new_entry = new_model[name]
        if name not in old_model:
            public = len(new_entry.get("members", {})) + len(new_entry.get("internal", []))
            out.additive.append(f"{path}: hwpx.model에 생김 (공개 이름 {public}개)")
            continue
        old_entry = old_model[name]
        old_members, new_members = old_entry.get("members", {}), new_entry.get("members", {})
        old_internal, new_internal = set(old_entry.get("internal", [])), set(new_entry.get("internal", []))
        for member, entry in old_members.items():
            if member in new_members:
                _entry_change(f"{path}.{member}", entry, new_members[member], out)
            elif member in new_internal:
                out.breaking.append(f"{path}.{member}: 계약에서 내림(계약 밖으로)")
            else:
                out.breaking.append(f"{path}.{member}: 없어짐")
        for member in new_members:
            if member not in old_members:
                was = "계약 밖에서 올림" if member in old_internal else "생김"
                out.additive.append(f"{path}.{member}: 계약에 {was}")
        for member in sorted(new_internal - old_internal - set(old_members)):
            out.other.append(f"{path}.{member}: 계약 밖 공개 이름 생김 (계약이면 --contract {name}.{member})")
        for member in sorted(old_internal - new_internal - set(new_members)):
            out.other.append(f"{path}.{member}: 계약 밖 공개 이름 없어짐")

    old_objects, new_objects = old.get("objects", {}), new.get("objects", {})
    for name in sorted(set(old_objects) | set(new_objects)):
        path = f"objects.{name}"
        if name not in new_objects:
            out.breaking.append(f"{path}: hwpx.objects에서 없어짐")
        elif name not in old_objects:
            out.additive.append(f"{path}: hwpx.objects에 생김")
        else:
            _entry_change(path, old_objects[name], new_objects[name], out)

    old_modules, new_modules = old.get("module", {}), new.get("module", {})
    for name in sorted(set(old_modules) | set(new_modules)):
        _map_change(name, old_modules.get(name, {}), new_modules.get(name, {}), out)

    if not out and _body(old) != _body(new):
        out.breaking.append("잠금 파일의 모양이 설치본과 다르다(손으로 고친 곳이 있다) — 다시 만들면 맞춰진다")
    return out


def _body(lock: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in lock.items() if key not in ("schemaVersion", "major")}


# --------------------------------------------------------------------------------------------- 수·문서


def counts(lock: Mapping[str, Any]) -> dict[str, int]:
    model = lock.get("model", {})
    objects = lock.get("objects", {})
    return {
        "top": len(lock.get("top", {})),
        "root": len(lock.get("root", {})),
        "namespaces": len(lock.get("namespaces", {})),
        "namespace_members": sum(len(v) for v in lock.get("namespaces", {}).values()),
        "model_classes": len(model),
        "model_members": sum(len(v.get("members", {})) for v in model.values()),
        "model_internal": sum(len(v.get("internal", [])) for v in model.values()),
        "objects_types": len(objects),
        "objects_fields": sum(len(v.get("fields", []) or []) for v in objects.values()),
        "objects_members": sum(len(v.get("members", {})) for v in objects.values()),
        "objects_values": sum(len(v.get("values", {}) or {}) for v in objects.values()),
        "modules": len(lock.get("module", {})),
        "module_names": sum(len(v) for v in lock.get("module", {}).values()),
    }


DOC_BEGIN = "<!-- public-surface-lock:begin (scripts/public_surface_lock.py가 다시 쓴다. 손으로 고치지 않는다) -->"
DOC_END = "<!-- public-surface-lock:end -->"


def render_doc_table(lock: Mapping[str, Any]) -> str:
    c = counts(lock)
    objects_total = c["objects_fields"] + c["objects_members"] + c["objects_values"]
    rows = [
        DOC_BEGIN,
        "| 층 | 잠근 것 | 수 |",
        "|---|---|---:|",
        f"| 최상위 `hwpx.__all__` | 이름(함수는 서명까지) | {c['top']} |",
        f"| 루트 `HwpxDocument` | 공개 멤버와 지원 dunder 4개의 서명 | {c['root']} |",
        f"| 묶음 {c['namespaces']}개(`doc.styles` …) | 멤버의 서명(꺼내기·세기 dunder 포함) | {c['namespace_members']} |",
        f"| `hwpx.model` {c['model_classes']}개 클래스 — 계약 | 멤버의 서명 | {c['model_members']} |",
        f"| `hwpx.model` — 계약 밖 | 이름만(구현 세부, minor에서 바뀔 수 있다) | {c['model_internal']} |",
        (
            f"| `hwpx.objects` {c['objects_types']}개 값 형식 | 필드 {c['objects_fields']} · 멤버 {c['objects_members']}"
            f" · enum 값 {c['objects_values']} | {objects_total} |"
        ),
        f"| 모듈 수준 stable 이름({c['modules']}개 모듈) | 서명(클래스는 멤버까지) | {c['module_names']} |",
        DOC_END,
    ]
    return "\n".join(rows)


def doc_table_in(text: str) -> str | None:
    text = text.replace("\r\n", "\n")
    start = text.find(DOC_BEGIN)
    end = text.find(DOC_END)
    if start < 0 or end < start:
        return None
    return text[start : end + len(DOC_END)]


class DocConflict(Exception):
    """docs/stable-api.md 에 잠금 표 밖의 병합 충돌이 남았다."""


def _resolve_doc_conflicts(text: str) -> str:
    """잠금 표 안의 충돌은 한쪽을 골라 둔다(곧 다시 쓴다). 표 밖의 충돌은 풀지 않는다."""

    lines = text.split("\n")
    out: list[str] = []
    inside = False
    outside_conflicts = 0
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.startswith("<<<<<<< "):
            if DOC_BEGIN in line:
                inside = True
            elif DOC_END in line:
                inside = False
            out.append(line)
            index += 1
            continue
        ours: list[str] = []
        index += 1
        while index < len(lines) and not lines[index].startswith(("=======", "|||||||")):
            ours.append(lines[index])
            index += 1
        while index < len(lines) and not lines[index].startswith("======="):
            index += 1
        index += 1
        theirs: list[str] = []
        while index < len(lines) and not lines[index].startswith(">>>>>>> "):
            theirs.append(lines[index])
            index += 1
        index += 1
        touches = inside or any(DOC_BEGIN in x or DOC_END in x for x in ours + theirs)
        if not touches:
            outside_conflicts += 1
        out.extend(ours)
        for line in ours:
            if DOC_BEGIN in line:
                inside = True
            elif DOC_END in line:
                inside = False
    if outside_conflicts:
        raise DocConflict(f"docs/stable-api.md: 잠금 표 밖의 병합 충돌 {outside_conflicts}곳은 손으로 푼다")
    return "\n".join(out)


def sync_doc(lock: Mapping[str, Any], path: Path = DOC, *, resolve_conflicts: bool = False) -> bool:
    """문서의 잠금 표를 잠금에 맞춘다. 바꿨으면 True."""

    raw = path.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in raw else "\n"
    text = raw.replace("\r\n", "\n")
    if resolve_conflicts and "\n<<<<<<< " in "\n" + text:
        text = _resolve_doc_conflicts(text)
    current = doc_table_in(text)
    if current is None:
        raise SystemExit(f"{path}: 잠금 표 표시({DOC_BEGIN!r} … {DOC_END!r})가 없다")
    rendered = render_doc_table(lock)
    if current == rendered and text == raw.replace("\r\n", "\n"):
        return False
    text = text.replace(current, rendered)
    path.write_bytes(text.replace("\n", newline).encode("utf-8"))
    return True


# --------------------------------------------------------------------------------------------- 파일


#: 이 열쇠의 목록은 한 줄에 하나씩 쓴다(이름 목록, 필드 목록).
_ONE_PER_LINE = frozenset({"internal", "bases", "fields"})


def dumps(lock: Mapping[str, Any]) -> str:
    """멤버 하나가 한 줄이 되게 쓴다(검토하기 쉽고, git이 줄 단위로 합친다)."""

    def leaf(value: Any, key: str | None) -> bool:
        if isinstance(value, dict):
            return not value or ("kind" in value and "members" not in value and "fields" not in value)
        if isinstance(value, list):
            return not value or key not in _ONE_PER_LINE
        return True

    def emit(value: Any, depth: int, key: str | None = None) -> str:
        if leaf(value, key):
            return json.dumps(value, ensure_ascii=False)
        pad = " " * (depth + 1)
        if isinstance(value, dict):
            items = [f"{pad}{json.dumps(k, ensure_ascii=False)}: {emit(v, depth + 1, k)}" for k, v in value.items()]
            return "{\n" + ",\n".join(items) + "\n" + " " * depth + "}"
        rows = [f"{pad}{json.dumps(item, ensure_ascii=False)}" for item in value]
        return "[\n" + ",\n".join(rows) + "\n" + " " * depth + "]"

    return emit(dict(lock), 0) + "\n"


def write_lock(lock: Mapping[str, Any], path: Path) -> None:
    path.write_text(dumps(lock), encoding="utf-8", newline="\n")


def read_lock(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def append_ledger(path: Path, changes: Changes, reason: str, *, version: str, today: str | None = None) -> int:
    date = today or _dt.date.today().isoformat()
    lines = [
        json.dumps({"date": date, "version": version, "kind": kind, "change": change, "reason": reason}, ensure_ascii=False)
        for kind, change in changes.items()
    ]
    if lines:
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join(lines) + "\n")
    return len(lines)


# --------------------------------------------------------------------------------------------- 병합


#: 이 잠금 전에 hwpx.model 계약을 적던 파일(7.0 이름 정리 때 이 잠금으로 합쳤다). 그 전에 갈라진
#: 가지를 병합할 때 그 가지가 계약에 올리고 내린 것을 옮겨 오려고 읽는다.
LEGACY_MODEL_LOCK = "tests/data/model_surface.json"


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=False)


def _git_ok(root: Path, *args: str) -> str | None:
    result = _git(root, *args)
    return result.stdout.decode("utf-8").strip() if result.returncode == 0 else None


def _git_json(root: Path, spec: str) -> dict[str, Any] | None:
    result = _git(root, "show", spec)
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout.decode("utf-8"))
    except ValueError:
        return None


@dataclasses.dataclass
class MergeInputs:
    """병합의 두 쪽(과 바탕)의 잠금. 병합 중이 아니면 ``ours`` 에 지금 파일만 있다.

    ``*_legacy`` 는 그쪽의 옛 ``model_surface.json``(이 잠금이 생기기 전에 갈라진 가지)."""

    ours: dict[str, Any] | None
    theirs: dict[str, Any] | None = None
    base: dict[str, Any] | None = None
    ours_legacy: dict[str, Any] | None = None
    theirs_legacy: dict[str, Any] | None = None
    base_legacy: dict[str, Any] | None = None
    merging: bool = False


def _merge_refs(root: Path, lock_path: Path, relative: str) -> tuple[str, str] | None:
    """병합 중이면 (우리, 상대) 커밋. 방금 끝난 병합 커밋(충돌 없이 저절로 커밋된 병합)도 본다."""

    if _git_ok(root, "rev-parse", "-q", "--verify", "MERGE_HEAD"):
        return "HEAD", "MERGE_HEAD"
    if _git_ok(root, "rev-parse", "-q", "--verify", "HEAD^2") is None:
        return None
    committed = _git(root, "show", f"HEAD:{relative}")
    current = lock_path.read_bytes() if lock_path.exists() else b""
    if committed.returncode == 0 and committed.stdout.replace(b"\r\n", b"\n") != current.replace(b"\r\n", b"\n"):
        return None  # 병합 커밋 뒤에 잠금을 또 고쳤다: 병합이 아니라 지금 파일을 본다
    return "HEAD^1", "HEAD^2"


def merge_inputs(lock_path: Path) -> MergeInputs:
    directory = lock_path.resolve().parent
    top = _git_ok(directory, "rev-parse", "--show-toplevel")
    if top is None:
        return MergeInputs(ours=read_lock(lock_path))
    root = Path(top)
    relative = lock_path.resolve().relative_to(root.resolve()).as_posix()
    refs = _merge_refs(root, lock_path, relative)
    if refs is None:
        try:
            return MergeInputs(ours=read_lock(lock_path))
        except ValueError as error:
            raise SystemExit(f"{relative}: JSON으로 읽을 수 없고 병합 중도 아니다 — git에서 되살린 뒤 다시 만든다") from error
    ours_ref, theirs_ref = refs
    base_ref = _git_ok(root, "merge-base", ours_ref, theirs_ref)
    legacy = PurePosixPath(relative).with_name(PurePosixPath(LEGACY_MODEL_LOCK).name).as_posix()

    def read(ref: str | None, path: str) -> dict[str, Any] | None:
        return _git_json(root, f"{ref}:{path}") if ref else None

    return MergeInputs(
        ours=read(ours_ref, relative),
        theirs=read(theirs_ref, relative),
        base=read(base_ref, relative),
        ours_legacy=read(ours_ref, legacy),
        theirs_legacy=read(theirs_ref, legacy),
        base_legacy=read(base_ref, legacy),
        merging=True,
    )


def merge_contract(
    base: Mapping[str, Any] | None, ours: Mapping[str, Any], theirs: Mapping[str, Any] | None
) -> dict[str, set[str]]:
    """계약 분류의 세 갈래 합치기: 두 쪽이 다 남긴 것 + 어느 쪽이든 새로 올린 것."""

    mine = contract_of(ours)
    if theirs is None:
        return mine
    other = contract_of(theirs)
    root = contract_of(base) if base is not None else {}
    merged: dict[str, set[str]] = {}
    for name in set(mine) | set(other):
        a, b, o = mine.get(name, set()), other.get(name, set()), root.get(name, set())
        merged[name] = (a & b) | (a - o) | (b - o) if base is not None else a | b
    return merged


def _legacy_contract(model_surface: Mapping[str, Any] | None) -> dict[str, set[str]]:
    if model_surface is None:
        return {}
    return {name: set(entry.get("stable", [])) for name, entry in model_surface.get("classes", {}).items()}


def transition_contract(
    lock: Mapping[str, Any], legacy_side: Mapping[str, Any] | None, legacy_base: Mapping[str, Any] | None
) -> dict[str, set[str]]:
    """한쪽만 이 잠금을 가진 병합: 잠금의 계약에, 다른 쪽이 옛 model_surface.json에서 올리고 내린 것을 얹는다."""

    contract = {name: set(members) for name, members in contract_of(lock).items()}
    side, base = _legacy_contract(legacy_side), _legacy_contract(legacy_base)
    for name in set(side) | set(base):
        added = side.get(name, set()) - base.get(name, set())
        removed = base.get(name, set()) - side.get(name, set())
        contract[name] = (contract.get(name, set()) - removed) | added
    return contract


def _minus(changes: Changes, explained: Changes) -> Changes:
    known = set(explained.breaking) | set(explained.additive) | set(explained.other)
    return Changes(
        breaking=[x for x in changes.breaking if x not in known],
        additive=[x for x in changes.additive if x not in known],
        other=[x for x in changes.other if x not in known],
    )


def _union(first: Changes, second: Changes) -> Changes:
    out = Changes()
    for kind in ("breaking", "additive", "other"):
        merged = list(getattr(first, kind))
        merged += [x for x in getattr(second, kind) if x not in merged]
        setattr(out, kind, merged)
    return out


def plan_rebuild(inputs: MergeInputs) -> tuple[dict[str, set[str]], int, Callable[[dict[str, Any]], Changes]]:
    """(계약 분류, 잠금의 메이저, 다시 만든 표면에서 '어느 쪽 잠금에도 적히지 않은 변경'을 찾는 함수)."""

    ours, theirs = inputs.ours, inputs.theirs
    if ours is not None and theirs is not None:
        contract = merge_contract(inputs.base, ours, theirs)
        major = max(ours["major"], theirs["major"])

        def unexplained(live: dict[str, Any]) -> Changes:
            # 우리 잠금에서 달라진 것 가운데 상대 쪽 잠금이 이미 적은 것, 반대도 같다.
            return _union(
                _minus(compare(ours, live), compare(ours, theirs)),
                _minus(compare(theirs, live), compare(theirs, ours)),
            )

        return contract, major, unexplained
    if ours is None and theirs is None:
        raise SystemExit("병합의 어느 쪽에도 공개 표면 잠금이 없다")
    lock = ours if ours is not None else theirs
    assert lock is not None
    other_legacy = inputs.theirs_legacy if ours is not None else inputs.ours_legacy
    if inputs.merging and other_legacy is not None:
        contract = transition_contract(lock, other_legacy, inputs.base_legacy)
    else:
        contract = contract_of(lock)
    return contract, lock["major"], lambda live: compare(lock, live)


def _resolve_ledger(path: Path) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    markers = ("<<<<<<< ", "=======", "|||||||", ">>>>>>> ")
    if not any(line.startswith(markers) for line in text.splitlines()):
        return False
    kept = [line for line in text.splitlines() if line and not line.startswith(markers)]
    path.write_text("\n".join(kept) + "\n", encoding="utf-8", newline="\n")
    return True


# --------------------------------------------------------------------------------------------- 명령


def format_changes(changes: Changes, *, limit: int | None = None) -> list[str]:
    rows = changes.items()
    lines = [f"  {_LABEL[kind]}  {change}" for kind, change in (rows[:limit] if limit else rows)]
    if limit and len(rows) > limit:
        lines.append(f"  … {len(rows) - limit}줄 더")
    return lines


def _print_changes(changes: Changes, *, limit: int | None = None) -> None:
    for line in format_changes(changes, limit=limit):
        print(line)


def explain(changes: Changes, *, lock_name: str, lock_major: int, major: int, limit: int | None = 200) -> str:
    """잠금과 설치본이 다를 때 보여 줄 글: 무엇이 어떻게 다른지와 고치는 명령."""

    lines = [
        (
            f"공개 표면이 잠금({lock_name})과 다르다: 깨짐 {len(changes.breaking)} · 더함 {len(changes.additive)}"
            f" · 기타 {len(changes.other)}"
        ),
        *format_changes(changes, limit=limit),
        "의도한 변경이면 잠금을 다시 만든다(바뀐 것마다 tests/data/public_surface_changes.jsonl에 한 줄):",
        f"  {UPDATE_HINT}",
    ]
    if changes.breaking:
        lines.append(
            f"  깨지는 변경은 패키지 메이저({major})가 잠금의 메이저({lock_major})보다 클 때만 받는다."
            " 다음 메이저를 만드는 중이면 --allow-major-break를 붙인다."
        )
    if any("model." in line for line in changes.breaking + changes.other):
        lines.append("  hwpx.model 계약 멤버의 이름을 바꿨으면 새 이름을 계약에 올린다: --contract 클래스.새이름")
    lines.append(f"  git 병합 충돌이면 손으로 합치지 않는다: python {SCRIPT} rebuild")
    lines.append("  의도하지 않은 변경이면 코드를 되돌린다.")
    return "\n".join(lines)


def _reclassify(contract: dict[str, set[str]], promote: list[str], demote: list[str]) -> dict[str, set[str]]:
    import hwpx.model as model

    contract = {name: set(members) for name, members in contract.items()}
    for spec, add in [(x, True) for x in promote] + [(x, False) for x in demote]:
        class_name, _, member = spec.partition(".")
        if class_name not in model.__all__ or not member:
            raise SystemExit(f"--contract/--internal {spec!r}: 'hwpx.model 클래스.멤버' 꼴이어야 한다")
        public = _public_names(getattr(model, class_name))
        names = public if member == "*" else {member}
        if not names <= public:
            raise SystemExit(f"--contract/--internal {spec!r}: {class_name}에 그런 공개 이름이 없다")
        target = contract.setdefault(class_name, set())
        if add:
            target |= names
        else:
            target -= names
    return contract


def cmd_check(args: argparse.Namespace) -> int:
    lock_path = Path(args.lock)
    if not lock_path.exists():
        print(f"{lock_path}가 없다")
        return 2
    old = read_lock(lock_path)
    contract = contract_of(old)
    if args.update:
        contract = _reclassify(contract, args.contract or [], args.internal or [])
    elif args.contract or args.internal:
        print("--contract/--internal은 --update와 함께 쓴다")
        return 2
    live = build_live(contract, major=old["major"])
    changes = compare(old, live)
    doc_path = Path(args.doc)
    doc_ok = doc_table_in(doc_path.read_text(encoding="utf-8")) == render_doc_table(live if changes else old)

    if not changes:
        if doc_ok:
            print(f"공개 표면이 잠금과 같다 {json.dumps(counts(old), ensure_ascii=False)}")
            return 0
        if args.update:
            sync_doc(old, doc_path)
            print(f"{doc_path.name}의 잠금 표를 잠금에 맞췄다")
            return 0
        print(f"{doc_path.name}의 잠금 표가 잠금과 다르다. 고치려면: python {SCRIPT} check --update")
        return 1

    major = package_major()
    if not args.update:
        print(explain(changes, lock_name=lock_path.name, lock_major=old["major"], major=major))
        return 1
    print(
        f"공개 표면이 잠금({lock_path.name})과 다르다: 깨짐 {len(changes.breaking)} · 더함 {len(changes.additive)}"
        f" · 기타 {len(changes.other)}"
    )
    _print_changes(changes)
    if not args.reason:
        print("--update에는 --reason이 필요하다(무엇을 왜 바꿨는지 한 줄)")
        return 2
    if changes.breaking and major <= old["major"] and not args.allow_major_break:
        print(
            f"깨지는 변경 {len(changes.breaking)}개: 패키지 메이저({major})가 잠금의 메이저({old['major']})보다"
            " 클 때만 받는다. 다음 메이저를 만드는 중이면 --allow-major-break를 붙인다."
        )
        return 1
    new_major = max(old["major"], major)
    if changes.breaking and args.allow_major_break:
        new_major = max(new_major, major + 1)
    live["major"] = new_major
    write_lock(live, lock_path)
    written = append_ledger(Path(args.ledger), changes, args.reason, version=package_version())
    sync_doc(live, doc_path)
    print(f"잠금을 다시 만들었다 (major {new_major}, 장부 {written}줄) {json.dumps(counts(live), ensure_ascii=False)}")
    return 0


def cmd_rebuild(args: argparse.Namespace) -> int:
    """병합된 코드에서 잠금을 다시 만든다. 두 쪽이 각자 장부에 적은 변경은 그대로 받고, 어느 쪽 잠금에도
    없던 변경(잠금을 다시 만들지 않은 가지, 이 잠금 전에 갈라진 가지)은 ``--reason`` 이 있어야 받는다."""

    lock_path, ledger_path, doc_path = Path(args.lock), Path(args.ledger), Path(args.doc)
    inputs = merge_inputs(lock_path)
    contract, major, unexplained_in = plan_rebuild(inputs)
    live = build_live(contract, major=major)
    unexplained = unexplained_in(live)
    package = package_major()
    if unexplained:
        print(
            f"어느 쪽 잠금에도 적히지 않은 변경: 깨짐 {len(unexplained.breaking)} · 더함 {len(unexplained.additive)}"
            f" · 기타 {len(unexplained.other)}"
        )
        _print_changes(unexplained, limit=None if args.reason else 200)
        if not args.reason:
            print(f'받으려면 장부에 남길 까닭을 준다: python {SCRIPT} rebuild --reason "<가지>: <무엇을 왜>"')
            return 1
        if unexplained.breaking and package <= major and not args.allow_major_break:
            print(
                f"깨지는 변경은 패키지 메이저({package})가 잠금의 메이저({major})보다 클 때만 받는다."
                " 다음 메이저를 만드는 중이면 --allow-major-break를 붙인다."
            )
            return 1
        if unexplained.breaking and args.allow_major_break:
            major = max(major, package + 1)
    live["major"] = major
    if _resolve_ledger(ledger_path):
        print(f"{ledger_path.name}: 충돌 표시를 지우고 두 쪽 줄을 다 남겼다")
    try:
        sync_doc(live, doc_path, resolve_conflicts=True)
    except DocConflict as error:
        print(error)
        return 1
    write_lock(live, lock_path)
    written = append_ledger(ledger_path, unexplained, args.reason, version=package_version()) if unexplained else 0
    where = "병합된 코드에서" if inputs.merging else "지금 코드에서"
    print(f"잠금을 {where} 다시 만들었다 (major {major}, 장부 {written}줄) {json.dumps(counts(live), ensure_ascii=False)}")
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    old = read_lock(Path(args.old))
    new = read_lock(Path(args.new))
    changes = compare(old, new)
    print(f"깨짐 {len(changes.breaking)} · 더함 {len(changes.additive)} · 기타 {len(changes.other)}")
    _print_changes(changes, limit=args.limit)
    if args.json:
        Path(args.json).write_text(
            json.dumps(dataclasses.asdict(changes), ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
    return 1 if changes else 0


def cmd_live(args: argparse.Namespace) -> int:
    lock_path = Path(args.lock)
    contract = contract_of(read_lock(lock_path)) if lock_path.exists() else {}
    live = build_live(contract)
    write_lock(live, Path(args.out))
    print(json.dumps(counts(live), ensure_ascii=False))
    return 0


def cmd_counts(args: argparse.Namespace) -> int:
    print(json.dumps(counts(read_lock(Path(args.lock))), ensure_ascii=False, indent=1))
    return 0


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog=SCRIPT, description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def paths(p: argparse.ArgumentParser, *, ledger: bool = False, doc: bool = False) -> None:
        p.add_argument("--lock", default=str(LOCK), help="잠금 파일(기본 tests/data/public_surface.json)")
        if ledger:
            p.add_argument("--ledger", default=str(LEDGER), help="변경 장부(기본 tests/data/public_surface_changes.jsonl)")
        if doc:
            p.add_argument("--doc", default=str(DOC), help="잠금 표가 있는 문서(기본 docs/stable-api.md)")

    check = sub.add_parser("check", help="설치본이 잠금과 같은지 본다(--update면 다시 만든다)")
    paths(check, ledger=True, doc=True)
    check.add_argument("--update", action="store_true", help="잠금을 설치본에 맞춰 다시 쓴다")
    check.add_argument("--reason", help="바꾼 까닭 한 줄(장부에 남는다)")
    check.add_argument(
        "--allow-major-break",
        action="store_true",
        help="다음 메이저를 만드는 동안 깨지는 변경을 받는다(잠금의 major를 패키지 메이저 + 1로)",
    )
    check.add_argument("--contract", action="append", metavar="클래스.멤버", help="hwpx.model 이름을 계약에 올린다(클래스.* = 전부)")
    check.add_argument("--internal", action="append", metavar="클래스.멤버", help="hwpx.model 이름을 계약에서 내린다")
    check.set_defaults(func=cmd_check)

    rebuild = sub.add_parser("rebuild", help="git 병합 뒤 두 쪽의 계약 분류를 합쳐 다시 만든다")
    paths(rebuild, ledger=True, doc=True)
    rebuild.add_argument("--reason", help="어느 쪽 잠금에도 적히지 않은 변경을 받을 때 장부에 남길 까닭")
    rebuild.add_argument("--allow-major-break", action="store_true", help="check와 같다")
    rebuild.set_defaults(func=cmd_rebuild)

    diff = sub.add_parser("diff", help="잠금 파일 둘을 견준다(다르면 1)")
    diff.add_argument("old")
    diff.add_argument("new")
    diff.add_argument("--json")
    diff.add_argument("--limit", type=int, default=80)
    diff.set_defaults(func=cmd_diff)

    live = sub.add_parser("live", help="설치본의 표면을 파일로 쓴다(계약 분류는 잠금에서)")
    paths(live)
    live.add_argument("--out", required=True)
    live.set_defaults(func=cmd_live)

    count = sub.add_parser("counts", help="잠금의 층별 수")
    paths(count)
    count.set_defaults(func=cmd_counts)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "src"))
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass
    raise SystemExit(main())
