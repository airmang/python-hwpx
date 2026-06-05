# CCTV AI 탐지 일일 보고서 HWPX 자동 생성 모듈

## Context

`feature_docs.md`에 명시된 "CCTV AI 탐지 일일 보고서" 파이프라인을 구현해야 한다.
정형 데이터(통계·이벤트 메타)를 mock으로 구성하고, 이미 가동 중인 vLLM 서버
(`pia_summary` 컨테이너, `Qwen/Qwen3.5-0.8B`, `http://localhost:8000`)를 사용해
이벤트 시각 요약과 보고서 자연어 문장을 생성한 뒤, `template.hwpx`를 베이스로
1장 분량의 HWPX 보고서를 출력한다.

서버는 README상 "영어 단일 출력" 사양이므로, **VLM/LLM 파이프라인 전체를 영어로 운영**
하고 동일 서버를 **번역기 LLM**으로 한 번 더 호출해 최종 한국어 문장을 얻는다.
0.8B 모델 한계에 대비해 각 단계에 rule-based fallback을 둔다.

기존 변환 파이프라인(이전 턴에서 만든 `template.hwp → template.hwpx`)이 산출한
`template.hwpx`가 이미 OPC 정합성 보정된 상태로 루트에 존재한다.

## 모듈 구조 (신규)

새 패키지: `src/cctv_daily_report/` (기존 `src/hwpx`와 분리, 같은 setuptools src layout 안에 공존).

```
src/cctv_daily_report/
├── __init__.py
├── config.py          # VLLM_URL, MODEL, 템플릿/출력 경로
├── mock_data.py       # feature_docs §4·§12 기반 mock 이벤트/통계 dataset
├── statistics.py      # 이벤트 리스트 → event_summary dict
├── event_selector.py  # 주요 이벤트 선정 (정책: §5)
├── images.py          # mock 대표 프레임 JPEG 생성 (PIL)·base64 인코딩
├── vllm_client.py     # /v1/chat/completions httpx 호출 1군데로 통일
├── vlm.py             # 이벤트별 영문 visual_summary (build_chat_payload 재사용)
├── summarizer.py      # 영문 4종 보고 문장 (daily/main_event/special/review)
├── translator.py      # 영문 보고 문장 → 한국어 (동일 서버 텍스트 전용 호출)
├── renderer.py        # template.hwpx에 데이터 주입·저장
├── pipeline.py        # 전 단계 오케스트레이션 (run_report(...))
└── cli.py             # python -m cctv_daily_report
```

- 새 패키지는 `src/` 아래로 들어가지만 pyproject 패키지 find가 `hwpx*`로 한정되어
  있으므로 자동 install 대상에 들어가지 않는다. 실행은 `PYTHONPATH=src python -m
  cctv_daily_report.cli` 또는 `pip install -e .` 후 `python src/cctv_daily_report/cli.py`.
  pyproject 수정은 하지 않는다 (사용자가 "따로 src 만들어서 구현"으로 분리 의도 표현).

## 데이터 흐름

```
mock_data ─┬─> statistics ─> event_summary
           └─> event_selector ─> main_events (≤3)
                                     │
                                     ├─ images.encode_dummy_jpeg(b64) ─┐
                                     │                                 ▼
                                     │                       vlm.summarize_event
                                     │                                 │
                                     ▼                                 ▼
                          report_payload (영문 입력, §12 형태) ────────┘
                                     │
                          summarizer.generate_en_block (4종 영문 문장)
                                     │
                          translator.to_korean (4종 한국어 문장)
                                     │
                          renderer.render(template.hwpx, 데이터)
                                     │
                                     ▼
                   outputs/CCTV_AI_Daily_Report_<YYYYMMDD>.hwpx
```

## 단계별 구현 상세

### 1. config.py

- `VLLM_BASE_URL = "http://localhost:8000"` (env override 허용)
- `VLLM_MODEL = "Qwen/Qwen3.5-0.8B"`
- `TEMPLATE_PATH`, `OUTPUT_DIR`, `TIMEOUT_SECONDS = 120`
- `MAX_MAIN_EVENTS = 3`

### 2. mock_data.py

feature_docs §4(이벤트 메타) + §12(전체 보고 입력)의 예시 JSON을 그대로 type-hint된
dataclass로 변환. 18건 이벤트 합성:
- 화재 1건, 연기 4건, 쓰러짐 13건, 기타 0건
- 5건 confirmed, 3건 need_review, 10건 false_positive
- 반복 카메라 CAM-08 (1층 로비, 쓰러짐 7건)
- 대표 이벤트 EVT-20260511-0001 (CAM-03 본관 출입구, 쓰러짐, 신뢰도 0.91)

### 3. statistics.py / event_selector.py

`statistics.aggregate(events) -> dict` — feature_docs §4 출력 형태 dict 그대로 생성.

`event_selector.pick_main(events, max_n=3)` — §5 정책:
1. confirmed > need_review > 기타 우선
2. 동률 시 신뢰도 내림차순
3. 카테고리 가중치: fire > smoke > falldown > etc
4. 동일 CCTV 반복은 대표 1건만

### 4. images.py

PIL이 dev deps에 없을 수 있으므로 **표준 라이브러리 zlib + 미리 만든 1x1 픽셀 JPEG
바이트** 상수 사용. 또는 `pia_summary/tests/sample.jpg`가 존재하면 그 파일 재사용.
함수: `dummy_jpeg_b64(event) -> str` (event_id를 시드로 결정적 출력).

### 5. vllm_client.py

`post_chat(messages: list, max_tokens=128, temperature=0.0) -> str`
- httpx로 `/v1/chat/completions` POST, 응답에서 `choices[0].message.content` 추출
- 재시도 1회 (429/503), 타임아웃·기타 예외는 호출자에게 `VllmError` 전파

### 6. vlm.py

`summarize_event(event) -> dict` — feature_docs §11 출력 구조 그대로 반환:
```python
{"event_id": ..., "visual_summary": <영문 1문장>, "visual_verification": "confirmed|unclear|mismatch"}
```
- `pia_summary.prompts.build_chat_payload`를 import해서 그대로 사용
- import 경로: `pia_summary`는 `src/`나 site-packages 아래가 아니므로 `sys.path`에
  `python-hwpx/` 루트를 추가해 import (config에서 처리). 또는 함수 본문을 모듈 내부에
  복사하지 않고 직접 prompt 문자열 한 줄로 인라인 구현. → **path 추가 방식** 채택 (의도
  존중).
- VLM 호출 실패 시: `visual_summary = "Visual analysis unavailable."`,
  `visual_verification = "unclear"` (feature_docs §17 예외 처리 기준).

### 7. summarizer.py

`generate_en_block(report_payload) -> dict` — feature_docs §13 프롬프트의 **영문판**
사용, §14 JSON 형식으로 4종 반환.
- 입력 JSON을 messages에 text로 직렬화
- 응답이 JSON 파싱 실패 시 rule-based fallback:
  ```
  daily_summary = f"A total of {total} events were detected today, of which {confirmed} were confirmed."
  main_event_description = "..."
  special_note = "No noteworthy issues." | f"Camera {cam} repeatedly triggered ..."
  review_note = f"{need_review} events require operator review." | "No review required."
  ```

### 8. translator.py

`to_korean(en_dict) -> dict` — 같은 vLLM 서버에 텍스트 전용 chat completion으로 호출,
프롬프트: "Translate the following English report sentences to formal Korean used in
public-sector reports. Output JSON with the same keys."
- JSON 파싱 실패 시: 영문을 그대로 반환 + 경고 로그 (보고서는 어떻게든 생성).

### 9. renderer.py

`render(template_path, output_path, render_data)` — `HwpxDocument.open` 후 다음을
**paragraph 단위 텍스트 교체**로 수행 (구조 변경 최소화):

| Template 영역 | 매핑 |
|---|---|
| "기관 홈페이지" → center_name |
| "제목" (3 곳 중 첫 곳) → "CCTV AI 탐지 일일 보고서" |
| "2000. 00. 00" → report_date |
| "기관명" → center_name |
| "[ 부서명 ]" → "AI 관제팀" |
| "OOO 사업 기본 계획 보고" 도형 → "CCTV AI 탐지 일일 보고서" |
| "(보고 취지 및 개요)" 글상자 → daily_summary 한국어 |
| "추진배경" 반복 4개 → "1. 기본 정보" / "2. 일일 탐지 현황" / "3. 주요 탐지 이벤트" / "4. 특이사항 및 확인 필요 사항" |
| 각 "내용을 입력하세요" → 위 항목 본문 텍스트 블록 |

구현 방법:
- `doc.sections[0].paragraphs`를 순회하며 정확한 텍스트 일치 시 `paragraph.text = new` 로 교체
- 같은 placeholder가 여러 번 등장하므로 `_iter_placeholders(doc)` 헬퍼가 출현 순서대로
  매칭 인덱스를 반환하고, 매핑은 (placeholder, occurrence_idx) → new_text 형태
- 통계 본문은 멀티라인 단일 paragraph 텍스트로 join ("- 화재: 1건\n- 연기: 4건 ..." 등;
  HWPX 단락은 줄바꿈 표현이 제한적이므로 paragraph.text는 한 줄로 두고 `add_paragraph`
  로 항목별 단락을 placeholder 위치 다음에 삽입한다 — `add_paragraph`는 문서 끝에만
  추가되므로 **세련된 다단락 삽입 대신 한 paragraph에 가독 가능한 줄로 압축**해서
  ", " 또는 " / "로 구분):
  ```
  "전체 18건 / 확정 5건 / 확인 필요 3건 / 오탐 의심 10건 · 유형별 — 화재 1, 연기 4, 쓰러짐 13, 기타 0"
  ```
- 주요 탐지 이벤트는 1~3 라인을 ` | ` 구분 텍스트로:
  ```
  "1) 14:23:10 · CAM-03 본관 출입구 · 쓰러짐 · 확인 필요 · clips/EVT-...mp4"
  ```
- 저장 시 `doc.save_to_path(output_path)`로 OPC 정합성 자동 보장.

활용 핵심 API:
- `HwpxDocument.open` / `.save_to_path` (src/hwpx/document.py:123)
- `paragraph.text = "..."` (Paragraph 객체의 단순 setter)
- `doc.export_text()` (디버그/검증용)

> 참고: README가 광고하는 `replace_text_in_runs`는 첫 매칭부터 순차 적용되어 중복 라벨
> 처리가 어렵다. 본 보고서는 "추진배경"이 4번 등장하므로 **paragraph 순회 + 인덱스**가
> 더 안전.

### 10. pipeline.py / cli.py

`run_report(report_date: str = "2026-05-11", output_dir: Path | None = None) -> Path`
- 위 단계 호출 + 진행 로그 (`print`)
- 반환: 생성된 hwpx 경로

CLI:
```
python -m cctv_daily_report --report-date 2026-05-11 --output outputs/
```

## 검증 (verification)

1. `conda activate python-hwpx`
2. vLLM 컨테이너 살아있는지 사전 확인:
   ```
   curl -s http://localhost:8000/v1/models | python -c "import sys, json; print(json.load(sys.stdin)['data'][0]['id'])"
   ```
3. 모듈 실행:
   ```
   PYTHONPATH=src python -m cctv_daily_report.cli --report-date 2026-05-11 --output outputs/
   ```
4. 결과 검증:
   ```
   hwpx-validate-package outputs/CCTV_AI_Daily_Report_20260511.hwpx
   python -c "from hwpx import HwpxDocument; print(HwpxDocument.open('outputs/CCTV_AI_Daily_Report_20260511.hwpx').export_text())"
   ```
5. 한컴오피스에서 직접 열어 깨짐 없는지(가능한 환경에서) 육안 확인.

## 산출물

- 신규 모듈: 위 파일들
- 보고서 파일: `outputs/CCTV_AI_Daily_Report_20260511.hwpx`
- `RESULT.md` (프로젝트 루트): 작업 요약, 모듈 구조 다이어그램, 실행 방법, 환경 변수,
  실패 시 fallback 동작, 향후 실제 데이터 연동 시 변경 포인트(`mock_data.py` 교체와
  `pia_summary` 외 모델 사용 시 `config.VLLM_MODEL` 변경) 명시.

## 비-목표

- `pia_summary/prompts.py` 변경 (영어 단일 가이드 준수)
- 실제 DB·MinIO·이벤트 큐 연동 (mock으로 대체)
- HWPX 표 구조 신규 삽입 (template 내 표는 그대로 두고 텍스트만 교체)
- pyproject.toml에 cctv_daily_report 패키지 등록 (사용자 의도상 "따로 src" 유지)
- 비동기/배치 처리 (단발 호출 전제)

## 위험 요소

- Qwen3.5-0.8B는 한국어 번역 품질이 보장되지 않음 → translator 단계에 JSON-파싱 실패
  fallback과 영문 원문 그대로 출력 옵션을 둠.
- VLM이 영문 단어 수 hint(max_words=40)를 종종 어김 → 보고서에 한 줄 이상 들어가도
  paragraph.text 가 줄바꿈 그대로 보존하므로 문제 없음 (다만 1장 분량을 넘기지 않게
  렌더러에서 80자 잘림 옵션 제공).
- template.hwpx의 placeholder가 같은 텍스트로 여러 번 등장 → occurrence 인덱스 기반
  매핑으로 처리.
