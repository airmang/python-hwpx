# 실측 코퍼스 메트릭 (M9 Published Corpus)

`python-hwpx` 스택이 만든 산출물을 **실제 한컴오피스**(Windows COM + Mac GUI 오라클)로
전수 측정한 결과다. 아래 숫자는 전부 동결 코퍼스 위에서 기계 판정으로 산출되며,
릴리스마다 재측정해 이 페이지와 히스토리 파일에 추가된다.

```{note}
**지표 축 주석 (반드시 읽을 것).** 이 페이지의 숫자는 *생성물 수용률* 계열이다 —
"우리가 만든 HWPX를 실제 한컴이 열고/파싱하고/렌더하는가, 채움이 서식을 보존하는가,
개인정보가 새지 않는가". 문서 *파싱 recall*(남의 파일을 얼마나 잘 읽는가)과는 다른
축이므로, 파서 프로젝트의 수치와 병치 비교하면 안 된다.
```

## 최신 측정 (2026-07-19 · corpus v2 · N=497 produced + 9 negative controls)

측정 스택: python-hwpx 3.4.0 후보(코퍼스 측정 시점 소스) · 실한컴 12.0.0.3288
(Windows COM, 무인 scheduled task) · Mac 한컴 12.30 GUI(샘플 오라클).

| 축 | 결과 | 판정자 | 비고 |
|---|---|---|---|
| **오픈 수용률** | **476/476 = 100% all-pass** (하한 ≥99.4%, rule-of-three) | 실한컴 COM `Open()` | product-provenance 분모. 내부 픽스처 21건은 별도 발행(아래) |
| 파싱(내용 적재) | 458/476 = 96.2% | COM 텍스트 프로브 (redline 문서는 `InitScan/GetText` 42/42) | 비텍스트 문서(그림 전용 등)는 정의상 비파싱 집계 |
| 렌더 검증 | render_checked 416/476 | COM `SaveAs("PDF")` → 오프라인 fitz | +43 `render_unavailable` (한컴이 변경추적 문서의 PDF export 자체를 거부 — 실측 한계) · +17 unverified |
| 바이트 보존 | **497/497 = 100%** (미수정 part) | zip-part diff (오라클 불요) | patch 경로 한정 — 풀세이브는 명시적 out-of-claim |
| 양식 채움 차등 | pass 31/63 = 49.2% (wild 공개 양식 25종) | blank↔filled 실렌더 기하 비교 | **정직 실측**: short 15/22 · medium 12/22 · overflow-스트레스 7/22 (overflow 변종은 의도적 과적재). 검증된 특정 양식 대비 wild-base 강건성이 현재 잔여 과제 |
| 저작 품질 게이트 | 58/65 = 89.2% | 공문 구조 hard-gate + 품질 검사 (오라클 불요) | 실패 7건 전원이 **의도적 결문-생략 네거티브 변종** (게이트 판별력 증거) — 실저작 58/58 |
| PII 0-leak | **0 누출** (35문서 / 합성 개인정보 140값) | raw-grep 전 산출물 + MCP 추출 3표면 | 마스킹 default-on 경로 |
| 네이티브 목차 | 구조 15/15 · 실한컴 재계산 후 페이지 정합 5/5 | 구조 검사 + Mac 한컴 refresh→render 샘플 | refresh와 export는 세션 분리(한컴 크래시 회피 계약) |

**정직 버킷 규율**: 렌더 실패·미검증은 절대 pass로 집계하지 않는다. 변경추적 문서
43건의 `render_unavailable`은 한컴 자체의 제약을 그대로 발행한 것이다. 내부 진단
픽스처 21건(재생 프로브·스크립트 제작 마스터)은 정체 기준으로 태깅해 분리 발행한다
(10 open / 11 refuse — 제품 산출물 아님).

## 릴리스별 히스토리

기계 판독본: {download}`corpus-metrics-history.json <corpus-metrics-history.json>`.
오라클 열은 **실제 박스 런이 있었던 릴리스만** 채운다(추정 금지).

| 릴리스(측정 스택) | 일자 | N | 오픈 | 파싱 | 렌더 | 바이트 | PII |
|---|---|---|---|---|---|---|---|
| 3.4.0 후보 (corpus v2) | 2026-07-19 | 497 | **100%** (476/476) | 96.2% | 416 checked / 43 unavailable / 17 unverified | 100% | 0-leak |
| 2.29.x (corpus v1, FLOOR) | 2026-07-01 | 100 | 100% (100/100) | 95% | — (미공급) | — | — |

## 방법론 요약

- **코퍼스 동결**: manifest sha256·시드·도구 버전 기록, additive-only(v1 불변 가드).
  네거티브 컨트롤(손상 파일 등)이 먼저 판정되어 오라클 자체를 검증한다.
- **분모 규율**: judged-only, unverified 별도 버킷, rule-of-three 하한 병기,
  vacuous 측정 금지(PII는 PII-보유 스트라텀 위에서만).
- **재현**: `scripts/generate_openrate_corpus.py`(생성) →
  `scripts/hancom_open_rate.ps1`·`scripts/hancom_render_batch.ps1`(박스 무인 판정) →
  `scripts/corpus_open_rate.py` 외 축별 드라이버(집계). 전 과정 영수증(JSONL) 기반.
