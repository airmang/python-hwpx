#!/usr/bin/env python3
"""점진 변환 대상 파일에서 typing 제네릭 별칭 사용을 검사한다."""

from __future__ import annotations

from pathlib import Path
import re
import sys

TARGET_FILES = [
    Path("src/hwpx/document.py"),
    Path("src/hwpx/oxml/document.py"),
]

FORBIDDEN = ("List[", "Dict[", "Tuple[")


def main() -> int:
    has_error = False
    for path in TARGET_FILES:
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN:
            for match in re.finditer(re.escape(token), text):
                line_no = text.count("\n", 0, match.start()) + 1
                print(f"{path}:{line_no}: 금지된 typing 별칭 '{token}' 사용 발견")
                has_error = True

    if has_error:
        print("\n점진 변환 범위 검사 실패: list/dict/tuple 내장 제네릭을 사용하세요.")
        return 1

    print("점진 변환 범위 검사 통과: 대상 파일에서 List/Dict/Tuple 사용이 없습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
