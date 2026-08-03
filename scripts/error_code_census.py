#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""공개 경로의 `raise` 를 세어 typed-error 전환 진척을 산출한다.

## 왜 개수 게이트가 아니라 인구조사인가

"typed error 200건 달성" 같은 목표는 Goodhart 한다 — 의미 없는 곳을 감싸서
숫자를 올릴 수 있다. 그래서 이 도구는 **목표치를 정하지 않고 현재 상태를
기록**하고, 락(`tests/data/error_census.json`)이 **악화만 막는다**(ratchet).

## 무엇을 세는가

`raise X(...)` 를 세 부류로 나눈다:

- **typed** — `HwpxError` 계열. `code` 를 명시했는지도 따로 센다.
- **untyped** — `ValueError`/`TypeError`/`KeyError`/`RuntimeError` 등 맨 builtin.
  전환 대상이다.
- **other** — `NotImplementedError`, 재-raise(`raise` 단독), OS 예외 등.
  전환 대상이 아니다(헌법: OS·컨테이너 실패는 Python 이 내는 그대로 둔다).

`scope` 는 **공개 경로**다 — 사용자가 `HwpxDocument` 에서 출발해 닿는 표면
(`document.py` + `_document/`). `oxml/`·`patch`·`table_patch` 등 내부는
6.x 에서 점진 전환하므로 `observed` 로만 기록한다.
"""

from __future__ import annotations

import argparse
import ast
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "hwpx"
LOCK = ROOT / "tests" / "data" / "error_census.json"

#: 사용자가 파사드에서 출발해 닿는 경로. 6.0 의 ≥90% 게이트가 걸리는 범위다.
PUBLIC_SCOPE = ("document.py", "_document")

#: 전환 대상 builtin. 이 이름으로 raise 하면 `code`·`context`·`suggestion` 이 없다.
UNTYPED = frozenset({"ValueError", "TypeError", "KeyError", "RuntimeError", "LookupError"})

#: 코드 형식: ``<도메인>-<조건>`` kebab-case.
CODE_PATTERN = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)+$")


def _exception_name(node: ast.expr | None) -> str | None:
    if node is None:
        return None
    if isinstance(node, ast.Call):
        return _exception_name(node.func)
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _explicit_code(node: ast.expr | None) -> str | None:
    if not isinstance(node, ast.Call):
        return None
    for keyword in node.keywords:
        if keyword.arg == "code" and isinstance(keyword.value, ast.Constant):
            value = keyword.value.value
            return value if isinstance(value, str) else None
    return None


def _is_public(relative: str) -> bool:
    return relative == "document.py" or relative.startswith("_document/")


def survey() -> dict:
    typed: list[dict] = []
    untyped: list[dict] = []
    other: list[dict] = []
    codes: dict[str, list[str]] = {}

    for path in sorted(SRC.rglob("*.py")):
        relative = path.relative_to(SRC).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Raise):
                continue
            name = _exception_name(node.exc)
            if name is None:  # bare ``raise`` — 재-raise 는 전환 대상이 아니다
                continue
            entry = {"file": relative, "line": node.lineno, "exception": name}
            if name.startswith("Hwpx") or name in {"SaveError", "PreservationDowngradeError"}:
                code = _explicit_code(node.exc)
                if code is not None:
                    entry["code"] = code
                    codes.setdefault(code, []).append(f"{relative}:{node.lineno}")
                typed.append(entry)
            elif name in UNTYPED:
                untyped.append(entry)
            else:
                other.append(entry)

    public_typed = [e for e in typed if _is_public(e["file"])]
    public_untyped = [e for e in untyped if _is_public(e["file"])]
    public_total = len(public_typed) + len(public_untyped)
    coverage = (len(public_typed) / public_total) if public_total else 1.0

    return {
        "schemaVersion": "python-hwpx.error-census/v1",
        "scope": {
            "public": list(PUBLIC_SCOPE),
            "note": (
                "공개 경로 = 사용자가 HwpxDocument 에서 출발해 닿는 표면. "
                "oxml/·patch·table_patch 등 내부는 6.x 에서 점진 전환하며 "
                "observed 로만 기록한다."
            ),
        },
        "public": {
            "typed": len(public_typed),
            "untyped": len(public_untyped),
            "total": public_total,
            "typedRatio": round(coverage, 4),
            "untypedSites": sorted(
                f"{e['file']}:{e['line']} {e['exception']}" for e in public_untyped
            ),
        },
        "observed": {
            "typed": len(typed),
            "untyped": len(untyped),
            "other": len(other),
            "untypedByFile": {
                file: sum(1 for e in untyped if e["file"] == file)
                for file in sorted({e["file"] for e in untyped})
            },
        },
        "codes": {code: sorted(sites) for code, sites in sorted(codes.items())},
        "malformedCodes": sorted(c for c in codes if not CODE_PATTERN.match(c)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="락과 대조만 한다(악화면 비-0 종료). 갱신하지 않는다.",
    )
    args = parser.parse_args()

    report = survey()
    if args.check:
        if not LOCK.exists():
            print(f"락이 없습니다: {LOCK}", file=sys.stderr)
            return 1
        locked = json.loads(LOCK.read_text(encoding="utf-8"))
        problems = []
        if report["public"]["untyped"] > locked["public"]["untyped"]:
            problems.append(
                f"공개 경로 untyped 증가: {locked['public']['untyped']} → "
                f"{report['public']['untyped']}"
            )
        if report["observed"]["untyped"] > locked["observed"]["untyped"]:
            problems.append(
                f"전체 untyped 증가: {locked['observed']['untyped']} → "
                f"{report['observed']['untyped']}"
            )
        if report["malformedCodes"]:
            problems.append(f"형식 위반 코드: {report['malformedCodes']}")
        if problems:
            print("error census ratchet 위반:\n  " + "\n  ".join(problems), file=sys.stderr)
            return 1
        print(
            "error census ok — 공개 경로 typed "
            f"{report['public']['typed']}/{report['public']['total']} "
            f"({report['public']['typedRatio']:.1%}), untyped {report['observed']['untyped']}"
        )
        return 0

    LOCK.parent.mkdir(parents=True, exist_ok=True)
    LOCK.write_text(
        json.dumps(report, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {LOCK}\n"
        f"  공개 경로: typed {report['public']['typed']} / "
        f"untyped {report['public']['untyped']} "
        f"({report['public']['typedRatio']:.1%} typed)\n"
        f"  전체: typed {report['observed']['typed']} / "
        f"untyped {report['observed']['untyped']} / other {report['observed']['other']}\n"
        f"  코드 {len(report['codes'])}종, 형식 위반 {len(report['malformedCodes'])}건"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
