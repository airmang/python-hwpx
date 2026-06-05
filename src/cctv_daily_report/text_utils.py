"""LLM/번역 응답을 보고서에 넣기 전 정리하는 유틸."""

from __future__ import annotations

import re
import unicodedata

_EMOJI_RANGES = (
    (0x1F300, 0x1F5FF),
    (0x1F600, 0x1F64F),
    (0x1F680, 0x1F6FF),
    (0x1F700, 0x1F77F),
    (0x1F780, 0x1F7FF),
    (0x1F800, 0x1F8FF),
    (0x1F900, 0x1F9FF),
    (0x1FA00, 0x1FA6F),
    (0x1FA70, 0x1FAFF),
    (0x2600, 0x26FF),
    (0x2700, 0x27BF),
    (0xFE00, 0xFE0F),
)


def _is_emoji_char(c: str) -> bool:
    cp = ord(c)
    for lo, hi in _EMOJI_RANGES:
        if lo <= cp <= hi:
            return True
    return False


_DECORATIVE = set("•◇◆■□▶▷▲△★☆※◎●")  # 장식 기호만 제거. ○·은 placeholder/구분점으로 흔히 쓰여 유지
_FENCE_PATTERN = re.compile(r"```[^\n]*\n?|\n?```")
_MULTISPACE = re.compile(r"[ \t]{2,}")
_MULTILINE = re.compile(r"\n{3,}")


def strip_emoji(text: str) -> str:
    """이모지와 장식 문자 제거, 공백 정규화."""
    if not text:
        return ""
    out = []
    for c in text:
        if _is_emoji_char(c):
            continue
        if c in _DECORATIVE:
            continue
        # 변형 selector 등 비가시 문자 제거 (이미 _EMOJI_RANGES에 포함되어 있지만 안전망)
        cat = unicodedata.category(c)
        if cat in ("Cf",):  # format
            continue
        out.append(c)
    cleaned = "".join(out)
    cleaned = _FENCE_PATTERN.sub("", cleaned)
    cleaned = _MULTISPACE.sub(" ", cleaned)
    cleaned = _MULTILINE.sub("\n\n", cleaned)
    return cleaned.strip()


def clean_block(block: dict[str, str]) -> dict[str, str]:
    return {k: strip_emoji(v) for k, v in block.items()}
