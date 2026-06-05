"""대표 프레임 이미지 → base64 JPEG.

feature_docs §17 "대표 프레임이 없는 경우" 정책을 따라
프레임이 없으면 None을 반환하고 호출 측에서 VLM 호출을 생략한다.

mock 모드에서는 pia_summary/tests/sample.jpg를 재사용한다.
"""

from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

from .config import SAMPLE_JPEG_PATH


@lru_cache(maxsize=1)
def _sample_b64() -> str | None:
    path = SAMPLE_JPEG_PATH
    if not path.exists():
        return None
    return base64.b64encode(path.read_bytes()).decode("ascii")


def dummy_jpeg_b64(_event_id: str) -> str | None:
    """이벤트 ID는 인자로 받지만 mock 단계에서는 동일 sample을 반환."""
    return _sample_b64()


def load_jpeg_b64(path: str | Path) -> str | None:
    p = Path(path)
    if not p.exists():
        return None
    return base64.b64encode(p.read_bytes()).decode("ascii")
