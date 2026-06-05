"""테스트 환경 시스템 정보 수집 (OS, CPU, RAM, GPU, vLLM 환경변수) + 결과 파일용 slug."""

from __future__ import annotations

import os
import platform
import re
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any


def _read_os_pretty_name() -> str:
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
    except Exception:
        pass
    return ""


def _cpu_info() -> str:
    try:
        with open("/proc/cpuinfo") as f:
            text = f.read()
        threads = text.count("processor\t:")
        for line in text.splitlines():
            if line.startswith("model name"):
                return f"{line.split(':', 1)[1].strip()} ({threads} threads)"
    except Exception:
        pass
    return platform.processor() or "unknown"


def _ram_total_gb() -> str:
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return f"{kb / 1024 ** 2:.1f} GB"
    except Exception:
        pass
    return "N/A"


def _gpu_info() -> tuple[str, str]:
    """('name | total | driver' 멀티 GPU 콤마 join, CUDA Version) 반환."""
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=5,
        ).strip()
    except Exception:
        return "N/A", "N/A"

    lines = [l.strip() for l in out.splitlines() if l.strip()]
    cuda = "N/A"
    try:
        smi = subprocess.check_output(["nvidia-smi"], text=True, timeout=5)
        for line in smi.splitlines():
            if "CUDA Version" in line:
                cuda = line.split("CUDA Version:")[1].strip().rstrip("|").strip()
                break
    except Exception:
        pass
    return " | ".join(lines), cuda


_VLLM_KEYS = [
    "VLLM_IMAGE",
    "VLLM_MODEL",
    "GPU_MEMORY_UTILIZATION",
    "MAX_MODEL_LEN",
    "MAX_NUM_SEQS",
    "MAX_NUM_BATCHED_TOKENS",
    "DTYPE",
    "TENSOR_PARALLEL_SIZE",
    "DATA_PARALLEL_SIZE",
    "ENABLE_PREFIX_CACHING",
    "KV_CACHE_MEMORY_BYTES",
    "REASONING_PARSER",
    "VLLM_SEED",
    "NVIDIA_VISIBLE_DEVICES",
    "EXTRA_VLLM_ARGS",
]


def _read_dotenv() -> dict[str, str]:
    """packages/pia_summary/.env 파싱. compose가 컨테이너에 주입하는 값을 호스트에서도 읽기 위함."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return {}
    out: dict[str, str] = {}
    try:
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip()
            if (v.startswith('"') and v.endswith('"')) or \
               (v.startswith("'") and v.endswith("'")):
                v = v[1:-1]
            if k and v:
                out[k] = v
    except Exception:
        pass
    return out


def collect_system_info() -> dict[str, Any]:
    """result.md '환경' 표에 들어갈 dict. .env + 호스트 환경변수 모두 수집."""
    info: dict[str, Any] = {}
    info["hostname"] = socket.gethostname()
    info["os"] = _read_os_pretty_name() or platform.platform()
    info["kernel"] = platform.release()
    info["cpu"] = _cpu_info()
    info["ram"] = _ram_total_gb()
    gpu, cuda = _gpu_info()
    info["gpu"] = gpu
    info["cuda"] = cuda
    info["python"] = sys.version.split()[0]

    dotenv = _read_dotenv()
    for key in _VLLM_KEYS:
        v = os.environ.get(key) or dotenv.get(key)
        if v is not None and v != "":
            info[key.lower()] = v
    info.setdefault("vllm_image", "(default: vllm/vllm-openai:cu130-nightly)")
    info.setdefault("vllm_model", "Qwen/Qwen3.5-0.8B")

    return info


# ---------------------------------------------------------------------------
# 결과 파일명용 slug
# ---------------------------------------------------------------------------

_GPU_SUFFIX_TRIM = [
    "max-q workstation edition",
    "workstation edition",
    "edition",
]


def _slugify(text: str) -> str:
    """파일명 안전 슬러그. 영숫자 / `.` / `-` 만 남기고 `_` 로 합침. 소문자."""
    s = text.lower()
    s = re.sub(r"[^a-z0-9.\-]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_-.")
    return s


def gpu_slug(gpu_field: str) -> str:
    """`collect_system_info()['gpu']` 한 줄에서 슬러그 추출.

    예: 'NVIDIA RTX PRO 6000 Blackwell Max-Q Workstation Edition, 97887, 580.82.07'
        → 'rtx_pro_6000_blackwell'
    """
    name = gpu_field.split(",")[0].strip()
    if name.upper().startswith("NVIDIA "):
        name = name[7:]
    low = name.lower()
    for suffix in _GPU_SUFFIX_TRIM:
        if low.endswith(suffix):
            name = name[: -len(suffix)].strip()
            low = name.lower()
    return _slugify(name) or "unknown_gpu"


def model_slug(model: str) -> str:
    """HF 모델 path 에서 슬래시 이후만 슬러그.

    예: 'Qwen/Qwen3.5-0.8B' → 'qwen3.5-0.8b'
    """
    base = model.rsplit("/", 1)[-1]
    return _slugify(base) or "unknown_model"


def result_filename(sys_info: dict[str, Any]) -> str:
    """{gpu_slug}-{model_slug}.md 형식의 결과 파일명."""
    return f"{gpu_slug(sys_info.get('gpu', ''))}-{model_slug(sys_info.get('vllm_model', ''))}.md"


if __name__ == "__main__":
    for k, v in collect_system_info().items():
        print(f"{k}: {v}")
