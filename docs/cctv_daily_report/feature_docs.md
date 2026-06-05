# HWPX 기반 CCTV AI 탐지 일일 보고서 자동 생성 상세 기능

## 1. 상세 기능 개요

본 기능은 CCTV 관제 시스템에서 발생한 AI 탐지 이벤트 데이터를 기반으로, **1장 분량의 HWPX 일일 보고서**를 자동 생성하는 기능.

보고서 내 날짜, CCTV 수, 이벤트 건수, 이벤트 목록 등 정형 데이터는 시스템 집계값을 기반으로 자동 입력한다.

LLM/VLM은 전체 보고서를 자유 생성하는 용도가 아니라, **주요 이벤트 상황 설명, 일일 관제 요약, 특이사항 정리**와 같이 자연어 작성이 필요한 영역에만 사용한다.

---

## 2. 주요 기능 구성

```
1. 일일 보고 데이터 수집
2. 이벤트 통계 집계
3. 주요 이벤트 선정
4. VLM 기반 이벤트 상황 요약
5. LLM 기반 관제 요약 생성
6. HWPX 템플릿 렌더링
7. 보고서 파일 저장 및 다운로드
```

---

## 3. 일일 보고 데이터 수집

보고 대상 날짜를 기준으로 해당 일자의 CCTV 탐지 데이터, 알림 이력, 이벤트 클립 정보를 수집한다.

수집 대상 정보:

```
- 보고 일자
- 관제센터명
- 전체 CCTV 수
- 분석 대상 CCTV 수
- 이벤트 발생 시간
- CCTV ID / CCTV 명칭
- 이벤트 유형
  - 화재
  - 연기
  - 쓰러짐
  - 기타
- 탐지 신뢰도
- 알람 확정 여부
- 처리 상태
- 이벤트 클립 경로
- 이벤트 대표 프레임 경로
```

이 단계에서는 LLM/VLM을 사용하지 않고, DB 및 이벤트 로그 기반으로 처리한다.

---

## 4. 이벤트 통계 집계

수집된 이벤트 데이터를 기반으로 일일 보고서에 필요한 통계 값을 집계한다.

집계 항목:

```
- 전체 탐지 알림 수
- 최종 알람 확정 수
- 확인 필요 이벤트 수
- 미확정 / 오탐 의심 수
- 이벤트 유형별 건수
  - 화재 건수
  - 연기 건수
  - 쓰러짐 건수
  - 기타 건수
- 이벤트 발생 CCTV 수
- 반복 발생 CCTV 목록
- 주요 발생 이벤트 유형
```

예시:

```json
{
  "total_event_count": 18,
  "confirmed_alarm_count": 5,
  "need_review_event_count": 3,
  "false_positive_count": 10,
  "event_counts": {
    "fire": 1,
    "smoke": 4,
    "falldown": 13,
    "etc": 0
  },
  "top_event_category": "falldown",
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

---

## 5. 주요 이벤트 선정

1장 보고서에 모든 이벤트를 표시하지 않고, 보고서에 포함할 주요 이벤트만 선별한다.

선정 기준:

```
1. 최종 알람 확정 이벤트 우선
2. 확인 필요 이벤트 우선
3. 신뢰도 높은 이벤트 우선
4. 화재 > 연기 > 쓰러짐 순으로 중요도 반영 가능
5. 동일 CCTV에서 반복 발생한 이벤트는 대표 이벤트만 표시
6. 최대 3건 또는 설정값 기준으로 제한
```

기본 권장값은 **최대 3건**.

1장 보고서 기준에서는 3건 이상 표시할 경우 문서가 과밀해질 수 있음.

---

## 6. VLM 기반 이벤트 상황 요약

VLM은 주요 이벤트의 대표 프레임 또는 클립을 기반으로, 보고서에 들어갈 **짧은 상황 설명**을 생성한다.

VLM 사용 목적:

```
- 주요 이벤트 대표 프레임 기반 화면 상황 요약
- 탐지 이벤트 유형과 화면 내용의 간단한 정합성 확인
- 보고서용 1문장 이벤트 설명 생성
```

VLM은 보고서 전체를 작성하지 않고, **이벤트별 시각 정보 요약**만 담당한다.

예시:

```
입력:
- 이벤트 유형: 쓰러짐
- CCTV ID: CAM-03
- 대표 프레임 이미지

출력:
화면 중앙 인근에서 사람으로 추정되는 객체가 바닥에 쓰러진 상태로 확인됨.
```

---

## 7. LLM 기반 관제 요약 생성

LLM은 시스템 통계값과 VLM 결과를 입력받아, 보고서에 들어갈 자연어 문장을 생성한다.

LLM 사용 목적:

```
- 금일 관제 요약 생성
- 주요 이벤트 설명 정리
- 특이사항 정리
- 확인 필요 사항 생성
```

LLM은 수치나 이벤트 목록을 새로 생성하지 않고, 백엔드에서 집계한 데이터를 기반으로 문장화만 수행한다.

예시:

```
금일 CCTV AI 탐지 결과, 총 18건의 탐지 알림이 발생하였고 이 중 5건이 최종 알람으로 확정됨. 이벤트 유형 중 쓰러짐이 13건으로 가장 높은 비중을 차지함.
```

---

## 8. 전체 처리 흐름

```
이벤트 데이터 조회
↓
통계 집계
↓
주요 이벤트 선정
↓
주요 이벤트 대표 프레임 추출
↓
VLM 요청
↓
VLM 이벤트 상황 요약 수신
↓
LLM 요청
↓
LLM 관제 요약 / 특이사항 수신
↓
HWPX 템플릿 데이터 삽입
↓
HWPX 보고서 생성
```

---

## 9. VLM 입력 구조

VLM에는 주요 이벤트 단위로 요청한다.

```json
{
  "event_id": "EVT-20260511-0001",
  "report_date": "2026-05-11",
  "camera_id": "CAM-03",
  "camera_name": "본관 출입구",
  "event_time": "2026-05-11 14:23:10",
  "event_category": "falldown",
  "confidence": 0.91,
  "image": {
    "encoding": "base64",
    "mime_type": "image/jpeg",
    "data": "{base64_image}"
  },
  "instruction": "해당 프레임에서 탐지 이벤트와 관련된 화면 상황을 보고서 문체로 1문장 요약"
}
```

---

## 10. VLM 프롬프트 템플릿

```
다음 이미지는 CCTV AI 탐지 이벤트의 대표 프레임입니다.

이벤트 정보:
- 이벤트 유형: {event_category}
- CCTV ID: {camera_id}
- CCTV 명칭: {camera_name}
- 발생 시간: {event_time}

작성 조건:
- 화면에서 확인 가능한 내용만 작성
- 추측성 표현 사용 금지
- 공공기관 보고서에 들어갈 수 있는 문장으로 작성
- 1문장으로 작성
- 이벤트 유형과 직접 관련된 내용만 작성
- 확실하지 않은 경우 "대표 프레임만으로 명확한 상황 확인은 어려움"으로 작성

출력 형식:
{
  "event_id": "{event_id}",
  "visual_summary": "...",
  "visual_verification": "confirmed | unclear | mismatch"
}
```

---

## 11. VLM 출력 구조

```json
{
  "event_id": "EVT-20260511-0001",
  "visual_summary": "화면 중앙 인근에서 사람으로 추정되는 객체가 바닥에 쓰러진 상태로 확인됨.",
  "visual_verification": "confirmed"
}
```

`visual_verification` 기준:

```
confirmed : 대표 프레임 기준 이벤트 상황 확인
unclear   : 대표 프레임만으로 명확한 판단 어려움
mismatch  : 이벤트 유형과 화면 내용 불일치 가능성
```

---

## 12. LLM 입력 구조

LLM에는 VLM 결과를 포함한 보고서 생성용 요약 데이터를 전달한다.

```json
{
  "report_info": {
    "report_date": "2026-05-11",
    "center_name": "○○시 CCTV 통합관제센터",
    "start_time": "2026-05-11 00:00:00",
    "end_time": "2026-05-11 23:59:59",
    "generated_at": "2026-05-12 09:00:00"
  },
  "camera_info": {
    "total_cctv_count": 120,
    "analyzed_cctv_count": 80
  },
  "event_summary": {
    "total_event_count": 18,
    "confirmed_alarm_count": 5,
    "need_review_event_count": 3,
    "false_positive_count": 10,
    "event_counts": {
      "fire": 1,
      "smoke": 4,
      "falldown": 13,
      "etc": 0
    },
    "main_event_category": "falldown"
  },
  "main_events": [
    {
      "event_id": "EVT-20260511-0001",
      "time": "2026-05-11 14:23:10",
      "camera_id": "CAM-03",
      "camera_name": "본관 출입구",
      "category": "falldown",
      "confidence": 0.91,
      "status": "need_review",
      "clip_url": "clips/EVT-20260511-0001.mp4",
      "visual_summary": "화면 중앙 인근에서 사람으로 추정되는 객체가 바닥에 쓰러진 상태로 확인됨.",
      "visual_verification": "confirmed"
    }
  ],
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

---

## 13. LLM 프롬프트 템플릿

```
다음 입력 데이터를 기반으로 CCTV AI 탐지 일일 보고서에 삽입할 자연어 문장을 작성하세요.

작성 대상:
1. 금일 관제 요약
2. 주요 이벤트 설명
3. 특이사항 및 확인 필요 사항

작성 조건:
- 공공기관 보고서 문체로 작성
- 제공된 데이터 외의 내용은 임의로 생성하지 않음
- 수치, CCTV ID, 이벤트 유형, 발생 시간은 입력값을 그대로 사용
- 날짜, CCTV 수, 이벤트 수 등 정형 항목은 다시 작성하지 않음
- 각 항목은 1~3문장 이내로 간결하게 작성
- 이벤트가 없으면 "금일 탐지 이벤트는 발생하지 않음"으로 작성
- 특이사항이 없으면 "특이사항 없음"으로 작성
- VLM visual_verification이 unclear인 경우 "대표 프레임 기준 추가 확인이 필요함"으로 표현
- VLM visual_verification이 mismatch인 경우 "탐지 결과와 대표 프레임 간 정합성 확인이 필요함"으로 표현

입력 데이터:
{input_json}

출력은 반드시 아래 JSON 형식으로 작성하세요.

{
  "daily_summary": "...",
  "main_event_description": "...",
  "special_note": "...",
  "review_note": "..."
}
```

---

## 14. LLM 출력 구조

```json
{
  "daily_summary": "금일 CCTV AI 탐지 결과, 총 18건의 탐지 알림이 발생하였고 이 중 5건이 최종 알람으로 확정됨. 이벤트 유형 중 쓰러짐이 13건으로 가장 높은 비중을 차지함.",
  "main_event_description": "주요 이벤트는 CAM-03 본관 출입구에서 발생한 쓰러짐 이벤트이며, 대표 프레임 기준 사람으로 추정되는 객체가 바닥에 쓰러진 상태로 확인됨.",
  "special_note": "CAM-08 1층 로비에서 쓰러짐 이벤트가 반복 발생하여 카메라 설치 각도, ROI 설정 또는 현장 환경에 대한 추가 확인이 필요함.",
  "review_note": "확인 필요 이벤트 3건에 대해 담당자 검토가 필요함."
}
```

---

## 15. HWPX 보고서 템플릿 구조

```
CCTV AI 탐지 일일 보고서

1. 기본 정보

보고 일자          : {report_date}
관제센터명        : {center_name}
보고 대상 시간    : {start_time} ~ {end_time}
전체 CCTV 수      : {total_cctv_count}대
분석 대상 CCTV 수 : {analyzed_cctv_count}대
보고서 생성 일시  : {generated_at}

2. 일일 탐지 현황

전체 탐지 알림 수      : {total_event_count}건
최종 알람 확정 수      : {confirmed_alarm_count}건
확인 필요 이벤트 수    : {need_review_event_count}건
미확정 / 오탐 의심 수  : {false_positive_count}건

이벤트 유형별 발생 건수
- 화재   : {fire_count}건
- 연기   : {smoke_count}건
- 쓰러짐 : {falldown_count}건
- 기타   : {etc_count}건

3. 주요 탐지 이벤트

| 순번 | 발생 시간 | CCTV | 이벤트 유형 | 처리 상태 | 이벤트 클립 |
|------|-----------|------|-------------|-----------|-------------|
| 1 | {event_1_time} | {event_1_camera} | {event_1_category} | {event_1_status} | {event_1_clip} |
| 2 | {event_2_time} | {event_2_camera} | {event_2_category} | {event_2_status} | {event_2_clip} |
| 3 | {event_3_time} | {event_3_camera} | {event_3_category} | {event_3_status} | {event_3_clip} |

4. 금일 관제 요약

{daily_summary}

5. 주요 이벤트 설명

{main_event_description}

6. 특이사항 및 확인 필요 사항

{special_note}

{review_note}

담당자 확인 : ____________________
```

---

## 16. 보고서 생성 API 예시

```
POST /api/reports/cctv-daily
Content-Type: application/json
```

요청:

```json
{
  "report_date": "2026-05-11",
  "center_id": "CENTER-001",
  "output_format": "hwpx",
  "include_vlm_summary": true,
  "include_llm_summary": true,
  "max_main_events": 3
}
```

응답:

```json
{
  "status": "success",
  "report_id": "RPT-20260511-0001",
  "report_file_name": "CCTV_AI_Daily_Report_20260511.hwpx",
  "report_file_path": "/reports/2026/05/11/CCTV_AI_Daily_Report_20260511.hwpx",
  "generated_at": "2026-05-12 09:00:00"
}
```

---

## 17. 예외 처리 기준

### 이벤트가 없는 경우

```
- 전체 탐지 알림 수: 0건
- 주요 탐지 이벤트: 해당 없음
- 금일 관제 요약: 금일 탐지 이벤트는 발생하지 않음
- 특이사항: 특이사항 없음
```

### 대표 프레임이 없는 경우

```
- VLM 요청 생략
- visual_summary: 대표 프레임 정보 없음
- visual_verification: unclear
```

### VLM 요청 실패 시

```
- 보고서 생성은 계속 진행
- 주요 이벤트 설명: 영상 분석 정보 생성 실패
- 실패 로그 저장
```

### LLM 요청 실패 시

```
- rule-based 기본 문장으로 대체
- 예: 금일 총 {total_event_count}건의 탐지 알림 발생
- 실패 로그 저장
```

---

## 18. 핵심 구현 방향

```
정형 데이터 입력:
DB / 로그 / 이벤트 메타데이터 기반 rule-based 처리

이미지 기반 설명:
VLM이 주요 이벤트 대표 프레임을 보고 1문장 생성

보고서 자연어:
LLM이 통계 + VLM 결과를 기반으로 요약 문장 생성

문서 생성:
HWPX 템플릿에 rule-based 값과 LLM/VLM 결과를 삽입
```

요약 문구는 이렇게 쓰면 자연스러움.

> 정형 항목은 시스템 집계값을 기반으로 자동 입력하고, 자연어 작성이 필요한 관제 요약·주요 이벤트 설명·특이사항 항목은 LLM/VLM을 활용하여 생성한다. 최종 결과는 사전 정의된 HWPX 템플릿에 삽입하여 1장 분량의 일일 보고서로 출력한다.
>