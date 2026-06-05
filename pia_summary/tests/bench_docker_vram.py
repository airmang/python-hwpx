"""docker로 띄운 vLLM 컨테이너의 idle VRAM 점유 측정.

부하를 주지 않은 상태에서 nvidia-smi 로 두 가지를 분리해 보고:
  - GPU 전체 used (= vLLM + 그 외 모든 프로세스)
  - vLLM 프로세스만의 used (compute-apps 쿼리에서 process_name 매칭)

Usage:
    python tests/bench_docker_vram.py
    python tests/bench_docker_vram.py --gpu-index 0 --samples 5
"""

from __future__ import annotations

import argparse
import sys
import time

from _vram import query_proc_vram, query_total_vram


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--gpu-index", type=int, default=0)
    p.add_argument("--samples", type=int, default=5,
                   help="평균 낼 단발 샘플 개수")
    p.add_argument("--interval", type=float, default=1.0,
                   help="샘플 간 간격(초)")
    p.add_argument("--proc-name", default="vllm",
                   help="VRAM 점유를 분리해 합산할 프로세스 이름 부분 매치")
    p.add_argument("--no-append", action="store_true",
                   help="result.md 에 결과를 append 하지 않음 (드라이런)")
    return p.parse_args()


def run(args: argparse.Namespace) -> dict:
    samples_total: list[int] = []
    samples_proc: list[int] = []
    total_mib = 0
    for i in range(args.samples):
        cur = query_total_vram(args.gpu_index)
        if cur is None:
            raise SystemExit("nvidia-smi 호출 실패 — PATH 확인 필요")
        used, total_mib = cur
        samples_total.append(used)
        proc_used = query_proc_vram(args.gpu_index, name_match=args.proc_name)
        if proc_used is not None:
            samples_proc.append(proc_used)
        if i < args.samples - 1:
            time.sleep(args.interval)

    avg_total = sum(samples_total) / len(samples_total)
    avg_proc = (sum(samples_proc) / len(samples_proc)) if samples_proc else None

    result = {
        "gpu_index": args.gpu_index,
        "gpu_total_mib": total_mib,
        "idle_total_used_mib": int(avg_total),
        "idle_total_util_pct": (avg_total / total_mib * 100) if total_mib else 0.0,
        "idle_proc_used_mib": int(avg_proc) if avg_proc is not None else None,
        "idle_proc_util_pct": (avg_proc / total_mib * 100) if (avg_proc and total_mib) else None,
        "proc_name": args.proc_name,
        "samples": args.samples,
    }

    print(f"[docker_vram] gpu_index            : {result['gpu_index']}")
    print(f"[docker_vram] gpu_total            : {result['gpu_total_mib']} MiB")
    print(f"[docker_vram] idle (total)         : "
          f"{result['idle_total_used_mib']} MiB "
          f"({result['idle_total_util_pct']:.1f}%)")
    if result["idle_proc_used_mib"] is not None:
        print(f"[docker_vram] idle ({args.proc_name} proc) : "
              f"{result['idle_proc_used_mib']} MiB "
              f"({result['idle_proc_util_pct']:.1f}%)")
    else:
        print(f"[docker_vram] idle ({args.proc_name} proc) : "
              f"n/a (해당 프로세스 미발견)")

    return result


def main() -> int:
    args = parse_args()
    res = run(args)
    if not args.no_append:
        from _common import write_to_result
        from _result import render_docker_vram
        write_to_result("docker_vram (idle)", render_docker_vram(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
