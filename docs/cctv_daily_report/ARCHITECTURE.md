# CCTV AI 탐지 일일 보고서 — 데이터 구조 및 작동 흐름

`src/cctv_daily_report/` 패키지의 입출력 schema, 현재(mock) 작동 흐름, 그리고
서비스 환경으로 전환할 때 필요한 컴포넌트 구성을 정리한 문서.

---

## 1. 단계별 입출력 데이터

### 1.1 CLI 입력

```bash
PYTHONPATH=src python -m cctv_daily_report.cli \
    --report-date 2026-05-12     # 보고 일자 (YYYY-MM-DD)
    --output outputs             # 출력 디렉토리
    [--skip-vlm] [--skip-llm]    # 디버그 플래그 (서버 호출 생략)
```

### 1.2 `mock_data.build_mock_dataset(report_date)` → `(ReportInfo, list[CctvEvent])`

**ReportInfo (1개)**
```python
ReportInfo(
    report_date="2026-05-12",
    center_name="○○시 CCTV 통합관제센터",
    start_time="2026-05-12 00:00:00",
    end_time="2026-05-12 23:59:59",
    generated_at="2026-05-12 23:59:59",
    total_cctv_count=120,
    analyzed_cctv_count=80,
)
```

**CctvEvent (18개)**
```python
CctvEvent(
    event_id="EVT-20260512-0001",
    report_date="2026-05-12",
    camera_id="CAM-03",
    camera_name="본관 출입구",
    event_time="2026-05-12 14:23:10",
    category="fire | smoke | falldown | etc",
    confidence=0.91,
    status="confirmed | need_review | false_positive",
    clip_url="clips/EVT-20260512-0001.mp4",
    frame_url="frames/EVT-20260512-0001.jpg",
)
```

### 1.3 `statistics.aggregate(events)` → event_summary dict

```json
{
  "total_event_count": 18,
  "confirmed_alarm_count": 5,
  "need_review_event_count": 3,
  "false_positive_count": 10,
  "event_counts": { "fire": 1, "smoke": 4, "falldown": 13, "etc": 0 },
  "main_event_category": "falldown",
  "repeated_cameras": [
    {
      "camera_id": "CAM-08",
      "camera_name": "1층 로비",
      "event_count": 7,
      "main_category": "falldown"
    }
  ]
}
```

### 1.4 `event_selector.pick_main(events, max_n=3)` → `list[CctvEvent]`

선정 정책:
1. `status` 우선순위: `confirmed` > `need_review` > `false_positive`
2. `category` 가중치: `fire` > `smoke` > `falldown` > `etc`
3. `confidence` 내림차순
4. 동일 CCTV에서 발생한 이벤트는 1건만 대표로 채택

### 1.5 `vlm.summarize_event(ev)` → dict

**HTTP 요청** — `POST http://localhost:8000/v1/chat/completions`
```json
{
  "model": "Qwen/Qwen3.5-0.8B",
  "messages": [{
    "role": "user",
    "content": [
      {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,…"}},
      {"type": "text", "text": "<pia_summary/prompts.py의 build_chat_payload 생성 프롬프트>"}
    ]
  }],
  "max_tokens": 96,
  "temperature": 0.0
}
```

**응답 파싱 후 반환**
```json
{
  "event_id": "EVT-20260512-0002",
  "visual_summary": "A fire alarm triggered on camera \"후문 주차장\" …",
  "visual_verification": "confirmed | unclear | mismatch"
}
```

호출 실패 시 fallback:
```json
{
  "event_id": "...",
  "visual_summary": "Visual analysis unavailable.",
  "visual_verification": "unclear"
}
```

### 1.6 `summarizer.generate_en_block(report_payload)` → 4종 영문 dict

**입력 (report_payload)**
```json
{
  "report_info": { ... },
  "camera_info": { "total_cctv_count": 120, "analyzed_cctv_count": 80 },
  "event_summary": { ... },
  "main_events": [
    {
      "event_id": "...",
      "time": "...",
      "camera_id": "...",
      "camera_name": "...",
      "category": "...",
      "confidence": 0.91,
      "status": "...",
      "clip_url": "...",
      "visual_summary": "...",
      "visual_verification": "..."
    }
  ],
  "repeated_cameras": [ ... ]
}
```

**출력 (영문 4종)**
```json
{
  "daily_summary": "Today's CCTV activity includes …",
  "main_event_description": "The main detected event is …",
  "special_note": "…",
  "review_note": "…"
}
```

LLM 응답이 JSON 파싱 실패 시 `_rule_based_fallback`이 동일 schema로 채움.

### 1.7 `translator.to_korean(en_block)` → 4종 한국어 dict

동일 schema, 값만 한국어. 번역 응답이 파싱 실패 시 영문 원문 그대로 반환.

### 1.8 `renderer.render(template, output_path, render_data)` → `Path`

**render_data**
```python
{
  "report_info": { ... },
  "camera_info": { ... },
  "event_summary": { ... },
  "main_events": [
    { ..., "visual_summary": "...", "visual_verification": "..." }
  ],
  "report_text_en": { 4종 영문 },
  "report_text_ko": { 4종 한국어 },
}
```

**산출물**: `outputs/CCTV_AI_Daily_Report_YYYYMMDD.hwpx`

처리 방식:
- `report_template.hwpx`를 base로 로드
- `paragraph` 인덱스 매핑(`paragraph_replacements`)으로 본문 단락 텍스트 교체
- 표/도형 안 텍스트는 `nested_replacements`로 매칭 후 교체
- `section.mark_dirty()` 호출하여 raw lxml 수정이 직렬화에 반영되도록 함
- 헤더 단락(`1. 기본 정보`, `2. 일일 탐지 현황`, `배경`, `5. 특이사항 …` 등)은 매핑에서 제외하여 그대로 유지

---

## 2. 현재 작동 흐름 (mock 모드)

```
┌──────────────────────────────────────────────────────────────────┐
│  CLI:  --report-date 2026-05-12  --output outputs                │
└────────────────────────┬─────────────────────────────────────────┘
                         ▼
        ┌──────────────────────────────────────┐
        │ [1] mock_data.build_mock_dataset()   │
        │     → ReportInfo + 18 × CctvEvent    │  (메모리 내 mock)
        └────────────────┬─────────────────────┘
                         ▼
        ┌──────────────────────────────────────┐
        │ [2] statistics.aggregate(events)     │
        │     → event_summary dict             │  (정형 집계)
        └────────────────┬─────────────────────┘
                         ▼
        ┌──────────────────────────────────────┐
        │ [3] event_selector.pick_main(...)    │
        │     → list[CctvEvent] (≤3)           │  (룰 기반 선정)
        └────────────────┬─────────────────────┘
                         ▼
        ┌──────────────────────────────────────┐
        │ [4] for ev in main_events:           │
        │       images.dummy_jpeg_b64(ev)      │
        │       └─► base64 JPEG                │
        │       vlm.summarize_event(ev)        │
        │       └─► HTTP POST /v1/chat/...     │──┐
        │     → visual_summary dict × 3        │  │
        └────────────────┬─────────────────────┘  │
                         ▼                         │
        ┌──────────────────────────────────────┐  │     ┌──────────────────┐
        │ [5] summarizer.generate_en_block()   │  ├────►│   pia_summary    │
        │     → 4종 영문 보고 문장 (JSON)       │──┤     │   (vLLM, Qwen)   │
        └────────────────┬─────────────────────┘  │     │   :8000          │
                         ▼                         │     └──────────────────┘
        ┌──────────────────────────────────────┐  │
        │ [6] translator.to_korean(...)        │──┘
        │     → 4종 한국어 보고 문장 (JSON)     │
        └────────────────┬─────────────────────┘
                         ▼
        ┌──────────────────────────────────────┐
        │ [7] renderer.render(                 │
        │       template=report_template.hwpx, │  (occurrence 기반
        │       data=render_data)              │   placeholder 치환)
        │     → outputs/...20260512.hwpx       │
        └──────────────────────────────────────┘
```

---

## 3. 서비스 환경 흐름

mock 입출력만 실제 인프라(DB/Object Storage/Message Queue/API/Scheduler)로
교체하면 동일한 코어 파이프라인이 그대로 동작한다.

```
                            ┌──────────────────────────────┐
                            │   CCTV 영상 수집·AI 추론      │
                            │   (Edge 또는 GPU 노드)        │
                            └──────────────┬───────────────┘
                                           ▼ 이벤트 발생 (Kafka)
            ┌────────────────────────────────────────────────────────┐
            │                Event Ingestion Layer                    │
            │  ┌──────────┐   ┌──────────────┐   ┌────────────────┐  │
            │  │  Kafka   │──▶│ Event Worker │──▶│   PostgreSQL    │  │
            │  │ (events) │   │  (consumer)  │   │  cctv_events    │  │
            │  └──────────┘   └──────┬───────┘   └────────────────┘  │
            │                        ▼                                │
            │                ┌───────────────┐                        │
            │                │     MinIO      │ 클립·대표 프레임 저장  │
            │                │  reports-bin   │                        │
            │                └───────────────┘                        │
            └────────────────────────────────────────────────────────┘
                                       │
       ┌──── (A) 정기 자동 ───┐         │         ┌──── (B) 온디맨드 ────┐
       │  cron / Airflow     │         │         │  사용자 → REST API   │
       │  매일 00:05         │         │         │  POST /reports/cctv  │
       └────────┬────────────┘         │         └────────┬────────────┘
                ▼                       ▼                  ▼
        ┌──────────────────────────────────────────────────────────┐
        │              Report Generation Service                    │
        │              (현재 cctv_daily_report 패키지)              │
        │                                                           │
        │  [1] DB Repository.fetch_events(date, center_id)         │
        │      → list[CctvEvent]   (mock_data 대체)                │
        │                                                           │
        │  [2] statistics.aggregate                                 │
        │  [3] event_selector.pick_main                             │
        │                                                           │
        │  [4] for ev in main_events (concurrent):                  │
        │      ObjectStore.fetch_frame(ev.frame_url) → JPEG bytes   │
        │      vlm.summarize_event ────────────────────────┐        │
        │                                                   │        │
        │  [5] summarizer.generate_en_block ───────────────┤        │
        │  [6] translator.to_korean ───────────────────────┤        │
        │  [7] renderer.render(template, render_data)      │        │
        │       → hwpx bytes                                │        │
        │                                                   │        │
        │  [8] ObjectStore.put("reports/2026/05/12/...hwpx")│        │
        │  [9] DB.insert into reports(...)                  │        │
        └────────────────────────────────────┬─────────────┼────────┘
                                              │             │
                                              ▼             ▼
                          ┌────────────────────┐   ┌────────────────────┐
                          │   PostgreSQL       │   │   vLLM Cluster     │
                          │   reports table    │   │  (pia_summary,     │
                          │  - report_id       │   │   2~N replica,     │
                          │  - file_path       │   │   load balanced)   │
                          │  - generated_at    │   └────────────────────┘
                          │  - status          │
                          └────────┬───────────┘
                                   ▼
              ┌─────────────────────────────────────────────┐
              │   사용자 / 관제 콘솔                          │
              │   GET /reports/{id}/download                 │
              │   ▼                                          │
              │   MinIO presigned URL → hwpx 다운로드        │
              └─────────────────────────────────────────────┘
```

### 트리거 두 가지

| 경로 | 트리거 | 동작 |
|---|---|---|
| (A) 정기 자동 | cron 또는 Airflow DAG (매일 00:05) | 전일자 보고서 자동 생성 → MinIO 적재 → DB record |
| (B) 온디맨드 | 사용자 API 호출 `POST /reports/cctv` | 요청한 날짜·관제센터에 대해 즉시 생성 후 응답에 download URL 포함 |

---

## 4. 서비스화 시 추가/변경 컴포넌트

| 계층 | 현재 (mock) | 서비스 환경 | 변경 위치 |
|---|---|---|---|
| 이벤트 데이터 | `mock_data.build_mock_dataset` | DB 조회 (`Repository.fetch_events(date, center_id)`) | `mock_data.py` → `repository.py`로 교체 |
| 대표 프레임 | `pia_summary/tests/sample.jpg` 재사용 | MinIO/S3 객체 fetch | `images.py` → `images.fetch_from_minio` |
| VLM/LLM 서버 | 단일 `localhost:8000` | 멀티 replica + LB (nginx, Envoy 등) | `config.VLLM_BASE_URL` 환경변수 |
| 동시성 | 직렬 호출 | `asyncio.gather` + `httpx.AsyncClient` | `vlm.py`, `vllm_client.py` 비동기 버전 |
| 트리거 | CLI 수동 | (A) cron/Airflow, (B) FastAPI 엔드포인트 | 신규 `api/` 패키지 |
| 결과 저장 | 로컬 `outputs/` | MinIO put + DB record | `pipeline.py` 후처리 단계 |
| 인증 | 없음 | JWT/OAuth, 다운로드 권한 검사 | API 게이트웨이 |
| 관측 | print 로그 | structlog + Prometheus + Sentry | `vllm_client.py`, `pipeline.py` |
| 실패 처리 | rule-based fallback | + dead-letter queue, 재시도 정책 | `vllm_client.py` 재시도 강화 |
| 보고서 보존 | 로컬 파일 | Object Storage + retention 정책 | `pipeline.py` 후처리 |

### 어댑터 교체 전략

핵심 인터페이스 `run_report(report_date, ...) → Path`는 그대로 두고
파이프라인 양 끝(데이터 입력·결과 출력)만 어댑터 패턴으로 갈아 끼우면
mock → 운영 전환이 깔끔하다.

```
[입력 어댑터]
  - MockRepository (현재)       ────► DBRepository (운영)
  - LocalSampleImages (현재)    ────► MinioImageFetcher (운영)

[코어 파이프라인]  (변경 없음)
  statistics → event_selector → vlm → summarizer → translator → renderer

[출력 어댑터]
  - LocalFileSaver (현재)       ────► MinioUploader + DbReportRecord (운영)
```

---

## 5. 관련 문서

- `PLAN.md` — 초기 설계 계획
- `RESULT.md` — 모듈 구현 결과·실행 방법·환경변수
- `feature_docs.md` — 비즈니스 요구사항 (보고서 구조·VLM/LLM 프롬프트 사양)
- `pia_summary/README.md` — vLLM 서버 호출 인터페이스
