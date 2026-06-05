# bench_results 인덱스

각 GPU + 모델 조합별로 한 파일이 자동 생성된다. 파일명 규칙:
`{gpu_slug}-{model_slug}.md` (예: `rtx_pro_6000_blackwell-qwen3.5-0.8b.md`).

같은 환경에서 벤치를 다시 돌리면 해당 파일을 **덮어쓴다** (마지막 결과만 유지).
다른 GPU 호스트나 다른 모델로 돌리면 새 파일이 자동 생성된다.

## 등록된 환경

| 파일 | GPU | 모델 | 핵심 vLLM 옵션 |
|---|---|---|---|
| [rtx_pro_6000_blackwell-qwen3.5-0.8b.md](rtx_pro_6000_blackwell-qwen3.5-0.8b.md) | RTX PRO 6000 Blackwell Max-Q (97 GB) | Qwen/Qwen3.5-0.8B | `util=0.2`, `max_seqs=64`, `max_len=4096` |
| [rtx_pro_6000_blackwell-qwen3.5-2b.md](rtx_pro_6000_blackwell-qwen3.5-2b.md) | RTX PRO 6000 Blackwell Max-Q (97 GB) | Qwen/Qwen3.5-2B | `util=0.2`, `max_seqs=64`, `max_len=4096` |

신규 환경 추가 시 위 표에 한 줄 수동으로 추가. (자동 갱신 X — git diff 노이즈 회피)
