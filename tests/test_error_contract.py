# SPDX-License-Identifier: Apache-2.0
"""062-engine-surface WP-E 게이트 — typed error 어휘.

5.x 는 공개 경로에서 맨 `ValueError` 로 실패했다. 메시지 말고는 아무것도 없어서
호출자가 분기할 수 없었고, 무엇을 고쳐야 하는지도 말하지 않았다.

6.0 은 같은 실패를 `code`·`context`·`suggestion` 과 함께 던진다. **기존
`except ValueError` 는 그대로 작동한다** — typed 클래스가 builtin 을 함께
상속하기 때문이다(`SaveError(HwpxError, ValueError)` 선례).
"""

from __future__ import annotations

import ast
import json
import pathlib
import re
import subprocess
import sys

import pytest

from hwpx.document import HwpxDocument
from hwpx.errors import (
    ERROR_CODE_DOMAINS,
    ERROR_CODES,
    GRANDFATHERED_CODES,
    HwpxError,
    HwpxLookupError,
    HwpxStateError,
    HwpxTypeError,
    HwpxValueError,
)
from hwpx.quality.report import ERROR_CODES as QUALITY_ERROR_CODES

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "hwpx"
CENSUS = ROOT / "tests" / "data" / "error_census.json"
DOC = ROOT / "docs" / "error-codes.md"

#: 코드 형식: ``<도메인>-<조건>`` kebab-case.
CODE_PATTERN = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)+$")

#: 공개 경로 typed 비율 하한(설계서 §6.5).
MIN_PUBLIC_TYPED_RATIO = 0.90


# --------------------------------------------------------------------------
# 게이트 ① 공개 경로에 맨 builtin raise 가 없다


def _untyped_raises(paths: list[pathlib.Path]) -> list[str]:
    offenders = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Raise) or node.exc is None:
                continue
            exc = node.exc
            func = exc.func if isinstance(exc, ast.Call) else exc
            name = func.id if isinstance(func, ast.Name) else None
            if name in {"ValueError", "TypeError", "KeyError", "RuntimeError", "LookupError"}:
                offenders.append(f"{path.relative_to(SRC)}:{node.lineno} {name}")
    return sorted(offenders)


def test_the_public_path_raises_no_bare_builtins() -> None:
    paths = [SRC / "document.py"]
    paths += sorted((SRC / "_document").rglob("*.py"))
    assert _untyped_raises(paths) == []


def test_the_census_reports_the_public_path_as_fully_typed() -> None:
    census = json.loads(CENSUS.read_text(encoding="utf-8"))
    assert census["public"]["untyped"] == 0
    assert census["public"]["typedRatio"] >= MIN_PUBLIC_TYPED_RATIO


# --------------------------------------------------------------------------
# 게이트 ③ 인구조사 ratchet — 악화하면 CI RED


def test_the_census_ratchet_is_green() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "error_code_census.py"), "--check"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_the_ratchet_can_actually_fail(tmp_path: pathlib.Path) -> None:
    """게이트가 실패할 수 있음을 증명한다 — 통과만 하는 게이트는 게이트가 아니다."""

    census = json.loads(CENSUS.read_text(encoding="utf-8"))
    tightened = json.loads(json.dumps(census))
    tightened["observed"]["untyped"] = census["observed"]["untyped"] - 1
    lock = tmp_path / "error_census.json"
    lock.write_text(json.dumps(tightened, ensure_ascii=False), encoding="utf-8")

    script = (ROOT / "scripts" / "error_code_census.py").read_text(encoding="utf-8")
    patched = tmp_path / "census.py"
    patched.write_text(
        script.replace(
            "ROOT = pathlib.Path(__file__).resolve().parent.parent",
            f"ROOT = pathlib.Path({str(ROOT)!r})",
        ).replace(
            'LOCK = ROOT / "tests" / "data" / "error_census.json"',
            f"LOCK = pathlib.Path({str(lock)!r})",
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(patched), "--check"], capture_output=True, text=True, cwd=ROOT
    )
    assert result.returncode != 0
    assert "untyped 증가" in result.stderr


# --------------------------------------------------------------------------
# 게이트 ⑤ 코드 형식 + 레지스트리 정합


@pytest.mark.parametrize("code", sorted(ERROR_CODES))
def test_every_registered_code_matches_the_format(code: str) -> None:
    assert CODE_PATTERN.match(code), f"{code} 는 <도메인>-<조건> 이 아니다"
    if code in GRANDFATHERED_CODES:
        pytest.skip("5.x 에 이미 나간 코드 — 7.0 에서 정리(errors.GRANDFATHERED_CODES)")
    assert code.split("-", 1)[0] in ERROR_CODE_DOMAINS, f"{code} 의 도메인이 미등록"


def test_the_grandfathered_list_only_shrinks() -> None:
    """유예는 부채다 — 늘 수 없다."""

    assert len(GRANDFATHERED_CODES) <= 2
    assert GRANDFATHERED_CODES <= set(ERROR_CODES)


def test_every_raised_code_is_registered() -> None:
    """코드를 새로 쓰면 레지스트리(=문서)에 반드시 등재된다."""

    census = json.loads(CENSUS.read_text(encoding="utf-8"))
    unregistered = sorted(set(census["codes"]) - set(ERROR_CODES))
    assert unregistered == [], (
        f"레지스트리에 없는 코드: {unregistered}. "
        "hwpx.errors.ERROR_CODES 에 등재하고 docs/error-codes.md 를 다시 생성하세요."
    )


def test_the_document_is_generated_from_the_registry() -> None:
    """문서와 코드가 어긋날 수 없게 한다 — 문서끼리 대조하는 가드는 놓친다."""

    text = DOC.read_text(encoding="utf-8")
    for code, meaning in ERROR_CODES.items():
        assert f"| `{code}` |" in text, f"{code} 가 문서에 없다"
        assert meaning in text, f"{code} 의 설명이 문서와 다르다"


def test_the_two_code_vocabularies_stay_separate() -> None:
    """kebab(예외) ↔ SCREAMING_SNAKE(영수증) 경계는 문서화된 사실이다."""

    assert not (set(ERROR_CODES) & set(QUALITY_ERROR_CODES))
    assert all(code.isupper() or "_" in code for code in QUALITY_ERROR_CODES)
    assert all(code.islower() for code in ERROR_CODES)
    text = DOC.read_text(encoding="utf-8")
    assert "SCREAMING_SNAKE" in text and "quality-gate-failed" in text


# --------------------------------------------------------------------------
# 하위 호환 — 5.x `except` 가 그대로 작동한다


@pytest.mark.parametrize(
    "typed,builtin",
    [
        (HwpxValueError, ValueError),
        (HwpxTypeError, TypeError),
        (HwpxLookupError, KeyError),
        (HwpxStateError, RuntimeError),
    ],
)
def test_typed_errors_still_answer_to_the_builtin_they_replaced(typed, builtin) -> None:
    assert issubclass(typed, builtin)
    assert issubclass(typed, HwpxError)


def test_lookup_error_keeps_the_human_sentence() -> None:
    """`KeyError.__str__` 은 메시지에 따옴표를 씌운다 — 베이스 계약을 지킨다."""

    error = HwpxLookupError("스타일을 찾을 수 없습니다.", code="style-not-found")
    assert str(error) == "스타일을 찾을 수 없습니다."


@pytest.mark.parametrize(
    "call,builtin,code",
    [
        (lambda d: d.add_paragraph("t", style="개요1"), KeyError, "style-not-found"),
        (lambda d: d.add_heading("t", level=99), ValueError, "heading-level-out-of-range"),
        (lambda d: d.page.set_header(section=0), ValueError, "page-argument-missing"),
        (lambda d: d.text.replace("", "x"), ValueError, "text-search-empty"),
        (lambda d: d.tracking.insert(999, "x"), KeyError, "paragraph-not-found"),
        (lambda d: d.shapes.add_equation("", section=0), ValueError, "shape-equation-script-empty"),
        (lambda d: d.fields.add("", section=0), ValueError, "field-name-empty"),
        (lambda d: d.shapes.add_chart(b"", section=0), ValueError, "shape-chart-xml-empty"),
    ],
)
def test_real_failures_carry_a_registered_code_and_stay_catchable(call, builtin, code) -> None:
    document = HwpxDocument.new()
    document.add_paragraph("본문")
    with pytest.raises(builtin) as excinfo:  # 5.x 스타일 except 가 그대로 잡는다
        call(document)
    error = excinfo.value
    assert isinstance(error, HwpxError)
    assert error.code == code
    assert error.code in ERROR_CODES
    assert error.to_dict()["code"] == code


def test_every_public_failure_offers_a_next_step() -> None:
    """`suggestion` 이 없는 실패는 '뭘 하라는 건지 모르겠다' 와 같다."""

    document = HwpxDocument.new()
    document.add_paragraph("본문")
    cases = [
        lambda d: d.add_paragraph("t", style="없는스타일"),
        lambda d: d.add_heading("t", level=0),
        lambda d: d.page.setup(section=999),
        lambda d: d.fields.add("", section=0),
        lambda d: d.tracking.delete(1, match=""),
    ]
    for call in cases:
        with pytest.raises(HwpxError) as excinfo:
            call(document)
        assert excinfo.value.suggestion, excinfo.value.code
