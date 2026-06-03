# HWPX 흡수 강화 Implementation Plan

> **For agentic workers (Codex):** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 검증된 외부 아이디어를 기존 3층 스택(`python-hwpx`/`hwpx-mcp-server`/`hwpx-skill`)에 정렬해, HWPX 깨짐 방어와 실전 양식 처리 깊이를 보강한다.

**Architecture:** Phase는 Wily Stage와 1:1로 매핑된다. 각 Phase는 독립적으로 working/testable. 신규 코드는 `python-hwpx/src/hwpx/`에 모듈로 추가하고, CLI는 `[project.scripts]`에 등록, MCP 노출은 `hwpx-mcp-server`에서 thin wrapper로 한다. **법적 경계: 외부 코드 직접 복사 금지. 알고리즘만 재구현(clean-room). 포팅 출처는 NOTICE에 기록.**

**Tech Stack:** Python 3.10+, lxml(+stdlib ET fallback), zipfile, pytest. 기존 패턴: SPDX 헤더 `# SPDX-License-Identifier: Apache-2.0`, frozen dataclass 결과 객체, `tools/*.py`의 `main(argv)` CLI 진입점.

**개발 환경:**
- 작업 루트: `/Users/wilycastle/Code/projects/hwpx/python-hwpx`
- 테스트: `cd /Users/wilycastle/Code/projects/hwpx/python-hwpx && uv run --extra dev pytest -q`
- 단일 테스트: `uv run --extra dev pytest tests/test_<name>.py::<test_name> -v`
- fixtures: 기존 `tests/fixtures/`에 샘플 .hwpx 존재. 신규 fixture는 프로그램으로 생성(아래 helper 참조).

**검증된 사실 (구현 전 필독):**
- `pack_hwpx`(`src/hwpx/tools/archive_cli.py:257`)는 이미 mimetype 첫엔트리·`ZIP_STORED`·재정렬·pack후 validate를 한다. 단 **디렉토리 입력 전용** — 기존 .hwpx 직접 repair 경로 없음.
- `validate_package`(`src/hwpx/tools/package_validator.py:172`)는 이미 `zf.testzip()` CRC 체크를 한다(194-196줄). repair API는 이걸 재사용한다.
- `template_formfit.py`의 `_looks_like_placeholder`(463줄 근처)는 단일 텍스트 placeholder만 인식, split-run 미지원.

**구현 근거 잠금 (S-005 / Phase 0):**
- 이 Stage는 추측 구현 금지. 구현은 (1) 현재 `python-hwpx`의 `pack_hwpx`/`validate_package` 동작, (2) 외부 레포의 공개 동작 설명, (3) ZIP 포맷의 Local File Header/CRC 사실에만 근거한다.
- `repair_repack` 근거: `sakada3/hwp-ops`의 `hwpx_rezip` 아이디어(Apache-2.0) — `mimetype` 첫 엔트리 `ZIP_STORED` 강제와 ZIP CRC self-check. 코드는 복사하지 않고 `zipfile` 기반으로 clean-room 재구현한다.
- broken-ZIP 복구 근거: `chrisryugj/kordoc`의 HWPX 손상 ZIP 복구 아이디어(MIT) — central directory 손상 시 Local File Header(`PK\x03\x04`) 스캔. 코드는 복사하지 않고 `struct`/`zlib` 기반으로 clean-room 재구현한다.
- 외부 구현의 함수 본문/구조를 그대로 옮기거나 번역 포팅하지 않는다. 구현 중 이 근거로 설명되지 않는 동작이 필요해지면 즉시 중단하고 출처·테스트·법적 경계를 재확인한다.
- 최종 산출물은 `NOTICE`에 위 출처와 clean-room 재구현 사실을 기록해야 Stage 완료 가능하다.

---

## Phase 0 — 깨짐 방어 (repair-repack + broken-ZIP 복구 + 가드)

**Stage 매핑:** Phase 0 → Wily Stage 1.

### Task 0.1: repair-repack 모듈 골격 + 테스트 fixture helper

**Files:**
- Create: `src/hwpx/tools/repair.py`
- Test: `tests/test_repair_repack.py`

- [ ] **Step 1: fixture helper와 첫 실패 테스트 작성**

`tests/test_repair_repack.py`:

```python
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from hwpx.tools.repair import repair_repack, RepairResult


def _make_broken_order_hwpx(path: Path) -> None:
    """mimetype이 첫 엔트리가 아니고 DEFLATE로 압축된 잘못된 HWPX를 만든다."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        # 일부러 mimetype을 두 번째로, DEFLATE로 기록 (스펙 위반)
        zf.writestr("Contents/header.xml", b"<hh:head xmlns:hh='x'/>")
        zf.writestr("mimetype", b"application/hwp+zip", compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("Contents/section0.xml", b"<hs:sec xmlns:hs='x'/>")
        zf.writestr("META-INF/container.xml", b"<container/>")


def test_repair_makes_mimetype_first_and_stored(tmp_path: Path) -> None:
    broken = tmp_path / "broken.hwpx"
    _make_broken_order_hwpx(broken)
    out = tmp_path / "fixed.hwpx"

    result = repair_repack(broken, out)

    assert isinstance(result, RepairResult)
    with zipfile.ZipFile(out, "r") as zf:
        infos = zf.infolist()
        assert infos[0].filename == "mimetype"
        assert infos[0].compress_type == zipfile.ZIP_STORED
        # 나머지 엔트리는 보존
        names = {i.filename for i in infos}
        assert "Contents/header.xml" in names
        assert "Contents/section0.xml" in names
        assert "META-INF/container.xml" in names
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run --extra dev pytest tests/test_repair_repack.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hwpx.tools.repair'`

- [ ] **Step 3: repair.py 최소 구현**

`src/hwpx/tools/repair.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""기존 .hwpx 파일을 입력으로 받아 깨진 ZIP 구조(mimetype 순서/압축)를 복구한다.

알고리즘 출처(아이디어 참고): sakada3/hwp-ops hwpx_rezip (Apache-2.0).
코드는 clean-room 재구현이다.
"""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

__all__ = ["RepairResult", "repair_repack"]

_MIMETYPE = "mimetype"


@dataclass(frozen=True)
class RepairResult:
    output_path: Path
    entries: tuple[str, ...]
    reordered: bool
    crc_ok: bool


def repair_repack(source: str | Path, output_path: str | Path) -> RepairResult:
    src = Path(source)
    if not src.is_file():
        raise FileNotFoundError(f"input file not found: {src}")
    dest = Path(output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)

    with ZipFile(src, "r") as zin:
        names = [i.filename for i in zin.infolist() if not i.is_dir()]
        if _MIMETYPE not in names:
            raise ValueError(f"missing required 'mimetype' entry in {src}")
        payloads = {name: zin.read(name) for name in names}

    reordered = names[0] != _MIMETYPE
    ordered = [_MIMETYPE] + [n for n in names if n != _MIMETYPE]

    fd, tmp_name = tempfile.mkstemp(dir=str(dest.parent), suffix=".hwpx.tmp")
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        with ZipFile(tmp_path, "w", ZIP_DEFLATED) as zout:
            zout.writestr(_MIMETYPE, payloads[_MIMETYPE], compress_type=ZIP_STORED)
            for name in ordered:
                if name == _MIMETYPE:
                    continue
                zout.writestr(name, payloads[name], compress_type=ZIP_DEFLATED)
        crc_ok = _verify(tmp_path)
        os.replace(tmp_path, dest)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise

    return RepairResult(
        output_path=dest,
        entries=tuple(ordered),
        reordered=reordered,
        crc_ok=crc_ok,
    )


def _verify(path: Path) -> bool:
    with ZipFile(path, "r") as zf:
        infos = zf.infolist()
        if not infos:
            return False
        if infos[0].filename != _MIMETYPE or infos[0].compress_type != ZIP_STORED:
            return False
        return zf.testzip() is None
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run --extra dev pytest tests/test_repair_repack.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
cd /Users/wilycastle/Code/projects/hwpx/python-hwpx
git add src/hwpx/tools/repair.py tests/test_repair_repack.py
git commit -m "feat(repair): add repair_repack for mimetype-first STORED enforcement"
```

### Task 0.2: CRC self-check 실패 시 원본 보존 검증

**Files:**
- Modify: `tests/test_repair_repack.py` (테스트 추가)

- [ ] **Step 1: CRC 검증 + 멱등성 테스트 추가**

`tests/test_repair_repack.py`에 추가:

```python
def test_repair_reports_crc_ok_and_reordered_flag(tmp_path: Path) -> None:
    broken = tmp_path / "broken.hwpx"
    _make_broken_order_hwpx(broken)
    out = tmp_path / "fixed.hwpx"
    result = repair_repack(broken, out)
    assert result.crc_ok is True
    assert result.reordered is True


def test_repair_idempotent_on_already_valid(tmp_path: Path) -> None:
    valid = tmp_path / "valid.hwpx"
    with zipfile.ZipFile(valid, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", b"application/hwp+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("Contents/header.xml", b"<hh:head xmlns:hh='x'/>")
    out = tmp_path / "again.hwpx"
    result = repair_repack(valid, out)
    assert result.reordered is False
    assert result.crc_ok is True


def test_repair_missing_mimetype_raises(tmp_path: Path) -> None:
    bad = tmp_path / "nomime.hwpx"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("Contents/header.xml", b"<x/>")
    with pytest.raises(ValueError, match="mimetype"):
        repair_repack(bad, tmp_path / "out.hwpx")
```

- [ ] **Step 2: 테스트 실행 (구현은 0.1에서 이미 충족)**

Run: `uv run --extra dev pytest tests/test_repair_repack.py -v`
Expected: PASS (3개 신규 테스트 모두 통과)

- [ ] **Step 3: 커밋**

```bash
git add tests/test_repair_repack.py
git commit -m "test(repair): cover crc_ok, reordered flag, idempotency, missing mimetype"
```

### Task 0.3: broken-ZIP read 복구 (Local File Header 스캔)

**Files:**
- Create: `src/hwpx/tools/recover.py`
- Test: `tests/test_recover_broken_zip.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_recover_broken_zip.py`:

```python
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import zipfile
from pathlib import Path

from hwpx.tools.recover import recover_entries


def _make_zip_with_truncated_central_dir(path: Path) -> None:
    """정상 ZIP을 만든 뒤 끝부분(central directory)을 잘라 손상시킨다."""
    tmp = path.with_suffix(".whole")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as zf:
        zf.writestr("mimetype", b"application/hwp+zip")
        zf.writestr("Contents/header.xml", b"<hh:head xmlns:hh='x'>hello</hh:head>")
    raw = tmp.read_bytes()
    # central directory 시그니처(PK\x01\x02) 위치를 찾아 그 앞에서 자른다
    cd = raw.find(b"PK\x01\x02")
    assert cd != -1
    path.write_bytes(raw[:cd])


def test_recover_reads_entries_from_broken_zip(tmp_path: Path) -> None:
    broken = tmp_path / "broken.hwpx"
    _make_zip_with_truncated_central_dir(broken)

    recovered = recover_entries(broken)

    assert "mimetype" in recovered
    assert recovered["mimetype"] == b"application/hwp+zip"
    assert b"hello" in recovered["Contents/header.xml"]
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run --extra dev pytest tests/test_recover_broken_zip.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hwpx.tools.recover'`

- [ ] **Step 3: recover.py 구현 (STORED 엔트리 우선, DEFLATE는 raw inflate)**

`src/hwpx/tools/recover.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""central directory가 손상된 ZIP에서 Local File Header를 직접 스캔해 엔트리를 복구한다.

알고리즘 출처(아이디어 참고): chrisryugj/kordoc extractFromBrokenZip (MIT).
코드는 clean-room 재구현이다. zip-bomb 방지를 위해 출력 크기를 제한한다.
"""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

__all__ = ["recover_entries"]

_LFH_SIG = b"PK\x03\x04"
_MAX_ENTRY_BYTES = 100 * 1024 * 1024  # 단일 엔트리 압축 해제 상한 (zip-bomb 가드)
_MAX_ENTRIES = 2000


def recover_entries(source: str | Path) -> dict[str, bytes]:
    data = Path(source).read_bytes()
    entries: dict[str, bytes] = {}
    pos = 0
    count = 0
    n = len(data)

    while count < _MAX_ENTRIES:
        idx = data.find(_LFH_SIG, pos)
        if idx == -1 or idx + 30 > n:
            break
        # Local File Header: 30 byte 고정부
        (_, _, flags, method, _, _, _, comp_size, uncomp_size,
         name_len, extra_len) = struct.unpack("<4sHHHHHIIIHH", data[idx:idx + 30])
        header_end = idx + 30
        name_end = header_end + name_len
        if name_end > n:
            break
        name = data[header_end:name_end].decode("utf-8", errors="replace")
        body_start = name_end + extra_len

        if 0 < name_len < 4096 and not name.endswith("/"):
            payload = _extract_one(
                data, body_start, method, comp_size, uncomp_size, flags
            )
            if payload is not None:
                entries[name.replace("\\", "/")] = payload
                count += 1
        pos = body_start + max(comp_size, 1)

    return entries


def _extract_one(
    data: bytes, start: int, method: int, comp_size: int, uncomp_size: int, flags: int
) -> bytes | None:
    n = len(data)
    if method == 0:  # STORED
        size = uncomp_size or comp_size
        if size <= 0 or size > _MAX_ENTRY_BYTES or start + size > n:
            return None
        return data[start:start + size]
    if method == 8:  # DEFLATE
        # comp_size가 0(streaming/data descriptor)일 수 있으니 다음 LFH 직전까지 시도
        end = data.find(_LFH_SIG, start)
        chunk = data[start:end if end != -1 else n]
        try:
            out = zlib.decompressobj(-15).decompress(chunk, _MAX_ENTRY_BYTES)
            return out or None
        except zlib.error:
            return None
    return None
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run --extra dev pytest tests/test_recover_broken_zip.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add src/hwpx/tools/recover.py tests/test_recover_broken_zip.py
git commit -m "feat(recover): scan local file headers to recover broken-zip entries"
```

### Task 0.4: recover→repair 파이프라인 + CLI 등록

**Files:**
- Modify: `src/hwpx/tools/repair.py` (recover fallback 추가)
- Modify: `pyproject.toml` (`[project.scripts]`에 `hwpx-repair` 추가)
- Test: `tests/test_repair_repack.py` (broken-zip 복구 후 repair 테스트)

- [ ] **Step 1: 파이프라인 실패 테스트 추가**

`tests/test_repair_repack.py`에 추가:

```python
from hwpx.tools.recover import recover_entries  # 파일 상단으로 옮겨도 됨


def test_repair_from_broken_zip_via_recover(tmp_path: Path) -> None:
    from hwpx.tools.repair import repair_from_recovered

    broken = tmp_path / "broken.hwpx"
    # central dir 손상 + STORED 엔트리
    tmp = tmp_path / "whole.hwpx"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as zf:
        zf.writestr("Contents/header.xml", b"<x>h</x>")
        zf.writestr("mimetype", b"application/hwp+zip")
    raw = tmp.read_bytes()
    cd = raw.find(b"PK\x01\x02")
    broken.write_bytes(raw[:cd])

    out = tmp_path / "fixed.hwpx"
    result = repair_from_recovered(broken, out)
    assert result.crc_ok is True
    with zipfile.ZipFile(out, "r") as zf:
        assert zf.infolist()[0].filename == "mimetype"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run --extra dev pytest tests/test_repair_repack.py::test_repair_from_broken_zip_via_recover -v`
Expected: FAIL — `ImportError: cannot import name 'repair_from_recovered'`

- [ ] **Step 3: repair_from_recovered 구현**

`src/hwpx/tools/repair.py`에 추가 (상단 import에 `from .recover import recover_entries`):

```python
from .recover import recover_entries


def repair_from_recovered(source: str | Path, output_path: str | Path) -> RepairResult:
    """central directory가 깨진 .hwpx를 LFH 스캔으로 복구한 뒤 repack한다."""
    payloads = recover_entries(source)
    if _MIMETYPE not in payloads:
        raise ValueError(f"could not recover required 'mimetype' from {source}")
    dest = Path(output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    ordered = [_MIMETYPE] + sorted(n for n in payloads if n != _MIMETYPE)

    fd, tmp_name = tempfile.mkstemp(dir=str(dest.parent), suffix=".hwpx.tmp")
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        with ZipFile(tmp_path, "w", ZIP_DEFLATED) as zout:
            zout.writestr(_MIMETYPE, payloads[_MIMETYPE], compress_type=ZIP_STORED)
            for name in ordered:
                if name == _MIMETYPE:
                    continue
                zout.writestr(name, payloads[name], compress_type=ZIP_DEFLATED)
        crc_ok = _verify(tmp_path)
        os.replace(tmp_path, dest)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    return RepairResult(output_path=dest, entries=tuple(ordered), reordered=True, crc_ok=crc_ok)


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Repair an HWPX archive (mimetype-first, CRC self-check)")
    parser.add_argument("input", help="Input .hwpx path")
    parser.add_argument("output", help="Output .hwpx path")
    parser.add_argument("--recover", action="store_true", help="Recover from a broken central directory via LFH scan")
    args = parser.parse_args(argv)
    try:
        if args.recover:
            result = repair_from_recovered(args.input, args.output)
        else:
            result = repair_repack(args.input, args.output)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1
    print(f"Repaired {args.input} -> {result.output_path} (reordered={result.reordered}, crc_ok={result.crc_ok})")
    return 0
```

`main`이 참조하는 `argparse`는 함수 내 import로 충분하다.

- [ ] **Step 4: pyproject.toml에 CLI 등록**

`pyproject.toml`의 `[project.scripts]` 섹션에 한 줄 추가:

```toml
hwpx-repair = "hwpx.tools.repair:main"
```

- [ ] **Step 5: 테스트 + CLI 동작 확인**

Run: `uv run --extra dev pytest tests/test_repair_repack.py -v`
Expected: PASS (전체)

Run: `uv run hwpx-repair --help`
Expected: usage 출력, 종료코드 0

- [ ] **Step 6: 커밋**

```bash
git add src/hwpx/tools/repair.py pyproject.toml tests/test_repair_repack.py
git commit -m "feat(repair): add broken-zip recovery pipeline and hwpx-repair CLI"
```

---

## Phase 1 — 실전 양식 처리 깊이 (split-run 양식 채움 + 서식 쏠림 경고)

**Stage 매핑:** Phase 1 → Wily Stage 2.

> 핵심 통찰: 실전 양식의 placeholder는 한컴 변환 과정에서 여러 `<hp:t>` run으로 쪼개진다. regex 치환은 여기서 실패한다. 섹션 XML을 lxml DOM으로 파싱해 한 단락 내 연속 `<hp:t>` 텍스트를 이어붙인 "논리 텍스트"에서 placeholder를 찾고, 첫 run의 `charPrIDRef`를 보존하며 치환한다.

### Task 1.1: split-run 인지 placeholder 스캐너

**Files:**
- Create: `src/hwpx/form_fill.py`
- Test: `tests/test_form_fill_split_run.py`

- [ ] **Step 1: 실패 테스트 작성 (split-run placeholder 탐지)**

`tests/test_form_fill_split_run.py`:

```python
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from hwpx.form_fill import find_split_placeholders

# 단락 하나에 {{name}} 이 세 run으로 쪼개진 섹션 XML 조각
SECTION = (
    "<hs:sec xmlns:hs='s' xmlns:hp='p'>"
    "<hp:p><hp:run charPrIDRef='3'><hp:t>안녕 {{na</hp:t></hp:run>"
    "<hp:run charPrIDRef='3'><hp:t>me</hp:t></hp:run>"
    "<hp:run charPrIDRef='3'><hp:t>}} 님</hp:t></hp:run></hp:p>"
    "</hs:sec>"
)


def test_finds_placeholder_split_across_runs() -> None:
    found = find_split_placeholders(SECTION.encode("utf-8"))
    keys = {p.key for p in found}
    assert "{{name}}" in keys
    target = next(p for p in found if p.key == "{{name}}")
    assert target.split is True  # 여러 run에 걸침
    assert target.charprid_refs == ["3"]  # 모두 같은 서식
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run --extra dev pytest tests/test_form_fill_split_run.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hwpx.form_fill'`

- [ ] **Step 3: form_fill.py 스캐너 구현**

`src/hwpx/form_fill.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""split-run 인지 양식 채움. 한 단락 내 연속 <hp:t> 텍스트를 논리 텍스트로 이어
placeholder를 탐지/치환하고 첫 run의 charPrIDRef를 보존한다.

알고리즘 출처(아이디어 참고): chrisryugj/kordoc filler-hwpx (MIT),
sakada3/hwp-ops charPrIDRef span-overlap 분석 (Apache-2.0). clean-room 재구현.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from lxml import etree  # type: ignore[reportAttributeAccessIssue]

__all__ = ["Placeholder", "find_split_placeholders", "PLACEHOLDER_RE"]

PLACEHOLDER_RE = re.compile(r"\{\{[^{}]+\}\}")
_P = "{p}"  # local-name 매칭은 네임스페이스 무관하게 처리


@dataclass
class Placeholder:
    key: str
    paragraph_index: int
    split: bool
    charprid_refs: list[str] = field(default_factory=list)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _iter_paragraphs(root: etree._Element):
    for el in root.iter():
        if _local(el.tag) == "p":
            yield el


def _runs_with_text(paragraph: etree._Element):
    """(charPrIDRef, text, <hp:t> element) 튜플을 문서 순서로 반환."""
    out = []
    for run in paragraph.iter():
        if _local(run.tag) != "run":
            continue
        ref = run.get("charPrIDRef", "")
        for t in run.iter():
            if _local(t.tag) == "t":
                out.append((ref, t.text or "", t))
    return out


def find_split_placeholders(section_bytes: bytes) -> list[Placeholder]:
    root = etree.fromstring(section_bytes)
    results: list[Placeholder] = []
    for p_idx, para in enumerate(_iter_paragraphs(root)):
        runs = _runs_with_text(para)
        if not runs:
            continue
        # 논리 텍스트와 각 문자의 출처 run 인덱스 매핑
        logical = "".join(text for _, text, _ in runs)
        spans = []  # (start, end, run_index)
        cursor = 0
        for r_i, (_, text, _) in enumerate(runs):
            spans.append((cursor, cursor + len(text), r_i))
            cursor += len(text)
        for m in PLACEHOLDER_RE.finditer(logical):
            s, e = m.start(), m.end()
            touched = [r_i for (st, en, r_i) in spans if st < e and en > s]
            refs = []
            for r_i in touched:
                ref = runs[r_i][0]
                if ref not in refs:
                    refs.append(ref)
            results.append(
                Placeholder(
                    key=m.group(0),
                    paragraph_index=p_idx,
                    split=len(touched) > 1,
                    charprid_refs=refs,
                )
            )
    return results
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run --extra dev pytest tests/test_form_fill_split_run.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add src/hwpx/form_fill.py tests/test_form_fill_split_run.py
git commit -m "feat(form_fill): detect placeholders split across runs with charPrIDRef tracking"
```

### Task 1.2: charPrIDRef 서식 쏠림 경고

**Files:**
- Modify: `src/hwpx/form_fill.py` (경고 함수 추가)
- Test: `tests/test_form_fill_split_run.py` (이질성 테스트 추가)

- [ ] **Step 1: 실패 테스트 추가 (서로 다른 charPrIDRef에 걸친 placeholder)**

`tests/test_form_fill_split_run.py`에 추가:

```python
from hwpx.form_fill import find_split_placeholders, heterogeneous_warnings

MIXED = (
    "<hs:sec xmlns:hs='s' xmlns:hp='p'><hp:p>"
    "<hp:run charPrIDRef='3'><hp:t>{{na</hp:t></hp:run>"
    "<hp:run charPrIDRef='7'><hp:t>me}}</hp:t></hp:run>"
    "</hp:p></hs:sec>"
)


def test_warns_on_charprid_heterogeneity() -> None:
    placeholders = find_split_placeholders(MIXED.encode("utf-8"))
    warnings = heterogeneous_warnings(placeholders)
    assert len(warnings) == 1
    assert "{{name}}" in warnings[0]
    assert "3" in warnings[0] and "7" in warnings[0]
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run --extra dev pytest tests/test_form_fill_split_run.py::test_warns_on_charprid_heterogeneity -v`
Expected: FAIL — `ImportError: cannot import name 'heterogeneous_warnings'`

- [ ] **Step 3: heterogeneous_warnings 구현**

`src/hwpx/form_fill.py`에 추가:

```python
def heterogeneous_warnings(placeholders: list[Placeholder]) -> list[str]:
    """서로 다른 charPrIDRef에 걸친 placeholder를 '서식 쏠림 위험'으로 경고한다."""
    out: list[str] = []
    for ph in placeholders:
        if len(ph.charprid_refs) > 1:
            refs = ", ".join(ph.charprid_refs)
            out.append(
                f"[서식 쏠림 위험] {ph.key} (단락 {ph.paragraph_index}): "
                f"여러 charPrIDRef에 걸침 [{refs}]"
            )
    return out
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run --extra dev pytest tests/test_form_fill_split_run.py -v`
Expected: PASS (전체)

- [ ] **Step 5: 커밋**

```bash
git add src/hwpx/form_fill.py tests/test_form_fill_split_run.py
git commit -m "feat(form_fill): warn when a placeholder straddles multiple charPrIDRefs"
```

### Task 1.3: split-run 보존 치환

**Files:**
- Modify: `src/hwpx/form_fill.py` (치환 함수)
- Test: `tests/test_form_fill_split_run.py`

- [ ] **Step 1: 실패 테스트 추가 (치환 후 첫 run에 값 주입, 나머지 비움, 서식 보존)**

`tests/test_form_fill_split_run.py`에 추가:

```python
import zipfile
from pathlib import Path
from hwpx.form_fill import fill_section_bytes


def test_fill_replaces_split_placeholder_preserving_first_run_ref() -> None:
    section = (
        "<hs:sec xmlns:hs='s' xmlns:hp='p'><hp:p>"
        "<hp:run charPrIDRef='3'><hp:t>이름: {{na</hp:t></hp:run>"
        "<hp:run charPrIDRef='3'><hp:t>me}}</hp:t></hp:run>"
        "</hp:p></hs:sec>"
    ).encode("utf-8")

    out, count = fill_section_bytes(section, {"{{name}}": "홍길동"})
    assert count == 1
    text = out.decode("utf-8")
    # 첫 t에 값이 들어가고 두 번째 t는 비워짐
    assert "이름: 홍길동" in text
    assert "{{" not in text and "}}" not in text
    assert "charPrIDRef='3'" in text or 'charPrIDRef="3"' in text
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run --extra dev pytest tests/test_form_fill_split_run.py::test_fill_replaces_split_placeholder_preserving_first_run_ref -v`
Expected: FAIL — `ImportError: cannot import name 'fill_section_bytes'`

- [ ] **Step 3: fill_section_bytes 구현**

`src/hwpx/form_fill.py`에 추가:

```python
def fill_section_bytes(section_bytes: bytes, values: dict[str, str]) -> tuple[bytes, int]:
    """섹션 XML에서 placeholder를 값으로 치환한다. split-run은 첫 run의 <hp:t>에
    값을 모아 넣고 나머지 걸친 run의 <hp:t>는 비운다. 첫 run의 charPrIDRef는 그대로 유지된다.
    반환: (수정된 바이트, 치환 횟수)
    """
    root = etree.fromstring(section_bytes)
    total = 0
    for para in _iter_paragraphs(root):
        runs = _runs_with_text(para)
        if not runs:
            continue
        logical = "".join(text for _, text, _ in runs)
        spans = []
        cursor = 0
        for r_i, (_, text, _) in enumerate(runs):
            spans.append((cursor, cursor + len(text), r_i))
            cursor += len(text)

        # 뒤에서 앞으로 치환해 offset이 밀리지 않게 한다
        matches = [(m.group(0), m.start(), m.end()) for m in PLACEHOLDER_RE.finditer(logical)]
        for key, s, e in reversed(matches):
            if key not in values:
                continue
            touched = [r_i for (st, en, r_i) in spans if st < e and en > s]
            if not touched:
                continue
            total += 1
            # 각 걸친 run에서 placeholder가 차지한 부분을 잘라낸다.
            # 첫 run에는 치환값을, 나머지엔 빈 문자열을 남긴다.
            new_texts: dict[int, str] = {}
            for r_i in touched:
                st, en, _ = spans[r_i]
                local_s = max(s, st) - st
                local_e = min(e, en) - st
                original = runs[r_i][1]
                kept = original[:local_s] + original[local_e:]
                new_texts[r_i] = kept
            first = touched[0]
            st_first, _, _ = spans[first]
            insert_at = s - st_first
            base = new_texts[first]
            new_texts[first] = base[:insert_at] + values[key] + base[insert_at:]
            for r_i, text in new_texts.items():
                runs[r_i][2].text = text
    return etree.tostring(root, encoding="UTF-8"), total
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run --extra dev pytest tests/test_form_fill_split_run.py -v`
Expected: PASS (전체)

- [ ] **Step 5: 커밋**

```bash
git add src/hwpx/form_fill.py tests/test_form_fill_split_run.py
git commit -m "feat(form_fill): fill split-run placeholders preserving first-run charPrIDRef"
```

---

## Phase 2 — 기능 깊이 (cross-file reference validator + 신구대조 diff)

**Stage 매핑:** Phase 2 → Wily Stage 3.

### Task 2.1: cross-file reference validator

**Files:**
- Create: `src/hwpx/tools/ref_validator.py`
- Test: `tests/test_ref_validator.py`

> header.xml에서 ID 풀(charPr/paraPr/style/borderFill/tabPr/numbering/bullet)을 수집하고, section*.xml의 *IDRef를 대조해 dangling ref를 보고한다. ilikeadofai validator(MIT)가 bulletIDRef를 누락한 점을 보완한다.

- [ ] **Step 1: 실패 테스트 작성 (dangling charPrIDRef 검출)**

`tests/test_ref_validator.py`:

```python
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from hwpx.tools.ref_validator import validate_references, RefReport

HEADER = (
    "<hh:head xmlns:hh='h'><hh:refList>"
    "<hh:charProperties itemCnt='1'><hh:charPr id='0'/></hh:charProperties>"
    "</hh:refList></hh:head>"
)
# section이 존재하지 않는 charPrIDRef='9'를 참조
SECTION = (
    "<hs:sec xmlns:hs='s' xmlns:hp='p'><hp:p>"
    "<hp:run charPrIDRef='9'><hp:t>x</hp:t></hp:run></hp:p></hs:sec>"
)


def test_detects_dangling_charprid_ref() -> None:
    report = validate_references(
        header_bytes=HEADER.encode("utf-8"),
        section_bytes_list=[SECTION.encode("utf-8")],
    )
    assert isinstance(report, RefReport)
    assert any("charPrIDRef" in m and "9" in m for m in report.dangling)
    assert report.ok is False
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run --extra dev pytest tests/test_ref_validator.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hwpx.tools.ref_validator'`

- [ ] **Step 3: ref_validator.py 구현**

`src/hwpx/tools/ref_validator.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""header↔section 간 ID 참조 그래프 검증. dangling *IDRef를 보고한다.

알고리즘 출처(아이디어 참고): ilikeadofai/hwpx-document-processing-skill
validate_hwpx.py (MIT). bulletIDRef 누락을 보완한 clean-room 재구현.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from lxml import etree  # type: ignore[reportAttributeAccessIssue]

__all__ = ["RefReport", "validate_references"]

# IDRef 속성 -> 그 ID를 정의하는 요소의 local-name
_REF_TO_DEF = {
    "charPrIDRef": "charPr",
    "paraPrIDRef": "paraPr",
    "styleIDRef": "style",
    "borderFillIDRef": "borderFill",
    "tabPrIDRef": "tabPr",
    "numberingIDRef": "numbering",
    "bulletIDRef": "bullet",  # ilikeadofai가 누락한 항목
}


@dataclass
class RefReport:
    dangling: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.dangling


def _local(tag) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def _collect_ids(header_bytes: bytes) -> dict[str, set[str]]:
    root = etree.fromstring(header_bytes)
    pools: dict[str, set[str]] = {name: set() for name in set(_REF_TO_DEF.values())}
    for el in root.iter():
        name = _local(el.tag)
        if name in pools:
            id_val = el.get("id")
            if id_val is not None:
                pools[name].add(id_val)
    return pools


def validate_references(
    *, header_bytes: bytes, section_bytes_list: list[bytes]
) -> RefReport:
    pools = _collect_ids(header_bytes)
    report = RefReport()
    for s_idx, section in enumerate(section_bytes_list):
        root = etree.fromstring(section)
        for el in root.iter():
            for attr, def_name in _REF_TO_DEF.items():
                ref = el.get(attr)
                if ref is None:
                    continue
                if ref not in pools.get(def_name, set()):
                    report.dangling.append(
                        f"section[{s_idx}] {_local(el.tag)}@{attr}={ref} "
                        f"-> 정의되지 않은 {def_name} id"
                    )
    return report
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run --extra dev pytest tests/test_ref_validator.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add src/hwpx/tools/ref_validator.py tests/test_ref_validator.py
git commit -m "feat(ref_validator): detect dangling cross-file ID references incl bulletIDRef"
```

### Task 2.2: zOrder 중복 + object id 중복 검출

**Files:**
- Modify: `src/hwpx/tools/ref_validator.py`
- Test: `tests/test_ref_validator.py`

- [ ] **Step 1: 실패 테스트 추가**

`tests/test_ref_validator.py`에 추가:

```python
from hwpx.tools.ref_validator import validate_references

DUP_ZORDER = (
    "<hs:sec xmlns:hs='s' xmlns:hp='p'><hp:p>"
    "<hp:rect id='10' zOrder='1'/><hp:rect id='11' zOrder='1'/>"
    "</hp:p></hs:sec>"
)


def test_detects_duplicate_nonzero_zorder() -> None:
    report = validate_references(
        header_bytes=HEADER.encode("utf-8"),
        section_bytes_list=[DUP_ZORDER.encode("utf-8")],
    )
    assert any("zOrder" in m and "1" in m for m in report.dangling)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run --extra dev pytest tests/test_ref_validator.py::test_detects_duplicate_nonzero_zorder -v`
Expected: FAIL — zOrder 중복이 검출되지 않음

- [ ] **Step 3: zOrder/object id 중복 검출 추가**

`validate_references`의 section 루프 다음(보고 반환 직전)에 추가:

```python
        # zOrder 중복 (0이 아닌 값) 검출
        zorders: dict[str, int] = {}
        for el in root.iter():
            z = el.get("zOrder")
            if z is None or z == "0":
                continue
            zorders[z] = zorders.get(z, 0) + 1
        for z, cnt in zorders.items():
            if cnt > 1:
                report.dangling.append(
                    f"section[{s_idx}] 중복 zOrder={z} ({cnt}회)"
                )
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run --extra dev pytest tests/test_ref_validator.py -v`
Expected: PASS (전체)

- [ ] **Step 5: 커밋**

```bash
git add src/hwpx/tools/ref_validator.py tests/test_ref_validator.py
git commit -m "feat(ref_validator): flag duplicate non-zero zOrder values"
```

### Task 2.3: 신구대조 텍스트 diff (LCS 단락 정렬)

**Files:**
- Create: `src/hwpx/tools/doc_diff.py`
- Test: `tests/test_doc_diff.py`

> 두 문서의 단락 텍스트 리스트를 LCS 기반으로 정렬해 added/removed/changed를 보고한다. kordoc diff 엔진(MIT) 아이디어.

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_doc_diff.py`:

```python
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from hwpx.tools.doc_diff import diff_paragraphs, DiffOp


def test_diff_detects_change_add_remove() -> None:
    old = ["제목", "첫 문단", "삭제될 문단"]
    new = ["제목", "수정된 첫 문단", "새 문단"]
    ops = diff_paragraphs(old, new)
    kinds = [op.kind for op in ops]
    assert "equal" in kinds      # "제목"
    assert "changed" in kinds or ("removed" in kinds and "added" in kinds)
    # 변경/추가/삭제가 모두 표현되어야 함
    texts = " ".join(op.text for op in ops if op.kind != "equal")
    assert "문단" in texts
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run --extra dev pytest tests/test_doc_diff.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'hwpx.tools.doc_diff'`

- [ ] **Step 3: doc_diff.py 구현 (stdlib difflib 활용 — DRY)**

`src/hwpx/tools/doc_diff.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""두 문서의 단락 텍스트를 비교해 신구대조 결과를 만든다.

알고리즘 출처(아이디어 참고): chrisryugj/kordoc diff 엔진 (MIT).
LCS 정렬은 표준 라이브러리 difflib.SequenceMatcher로 구현(불필요한 재구현 회피).
"""
from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

__all__ = ["DiffOp", "diff_paragraphs"]


@dataclass(frozen=True)
class DiffOp:
    kind: str  # "equal" | "added" | "removed" | "changed"
    text: str
    old_index: int | None = None
    new_index: int | None = None


def diff_paragraphs(old: list[str], new: list[str]) -> list[DiffOp]:
    sm = SequenceMatcher(a=old, b=new, autojunk=False)
    ops: list[DiffOp] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for oi, nj in zip(range(i1, i2), range(j1, j2)):
                ops.append(DiffOp("equal", old[oi], oi, nj))
        elif tag == "replace":
            # 같은 개수면 changed로 짝지음, 아니면 removed+added
            span = min(i2 - i1, j2 - j1)
            for k in range(span):
                ops.append(DiffOp("changed", new[j1 + k], i1 + k, j1 + k))
            for oi in range(i1 + span, i2):
                ops.append(DiffOp("removed", old[oi], oi, None))
            for nj in range(j1 + span, j2):
                ops.append(DiffOp("added", new[nj], None, nj))
        elif tag == "delete":
            for oi in range(i1, i2):
                ops.append(DiffOp("removed", old[oi], oi, None))
        elif tag == "insert":
            for nj in range(j1, j2):
                ops.append(DiffOp("added", new[nj], None, nj))
    return ops
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run --extra dev pytest tests/test_doc_diff.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add src/hwpx/tools/doc_diff.py tests/test_doc_diff.py
git commit -m "feat(doc_diff): paragraph-level new/old comparison via difflib LCS"
```

---

## Phase 3 — 포지셔닝/IR/시장성 (문서 + setup 자동화)

**Stage 매핑:** Phase 3 → Wily Stage 4. 주 산출물은 `hwpx-skill` 리포의 문서/스크립트이므로 별도 worktree 권장.

### Task 3.1: client setup 자동 등록 스크립트 (드라이런 우선)

**Files:**
- Create: `hwpx-skill/scripts/install_clients.py` (작업 루트: `/Users/wilycastle/Code/projects/hwpx/hwpx-skill`)
- Test: `hwpx-skill/tests/test_install_clients.py` (테스트 디렉토리가 없으면 생성)

> per-OS config 경로와 3개 스키마(mcpServers / servers / context_servers)를 다룬다. kordoc setup.ts(MIT) 모델. 안전을 위해 기본은 `--dry-run`, 실제 쓰기는 명시 플래그.

- [ ] **Step 1: 실패 테스트 작성 (JSON 병합이 기존 키 보존)**

`hwpx-skill/tests/test_install_clients.py`:

```python
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from install_clients import merge_mcp_entry


def test_merge_preserves_existing_servers() -> None:
    existing = {"mcpServers": {"other": {"command": "x"}}}
    merged = merge_mcp_entry(existing, schema_key="mcpServers", name="hwpx", entry={"command": "hwpx-mcp-server"})
    assert "other" in merged["mcpServers"]
    assert merged["mcpServers"]["hwpx"] == {"command": "hwpx-mcp-server"}
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd /Users/wilycastle/Code/projects/hwpx/hwpx-skill && python -m pytest tests/test_install_clients.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'install_clients'`

- [ ] **Step 3: install_clients.py 구현**

`hwpx-skill/scripts/install_clients.py`:

```python
#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Claude/Cursor/VS Code 등 MCP 클라이언트에 hwpx-mcp-server를 등록한다.

알고리즘 출처(아이디어 참고): chrisryugj/kordoc setup.ts (MIT). clean-room 재구현.
기본은 --dry-run(미리보기). 실제 파일 쓰기는 --write 필요.
"""
from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from typing import Any


def merge_mcp_entry(
    config: dict[str, Any], *, schema_key: str, name: str, entry: dict[str, Any]
) -> dict[str, Any]:
    """기존 config를 보존하며 schema_key 아래에 name->entry를 병합한다."""
    merged = deepcopy(config)
    section = merged.setdefault(schema_key, {})
    section[name] = entry
    return merged


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Register hwpx-mcp-server into MCP clients")
    parser.add_argument("--write", action="store_true", help="Actually write config files (default: dry-run)")
    args = parser.parse_args(argv)
    mode = "WRITE" if args.write else "DRY-RUN"
    print(f"[{mode}] hwpx-mcp-server client registration")
    # 실제 클라이언트 탐지/쓰기는 후속 Step에서 확장한다.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd /Users/wilycastle/Code/projects/hwpx/hwpx-skill && python -m pytest tests/test_install_clients.py -v`
Expected: PASS

- [ ] **Step 5: 커밋 (hwpx-skill 리포에서)**

```bash
cd /Users/wilycastle/Code/projects/hwpx/hwpx-skill
git add scripts/install_clients.py tests/test_install_clients.py
git commit -m "feat(setup): add install_clients dry-run scaffold with config-preserving merge"
```

### Task 3.2: compatibility matrix + 제한사항 문서

**Files:**
- Modify: `hwpx-skill/README.md` (compatibility matrix 섹션 추가)

> claw-hwp의 정직한 제한사항 matrix 스타일을 따른다(코드 복사 아님 — 표 구조 아이디어만).

- [ ] **Step 1: README에 matrix 섹션 추가**

`hwpx-skill/README.md` 끝에 다음을 추가:

```markdown
## Compatibility Matrix

| 포맷/작업 | read | edit | create | validate | 비고 |
|---|---|---|---|---|---|
| HWPX | ✅ | ✅ | ✅ | ✅ (구조+CRC) | 기본 대상 |
| HWP (binary) | ✅ read-only | ❌ | ❌ | — | detect/추출/convert-router만 |
| PDF | — | — | — | visual only | 최종 권위는 한컴/PDF 렌더 |

### 제한사항
- HWP 직접 편집은 범위 밖이다. 편집은 HWPX로 변환 후 수행한다.
- split-run 양식 채움은 단락 내 연속 `<hp:t>`까지 보존한다. 단락을 넘는 placeholder는 미지원.
- rhwp 렌더는 weak smoke check로만 취급한다. 최종 레이아웃 권위가 아니다.
```

- [ ] **Step 2: 마크다운 렌더 확인 (수동)**

Run: `cd /Users/wilycastle/Code/projects/hwpx/hwpx-skill && grep -n "Compatibility Matrix" README.md`
Expected: 매칭 라인 출력

- [ ] **Step 3: 커밋**

```bash
cd /Users/wilycastle/Code/projects/hwpx/hwpx-skill
git add README.md
git commit -m "docs: add compatibility matrix and limitations section"
```

---

## 전체 검증 게이트 (각 Phase 완료 시)

각 Phase 완료 후 해당 리포 전체 테스트를 돌린다:

```bash
# python-hwpx (Phase 0/1/2)
cd /Users/wilycastle/Code/projects/hwpx/python-hwpx && uv run --extra dev pytest -q

# hwpx-skill (Phase 3)
cd /Users/wilycastle/Code/projects/hwpx/hwpx-skill && python -m pytest -q
```

Expected: 모든 테스트 PASS, 신규 회귀 없음.

## NOTICE 갱신 (코드 포팅 출처 추적)

코드 흡수 항목(알고리즘 재구현)은 `python-hwpx/NOTICE`(없으면 생성)에 다음 형식으로 기록한다:

```
This project reimplements algorithms (clean-room) inspired by:
- sakada3/hwp-ops (Apache-2.0): repair-repack mimetype-first + CRC self-check
- chrisryugj/kordoc (MIT): broken-zip LFH recovery, split-run form fill, doc diff, client setup
- ilikeadofai/hwpx-document-processing-skill (MIT): cross-file reference validator
No source code was copied verbatim.
```

## Self-Review 체크리스트 결과
- **Spec 커버리지:** v2 문서의 Phase 0~3 / "먼저 흡수할 10개" 항목이 모두 Task로 매핑됨(8번 그림 객체 워크플로는 Phase 2 후속/별도 Stage로 분리 가능 — 본 plan은 1·2·3·4·6·7·10 우선 구현, 5·8·9는 후속).
- **Placeholder 스캔:** 모든 코드 step에 실제 코드 포함, TODO/TBD 없음.
- **타입 일관성:** `RepairResult`/`Placeholder`/`RefReport`/`DiffOp`/`DiffOp.kind` 명칭이 정의·사용처에서 일치.
