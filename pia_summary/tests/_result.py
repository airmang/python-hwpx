"""bench_results/{gpu}-{model}.md 갱신 헬퍼.

- 결과 파일은 GPU + 모델 조합별로 자동 라우팅 (`bench_results/{slug}.md`)
- 매 벤치는 자기 섹션을 덮어쓰기 (upsert). 누적/타임스탬프/fingerprint 박지 않음
- '## 테스트 환경' 섹션은 매 실행 시 갱신. 나머지 섹션은 정해진 순서대로 정렬
- 표 컬럼은 한국어 + 단위 명시
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

BENCH_RESULTS_DIR = Path(__file__).resolve().parent / "bench_results"


def _result_path(sys_info: dict[str, Any]) -> Path:
    """현재 환경에 맞는 결과 파일 경로. bench_results/ 디렉터리는 없으면 생성."""
    from _system import result_filename  # noqa: PLC0415

    BENCH_RESULTS_DIR.mkdir(exist_ok=True)
    return BENCH_RESULTS_DIR / result_filename(sys_info)


def _preamble(sys_info: dict[str, Any]) -> str:
    """결과 파일 맨 위에 들어갈 헤더. GPU / 모델 명을 제목에 박는다."""
    gpu = sys_info.get("gpu", "GPU").split(",")[0].strip()
    model = sys_info.get("vllm_model", "model")
    return (
        f"# {gpu} · {model}\n\n"
        "사용법 / 용어 / 해석은 [`../README.md`](../README.md).\n"
    )

_SECTION_ORDER = [
    "테스트 환경",
    "docker_vram (idle)",
    "concurrency_sweep",
    "max_tokens_sweep",
    "ramp",
]


# ---------------------------------------------------------------------------
# 파일 입출력 / upsert
# ---------------------------------------------------------------------------

def _ensure_preamble(path: Path, preamble: str) -> str:
    if path.exists() and path.stat().st_size > 0:
        return path.read_text(encoding="utf-8")
    path.write_text(preamble, encoding="utf-8")
    return preamble


def upsert_section(title: str, body: str) -> None:
    """현재 환경의 결과 파일에서 ## {title} 섹션 본문을 새 body 로 덮어쓰기.

    파일이 없으면 GPU + 모델 명을 제목에 박은 preamble 로 생성. 섹션이 없으면
    `_SECTION_ORDER` 순서대로 삽입.
    """
    from _system import collect_system_info  # noqa: PLC0415

    sys_info = collect_system_info()
    path = _result_path(sys_info)
    preamble_text = _preamble(sys_info)
    text = _ensure_preamble(path, preamble_text)

    m = re.search(r"^## ", text, re.MULTILINE)
    if m:
        preamble = text[: m.start()].rstrip("\n")
        rest = text[m.start():]
    else:
        preamble = text.rstrip("\n")
        rest = ""

    sections: dict[str, str] = {}
    for sm in re.finditer(r"^## (.+?)\n(.*?)(?=^## |\Z)", rest,
                          re.DOTALL | re.MULTILINE):
        sections[sm.group(1).strip()] = sm.group(2).strip("\n")

    sections[title] = body.strip("\n")

    ordered = [t for t in _SECTION_ORDER if t in sections]
    extras = [t for t in sections if t not in _SECTION_ORDER]

    out: list[str] = [preamble, ""]
    for t in ordered + extras:
        out.append(f"## {t}")
        out.append("")
        out.append(sections[t])
        out.append("")
    path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# 표 헬퍼
# ---------------------------------------------------------------------------

def _md_table(rows: Iterable[dict], cols: list[tuple[str, str, str]]) -> str:
    head = "| " + " | ".join(h for _, h, _ in cols) + " |"
    sep = "| " + " | ".join("---" for _ in cols) + " |"
    lines = [head, sep]
    for r in rows:
        cells: list[str] = []
        for k, _, fmt in cols:
            v = r.get(k, "")
            if v == "" or v is None:
                cells.append("-")
                continue
            if fmt:
                try:
                    cells.append(fmt.format(v))
                    continue
                except (ValueError, TypeError):
                    pass
            cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 섹션 렌더 함수
# ---------------------------------------------------------------------------

_ENV_LABELS = [
    ("hostname", "호스트명"),
    ("os", "OS"),
    ("kernel", "커널"),
    ("cpu", "CPU"),
    ("ram", "메모리"),
    ("gpu", "GPU"),
    ("cuda", "CUDA"),
    ("python", "Python"),
    ("vllm_image", "vLLM 이미지"),
    ("vllm_model", "vLLM 모델"),
    ("gpu_memory_utilization", "GPU_MEMORY_UTILIZATION"),
    ("max_model_len", "MAX_MODEL_LEN"),
    ("max_num_seqs", "MAX_NUM_SEQS"),
    ("max_num_batched_tokens", "MAX_NUM_BATCHED_TOKENS"),
    ("dtype", "DTYPE"),
    ("tensor_parallel_size", "TENSOR_PARALLEL_SIZE"),
    ("data_parallel_size", "DATA_PARALLEL_SIZE"),
    ("enable_prefix_caching", "ENABLE_PREFIX_CACHING"),
    ("kv_cache_memory_bytes", "KV_CACHE_MEMORY_BYTES"),
    ("nvidia_visible_devices", "NVIDIA_VISIBLE_DEVICES"),
]


def render_env_section(sys_info: dict[str, Any]) -> str:
    rows = ["| 항목 | 값 |", "|---|---|"]
    for key, label in _ENV_LABELS:
        v = sys_info.get(key)
        if v is None or v == "":
            continue
        rows.append(f"| {label} | {v} |")
    return "\n".join(rows)


def render_docker_vram(res: dict) -> str:
    from _system import collect_system_info  # noqa: PLC0415

    util = collect_system_info().get("gpu_memory_utilization")
    total = res["gpu_total_mib"]
    used = (
        res["idle_proc_used_mib"]
        if res.get("idle_proc_used_mib") is not None
        else res["idle_total_used_mib"]
    )
    used_pct = used / total * 100 if total else 0.0

    lines = [
        f"- 모델 로드 후 idle 사용량: {used:,} MiB / {total:,} MiB ({used_pct:.1f}%)",
    ]
    if util:
        try:
            limit_mib = int(total * float(util))
            lines.append(
                f"- 설정 상한 (`GPU_MEMORY_UTILIZATION={util}`): "
                f"{limit_mib:,} MiB 까지 사용 가능"
            )
        except (ValueError, TypeError):
            pass
    return "\n".join(lines)


def render_concurrency(rows: list[dict]) -> str:
    return _md_table(rows, [
        ("concurrency", "동시 요청 수", "{}"),
        ("total", "총 요청", "{}"),
        ("success", "성공", "{}"),
        ("fail", "실패", "{}"),
        ("wall_s", "총 소요시간 (초)", "{:.2f}"),
        ("throughput_rps", "처리량 (req/s)", "{:.2f}"),
        ("mean_ms", "평균 응답시간 (ms)", "{:.0f}"),
        ("p50_ms", "p50 (ms)", "{:.0f}"),
        ("p95_ms", "p95 (ms)", "{:.0f}"),
        ("p99_ms", "p99 (ms)", "{:.0f}"),
        ("max_ms", "최대 응답시간 (ms)", "{:.0f}"),
        ("vram_avg_mib", "VRAM 평균 (MiB)", "{:.0f}"),
        ("vram_peak_mib", "VRAM 최대 (MiB)", "{:.0f}"),
    ])


def render_max_tokens(rows: list[dict]) -> str:
    return _md_table(rows, [
        ("max_tokens", "max_tokens", "{}"),
        ("avg_ms", "평균 응답시간 (ms)", "{:.0f}"),
        ("min_ms", "최소 (ms)", "{:.0f}"),
        ("max_ms", "최대 (ms)", "{:.0f}"),
        ("avg_words", "평균 응답 단어 수", "{:.1f}"),
        ("avg_chars", "평균 응답 글자 수", "{:.0f}"),
        ("terminated", "마침표 종결", "{}"),
        ("truncated", "잘린 응답", "{}"),
        ("errors", "에러", "{}"),
    ])


def render_ramp(res: dict) -> str:
    table = _md_table(res["rows"], [
        ("concurrency", "동시 요청 수", "{}"),
        ("duration_s", "지속 시간 (초)", "{:.0f}"),
        ("total", "총 요청", "{}"),
        ("success", "성공", "{}"),
        ("error_rate_pct", "에러율 (%)", "{:.2f}"),
        ("throughput_rps", "처리량 (req/s)", "{:.2f}"),
        ("mean_ms", "평균 응답시간 (ms)", "{:.0f}"),
        ("p95_ms", "p95 (ms)", "{:.0f}"),
        ("p99_ms", "p99 (ms)", "{:.0f}"),
        ("vram_peak_mib", "VRAM 최대 (MiB)", "{:.0f}"),
    ])
    last_safe = res["last_safe_concurrency"]
    bp = res["breakpoint"]
    summary = ["", f"- 마지막 안전 동시 요청 수: {last_safe}"]
    if bp:
        summary.append(
            f"- 한계점: 동시 요청 {bp['concurrency']} 에서 break "
            f"({bp['reason']})"
        )
    else:
        summary.append("- 한계점: 미발생 (`--max` 까지 안전)")
    return table + "\n" + "\n".join(summary)
