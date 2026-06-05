# pia_summary + MinIO URL 모드 — 세팅 튜토리얼

`Product-AI-mono/packages/pia_summary` vLLM 서버를 **base64 대신 MinIO presigned URL** 로 호출하는 환경 구축 가이드. pia_summary 패키지 본체(`prompts.py`, `docker-compose.yml`, `.env.example`, `tests/`) 변경 없이 호출 측 코드만으로 도입 가능함.

진입점:

| 역할 | 섹션 |
|---|---|
| 백엔드 | §A → §4 |
| 인프라 / DevOps | §B → §1~§3 → §2.4 |
| 운영 | §6 |

---

## §A. 백엔드 통합

### A.1 백엔드가 할 일

```
(a) 이미지를 MinIO/S3 에 업로드 (자기 secret key 로)
(b) 그 객체의 presigned URL 생성 (= 시간 제한 권한 위임 토큰)
(c) vLLM 호출 시 OpenAI payload 의 image_url 자리에 그 URL 박아 전달
```

vLLM 이 하는 일: URL GET → 이미지 그대로 멀티모달 입력.

**vLLM 은 secret 도, MinIO endpoint 도, SDK 도 모름.** 인증은 URL 안 서명을 MinIO/S3 가 검증. 보안 모델은 §A.4.

### A.2 OpenAI payload 변화

**JSON 구조 동일. `image_url.url` 값만 다름.** OpenAI Chat Completions 스펙상 `url` 은 `data:` scheme 과 `http(s):` scheme 둘 다 합법.

base64 모드 (현재):

```json
{
  "messages": [{
    "role": "user",
    "content": [
      {
        "type": "image_url",
        "image_url": { "url": "data:image/jpeg;base64,/9j/4AAQ..." }
      },
      { "type": "text", "text": "..." }
    ]
  }],
  "model": "Qwen/Qwen3.5-0.8B",
  "max_tokens": 96,
  "temperature": 0.0
}
```

URL 모드 (presigned):

```json
{
  "messages": [{
    "role": "user",
    "content": [
      {
        "type": "image_url",
        "image_url": { "url": "https://minio.corp.example.com/pia-summary/thumb-abc.jpg?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=...&X-Amz-Date=...&X-Amz-Expires=600&X-Amz-Signature=..." }
      },
      { "type": "text", "text": "..." }
    ]
  }],
  "model": "Qwen/Qwen3.5-0.8B",
  "max_tokens": 96,
  "temperature": 0.0
}
```

차이가 있는 곳:

| 위치 | base64 모드 | URL 모드 |
|---|---|---|
| `messages[0].content[0].image_url.url` | `"data:image/jpeg;base64,..."` (수만 자) | `"https://...?X-Amz-Signature=..."` (수백 자) |
| 그 외 모든 필드 | 동일 | 동일 |

### A.3 코드

```python
import httpx
from prompts import build_chat_payload

payload = build_chat_payload(
    thumbnail_b64="",                # 자리 채움. 다음 줄에서 덮어씀
    event_metadata=event_metadata,
    model="Qwen/Qwen3.5-0.8B",
    max_tokens=96,
)
payload["messages"][0]["content"][0]["image_url"]["url"] = presigned_url

r = httpx.post("http://<vllm-host>:8000/v1/chat/completions", json=payload, timeout=120)
```

`presigned_url` 발급 코드는 §4 참고.

### A.4 보안 모델

의문: "vLLM 이 secret 없이 URL 만으로 접근 가능하면 보안 위험 아닌가?"

답: **presigned URL 자체가 시간 제한 인증 토큰임.** 흐름:

```
[백엔드]                          [vLLM]                       [MinIO/S3]
  | (1) URL 생성:                   |                              |
  |     자기 secret 으로 HMAC 서명  |                              |
  |     → URL 안에 박음             |                              |
  | (2) URL 만 vLLM 에 ----------->|                              |
  |     (secret 안 보냄)            |                              |
  |                                 | (3) URL 그대로 GET --------->|
  |                                 |                              | (4) 서명 검증:
  |                                 |                              |     - 자기 secret 으로 동일 서명 만들어 비교
  |                                 |                              |     - 만료시각 체크
  |                                 |                              |     - 통과 시 객체 / 아니면 403
  |                                 | (5) 200 + 이미지 <-----------|
```

| 보장 | 메커니즘 |
|---|---|
| 특정 객체에만 유효 | path 가 서명에 포함 — 다른 객체로 변조 불가 |
| 시간 제한 | `X-Amz-Expires` 만료 후 MinIO 가 거부 |
| 변조 불가 | query 한 글자만 바꿔도 서명 불일치 → 403 |
| vLLM 침해 시 secret 유출 0 | URL 외엔 아무 자격 정보 없음 |

운영 보안: HTTPS 전송, 만료 5~15분, private bucket, 로그 signature 마스킹. 자세한 건 §6.

### A.5 검증 자료

- 환경별 동작 검증 (curl + 응답): `RESULTS.md`
- 예제 코드: `example_basic.py` (단발 동등성), `example_external_node.py` (다른 노드 시뮬레이션)

---

## §B. 인프라 도달성 원칙

> **vLLM 은 MinIO 의 endpoint, credential, SDK 몰라도 동작 가능.**
> 백엔드가 만든 **presigned URL 의 host 가 vLLM 시점에서 도달 가능**하면 동작.

점검 한 가지:

```
[vLLM Pod / 컨테이너] --HTTP GET--> [presigned URL host:port]
```

화살표가 성립하면 환경(로컬 docker / Kubernetes / 사내 IDC / S3 호환 외부 스토리지) 무관 동작. 이하 §1~§2 는 **이 도달성을 만족시키는 구체 방법**들의 카탈로그.

"도달 가능" 의 4가지 조건 (모두 OK 여야 동작):

| 조건 | MinIO 로컬 | 클라우드 S3 / 사내 HTTPS |
|---|---|---|
| 네트워크 egress | docker network 일치 | 인터넷 / VPC endpoint / 사내 라우팅 |
| HTTPS CA verify | (보통 http) | public CA (vLLM base 이미지 포함) 또는 사내 CA 마운트 |
| DNS 해석 | 컨테이너 alias | 외부 도메인 해석 가능 |
| timeout | 5s 충분 | RTT 큼 → `VLLM_IMAGE_FETCH_TIMEOUT=15~30` |

도입 진단:

```bash
# vLLM 컨테이너/Pod 안에서 실제 presigned URL 한 건 curl
curl -I "<presigned-url>"
# 200          -> OK
# 4xx/5xx      -> URL 자체 문제 (만료, 서명)
# refused/timeout -> 네트워크 도달성 문제 (§2 참고)
```

---

## 0. 사전 요구사항

| 항목 | 버전/조건 |
|---|---|
| Docker | 24.x 이상 (compose v2 내장) |
| GPU 드라이버 | NVIDIA driver + nvidia-container-toolkit (vLLM 운영용) |
| Python | 3.10 이상 (백엔드 호출 코드 작성용) |
| 디스크 | HF 모델 캐시 + MinIO 버킷용 충분한 여유 (기본 `~/.cache/huggingface`, `./minio-data`) |

---

## 1. MinIO 컨테이너 기동

`Product-AI-mono/packages/pia_summary/` 와 같은 위치에 새 디렉터리를 두거나, 기존 인프라(예: 이미 띄워둔 다른 MinIO 컨테이너)를 재사용 가능. 신규로 띄우는 가장 단순한 형태:

```yaml
# docker-compose.minio.yml
services:
  pia-minio:
    image: minio/minio
    container_name: pia-minio
    ports:
      - "9100:9000"   # API
      - "9101:9001"   # Console
    environment:
      - MINIO_ROOT_USER=${MINIO_ROOT_USER:-minioadmin}
      - MINIO_ROOT_PASSWORD=${MINIO_ROOT_PASSWORD:-minioadmin}
    command: server /data --console-address ":9001"
    volumes:
      - ./minio-data:/data
    restart: unless-stopped
    networks:
      - pia_summary_default

networks:
  pia_summary_default:
    external: true   # pia_summary docker-compose가 만든 네트워크에 합류
```

기동 / 상태 확인:

```bash
docker compose -f docker-compose.minio.yml up -d
docker compose -f docker-compose.minio.yml ps
curl -s http://localhost:9100/minio/health/live
# 200 OK 응답이면 정상
```

콘솔 UI: 브라우저로 `http://<host>:9101` → minioadmin / minioadmin 로그인.

> 운영 환경 권장: `MINIO_ROOT_*` 를 강한 값으로 교체 후 `.env` 로 분리. IAM 사용자 발급 후 root credential 즉시 회수.

---

## 2. 네트워크 연결

§B 의 도달성 원칙을 만족시키는 구체적 방법. 환경별로 갈리는 유일한 섹션임.

### 2.1 로컬 docker / docker-compose

`pia_summary` 의 `docker-compose.yml` 은 별도 네트워크 지정이 없으므로 **`pia_summary_default`** default network 가 자동 생성됨. MinIO 컨테이너도 같은 network 에 있어야 vLLM 이 hostname (`pia-minio`) 으로 fetch 가능.

확인:

```bash
docker network inspect pia_summary_default --format '{{range .Containers}}{{.Name}} {{end}}'
# 출력에 report-vllm 과 pia-minio 가 모두 포함되어야 함
```

기존 MinIO 가 다른 network 에 있다면 추가 connect 만 해도 충분 (vLLM 컨테이너 재시작 불필요):

```bash
docker network connect pia_summary_default <기존-minio-컨테이너>
```

vLLM 내부에서 도달 검증:

```bash
docker exec report-vllm curl -s -o /dev/null -w "%{http_code}\n" \
    http://pia-minio:9000/minio/health/live
# 200
```

### 2.2 Kubernetes

#### Service DNS

vLLM Pod 가 같은 클러스터의 MinIO Service 를 호출. presigned URL 의 host 부분을 다음 형태로 서명함:

```
http://<minio-service>.<namespace>.svc.cluster.local:9000
```

예: MinIO 가 `data` namespace 의 `minio` Service 라면 host 는 `minio.data.svc.cluster.local:9000`.

#### Manifest

```yaml
# minio.yaml — 본 가이드 동작 확인용 최소 구성 (운영용 아님)
apiVersion: v1
kind: Secret
metadata:
  name: minio-credentials
  namespace: data
type: Opaque
stringData:
  rootUser: minioadmin
  rootPassword: minioadmin
---
apiVersion: apps/v1
kind: Deployment
metadata: { name: minio, namespace: data }
spec:
  replicas: 1
  selector: { matchLabels: { app: minio } }
  template:
    metadata: { labels: { app: minio } }
    spec:
      containers:
        - name: minio
          image: minio/minio
          args: ["server", "/data", "--console-address", ":9001"]
          env:
            - name: MINIO_ROOT_USER
              valueFrom: { secretKeyRef: { name: minio-credentials, key: rootUser } }
            - name: MINIO_ROOT_PASSWORD
              valueFrom: { secretKeyRef: { name: minio-credentials, key: rootPassword } }
          ports:
            - { containerPort: 9000, name: api }
            - { containerPort: 9001, name: console }
          volumeMounts:
            - { name: data, mountPath: /data }
      volumes:
        - name: data
          emptyDir: {}      # 운영 환경에서는 PVC 로 교체
---
apiVersion: v1
kind: Service
metadata: { name: minio, namespace: data }
spec:
  selector: { app: minio }
  ports:
    - { name: api, port: 9000, targetPort: 9000 }
    - { name: console, port: 9001, targetPort: 9001 }
```

#### endpoint

§4.2 의 두 client 분리 패턴이 K8s 에서도 동일:

| client 용도 | endpoint_url 값 |
|---|---|
| 업로드 (백엔드 Pod → MinIO) | `http://minio.data.svc.cluster.local:9000` |
| presigned 서명 (vLLM Pod 가 fetch 할 때 쓸 host) | `http://minio.data.svc.cluster.local:9000` |

백엔드도 같은 클러스터면 둘 동일. 콘솔 UI 는 별도 `Ingress` 또는 `kubectl port-forward svc/minio 9101:9001 -n data`.

#### NetworkPolicy

NetworkPolicy 가 활성된 클러스터라면 vLLM Pod → MinIO Service egress 명시 허용:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: vllm-egress-to-minio
  namespace: <vllm-namespace>
spec:
  podSelector: { matchLabels: { app: report-vllm } }
  policyTypes: [Egress]
  egress:
    - to:
        - namespaceSelector: { matchLabels: { name: data } }
          podSelector: { matchLabels: { app: minio } }
      ports:
        - { protocol: TCP, port: 9000 }
```

#### 도달성 검증

```bash
# vLLM Pod 안에서
kubectl exec -n <vllm-ns> deploy/report-vllm -- \
    curl -s -o /dev/null -w "%{http_code}\n" \
    http://minio.data.svc.cluster.local:9000/minio/health/live
# 200
```

200 이 안 나오면 presigned URL 도 미동작. §B 박스의 화살표가 끊긴 상태임.

### 2.3 외부 MinIO / S3

이미 사내 IDC 또는 클라우드에 운영 중인 MinIO 사용 시. 추가 인프라 없이 도달성 원칙만 만족시키면 됨.

| 케이스 | presigned URL host 부분 | vLLM 측 요구 |
|---|---|---|
| 사내 IDC MinIO | `https://minio.corp.example.com:9000` | vLLM Pod 의 egress 가 회사 네트워크 도달 가능 (DNS, NAT, 방화벽) |
| AWS S3 | `https://<bucket>.s3.<region>.amazonaws.com/...` | vLLM Pod 의 egress 가 인터넷 또는 VPC endpoint 로 S3 도달 |
| 다른 클라우드 (GCS HMAC, R2 등) | 각 서비스의 presigned URL host | egress 도달성 |

이 경우 별도 docker-compose 나 Kubernetes Manifest 불필요. **§4 의 백엔드 코드만 자기 endpoint/credential 로 갈아 끼우면 끝.** vLLM 은 외부 URL 을 fetch 할 뿐.

세부 인자/볼륨/CA 설정은 §2.4 참고.

### 2.4 vLLM 추가 설정 (다른 노드 / 외부 MinIO)

**원칙**: pia_summary 패키지(`docker-compose.yml`, `.env.example`) 본체는 미변경. 사용자 환경별 차이는 **`docker-compose.override.yml`** 또는 사용자 측 별도 compose 파일로 주입함.

#### 추가 항목

| 항목 | 언제 필요 | 어디에 |
|---|---|---|
| `VLLM_IMAGE_FETCH_TIMEOUT` (초) | 외부 노드는 RTT 큼. 기본 5s 부족 → 15s 권장 | `environment` |
| `HTTP_PROXY` / `HTTPS_PROXY` / `NO_PROXY` | 사내망에서 외부 인터넷 통할 때 | `environment` |
| `extra_hosts` | 사내 DNS 미등록 host alias 강제 매핑 | `extra_hosts` |
| `dns` | 컨테이너 DNS 가 외부 도메인 해석 못 할 때 (사내 DNS 강제) | `dns` |
| 사내 CA 인증서 마운트 | self-signed HTTPS presigned URL 사용 시 | `volumes` |
| egress 방화벽 규칙 | 노드 → MinIO 노드 방화벽 (9000/443) | 인프라 정책 |

#### override 예시

`Product-AI-mono/packages/pia_summary/` 와 같은 위치(또는 운영자 작업 폴더)에 다음 파일 배치:

```yaml
# docker-compose.override.yml — 사용자 인프라별 작성, 본체 미수정
services:
  report-vllm:
    environment:
      # 외부 노드 fetch 타임아웃 (기본 5s → 15s)
      - VLLM_IMAGE_FETCH_TIMEOUT=${VLLM_IMAGE_FETCH_TIMEOUT:-15}
      # 사내 프록시
      - HTTP_PROXY=${HTTP_PROXY:-}
      - HTTPS_PROXY=${HTTPS_PROXY:-}
      - NO_PROXY=${NO_PROXY:-localhost,127.0.0.1}
    extra_hosts:
      # DNS 미등록 host alias 강제 매핑 (필요 시만)
      # 비워두려면 한 줄 주석 처리
      - "host.docker.internal:host-gateway"   # 호스트 라우팅 fallback
    dns:
      # 사내 DNS 강제 (필요 시만)
      - 8.8.8.8
    volumes:
      # 사내 self-signed CA (필요 시만 — 파일 없으면 한 줄 통째 주석)
      - ${EXTRA_CA_BUNDLE:-/dev/null}:/usr/local/share/ca-certificates/corp-ca.crt:ro
```

기동 명령은 평소와 동일 — Docker 가 본체 + override 자동 병합:

```bash
docker compose up -d
# 내부적으로 docker-compose.yml + docker-compose.override.yml 병합 실행
```

본체 가이드(`§1` 의 docker-compose.yml) 만 쓰던 사용자에게 영향 없음.

#### 명시 합치기 (옵션)

override 를 항상 켜고 싶지 않다면 별도 이름(`docker-compose.external-minio.yml`)으로 두고 명시 합치기:

```bash
docker compose -f docker-compose.yml -f docker-compose.external-minio.yml up -d
```

#### 검증 명령

```bash
# 1) presigned URL host 가 vLLM 시점에서 보이는지
docker exec report-vllm getent hosts minio.corp.example.com   # DNS 또는 extra_hosts 확인
docker exec report-vllm curl -I --max-time 10 \
    "$(echo '<백엔드가 만든 presigned URL 한 건 그대로>')"
# 200 + Content-Type: image/jpeg 면 OK

# 2) HTTPS + 사내 CA 케이스
docker exec report-vllm openssl s_client -connect minio.corp.example.com:443 -servername minio.corp.example.com </dev/null 2>&1 | grep -E "(verify|CN=)"

# 3) 프록시 환경변수 적용 여부
docker exec report-vllm sh -c 'env | grep -i proxy'
```

#### 함정 정리

| 함정 | 증상 | 해결 |
|---|---|---|
| presigned URL host 가 `localhost` | vLLM 안에서 자기 컨테이너 localhost 로 가서 fail | §4.2 두 client 분리 (서명 전용 endpoint 를 컨테이너 도달 가능 host 로) |
| `host.docker.internal` 이 Linux 에서 미동작 | 기본 미해석 | `extra_hosts: ["host.docker.internal:host-gateway"]` 명시 (Docker 20.10+) |
| HTTPS verify 실패 | self-signed CA 미반영 | volume 마운트 + 컨테이너에 `update-ca-certificates` 필요 시 entrypoint 한 줄 추가 또는 `REQUESTS_CA_BUNDLE` 환경변수 |
| timeout 빈발 | 기본 5s 부족 | `VLLM_IMAGE_FETCH_TIMEOUT=15~30` |
| 첫 요청만 느리고 이후 정상 | DNS 캐시 워밍업 | 정상. 운영 영향 없음 |

---

## 3. Bucket 생성 + 권한 정책

MinIO Client(`mc`)를 호스트에 설치했거나 컨테이너 내장 `mc` 사용. 가장 빠른 방법은 컨테이너 안에서:

```bash
docker exec -i pia-minio mc alias set local http://localhost:9000 minioadmin minioadmin
docker exec -i pia-minio mc mb local/pia-summary --ignore-existing
docker exec -i pia-minio mc ls local/
```

운영용 권장: **bucket 은 private**. 모든 접근은 백엔드가 서명한 presigned URL 로만. 버킷 정책으로 anonymous read 켜는 방식 비권장.

- **Public-read 비추천 이유**: thumbnail 이 곧 PII (관제 영상 일부). 일정 시간짜리 presigned URL 로만 흘리는 게 맞음.

---

## 4. 백엔드 코드

### 4.1 의존성

```bash
pip install boto3 httpx pillow
# 또는: minio (=minio-py)
```

본 가이드는 boto3 사용 — `pia` 패키지의 `DataLakeManager` 와 SDK 컨벤션 동일하므로 재사용 친화적.

### 4.2 boto3 client 분리 (업로드용, 서명용)

presigned URL 의 hostname 은 **vLLM 컨테이너에서 도달 가능한 형태로 서명**되어야 함. 백엔드가 호스트에서 도는 경우, 업로드는 호스트 endpoint, 서명은 컨테이너 endpoint 로 분리.

```python
import boto3
from botocore.client import Config

_common = dict(
    aws_access_key_id="minioadmin",
    aws_secret_access_key="minioadmin",
    region_name="us-east-1",
    config=Config(signature_version="s3v4"),
)
upload_s3  = boto3.client("s3", endpoint_url="http://localhost:9100", **_common)
presign_s3 = boto3.client("s3", endpoint_url="http://pia-minio:9000", **_common)
```

> 백엔드도 같은 docker network 안 컨테이너로 도는 경우라면 두 개를 만들 필요 없이 `http://pia-minio:9000` 단일 endpoint 로 일치.

### 4.3 업로드 + presigned URL

```python
import uuid

def upload_thumbnail_and_get_url(jpeg_bytes: bytes,
                                  bucket: str = "pia-summary",
                                  expire: int = 600) -> str:
    key = f"thumbnails/{uuid.uuid4().hex}.jpg"
    upload_s3.put_object(Bucket=bucket, Key=key, Body=jpeg_bytes,
                         ContentType="image/jpeg")
    return presign_s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expire,
    )
```

### 4.4 build_chat_payload 결합

§A.3 코드 한 줄 그대로. 풀 흐름:

```python
import httpx
from prompts import build_chat_payload

# 1) build_chat_payload 가 만든 dict 를 시작점으로 (b64 자리는 빈값)
payload = build_chat_payload(
    thumbnail_b64="",                      # 자리 채움. 다음 줄에서 덮어씀
    event_metadata=event_metadata,
    model="Qwen/Qwen3.5-0.8B",
    max_tokens=96,
)

# 2) 이미지 부분만 presigned URL 로 교체 — OpenAI 스펙 그대로, 값만 다름
payload["messages"][0]["content"][0]["image_url"]["url"] = presigned_url

# 3) 호출
r = httpx.post("http://localhost:8000/v1/chat/completions",
               json=payload, timeout=120)
r.raise_for_status()
summary = r.json()["choices"][0]["message"]["content"].strip()
```

> pia_summary 패키지(`prompts.py`, `docker-compose.yml`, `.env.example`, `tests/`) 본체에 어떤 변경도 요구하지 않음. 환경별 검증은 `RESULTS.md` 참고.

> 호출 ergonomics 개선이 필요하면 별도 작업으로 `prompts.py` 에 `thumbnail_url=` 인자 추가해 한 줄 호출로 정리 가능. 동작/안정성/성능 차이 없으며, 도입 시점은 별개 결정.

---

## 5. 환경변수

`.env` 컨벤션은 다른 모듈(`pe_vle_2stage_async/validation_server/.env` 등) 과 동일 prefix 권장.

```bash
# === MinIO / S3 (pia_summary URL 모드용) ===
SUMMARY_S3_ENDPOINT_HOST=http://localhost:9100
SUMMARY_S3_ENDPOINT_INTERNAL=http://pia-minio:9000
SUMMARY_S3_ACCESS_KEY=minioadmin
SUMMARY_S3_SECRET_KEY=minioadmin
SUMMARY_S3_BUCKET=pia-summary
SUMMARY_S3_REGION=us-east-1
SUMMARY_S3_PRESIGN_EXPIRE_SEC=600
```

분리 이유:

- `*_HOST` — 백엔드가 호스트에서 도는 경우의 업로드/관리용 endpoint
- `*_INTERNAL` — vLLM 이 fetch 할 때 사용할 도메인. presigned URL 서명 시 이 endpoint 로 client 생성.

백엔드도 컨테이너 안에서 도는 환경(예: backend 가 같은 docker network) 이면 둘 다 같은 값.

---

## 6. 운영 시 고려사항

| 항목 | 권장 |
|---|---|
| presigned URL 만료 시간 | 5~15분. vLLM 호출 평균 latency × 마진 (재시도 1~2회 커버). 너무 길면 외부 유출 시 권한 오남용. 너무 짧으면 vLLM 큐잉 중 만료. |
| Bucket lifecycle | 30일 후 자동 삭제 정책 설정. thumbnail 은 일회성 추론용이므로 장기 보관 불필요. |
| 동시성 부하 | 32 이상 동시 추론 필요 시 MinIO 단일 노드 → distributed 모드 또는 nginx caching proxy 검토. |
| 권한 분리 | 백엔드용 IAM 사용자에 `s3:PutObject`, `s3:GetObject` 만 부여. root credential 은 콘솔 관리에만 사용. |
| 모니터링 | MinIO `/minio/v2/metrics/cluster` Prometheus 엔드포인트 또는 `mc admin trace` 로 fetch 패턴 관찰. |
