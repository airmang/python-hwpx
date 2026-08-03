#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""대조군(python-docx / openpyxl)의 표면을 **리플렉션으로 실측**한다.

## 왜 하드코딩하지 않는가

방향 문서 §4 철칙: *모든 게이트는 ① 우리가 만들지 않은 입력 또는 ② 우리가
통제하지 않는 관찰자 중 최소 하나를 포함한다.* 비교표에 "python-docx 는 19"
라고 적어 두면 그건 우리가 쓴 숫자다. 핀 고정된 휠을 받아 그 자리에서 세면
**우리가 만들지 않은 입력**이 된다.

## 무엇을 세는가

각 라이브러리의 "문서 객체" 하나를 정해 `vars(cls)` 의 공개 멤버를 센다.
`vars` 인 이유는 우리 쪽 락(`document_facade_surface.json`)이 같은 방식이기
때문이다 — 상속 멤버를 세면 `object` 의 것까지 들어와 비교가 무의미해진다.

- `python-docx` → `docx.document.Document`
- `openpyxl` → `openpyxl.workbook.workbook.Workbook`
- `python-hwpx` → `hwpx.document.HwpxDocument` (지원 dunder 4종 포함)

## 오프라인 CI

`--check` 는 네트워크를 쓰지 않는다. 커밋된 측정 JSON 을 읽어 **우리 쪽
숫자만** 다시 재고 대조한다. 대조군 값은 핀이 바뀌지 않는 한 고정이므로,
측정을 새로 하려면 네트워크가 있는 곳에서 인자 없이 실행한다.
"""

from __future__ import annotations

import argparse
import inspect
import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
MEASUREMENT = ROOT / "docs" / "control-surfaces.json"

#: 대조군 핀. 바꾸려면 의도적으로 바꾸고 재측정한다.
CONTROLS = {
    "python-docx": {
        "version": "1.2.0",
        "module": "docx.document",
        "attribute": "Document",
        "role": "문서 객체",
    },
    "openpyxl": {
        "version": "3.1.5",
        "module": "openpyxl.workbook.workbook",
        "attribute": "Workbook",
        "role": "통합문서 객체",
    },
}

#: 우리 파사드가 계약으로 인정하는 dunder. 대조군에도 같은 규칙을 적용한다.
PUBLIC_DUNDERS = {"__init__", "__repr__", "__enter__", "__exit__"}


def _surface(cls: type) -> dict[str, list[str]]:
    """`vars(cls)` 의 공개 멤버를 종류별로 나눈다."""

    methods: list[str] = []
    properties: list[str] = []
    other: list[str] = []
    for name, member in vars(cls).items():
        if name.startswith("_") and name not in PUBLIC_DUNDERS:
            continue
        if isinstance(member, property):
            properties.append(name)
        elif inspect.isfunction(member) or isinstance(member, (classmethod, staticmethod)):
            methods.append(name)
        else:
            other.append(name)
    return {
        "methods": sorted(methods),
        "properties": sorted(properties),
        "other": sorted(other),
    }


def _measure_control(name: str, spec: dict[str, str], workdir: pathlib.Path) -> dict:
    """핀 고정된 휠을 임시 디렉터리에 받아 그 자리에서 리플렉션한다."""

    target = workdir / name
    # 의존성까지 받는다. `--no-deps` 로는 python-docx 가 typing_extensions 를
    # 못 찾아 import 자체가 실패한다 — 리플렉션을 하려면 실제로 import 돼야 한다.
    subprocess.run(
        [
            sys.executable, "-m", "pip", "install", "--quiet",
            "--target", str(target), f"{name}=={spec['version']}",
        ],
        check=True,
        capture_output=True,
    )
    probe = (
        "import inspect, json, sys\n"
        f"sys.path.insert(0, {str(target)!r})\n"
        f"import {spec['module']} as mod\n"
        f"cls = getattr(mod, {spec['attribute']!r})\n"
        "public = {'__init__', '__repr__', '__enter__', '__exit__'}\n"
        "m, p, o = [], [], []\n"
        "for name, member in vars(cls).items():\n"
        "    if name.startswith('_') and name not in public: continue\n"
        "    if isinstance(member, property): p.append(name)\n"
        "    elif inspect.isfunction(member) or isinstance(member, (classmethod, staticmethod)): m.append(name)\n"
        "    else: o.append(name)\n"
        "print(json.dumps({'methods': sorted(m), 'properties': sorted(p), 'other': sorted(o)}))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], check=True, capture_output=True, text=True
    )
    surface = json.loads(result.stdout)
    surface["total"] = sum(len(surface[k]) for k in ("methods", "properties", "other"))
    surface["version"] = spec["version"]
    surface["qualname"] = f"{spec['module']}.{spec['attribute']}"
    surface["role"] = spec["role"]
    return surface


def measure_ours() -> dict:
    """우리 파사드는 커밋된 락에서 읽는다 — 락이 코드에서 유도되기 때문이다."""

    lock = json.loads(
        (ROOT / "tests" / "data" / "document_facade_surface.json").read_text(encoding="utf-8")
    )
    shims = json.loads(
        (ROOT / "tests" / "data" / "document_legacy_shims.json").read_text(encoding="utf-8")
    )
    kinds: dict[str, list[str]] = {"methods": [], "properties": [], "other": []}
    for name, entry in lock.items():
        if entry["kind"] == "property":
            kinds["properties"].append(name)
        elif entry["kind"] in {"method", "classmethod", "staticmethod"}:
            kinds["methods"].append(name)
        else:
            kinds["other"].append(name)
    return {
        "version": _our_version(),
        "qualname": "hwpx.document.HwpxDocument",
        "role": "문서 객체",
        "methods": sorted(kinds["methods"]),
        "properties": sorted(kinds["properties"]),
        "other": sorted(kinds["other"]),
        "total": len(lock),
        "legacyShims": len(shims),
        "surfaceBefore6_0": len(lock) + len(shims),
    }


def _our_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("version = "):
            return line.split("=", 1)[1].strip().strip('"')
    return "unknown"  # pragma: no cover


def survey() -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        workdir = pathlib.Path(tmp)
        controls = {
            name: _measure_control(name, spec, workdir) for name, spec in CONTROLS.items()
        }
    return {
        "schemaVersion": "python-hwpx.control-surfaces/v1",
        "method": (
            "vars(cls) 의 공개 멤버를 센다(상속 제외). 우리 락과 같은 규칙이라야 "
            "비교가 성립한다. 지원 dunder 4종(__init__/__repr__/__enter__/__exit__)은 "
            "양쪽 모두 포함한다."
        ),
        "controls": controls,
        "ours": measure_ours(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="네트워크 없이 검증한다 — 커밋된 대조군 값은 그대로 두고 우리 쪽만 다시 잰다.",
    )
    args = parser.parse_args()

    if args.check:
        if not MEASUREMENT.exists():
            print(f"측정 파일이 없습니다: {MEASUREMENT}", file=sys.stderr)
            return 1
        stored = json.loads(MEASUREMENT.read_text(encoding="utf-8"))
        ours = measure_ours()
        problems = []
        if ours["total"] != stored["ours"]["total"]:
            problems.append(
                f"우리 표면이 바뀌었습니다: {stored['ours']['total']} → {ours['total']}. "
                "measure_control_surfaces.py 를 다시 실행하세요."
            )
        if ours["legacyShims"] != stored["ours"]["legacyShims"]:
            problems.append(
                f"shim 수가 바뀌었습니다: {stored['ours']['legacyShims']} → {ours['legacyShims']}."
            )
        if problems:
            print("control surface drift:\n  " + "\n  ".join(problems), file=sys.stderr)
            return 1
        controls = ", ".join(
            f"{name} {entry['version']} = {entry['total']}"
            for name, entry in sorted(stored["controls"].items())
        )
        print(f"control surfaces ok — ours {ours['total']} | {controls}")
        return 0

    report = survey()
    MEASUREMENT.write_text(
        json.dumps(report, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {MEASUREMENT}")
    for name, entry in sorted(report["controls"].items()):
        print(
            f"  {name} {entry['version']} ({entry['qualname']}): {entry['total']} "
            f"= {len(entry['methods'])} methods + {len(entry['properties'])} properties"
        )
    ours = report["ours"]
    print(
        f"  python-hwpx {ours['version']} ({ours['qualname']}): {ours['total']} "
        f"(+ legacy shims {ours['legacyShims']}, 6.0 이전 {ours['surfaceBefore6_0']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
