# Report Summary Server

CCTV AI 관제 시스템의 알람 레코드(썸네일 + 메타데이터)에 대해 **영어 한 문장 요약**을 생성하는 stand-alone vLLM 추론 서버.

## 1. 패키지 구성

- `docker-compose.yml` — vLLM 공식 이미지 기동 compose
- `prompts.py` — 백엔드가 import하는 프롬프트 빌더 (외부 의존성 없음)
- `tests/` — sanity check + 동시성/VRAM/max_tokens 부하 도구
- `.env.example` — 모델/포트/GPU 설정 템플릿

별도 wrapper 서버 없음. vLLM이 OpenAI 호환 HTTP API(`/v1/chat/completions`) 직접 노출. 백엔드는 이 엔드포인트를 직접 호출.

## 2. 동작 모델

- **트리거**: 백엔드 on-demand HTTP 호출. 자동 실행/큐잉 없음.
- **상태**: stateless. UUID 추적, 외부 publish, DB 저장 없음.
- **책임**: thumbnail(base64 JPEG) + metadata dict 입력 → 영어 한 문장 응답.
- **백엔드 책임**: DB 폴링, 호출, 응답을 summary 컬럼에 저장. 실패 처리/재시도/큐잉은 운영 정책.

## 3. Quick start

```bash
cd Product-AI-mono/packages/pia_summary
cp .env.example .env             # 모델 / GPU / 포트 설정
# .env 에서 다음 항목 확인:
#   - VLLM_MODEL          (기본 Qwen/Qwen3.5-0.8B)
#   - VLLM_IMAGE          (GPU 아키텍처에 맞춰 — §9 참고)
#   - HF_TOKEN            (gated/private 모델 사용 시 필수, 공개 모델은 빈 값)
docker compose up -d
docker compose logs -f report-vllm    # 모델 로딩 → API 서버 기동 로그 대기
curl http://localhost:8000/health
python tests/sanity_check.py
```

### HF_TOKEN 설정 (gated / private 모델 사용 시)

공개 모델 (예: `Qwen/Qwen3.5-0.8B`) 만 쓴다면 건너뛰어도 된다. gated 모델 (예: `meta-llama/*`) 이나 private 저장소를 쓰려면 다음 절차를 거친다.

1. <https://huggingface.co/settings/tokens> 에서 `read` 권한 토큰 발급 (`hf_` 로 시작하는 ~37 자)
2. 해당 모델 페이지에서 라이선스 동의 (gated 모델만, 모델별 1회)
3. `.env` 의 `HF_TOKEN` 항목에 토큰 입력 — 따옴표 / 공백 없이:
   ```
   HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```
4. `docker compose down && docker compose up -d` 로 재기동 (토큰은 컨테이너 시작 시 주입됨)

`.env` 는 `.gitignore` 처리되어 있으나, 토큰이 다른 경로 (로그, 채팅, 스크린샷 등) 로 새지 않도록 주의.

첫 기동 시 모델 다운로드로 수 분 소요. healthcheck `start_period: 600s` 로 유예.

## 4. API 호출과 함수 레퍼런스

### 4.1 curl

```bash
# tests/sample.jpg는 sanity_check.py 첫 실행 시 자동 생성됨.
# 직접 확인 시에는 임의 JPEG 경로로 교체 가능.
B64=$(base64 -w0 tests/sample.jpg)
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d "{
    \"model\": \"Qwen/Qwen3.5-0.8B\",
    \"max_tokens\": 96,
    \"temperature\": 0,
    \"messages\": [{
      \"role\": \"user\",
      \"content\": [
        {\"type\": \"image_url\", \"image_url\": {\"url\": \"data:image/jpeg;base64,$B64\"}},
        {\"type\": \"text\", \"text\": \"<get_report_prompt(metadata) 결과>\"}
      ]
    }]
  }"
```

### 4.2 Python httpx + 본 패키지의 build_chat_payload

```python
import httpx
from prompts import build_chat_payload

body = build_chat_payload(
    thumbnail_b64=row.thumbnail_b64,
    event_metadata={
        "event_id": row.id,
        "camera_name": row.camera_name,
        "detected_category": row.category,
        "event_start_time": row.started_at,
    },
    model="Qwen/Qwen3.5-0.8B",
    max_tokens=96,
)

r = httpx.post("http://localhost:8000/v1/chat/completions",
               json=body, timeout=120)
r.raise_for_status()
summary = r.json()["choices"][0]["message"]["content"].strip()
```

### 4.3 OpenAI SDK 호환 호출

```python
from openai import OpenAI
from prompts import get_report_prompt

client = OpenAI(base_url="http://localhost:8000/v1", api_key="EMPTY")

resp = client.chat.completions.create(
    model="Qwen/Qwen3.5-0.8B",
    max_tokens=96,
    temperature=0,
    messages=[{
        "role": "user",
        "content": [
            {"type": "image_url",
             "image_url": {"url": f"data:image/jpeg;base64,{thumbnail_b64}"}},
            {"type": "text", "text": get_report_prompt(metadata)},
        ],
    }],
)
summary = resp.choices[0].message.content.strip()
```

### 4.4 prompts.py 함수 레퍼런스

`prompts.py`가 export하는 함수는 두 개. 둘 다 백엔드가 import해서 쓰는 헬퍼이며, 호출 스타일에 따라 편한 쪽을 선택한다. 자세한 인자 의미는 함수 docstring 참고.

#### `get_report_prompt(event_metadata, max_words=40) -> str`

VLM에 보낼 텍스트 프롬프트만 만들어 반환. 썸네일/메시지 구조 조립은 호출 측 책임.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `event_metadata` | `dict` | (필수) | 알람 메타데이터. 키 자유. 빈 값(None, "")은 자동 제외 |
| `max_words` | `int` | `40` | 응답 한 문장의 단어 상한 (모델에게 전달되는 hint) |

언제 쓰나: OpenAI SDK처럼 `messages` 구조를 직접 조립하는 흐름에서 텍스트 부분만 채울 때 (§4.3).

#### `build_chat_payload(thumbnail_b64, event_metadata, *, model, max_tokens=96, temperature=0.0, max_words=40) -> dict`

vLLM `/v1/chat/completions`에 그대로 POST 가능한 request body 통째를 만들어 반환. 내부에서 `get_report_prompt`를 호출.

| 인자 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `thumbnail_b64` | `str` | (필수) | base64 인코딩된 JPEG 본문. `data:image/jpeg;base64,` prefix 없이 |
| `event_metadata` | `dict` | (필수) | 위와 동일 |
| `model` | `str` | (필수, 키워드) | vLLM 띄운 모델 이름. `.env`의 `VLLM_MODEL`과 일치 |
| `max_tokens` | `int` | `96` | 모델 생성 최대 토큰. `tests/benchmark_max_tokens.py`로 적정값 측정 |
| `temperature` | `float` | `0.0` | 샘플링 온도. 관제용 일관성 위해 0 권장 |
| `max_words` | `int` | `40` | `get_report_prompt`로 전달 |

언제 쓰나: `httpx.post(url, json=...)` 형태로 직접 호출하는 흐름에서 messages 구조 보일러플레이트를 줄이고 싶을 때 (§4.2).

#### 어느 걸 쓸지 선택 가이드

- **OpenAI SDK 사용** (`from openai import OpenAI` 또는 `AsyncOpenAI`) → `get_report_prompt`만 import. SDK가 messages 구조 조립.
- **httpx 직접 호출** → `build_chat_payload`가 편함. body dict 한 번에 만들고 `json=body`로 POST.
- **둘 다 안 쓰고 싶음** → 이 모듈 import 안 해도 동작. 다만 프롬프트 변경 시 백엔드 코드도 같이 손봐야 함.

## 5. event_metadata 자유도

`get_report_prompt`/`build_chat_payload`는 **임의 dict** 수용. 키 이름/개수/타입 자유. 백엔드가 자기 DB 컬럼을 그대로 dict에 담아 전달. 빈 값(None, "")은 자동 필터링.

세 가지 호출 예 — 모두 동일 동작:

```python
# 최소
get_report_prompt({})

# feature.md §4 표 그대로
get_report_prompt({
    "event_id": "EVT-001",
    "camera_id": "CAM-03",
    "camera_name": "Server Room Entrance",
    "zone_name": "Zone-A",
    "detected_category": "fall_down",
    "event_start_time": "2026-04-28 14:23:11",
})

# 백엔드가 자기 컬럼 추가
get_report_prompt({
    "alarm_id": 42,
    "site": "Daejeon HQ",
    "rule": "loitering",
    "started": "2026-04-28T14:23:11Z",
    "operator_note": "after-hours",
})
```

프롬프트 본문에 `key: value` 라인으로 그대로 펼침.

## 6. 프롬프트 커스터마이즈

`prompts.py`의 `PROMPT_TEMPLATE` 문자열만 수정하면 출력 톤/형식/길이 변경 가능. 호출 시 `max_words` 인자로 단어 상한 조정.

카테고리별 분기 필요 시 다음 패턴으로 확장 (validation_server/prompts.py 참고). `prompts.py`는 `.format()` 대신 `<<...>>` 자리표시자 + `.replace()`를 쓰므로 (JSON 예시와의 brace 충돌 회피) 확장 시에도 동일 패턴 유지를 권장:

```python
_PROMPT_MAP = {
    "fire": FIRE_TEMPLATE,
    "smoke": SMOKE_TEMPLATE,
    "fall_down": FALLDOWN_TEMPLATE,
}
DEFAULT_TEMPLATE = PROMPT_TEMPLATE  # 모든 템플릿이 <<METADATA_BLOCK>>, <<MAX_WORDS>> 자리표시자를 가진다고 가정

def get_report_prompt(event_metadata, max_words=40):
    cat = event_metadata.get("detected_category", "")
    template = _PROMPT_MAP.get(cat, DEFAULT_TEMPLATE)
    return (
        template
        .replace("<<METADATA_BLOCK>>", _format_metadata_block(event_metadata))
        .replace("<<MAX_WORDS>>", str(max_words))
    )
```

## 7. 환경변수

`.env` (또는 셸 export)로 주입. compose 파싱 시점에 보간 후 컨테이너 내부 shell에서 vLLM CLI 인자로 expansion. 각 변수의 상세 의미/주의점은 `.env.example` 주석 참고.

### 7.1 베이스 / 모델

| 변수 | 기본값 | 영향 | 설명 |
|---|---|---|---|
| `VLLM_IMAGE` | `vllm/vllm-openai:cu130-nightly` | 호환성 | GPU 아키텍처별 베이스 이미지 (§9) |
| `VLLM_MODEL` | `Qwen/Qwen3.5-0.8B` | VRAM/품질 | HF 모델 path |
| `HF_TOKEN` | "" | 다운로드 | gated/private 모델 다운로드 토큰 |

### 7.2 병렬화

| 변수 | 기본값 | 영향 | 설명 |
|---|---|---|---|
| `TENSOR_PARALLEL_SIZE` | `1` | VRAM 분산 | 단일 모델을 N개 GPU에 weight split |
| `DATA_PARALLEL_SIZE` | `1` | throughput | 모델 N복제 — N배 throughput. MoE/대용량 멀티모달에서 의미 |

### 7.3 VRAM / KV 캐시 / dtype

| 변수 | 기본값 | 영향 | 설명 |
|---|---|---|---|
| `GPU_MEMORY_UTILIZATION` | `0.2` | VRAM 상한 | 모델+KV+activation 합계 점유율. `tests/benchmark_vram.py`로 측정 |
| `KV_CACHE_MEMORY_BYTES` | `1G` | KV 슬롯 | 0.8B + 짧은 응답 기준 동시 수십 건 처리에 충분. 빈 값=자동(GPU_MEMORY_UTILIZATION 기반). 동시성↑ 시 2G/4G 상향 |
| `DTYPE` | `auto` | VRAM/품질 | `auto`/`bfloat16`/`float16`/`float8` |

### 7.4 컨텍스트 / 동시 처리 한계

| 변수 | 기본값 | 영향 | 설명 |
|---|---|---|---|
| `MAX_MODEL_LEN` | `4096` | VRAM/허용길이 | 한 요청 input+output+이미지 토큰 상한 |
| `MAX_NUM_SEQS` | `64` | throughput/VRAM | 동시 디코딩 시퀀스 상한. 초과 요청은 큐잉 |
| `MAX_NUM_BATCHED_TOKENS` | `8192` | latency | 한 step의 prefill+decode 토큰 상한. 너무 작으면 prefill 절단 |
| `LIMIT_MM_PER_PROMPT` | `{"image":1}` | 멀티모달 | 프롬프트당 미디어 입력 상한 |

### 7.5 처리량 최적화 / 모델 옵션

| 변수 | 기본값 | 영향 | 설명 |
|---|---|---|---|
| `ENABLE_PREFIX_CACHING` | `true` | latency/throughput | 동일 prefix 반복 요청 캐시. PROMPT_TEMPLATE이 고정이면 효과 큼 |
| `REASONING_PARSER` | "" | 응답 파싱 | reasoning 모델용 (예: `qwen3`). 비-reasoning 모델은 빈 값 유지 |
| `VLLM_SEED` | `0` | 재현성 | 동일 입력에 대한 결정적 출력 |

### 7.6 자유 입력

| 변수 | 기본값 | 영향 | 설명 |
|---|---|---|---|
| `EXTRA_VLLM_ARGS` | "" | 임의 | 위 항목으로 표현되지 않는 vLLM CLI 옵션을 자유 추가. 옵션별 의미/주의는 `.env.example` §[7] 주석 참고 (`--speculative-config`, `--max-cudagraph-capture-size`, `--enable-expert-parallel`, `--language-model-only`, `--mm-encoder-tp-mode`, `--hf-overrides` 등) |

### 7.7 네트워킹 / GPU / 캐시

| 변수 | 기본값 | 설명 |
|---|---|---|
| `VLLM_PORT` | `8000` | 호스트 매핑 포트 |
| `NVIDIA_VISIBLE_DEVICES` | `0` | 컨테이너 노출 GPU index (콤마 구분 다중 가능) |
| `GPU_COUNT` | `1` | compose reserve GPU 수 (위 값과 일치 권장) |
| `HF_CACHE_DIR` | `~/.cache/huggingface` | 모델 캐시 호스트 경로 (재기동 시 재다운로드 방지) |

## 8. 운영 튜닝 가이드

`tests/README.md` 권장 절차 요약:

1. `tests/sanity_check.py` — 사전 게이트 (호출 경로 정상성)
2. `tests/bench_docker_vram.py` — idle 상태 컨테이너 VRAM 점유 측정
3. `tests/bench_concurrency.py` — 동시 요청 1, 2, 4, 8, 16 sweep → 처리량 포화점, `MAX_NUM_SEQS` / 백엔드 워커 수 산정
4. `tests/bench_max_tokens.py` — `truncated == 0` 이 되는 최소 `max_tokens` 결정
5. `tests/bench_ramp.py` — 부하 점증 한계 탐지 (ramp-up stress, `last_safe_concurrency`, breakpoint)

각 도구 상세 사용법 / 결과 해석은 `tests/README.md`. 측정 결과는 `tests/bench_results/{gpu_slug}-{model_slug}.md` 로 자동 라우팅.

## 9. GPU 아키텍처별 베이스 이미지

| GPU | `VLLM_IMAGE` |
|---|---|
| Blackwell (B200, B100, RTX 5090) | `vllm/vllm-openai:cu130-nightly` |
| Hopper (H100, H200) | `vllm/vllm-openai:latest` |
| Ampere (A100, A10, A30, RTX 30/40 시리즈) | `vllm/vllm-openai:latest` |

`.env`의 `VLLM_IMAGE` 변경 후 재기동.

## 10. GPU 별 권장 VRAM 할당 (`GPU_MEMORY_UTILIZATION`)

`tests/bench_results/` 측정 데이터 기반 베이스라인. 운영 환경 / 모델 / 응답 길이가 본 전제와 다르면 직접 측정 후 조정.

**전제**
- 모델: Qwen3.5-2B (FP16 weight)
- 응답 길이: ~30 토큰 (한 문장 영어 요약)
- `MAX_MODEL_LEN=4096`, `MAX_NUM_SEQS=64`, `KV_CACHE_MEMORY_BYTES=1G`
- 동시 요청 수 100 처리 가정
- 실측: 동시성 64 peak ≈ 7.1 GB → 안전 마진 포함 시 **약 10 GB 할당**

| 모델 | VRAM | 동시성 100 권장 할당 | 권장 `GPU_MEMORY_UTILIZATION` |
| ------------ | ---: | ---: | ---: |
| RTX A4000    | 16GB | 10GB | 0.65 |
| RTX A5000    | 24GB | 10GB | 0.45 |
| RTX A6000    | 48GB | 10GB | 0.25 |
| RTX PRO 4000 | 24GB | 10GB | 0.45 |
| RTX PRO 5000 | 48GB | 10GB | 0.20 |
| RTX PRO 6000 | 96GB | 10GB | 0.12 |

`GPU_MEMORY_UTILIZATION` 은 **상한값**이다. vLLM 이 모델 weight + KV 캐시 + activation 을 이 비율 안에서만 운용하며, 토큰을 더 생성한다고 cap 을 초과하지는 않는다. cap 이 모자라면 동시 처리량 / latency 가 저하될 뿐 VRAM 자체는 늘지 않는다.

**다른 모델로 교체 시**
- 더 큰 모델 (예: 7B, 14B) → 권장 할당 비례 상향
- 응답 길이가 길어지면 (수백 토큰) → KV 캐시 점유 증가 → 권장 할당 상향
- 가장 정확한 값은 `tests/` 5단계 절차 재실행 후 `bench_results/` 결과 기준으로 결정

## 11. 에러 응답

vLLM 자체 응답 코드를 그대로 수신. 백엔드 측 처리 가이드:

| 상태 | 의미 | 백엔드 권장 처리 |
|---|---|---|
| `200` | 성공 | `choices[0].message.content` 사용 |
| `400` | 잘못된 payload (이미지 URL/messages 형식 등) | 에러 로그 후 폐기 (재시도 무의미) |
| `404` | 잘못된 model 이름 | 설정/배포 문제 — 알림 발송 |
| `429` | vLLM throttle (드물게) | 짧게 대기 후 재시도 |
| `500` | vLLM 내부 오류 | 재시도 1~2회, 실패 시 dead-letter |
| `503` | 모델 로딩 중 / 비정상 종료 후 재기동 | start_period 내에 ready 복귀 — 재시도 |
| 타임아웃 | 응답 길이 과대 / 부하 과다 | `max_tokens` 축소 또는 동시성 하향 |

## 12. Out of scope

본 패키지가 의도적으로 다루지 않는 항목:

- 카테고리별 프롬프트 자동 분기 (§6에 확장 예시 인라인)
- MinIO 등에서 비디오 클립 다운로드 후 다중 프레임 입력
- Pod / Helm chart 매니페스트
- 백엔드 큐잉 / 비동기 처리 정책
- JSON 구조화 출력 옵션
- 권한별 표출 차등
- 한국어 출력 (현재 영어 단일)

추가 요구 시 `prompts.py` 템플릿 변경 + 백엔드 호출 코드 변경으로 대부분 대응 가능.
