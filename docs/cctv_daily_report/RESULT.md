# CCTV AI 탐지 일일 보고서 자동 생성 — 작업 결과

`feature_docs.md`에 명시된 1장 분량 HWPX 일일 보고서 자동 생성 파이프라인을
`src/cctv_daily_report/` 패키지로 구현했다. mock 이벤트 데이터에서 출발해 이미
가동 중인 vLLM 서버(`pia_summary`, `Qwen/Qwen3.5-0.8B`)에 VLM·LLM·번역 호출을
수행하고, `template.hwpx`를 베이스로 결과 보고서를 저장한다.

## 1. 모듈 구조

```
src/cctv_daily_report/
├── __init__.py        # public API: run_report
├── __main__.py        # python -m cctv_daily_report
├── cli.py             # argparse 진입점
├── config.py          # 서버 URL/모델/경로/타임아웃 (env 오버라이드)
├── mock_data.py       # feature_docs §4·§9 기반 18건 mock 이벤트 + ReportInfo
├── statistics.py      # 이벤트 리스트 → event_summary (§4 출력)
├── event_selector.py  # 주요 이벤트 선정 (§5 정책, 동일 CCTV 1건만)
├── images.py          # pia_summary/tests/sample.jpg → base64 (대표 프레임 fallback)
├── vllm_client.py     # /v1/chat/completions 단일 호출 지점 (재시도 1회)
├── vlm.py             # 이벤트별 영문 visual_summary (build_chat_payload 재사용)
├── summarizer.py      # 영문 4종 보고 문장 + rule-based fallback
├── translator.py      # 영문 보고 문장 → 한국어 (JSON 라운드트립)
├── renderer.py        # template.hwpx paragraph 인덱스 치환 + 저장
└── pipeline.py        # run_report — 전체 흐름 오케스트레이션
```

## 2. 데이터 흐름

```
mock 이벤트 18건 ┬─ statistics.aggregate ─────► event_summary
                └─ event_selector.pick_main ── main_events (≤3)
                                                │
                                                ▼
                      vlm.summarize_event (사진 + 메타 → 영문 1문장)
                                                │
                                                ▼
                summarizer.generate_en_block (영문 4종 보고 문장)
                                                │
                                                ▼
                       translator.to_korean (한국어 4종)
                                                │
                                                ▼
              renderer.render(template.hwpx + 데이터)
                                                │
                                                ▼
                 outputs/CCTV_AI_Daily_Report_YYYYMMDD.hwpx
```

## 3. 환경 셋업

이미 conda env `python-hwpx`를 만들어두었다 (Python 3.11 + Maven + OpenJDK 17).
새로 필요한 의존성은 `httpx`만 추가했다.

```bash
conda activate python-hwpx
pip install httpx          # 최초 1회
```

`python-hwpx` 패키지는 editable install 상태(`pip install -e ".[dev]"`).

## 4. vLLM 서버 사전 확인

```bash
curl -s http://localhost:8000/v1/models | python -c "import sys, json; print(json.load(sys.stdin)['data'][0]['id'])"
# 기대 출력: Qwen/Qwen3.5-0.8B
```

`docker compose -f pia_summary/docker-compose.yml ps`로 컨테이너 상태도 확인 가능.

## 5. 실행 방법

```bash
cd /home/gpuadmin/Repo/seoik/python-hwpx
conda activate python-hwpx

# 일반 실행 (실제 vLLM 호출)
PYTHONPATH=src python -m cctv_daily_report.cli \
    --report-date 2026-05-11 \
    --output outputs

# 디버그용: VLM/LLM 호출 생략 (rule-based fallback만 사용)
PYTHONPATH=src python -m cctv_daily_report.cli \
    --report-date 2026-05-11 --output outputs --skip-vlm --skip-llm
```

산출물: `outputs/CCTV_AI_Daily_Report_20260511.hwpx` (약 37 KB).

검증:

```bash
hwpx-validate-package outputs/CCTV_AI_Daily_Report_20260511.hwpx
python -c "from hwpx import HwpxDocument; print(HwpxDocument.open('outputs/CCTV_AI_Daily_Report_20260511.hwpx').export_text())"
```

`Package validation passed with warnings.` 가 나오면 정상(워닝은 템플릿
manifest의 version 파트 누락 알림이며 실제 열람에는 영향 없음).

## 6. 환경 변수

전부 선택적. 기본값은 `config.py` 참고.

| 변수 | 기본값 | 용도 |
|---|---|---|
| `VLLM_BASE_URL` | `http://localhost:8000` | vLLM endpoint |
| `VLLM_MODEL` | `Qwen/Qwen3.5-0.8B` | 호출 모델 (vLLM이 띄운 이름과 일치해야 함) |
| `VLLM_TIMEOUT` | `120` | HTTP 타임아웃(초) |
| `CCTV_REPORT_TEMPLATE` | `<project>/template.hwpx` | 베이스 템플릿 경로 |
| `CCTV_REPORT_OUTPUT_DIR` | `<project>/outputs` | 출력 디렉토리 |
| `CCTV_REPORT_MAX_MAIN_EVENTS` | `3` | 1장 보고서에 들어갈 최대 이벤트 |
| `CCTV_REPORT_MAX_TOKENS_VLM` | `96` | VLM 호출 토큰 상한 |
| `CCTV_REPORT_MAX_TOKENS_LLM` | `512` | 영문 요약 호출 토큰 상한 |

## 7. 언어 처리 결정

vLLM 서버(`pia_summary`)는 README에 "영어 단일 출력" 사양으로 못박혀 있다.
이를 존중하기 위해 파이프라인을 다음 순서로 구성했다.

1. VLM: pia_summary의 `prompts.build_chat_payload`를 그대로 import해서
   영문 한 문장 visual_summary를 받는다. **prompts.py는 손대지 않는다.**
2. LLM 요약: 동일 서버에 텍스트 전용으로 호출, 영문 4종 보고 문장을 JSON으로 받는다.
3. 번역기: 같은 서버에 다시 텍스트 호출, "영문 → 한국어 공공기관 보고서 문체"
   프롬프트로 한국어 JSON을 받는다.

0.8B 모델은 한국어 생성 품질이 보장되지 않으므로 각 단계에 다음 fallback이 있다.

- VLM 호출 실패 → `visual_summary = "Visual analysis unavailable."`,
  `visual_verification = "unclear"` (feature_docs §17 준수)
- LLM 응답이 JSON 파싱 실패 → `summarizer._rule_based_fallback`이 영문
  통계 기반 문장 생성
- 번역기 응답이 JSON 파싱 실패 → 영문 원문을 그대로 보고서에 삽입(경고 로그)

## 8. template.hwpx 매핑

`template.hwpx`의 placeholder paragraph 인덱스를 분석해서 다음과 같이 1:1 치환한다.
구조 변경 없음(표 신규 삽입 없음, paragraph 추가 없음).

| paragraph idx | 원본 텍스트 | 치환 후 |
|---|---|---|
| 13 | "2000. 00. 00      " | 보고 일자 |
| 23 | "기관명" | 관제센터명 |
| 24 | "[ 부서명 ]" | "[ AI 관제팀 ]" |
| 30 | "추진배경" | "1. 기본 정보" |
| 31~33 | "내용을 입력하세요" x 3 | 보고 일자/생성 일시/시간 범위/CCTV 수 |
| 34 | "추진배경" | "2. 일일 탐지 현황" |
| 35 | "내용을 입력하세요" | 통계 한 줄 (전체/확정/확인 필요/오탐 + 유형별) |
| 36 | "추진배경" | "3. 주요 탐지 이벤트" |
| 37 | "내용을 입력하세요" | 이벤트 1~3건 한 줄 요약 |
| 38 | "추진배경" | "4. 금일 관제 요약" |
| 39 | "내용을 입력하세요" | `daily_summary` (한국어) |
| 41 | "내용을 입력하세요" | `main_event_description` (한국어) |
| 43 | "내용을 입력하세요" | VLM 영문 visual_summary 합본(`[CAM-XX] ...`) |
| 44 | "추진배경" | "5. 특이사항 및 확인 필요 사항" |
| 45 | "내용을 입력하세요" | `special_note` + `review_note` |

## 9. 실측 결과 (`2026-05-11` 기준)

- mock 이벤트: 18건 (화재 1 / 연기 4 / 쓰러짐 13 / 기타 0)
- 선정된 주요 이벤트 3건: CAM-12 화재(확정·0.87), CAM-05 연기(확정·0.78),
  CAM-14 쓰러짐(확정·0.88)
- VLM 영문 1문장 응답: 정상 (예: `A fire alarm triggered on camera "후문 주차장"
  (CAM-12) at 03:11:42, indicating a fire event in the parking lot zone.`)
- LLM 영문 4종 응답: 정상 JSON 파싱
- 한국어 번역: 정상 JSON 파싱 (단어 선택은 0.8B 한계로 다소 어색)
- 산출 파일 크기: 36,870 bytes
- `hwpx-validate-package`: 통과(warnings)
- `python-hwpx`로 열람 정상

## 10. 실제 운영 환경 전환 시 변경 포인트

| 영역 | 변경 위치 | 변경 내용 |
|---|---|---|
| 실제 이벤트 데이터 | `mock_data.py` | DB·이벤트 로그 조회 함수로 교체. `CctvEvent`/`ReportInfo` dataclass는 그대로 사용 가능 |
| 실제 대표 프레임 | `images.py` | `dummy_jpeg_b64`를 MinIO/스토리지에서 JPEG를 가져오도록 교체 |
| 다른 vLLM 모델 | env `VLLM_MODEL` | 한국어 품질이 더 좋은 모델 사용 시 `translator.py` 프롬프트 단순화 가능 |
| 한국어 직접 출력 모델 | `summarizer.py`, `translator.py` | LLM이 직접 한국어로 출력하면 translator 단계 제거 |
| 표 형태 출력 | `renderer.py` | feature_docs §15의 표 구조가 필요하면 `doc.add_table()` 활용 |

## 11. 비-목표

- `pia_summary/prompts.py` 수정 (영어 단일 가이드 존중)
- 실제 DB·MinIO·이벤트 큐 연동 (mock 대체)
- HWPX 표 신규 삽입 (template 표는 유지, 텍스트만 교체)
- pyproject.toml에 `cctv_daily_report` 패키지 등록 (사용자 의도상 분리 유지 — `PYTHONPATH=src`로 실행)
- 비동기/배치 처리 (단발 호출 전제)

## 12. 산출물 일람

- `PLAN.md` — 작업 시작 전 승인된 계획 문서 (`/home/gpuadmin/.claude/plans/hwpx-glimmering-clarke.md`의 사본)
- `src/cctv_daily_report/` — 본 모듈
- `templates/report_template_blank.hwpx` — 렌더링 베이스(빈 양식)
- `templates/report_template_filled.hwpx` — 채워진 완성 예시
- `outputs/CCTV_AI_Daily_Report_20260511.hwpx` — 실제 vLLM 호출로 생성된 한국어 1장 보고서
- `RESULT.md` — 본 문서
