"""테스트 공용 헬퍼: prompts.build_chat_payload 기반 페이로드 + 더미 샘플 이미지."""

from __future__ import annotations

import base64
import io
import os
import sys
from pathlib import Path

# prompts.py를 import할 수 있도록 부모 디렉터리 노출.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prompts import build_chat_payload, get_report_prompt  # noqa: E402

def _resolve_default(env_key: str, fallback: str) -> str:
    """호스트 셸 환경변수 → packages/pia_summary/.env → 하드코딩 기본값 순으로 해석.

    `.env` 는 docker compose 가 컨테이너에 주입할 뿐 호스트 셸에는 export 되지
    않으므로, 별도 export 없이 `.env` 만 바꿔도 벤치가 같은 값을 가리키도록
    fallback 으로 직접 파싱한다.
    """
    v = os.environ.get(env_key)
    if v:
        return v
    from _system import _read_dotenv  # noqa: PLC0415
    return _read_dotenv().get(env_key) or fallback


def _resolve_url(env_key: str, path: str) -> str:
    """`REPORT_*_URL` → `.env` 의 `VLLM_PORT` → 8000 순으로 호스트 URL 조립.

    `.env` 의 `VLLM_PORT` 만 변경해도 벤치가 자동으로 같은 포트를 호출하도록.
    명시적 `REPORT_VLLM_URL` 이 있으면 그것이 최우선.
    """
    v = os.environ.get(env_key)
    if v:
        return v
    from _system import _read_dotenv  # noqa: PLC0415
    dotenv = _read_dotenv()
    v = dotenv.get(env_key)
    if v:
        return v
    port = os.environ.get("VLLM_PORT") or dotenv.get("VLLM_PORT") or "8000"
    return f"http://localhost:{port}{path}"


DEFAULT_VLLM_URL = _resolve_url("REPORT_VLLM_URL", "/v1/chat/completions")
DEFAULT_MODELS_URL = _resolve_url("REPORT_MODELS_URL", "/v1/models")
DEFAULT_MODEL = _resolve_default("VLLM_MODEL", "Qwen/Qwen3.5-0.8B")
SAMPLE_PATH = Path(__file__).resolve().parent / "sample.jpg"


def _render_sample_jpeg() -> bytes:
    """샘플 이미지가 없을 때만 사용하는 320x240 더미 JPEG 생성기."""
    try:
        from PIL import Image, ImageDraw  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "Pillow 필요. `pip install pillow` 후 재시도."
        ) from exc

    img = Image.new("RGB", (320, 240), color=(20, 20, 28))
    draw = ImageDraw.Draw(img)
    draw.rectangle([80, 80, 240, 200], outline=(220, 220, 220), width=4)
    draw.text((100, 110), "DUMMY", fill=(220, 220, 220))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def load_or_make_sample_b64() -> str:
    """tests/sample.jpg 를 base64 ASCII로 반환. 없으면 생성 후 저장."""
    if SAMPLE_PATH.exists():
        jpeg_bytes = SAMPLE_PATH.read_bytes()
    else:
        jpeg_bytes = _render_sample_jpeg()
        SAMPLE_PATH.write_bytes(jpeg_bytes)
    return base64.b64encode(jpeg_bytes).decode("ascii")


def dummy_metadata() -> dict:
    """알람 메타데이터 픽스처. prompts.PROMPT_TEMPLATE 예시와 같은 키 셋."""
    return {
        "event_id": "EVT-DUMMY-001",
        "camera_id": "CAM-03",
        "camera_name": "Server Room Entrance",
        "zone_name": "Zone-A",
        "detected_category": "fall_down",
        "event_start_time": "2026-04-28 14:23:11",
        "event_end_time": "2026-04-28 14:23:18",
        "event_duration_sec": 7,
        "event_status": "pending_review",
    }


def make_payload(
    *,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 96,
    temperature: float = 0.0,
    max_words: int = 40,
    metadata: dict | None = None,
) -> dict:
    """모든 벤치가 공유하는 단일 페이로드 진입점. prompts.build_chat_payload를 그대로 호출."""
    return build_chat_payload(
        load_or_make_sample_b64(),
        metadata if metadata is not None else dummy_metadata(),
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        max_words=max_words,
    )


def extract_summary(response_json: dict) -> str:
    """choices[0].message.content 추출."""
    return response_json["choices"][0]["message"]["content"].strip()


def write_to_result(section_title: str, body_md: str) -> None:
    """현재 환경의 `bench_results/{gpu}-{model}.md` 파일을 갱신 (덮어쓰기).

    `## 테스트 환경` 과 주어진 결과 섹션을 둘 다 upsert. 결과 파일은
    `_system.result_filename()` 으로 자동 라우팅됨.
    """
    from _result import (  # noqa: PLC0415
        render_env_section,
        upsert_section,
        _result_path,
    )
    from _system import collect_system_info  # noqa: PLC0415

    sys_info = collect_system_info()
    upsert_section("테스트 환경", render_env_section(sys_info))
    upsert_section(section_title, body_md)
    print(f"\n[bench_results] {_result_path(sys_info).name} 갱신 완료.")


__all__ = [
    "DEFAULT_VLLM_URL",
    "DEFAULT_MODELS_URL",
    "DEFAULT_MODEL",
    "SAMPLE_PATH",
    "build_chat_payload",
    "get_report_prompt",
    "load_or_make_sample_b64",
    "dummy_metadata",
    "make_payload",
    "extract_summary",
    "write_to_result",
]
