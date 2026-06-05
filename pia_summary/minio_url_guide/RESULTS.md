# pia_summary URL 모드 — 환경별 동작 검증

같은 vLLM summary 서버 (`Qwen/Qwen3.5-0.8B`, 호스트 :8000) 에 대해 환경 3종 + 실패 케이스 1종을 실측. 모든 호출은 동일 형태의 OpenAI Chat Completions curl 이며, **`image_url.url` 값만 환경별로 다름**.

측정 일시: 2026-05-08 (KST)

---

## 요약

| # | 환경 | URL host | HTTP | latency | 응답 |
|---:|---|---|:---:|---:|---|
| 1 | 같은 docker network | `http://pe-vle-test-minio:9000/...?X-Amz-Signature=...` | **200** | 0.11s | `A white box with the word "DUMMY" in the center is set against a dark background.` |
| 2 | 다른 노드 (host-gateway 통한 도달) | `http://172.19.0.1:9100/...?X-Amz-Signature=...` | **200** | 0.13s | `A white box with the word "DUMMY" in the center is set against a dark background.` |
| 3 | 클라우드 (외부 HTTPS) | `https://httpbin.org/image/jpeg` | **200** | 1.71s | `A gray wolf is walking on a dirt path.` |
| − | 도달 불가 (음성 케이스) | `http://pe-vle-test-minio:9000/...` (vLLM 시점 net 단절) | **500** | 5.01s | `Cannot connect to host pe-vle-test-minio:9000 ssl:default [Name or service not known]` |

핵심: 환경 1·2·3 모두 200, base64 모드와 동일하게 멀티모달 추론 정상. 실패 케이스는 vLLM 시점 도달 불가 — 응답 자체에 원인이 명확히 박혀 디버깅 친화.

---

## 환경 1 — 같은 docker network

vLLM 컨테이너 (`report-vllm`) 와 MinIO 컨테이너 (`pe-vle-test-minio`) 가 같은 docker network (`pia_summary_default`).

### presigned URL 생성 (백엔드 측)

```python
import boto3, uuid
from botocore.client import Config

c = dict(aws_access_key_id='minioadmin', aws_secret_access_key='minioadmin',
         region_name='us-east-1', config=Config(signature_version='s3v4'))
upload = boto3.client('s3', endpoint_url='http://localhost:9100', **c)
sign   = boto3.client('s3', endpoint_url='http://pe-vle-test-minio:9000', **c)  # vLLM 도달 host
key = f'env1-{uuid.uuid4().hex[:6]}.jpg'
upload.upload_file('sample.jpg', 'pia-summary-test', key, ExtraArgs={'ContentType':'image/jpeg'})
url = sign.generate_presigned_url('get_object',
    Params={'Bucket':'pia-summary-test','Key':key}, ExpiresIn=900)
```

생성된 URL:

```
http://pe-vle-test-minio:9000/pia-summary-test/env1-92c53c.jpg
  ?X-Amz-Algorithm=AWS4-HMAC-SHA256
  &X-Amz-Credential=minioadmin%2F20260508%2Fus-east-1%2Fs3%2Faws4_request
  &X-Amz-Date=20260508T075158Z
  &X-Amz-Expires=900
  &X-Amz-SignedHeaders=host
  &X-Amz-Signature=ec94fde986108718b6d5c9046ce77acbc2b9b141d16731159349f59acb3a1ddd
```

### 호출

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3.5-0.8B",
    "messages": [{
      "role": "user",
      "content": [
        {"type": "image_url", "image_url": {"url": "http://pe-vle-test-minio:9000/pia-summary-test/env1-92c53c.jpg?X-Amz-...&X-Amz-Signature=..."}},
        {"type": "text", "text": "Describe the image in one short English sentence."}
      ]
    }],
    "max_tokens": 96,
    "temperature": 0.0
  }'
```

### 응답

```
[HTTP 200] [0.11s]
A white box with the word "DUMMY" in the center is set against a dark background.
```

---

## 환경 2 — 다른 노드 (host-gateway 통한 도달)

MinIO 컨테이너를 vLLM 의 docker network 에서 `disconnect` 한 상태 (= 운영 환경의 다른 노드 / 사내 IDC / 외부 MinIO 와 동치). vLLM 시점에서는 service-name (`pe-vle-test-minio:9000`) 도달 불가.

### 사전 도달성 검증

```bash
docker network disconnect pia_summary_default pe-vle-test-minio

# vLLM 컨테이너 안에서 도달성 비교
docker exec report-vllm sh -c "curl -s -o /dev/null -w '%{http_code}\n' --max-time 3 http://pe-vle-test-minio:9000/minio/health/live"
# 000  (도달 불가)

docker exec report-vllm sh -c "curl -s -o /dev/null -w '%{http_code}\n' --max-time 3 http://172.19.0.1:9100/minio/health/live"
# 200  (호스트 게이트웨이 통한 도달 가능)
```

### presigned URL 생성

서명 endpoint 를 vLLM 시점 도달 가능한 호스트(`172.19.0.1:9100`) 로 만들어 서명함:

```python
sign = boto3.client('s3', endpoint_url='http://172.19.0.1:9100', **c)
url = sign.generate_presigned_url('get_object',
    Params={'Bucket':'pia-summary-test','Key':key}, ExpiresIn=900)
```

생성된 URL:

```
http://172.19.0.1:9100/pia-summary-test/env2-b2b283.jpg
  ?X-Amz-Algorithm=AWS4-HMAC-SHA256
  &X-Amz-Credential=...&X-Amz-Date=...&X-Amz-Expires=900
  &X-Amz-SignedHeaders=host
  &X-Amz-Signature=0e41aed0b0f45e3c7f5e8dae6181e22a122694a7be3828ee790cb9544529e8b1
```

### 호출

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3.5-0.8B",
    "messages": [{
      "role": "user",
      "content": [
        {"type": "image_url", "image_url": {"url": "http://172.19.0.1:9100/pia-summary-test/env2-b2b283.jpg?X-Amz-...&X-Amz-Signature=..."}},
        {"type": "text", "text": "Describe the image in one short English sentence."}
      ]
    }],
    "max_tokens": 96,
    "temperature": 0.0
  }'
```

### 응답

```
[HTTP 200] [0.13s]
A white box with the word "DUMMY" in the center is set against a dark background.
```

---

## 환경 3 — 클라우드 (외부 HTTPS)

vLLM 컨테이너가 외부 인터넷 egress 가능한 환경. 클라우드 S3 presigned URL 도 본질적으로 동일 코드 경로(HTTPS GET) 라서 public HTTPS image URL (httpbin.org) 로 동치 검증.

### 사전 도달성 검증

```bash
docker exec report-vllm curl -s -o /dev/null -w "%{http_code}\n" --max-time 10 https://httpbin.org/image/jpeg
# 200
```

(public CA verify + 인터넷 egress + DNS 해석 모두 OK)

### 호출

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3.5-0.8B",
    "messages": [{
      "role": "user",
      "content": [
        {"type": "image_url", "image_url": {"url": "https://httpbin.org/image/jpeg"}},
        {"type": "text", "text": "Describe the image in one short English sentence."}
      ]
    }],
    "max_tokens": 96,
    "temperature": 0.0
  }'
```

### 응답

```
[HTTP 200] [1.71s]
A gray wolf is walking on a dirt path.
```

응답에 늑대 묘사가 정확히 박힘 — vLLM 이 외부 HTTPS URL 을 정상 fetch + 디코딩 + 멀티모달 입력 인입한 증거.

---

## 음성 케이스

### 조건

MinIO 가 vLLM 의 docker network 에서 분리된 상태에서, presigned URL 의 host 를 service-name (`pe-vle-test-minio:9000`) 으로 두고 호출 — vLLM 시점 도달 불가.

### 호출 / 응답

```
[HTTP 500] [5.01s]
{
  "error": {
    "message": "Cannot connect to host pe-vle-test-minio:9000 ssl:default [Name or service not known]",
    "type": "InternalServerError",
    "param": null,
    "code": 500
  }
}
```

### 진단

| 신호 | 의미 |
|---|---|
| `Cannot connect to host` | 네트워크 도달성 문제 (DNS 미해석 / 라우팅 / 방화벽) |
| `[Name or service not known]` | DNS 단계 실패 — host alias 가 vLLM 컨테이너에서 안 보임 |
| 정확히 5.01s 후 fail | `VLLM_IMAGE_FETCH_TIMEOUT` 기본값 = 5초. 외부 노드용으로 15~30s 권장 |

해결: TUTORIAL.md §B 의 도달성 4가지 조건 (네트워크 egress / HTTPS CA / DNS / timeout) 을 자기 환경에서 점검. 또는 진단 한 줄:

```bash
docker exec report-vllm curl -I --max-time 10 "<백엔드가 만든 presigned URL>"
# 200 → OK / 4xx → URL 자체 문제 / refused·timeout → 네트워크
```

---

## 결론

- **3가지 환경 모두 동작.** 같은 net / 다른 노드 / 클라우드 외부 HTTPS, 모두 OpenAI Chat Completions 형식의 동일한 curl 로 처리됨. 차이는 `image_url.url` 값 하나뿐.
- pia_summary 패키지(`prompts.py`, `docker-compose.yml`, `.env.example`, `tests/`) 변경 0.
- "도달 불가" 케이스는 vLLM 응답에 원인이 명확히 박혀 진단 가능.

: **vLLM 시점에서 presigned URL 의 host 가 도달 가능한가?** (TUTORIAL.md §B)
