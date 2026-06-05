"""nvidia-smi 폴링 기반 VRAM 모니터/조회 헬퍼."""

from __future__ import annotations

import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field


@dataclass
class VramSample:
    used_mib: int
    total_mib: int
    timestamp: float


@dataclass
class VramMonitor:
    """백그라운드 스레드에서 일정 주기로 nvidia-smi를 폴링해 사용량 샘플 수집."""

    interval: float = 0.5
    gpu_index: int = 0
    samples: list[VramSample] = field(default_factory=list)
    _stop: threading.Event = field(default_factory=threading.Event)
    _thread: threading.Thread | None = None

    def start(self) -> None:
        if shutil.which("nvidia-smi") is None:
            raise RuntimeError("nvidia-smi가 PATH에 없음")
        self._stop.clear()
        self.samples.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.interval * 2)

    def _loop(self) -> None:
        cmd = [
            "nvidia-smi",
            f"--id={self.gpu_index}",
            "--query-gpu=memory.used,memory.total",
            "--format=csv,noheader,nounits",
        ]
        while not self._stop.is_set():
            ts = time.monotonic()
            try:
                out = subprocess.check_output(cmd, text=True, timeout=5).strip()
                used_str, total_str = (s.strip() for s in out.split(","))
                self.samples.append(
                    VramSample(int(used_str), int(total_str), ts)
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[vram] nvidia-smi 오류: {exc}", file=sys.stderr)
            self._stop.wait(self.interval)


def query_total_vram(gpu_index: int = 0) -> tuple[int, int] | None:
    """현재 (used_mib, total_mib) 단발 조회. nvidia-smi 없으면 None."""
    if shutil.which("nvidia-smi") is None:
        return None
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                f"--id={gpu_index}",
                "--query-gpu=memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=5,
        ).strip()
    except Exception:
        return None
    used_str, total_str = (s.strip() for s in out.split(","))
    return int(used_str), int(total_str)


def query_proc_vram(gpu_index: int = 0, name_match: str = "vllm") -> int | None:
    """주어진 GPU에서 name_match를 process_name에 포함한 모든 프로세스의 VRAM 합계(MiB).

    vLLM 컨테이너가 띄운 프로세스 1~N개의 점유량만 분리하여 측정하기 위함.
    매칭되는 프로세스가 없으면 None.
    """
    if shutil.which("nvidia-smi") is None:
        return None
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                f"--id={gpu_index}",
                "--query-compute-apps=pid,process_name,used_memory",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=5,
        ).strip()
    except Exception:
        return None
    if not out:
        return None
    total = 0
    found = False
    for line in out.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3:
            continue
        _, pname, used = parts[0], parts[1], parts[2]
        if name_match.lower() in pname.lower():
            try:
                total += int(used)
                found = True
            except ValueError:
                continue
    return total if found else None


def summarize(samples: list[VramSample]) -> dict:
    """샘플 리스트 → min/avg/peak/total 요약."""
    if not samples:
        return {"count": 0, "used_min": 0, "used_avg": 0.0, "used_peak": 0, "total": 0}
    used = [s.used_mib for s in samples]
    return {
        "count": len(samples),
        "used_min": min(used),
        "used_avg": sum(used) / len(used),
        "used_peak": max(used),
        "total": samples[0].total_mib,
    }
