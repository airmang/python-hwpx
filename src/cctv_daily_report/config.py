"""런타임 설정. 환경변수로 오버라이드 가능."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def today_iso() -> str:
    """오늘 날짜(YYYY-MM-DD). 보고 일자 기본값."""
    return date.today().isoformat()

VLLM_BASE_URL = os.environ.get("VLLM_BASE_URL", "http://localhost:8000")
VLLM_MODEL = os.environ.get("VLLM_MODEL", "Qwen/Qwen3.5-0.8B")
TIMEOUT_SECONDS = int(os.environ.get("VLLM_TIMEOUT", "120"))

TEMPLATE_PATH = Path(
    os.environ.get(
        "CCTV_REPORT_TEMPLATE",
        str(PROJECT_ROOT / "templates" / "report_template_blank.hwpx"),
    )
)
OUTPUT_DIR = Path(
    os.environ.get("CCTV_REPORT_OUTPUT_DIR", str(PROJECT_ROOT / "outputs"))
)

SAMPLE_JPEG_PATH = PROJECT_ROOT / "pia_summary" / "tests" / "sample.jpg"

MAX_MAIN_EVENTS = int(os.environ.get("CCTV_REPORT_MAX_MAIN_EVENTS", "3"))
MAX_TOKENS_VLM = int(os.environ.get("CCTV_REPORT_MAX_TOKENS_VLM", "96"))
MAX_TOKENS_LLM = int(os.environ.get("CCTV_REPORT_MAX_TOKENS_LLM", "512"))

PIA_SUMMARY_DIR = PROJECT_ROOT / "pia_summary"
