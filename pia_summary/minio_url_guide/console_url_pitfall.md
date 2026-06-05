# MinIO 콘솔 URL → 객체 URL 변환 함정 (실 사례)

사내 MinIO 의 **콘솔 UI URL** 을 그대로 vLLM 에 보내면 400 발생. **객체 직접 접근 URL** 로 변환 필요.

운영팀이 MinIO 콘솔에서 "URL 복사" 했을 때 `:9001/browser/...` 형태가 자주 나오는데, vLLM 에 보내기 전 `:9000/<bucket>/<key>` 형태로 변환해야 함. presigned URL 사용 시 자동 회피됨.

---

## 사용한 URL

| 종류 | 값 |
|---|---|
| 콘솔 UI URL (처음 받아온 형태) | `http://172.168.47.99:9001/browser/thumbnail/20260508%2F1_yujeho23_1778218378609.jpg` |
| 객체 접근 URL (변환) | `http://172.168.47.99:9000/thumbnail/20260508/1_yujeho23_1778218378609.jpg` |

차이:
- 포트 `:9001` (콘솔) → `:9000` (S3 API)
- 경로 `/browser/<bucket>/<key>` → `/<bucket>/<key>` (`/browser` 제거)
- key 의 `%2F` 는 `/` 그대로 사용 (encoded 면 307 redirect)

---

## 실패 — 콘솔 URL 그대로 보냄

### 요청

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3.5-0.8B",
    "messages": [{
      "role": "user",
      "content": [
        {"type": "image_url", "image_url": {"url": "http://172.168.47.99:9001/browser/thumbnail/20260508%2F1_yujeho23_1778218378609.jpg"}},
        {"type": "text", "text": "Describe the image in one short English sentence."}
      ]
    }],
    "max_tokens": 96,
    "temperature": 0.0
  }'
```

### 응답

```
[HTTP 400] [0.15s]
{"error":{"message":"Failed to load image: cannot identify image file <_io.BytesIO object>","type":"BadRequestError","param":null,"code":400}}
```

원인: vLLM 이 URL fetch 는 됐지만 응답이 HTML/redirect (콘솔 UI 페이지) 라 이미지 디코딩 실패.

---

## 성공 — 객체 URL 로 변환 후 호출

### 요청

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3.5-0.8B",
    "messages": [{
      "role": "user",
      "content": [
        {"type": "image_url", "image_url": {"url": "http://172.168.47.99:9000/thumbnail/20260508/1_yujeho23_1778218378609.jpg"}},
        {"type": "text", "text": "Describe the image in one short English sentence."}
      ]
    }],
    "max_tokens": 96,
    "temperature": 0.0
  }'
```

### 응답

```
[HTTP 200] [0.26s]
A person is using a long stick to ignite a small fire on a box on the ground.
```

---

## 결과 요약

| 항목 | 콘솔 URL | 객체 URL |
|---|---|---|
| HTTP | **400** | **200** |
| latency | 0.15s | 0.26s |
| vLLM 메시지 | `cannot identify image file` | 정상 추론 |

검증 일시: 2026-05-08 (KST)
