# pia_summary tests

`pia_summary` 패키지의 vLLM 서버를 운영 환경에 맞춰 튜닝하기 위한 단계별 벤치마크.
각 스크립트는 호스트에서 직접 실행되며, 측정 결과는 호스트 GPU + 모델 조합에 맞춰
[`bench_results/{gpu_slug}-{model_slug}.md`](./bench_results/) 로 자동 라우팅되고
해당 섹션을 덮어쓴다. 다른 GPU / 모델 조합에서 실행하면 새 파일이 자동 생성된다.

## 사전 조건

1. Python **3.10+** (코드가 `list[T]`, `int | None` 같은 PEP 585 / 604 문법 사용)
2. 호스트 사이드 Python 패키지 설치 (`httpx`, `pillow`):
   ```bash
   cd packages/pia_summary
   pip install -r requirements.txt
   ```
3. `packages/pia_summary/.env` 설정 (`.env.example` 참고. GPU 아키텍처에 맞춰 `VLLM_IMAGE` 선택)
4. **HuggingFace 토큰** (`HF_TOKEN`) 설정 — gated / private 모델을 사용할 때 필요. 공개 모델만 쓸 때는 빈 값 유지.
   ```bash
   # 1) https://huggingface.co/settings/tokens 에서 read 권한 토큰 발급
   # 2) 사용하려는 모델 페이지에서 라이선스 동의 (gated 모델만, 예: meta-llama/*)
   # 3) .env 에 토큰 입력 (따옴표 X, 공백 X):
   #    HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```
   토큰을 git 에 커밋하지 않도록 주의 (`.env` 는 `.gitignore` 처리되어 있음).
5. `docker compose up -d` 로 vLLM 컨테이너 기동 → `curl http://localhost:8000/v1/models` 가 200 응답할 때까지 대기 (첫 기동은 모델 다운로드로 ~3 분, 큰 모델은 더 길어질 수 있음)
6. VRAM 측정에는 PATH 의 `nvidia-smi` 필요 + Linux (코드가 `/proc/cpuinfo`, `/etc/os-release` 사용)

테스트는 서버와 동일 호스트(또는 GPU 가시성 있는 호스트)에서 실행해야
nvidia-smi 로 컨테이너의 VRAM 점유를 측정할 수 있다.

## 운영 원칙

- 한 번에 모든 벤치를 일괄 실행하지 않는다. 단계별 출력을 확인하고 다음 단계로 진행한다.
- 모든 벤치 스크립트는 `--no-append` 옵션으로 드라이런 가능 (콘솔 출력만, 결과 파일 변경 없음).
- 결과 파일은 `bench_results/{gpu_slug}-{model_slug}.md` 로 GPU + 모델 조합별 자동 라우팅된다.
- 같은 환경에서 재실행 시 해당 파일은 덮어쓰기된다. 시계열 비교는 git history 로 추적한다.
- 환경 정보(GPU / OS / CPU / vLLM 옵션)는 결과 파일 상단 `## 테스트 환경` 섹션에 매 실행 시 갱신된다.
- 결과 표는 한국어 컬럼명 + 단위 명시 (`req/s`, `ms`, `MiB`, `초`).

## 측정 한계 / 가정

본 벤치 결과를 해석할 때 다음 가정을 인지해야 한다.

- **prefix caching 활성 + 동일 페이로드**: 모든 호출이 동일한 `sample.jpg` + 더미 메타데이터를 사용한다. `ENABLE_PREFIX_CACHING=true` 와 결합되어 두 번째 호출부터 cache hit 이 일어나며, 실 운영의 다양한 입력 분포보다 latency 가 짧게 나올 수 있다 (best case 측정). 실 운영의 P95/P99 는 본 측정값보다 길게 나올 가능성이 있다.
- **KV cache cap 영향**: `KV_CACHE_MEMORY_BYTES` 가 작게 잡혀 있으면 동시 요청을 늘려도 VRAM peak 가 거의 변하지 않을 수 있다 (cap 안에서만 운용). 이 경우 VRAM 변동 자체로는 KV 압력을 잘 보여주지 못하므로, throughput / p95 변화 곡선으로 한계를 판단한다.
- **`bench_ramp` 의 범위**: 동시 요청 수를 점증시키며 한계를 탐지하는 ramp-up stress test 일 뿐, 장시간 운용 시의 메모리 누수 / latency drift 같은 노화 (aging) 효과 검출은 본 벤치 범위 외다.

## 실행 절차

### 1) sanity_check — 사전 게이트

```bash
python tests/sanity_check.py
```

**용도**: 후속 4개 벤치를 돌리기 전에 호출 경로(컨테이너, 모델, 페이로드 형식, 응답 형태)가 정상인지 1회 호출로 확인. 결과는 콘솔에만 출력되며 결과 파일에는 기록되지 않는다 (운영 튜닝 지표가 아님).

**정상 동작 조건**

- HTTP 200
- 응답이 `.` / `!` / `?` 로 종결
- 응답 단어 수 ≤ `--max-words` (기본 40)
- 영어 단일 문장 (한국어 / Markdown / JSON 섞임 없음)

위 조건을 만족하지 못하면 후속 벤치 결과는 신뢰할 수 없다. 컨테이너 로그와 `/v1/models` 응답을 먼저 점검한다.

### 2) bench_docker_vram — idle 상태 컨테이너 VRAM 점유

```bash
python tests/bench_docker_vram.py
```

**수집 지표** (기본 5회 평균)

- GPU 전체 used (vLLM + 기타 프로세스 합산)
- vLLM 프로세스만의 used (`nvidia-smi` compute-apps 쿼리에서 `process_name` 매칭)

**튜닝 근거**

- vLLM 프로세스 idle 점유는 `GPU_MEMORY_UTILIZATION` 으로 통제되는 영역. 설정 상한 대비 실제 점유 비율로 헤드룸 확인.
- GPU 전체 점유는 부하 인가 전 베이스라인. 후속 단계의 peak 와 비교해 부하에 따른 증가량 산출.

### 3) bench_concurrency — 동시성 sweep

```bash
python tests/bench_concurrency.py
# 또는
python tests/bench_concurrency.py --concurrency-list 1 2 4 8 16 32 \
                                  --per-step-multiplier 20 \
                                  --max-tokens 96
```

**수집 지표** (각 단계별)

- latency p50 / p95 / p99 / mean / max (ms)
- 처리량 (req/s), 성공 / 실패 건수
- VRAM 평균 / peak (MiB) — 백그라운드 `nvidia-smi` 폴링

**튜닝 근거**

- 동시 요청 수 증가에 따라 처리량이 동반 상승하다가 정체되거나 p95 가 급증하는 지점이 saturation point.
- 그 직전 값을 다음 결정의 근거로 사용:
  - 백엔드 워커 수 상한
  - vLLM `MAX_NUM_SEQS` 적정값
- VRAM peak 변화로 KV 캐시 압력 확인.

### 4) bench_max_tokens — `max_tokens` 별 응답시간

```bash
python tests/bench_max_tokens.py
# 또는
python tests/bench_max_tokens.py --tokens 32 64 96 128 192 256 --repeat 5
```

**수집 지표**: 각 `max_tokens` 후보별로 동일 페이로드를 sequential N회 호출하여 측정.

- 평균 / 최소 / 최대 응답 시간 (ms)
- 평균 응답 단어 / 글자 수
- 마침표 종결 비율 (`terminated`)
- 길이 초과로 잘린 응답 비율 (`truncated`, `finish_reason == "length"`)

**튜닝 근거**

- `truncated == 0 / N` 이고 `terminated == N / N` 이 되는 **최소** `max_tokens` 가 적정 상한.
- 결정된 값은 백엔드 호출 측 `build_chat_payload(..., max_tokens=...)` 인자에 반영.
- 컨테이너 재기동 불필요 (vLLM 이 요청 단위로 수용).

### 5) bench_ramp — 부하 점증 한계 탐지 (ramp-up stress)

```bash
python tests/bench_ramp.py
# 또는
python tests/bench_ramp.py --start 1 --step 2 --max 64 \
                           --step-duration 60 \
                           --err-threshold 2.0 \
                           --p95-threshold-ms 10000
```

> 본 벤치는 동시 요청 수를 점증시키며 한계점(saturation)을 탐지하는 ramp-up stress test 다. 시간 경과에 따른 메모리 누수 / latency drift 같은 진짜 aging 검출용은 아니므로, 장기 안정성 검증이 필요하면 별도 도구가 필요하다.

**수집 지표**: 각 단계에서 `--step-duration` 초 동안 지속 부하를 가하며 처리량 / latency / 에러율 / VRAM peak 기록. 중단 조건 충족 시 직전 단계를 `last_safe_concurrency` 로 보고.

**중단 조건** (둘 중 하나라도 만족 시 break)

- 에러율 > `--err-threshold` (%)
- p95 지연 > `--p95-threshold-ms`

**튜닝 근거 / 조치**

- 운영 가능 동시 요청 상한 = `last_safe_concurrency`.
- breakpoint 사유별 조치:
  - **에러율 초과**: vLLM 측 캐시 / VRAM 고갈 가능성. `GPU_MEMORY_UTILIZATION` 상향 또는 `MAX_NUM_SEQS` 하향으로 재시도.
  - **p95 초과**: 큐잉 지연. 백엔드 동시성을 `last_safe_concurrency` 이하로 제한하거나 GPU 추가 배치.

## 운영값 결정 절차

본 절차는 위 5개 벤치 결과를 운영 환경 설정값으로 환원하는 흐름이다.

1. (3) bench_concurrency / (5) bench_ramp → 안정 동시 요청 상한 결정 (백엔드 워커 수, vLLM `MAX_NUM_SEQS`)
2. (4) bench_max_tokens → 적정 `max_tokens` 결정 (백엔드 호출 인자)
3. (2) bench_docker_vram + (3) VRAM peak → `GPU_MEMORY_UTILIZATION` 결정
4. 결정값을 `.env` 또는 백엔드 호출 코드에 반영
5. 컨테이너 재기동 → (1) sanity_check 재확인 → (3) bench_concurrency 재실행 → 결과 파일 갱신 후 회귀 점검

> 다른 GPU 모델 별 베이스라인 권장 `GPU_MEMORY_UTILIZATION` 값은 [`../README.md`](../README.md) 의 "10. GPU 별 권장 VRAM 할당" 섹션 참고.

## 환경 변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `REPORT_VLLM_URL` | `http://localhost:8000/v1/chat/completions` | 호출 대상 |
| `REPORT_MODELS_URL` | `http://localhost:8000/v1/models` | readiness 체크 |
| `VLLM_MODEL` | `Qwen/Qwen3.5-0.8B` | 페이로드의 `model` 필드 |

벤치 스크립트의 `--url`, `--model` 인자가 환경변수보다 우선.

## 파일 구성

| 파일 | 용도 |
|---|---|
| `_common.py` | `prompts.build_chat_payload` 기반 페이로드 / 더미 이미지 / 결과 파일 갱신 헬퍼 |
| `_system.py` | OS / CPU / RAM / GPU / CUDA / vLLM 환경변수 수집, GPU·모델 슬러그 생성 |
| `_vram.py` | `nvidia-smi` 폴링 모니터, 단발 조회, 프로세스별 VRAM 합산 |
| `_result.py` | `bench_results/{gpu}-{model}.md` 섹션 upsert + 렌더 함수 |
| `sanity_check.py` | 단발 호출 사전 게이트 |
| `bench_docker_vram.py` | idle 컨테이너 VRAM 점유 측정 |
| `bench_concurrency.py` | 동시성 sweep + VRAM 동시 측정 |
| `bench_max_tokens.py` | `max_tokens` 별 응답시간 측정 |
| `bench_ramp.py` | 부하 점증 한계 탐지 (ramp-up stress) |
| `bench_results/` | GPU + 모델 조합별 결과 파일 (자동 라우팅 / 덮어쓰기) |
| `bench_results/README.md` | 등록된 환경 인덱스 (수동 갱신) |
| `README.md` | 본 문서 |
| `sample.jpg` | 더미 입력 이미지 (`sanity_check` 첫 실행 시 자동 생성) |

## 옵션 사용 예

```bash
# 결과 파일에 기록하지 않고 콘솔로만 확인 (sanity_check 은 항상 콘솔만)
python tests/bench_concurrency.py --no-append

# 다른 호스트의 vLLM 으로 호출
python tests/sanity_check.py --url http://10.0.0.5:8000/v1/chat/completions \
                             --model my-model

# 동시성 sweep 범위 확장
python tests/bench_concurrency.py --concurrency-list 1 2 4 8 16 32 64

# 램프를 곱셈이 아닌 +1 로 천천히 늘림
python tests/bench_ramp.py --start 1 --step 1 --max 16 --step-duration 60
```
