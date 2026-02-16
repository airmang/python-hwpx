# HWPX Editor Feature Registry (v0.2)

이 문서는 `hwpx-editor` 기능을 코드 기반으로 관리하기 위한 1차 레지스트리입니다.
기준 소스는 현재 코드(`src/lib/store.ts`, `src/components/**/*`)입니다.

## Status 기준

- `DONE`: 핵심 액션 + UI 연결 확인
- `PARTIAL`: 동작은 있으나 제약/보완 필요
- `TODO`: UI/타입은 있으나 실제 액션 미구현 또는 연결 미완

## 코드 규칙

- 형식: `<DOMAIN>-<3자리번호>` (예: `TBL-001`)
- 기능 폴더: `features/<CODE>_<slug>/`
- 테스트 케이스 ID: `<CODE>-TC-<3자리번호>`

## 기능 목록 (2차)

| CODE | DOMAIN | 기능 | STATUS | 권장 서브폴더 |
|---|---|---|---|---|
| DOC-001 | 문서 | 새 문서 생성/초기화 | DONE | `features/DOC-001_new-document/` |
| DOC-002 | 문서 | HWPX 파일 열기 | DONE | `features/DOC-002_open-document/` |
| DOC-003 | 문서 | 저장/다른 이름 저장 | DONE | `features/DOC-003_save-document/` |
| DOC-004 | 문서 | Undo/Redo | DONE | `features/DOC-004_undo-redo/` |
| TXT-001 | 텍스트 | 문단 텍스트 편집 | DONE | `features/TXT-001_paragraph-edit/` |
| TXT-002 | 텍스트 | 문단 분할/이전 문단과 병합 | DONE | `features/TXT-002_split-merge-paragraph/` |
| TXT-003 | 텍스트 | 블록 삽입/삭제 | DONE | `features/TXT-003_insert-delete-block/` |
| TXT-004 | 텍스트 | 셀 텍스트 편집 | DONE | `features/TXT-004_table-cell-text/` |
| TXT-005 | 텍스트 | 탭 삽입/커서 텍스트 삽입 | DONE | `features/TXT-005_insert-tab-text/` |
| FMT-001 | 서식 | 굵게/기울임/밑줄/취소선 | DONE | `features/FMT-001_char-toggles/` |
| FMT-002 | 서식 | 글꼴/글자크기 변경 | DONE | `features/FMT-002_font-family-size/` |
| FMT-003 | 서식 | 글자색/강조색 변경 | DONE | `features/FMT-003_text-highlight-color/` |
| FMT-004 | 서식 | 문단 정렬 | DONE | `features/FMT-004_alignment/` |
| FMT-005 | 서식 | 줄간격 | DONE | `features/FMT-005_line-spacing/` |
| FMT-006 | 서식 | 들여쓰기(왼쪽/첫 줄) | DONE | `features/FMT-006_indent/` |
| FMT-007 | 서식 | 문단 번호/글머리표 계층 자동 정렬 | DONE | `features/FMT-007_list-hierarchy/` |
| FMT-008 | 서식 | 서식 복사(페인트): 글자/문단/표 옵션 | DONE | `features/FMT-008_format-painter/` |
| TBL-001 | 표 | 표 삽입 | DONE | `features/TBL-001_insert-table/` |
| TBL-002 | 표 | 표 레이아웃: 행/열 삽입 | DONE | `features/TBL-002_insert-row-col/` |
| TBL-003 | 표 | 표 레이아웃: 행/열 삭제 | DONE | `features/TBL-003_delete-row-col/` |
| TBL-004 | 표 | 셀 병합/분할 | DONE | `features/TBL-004_merge-split-cells/` |
| TBL-005 | 표 | 표 삭제 | DONE | `features/TBL-005_delete-table/` |
| TBL-006 | 표 | 표 너비/높이 수정 | DONE | `features/TBL-006_table-size/` |
| TBL-007 | 표 | 열 너비 드래그 조절 | DONE | `features/TBL-007_resize-column/` |
| TBL-008 | 표 | 표 안/밖 여백 수정 | DONE | `features/TBL-008_table-margins/` |
| TBL-009 | 표 | 페이지 경계 분할/제목줄 반복 | DONE | `features/TBL-009_page-break-repeat-header/` |
| TBL-010 | 표 | 셀 테두리/배경/세로정렬 | DONE | `features/TBL-010_cell-style/` |
| TBL-011 | 표 | 표 전체 테두리/배경 | DONE | `features/TBL-011_table-style/` |
| TBL-012 | 표 | 병합 후 표 구조 무결성(회귀 방지) | PARTIAL | `features/TBL-012_merge-integrity/` |
| TBL-013 | 표 | 표 편집 UX: 열/행 균등분배, 행/열 이동(비병합 표) | PARTIAL | `features/TBL-013_table-ux/` |
| TBL-014 | 표 | 셀 범위 선택(Shift+클릭) + 글꼴 변경(사이드바) + 저장/재열기 유지 | DONE | `features/TBL-014_cell-range-font/` |
| IMG-001 | 이미지 | 이미지 삽입 | DONE | `features/IMG-001_insert-image/` |
| IMG-002 | 이미지 | 이미지 크기 수정(입력/드래그) | DONE | `features/IMG-002_resize-image/` |
| IMG-003 | 이미지 | 이미지 바깥 여백 | DONE | `features/IMG-003_image-margins/` |
| IMG-004 | 이미지 | 선택 이미지 삭제(액션) | DONE | `features/IMG-004_delete-image-object/` |
| IMG-005 | 이미지 | 선택 이미지 삭제(Backspace/Delete 단축키) | DONE | `features/IMG-005_delete-image-shortcut/` |
| IMG-006 | 이미지 | 이미지 배치/속성 고급 설정(배치 기준/자르기/색조/투명도/보호) | DONE | `features/IMG-006_image-advanced-props/` |
| PAG-001 | 페이지 | 페이지 크기/여백/방향 | DONE | `features/PAG-001_page-setup/` |
| PAG-002 | 페이지 | 쪽 번호 매기기 | DONE | `features/PAG-002_page-numbering/` |
| PAG-003 | 페이지 | 단 나누기/쪽 나누기 | DONE | `features/PAG-003_column-page-break/` |
| PAG-004 | 페이지 | 각주/미주 삽입 | PARTIAL | `features/PAG-004_footnote-endnote/` |
| PAG-005 | 페이지 | 워터마크 텍스트 | PARTIAL | `features/PAG-005_watermark/` |
| PAG-006 | 페이지 | 다단(열 개수/간격) 레이아웃 설정 | DONE | `features/PAG-006_multi-column-layout/` |
| DIA-001 | 대화상자 | 글자 모양/문단 모양/글자표 | DONE | `features/DIA-001_format-char-para-charmap/` |
| DIA-002 | 대화상자 | 찾기/바꾸기 | DONE | `features/DIA-002_find-replace/` |
| DIA-003 | 대화상자 | 템플릿 관리 | DONE | `features/DIA-003_template-manager/` |
| DIA-004 | 대화상자 | 머리말/꼬리말 | DONE | `features/DIA-004_header-footer/` |
| DIA-005 | 대화상자 | 스타일/개요/목차 | DONE | `features/DIA-005_style-outline-toc/` |
| DIA-006 | 대화상자 | 자동 고침 | DONE | `features/DIA-006_auto-correct/` |
| DIA-007 | 대화상자 | 도형 삽입 | PARTIAL | `features/DIA-007_shape-insert/` |
| DIA-008 | 대화상자 | 글자 수 세기 | DONE | `features/DIA-008_word-count/` |
| DIA-009 | 대화상자 | 클립보드 히스토리/스니펫 | DONE | `features/DIA-009_clipboard-snippets/` |
| DIA-010 | 대화상자 | 캡션 삽입 + 그림/표 목차 생성 | PARTIAL | `features/DIA-010_captions-lists/` |
| SYS-001 | 시스템 | 사이드바 토글/탭 전환 | DONE | `features/SYS-001_sidebar-state/` |
| SYS-002 | 시스템 | 선택 상태(문단/셀/표) 관리 | DONE | `features/SYS-002_selection-state/` |
| SYS-003 | 시스템 | 스마트 선택(단어/문장/문단) | DONE | `features/SYS-003_smart-selection/` |

## 요청 반영 매핑 (상세)

| 요청 항목 | 연결 CODE | 현재 상태 | 메모 |
|---|---|---|---|
| 표 상/하/좌/우 여백 조절 | `TBL-008` | DONE | 표 안/밖 여백 모두 지원 |
| 표/셀 선 두께 조절 | `TBL-010`, `TBL-011` | DONE | side 단위 지정 가능 |
| 선 종류(예: dashed, none/empty) | `TBL-010`, `TBL-011` | DONE | `NONE`, `DASH`, `DOT`, `DASH_DOT`, `DOUBLE_SLIM` |
| 선 색상 조절 | `TBL-010`, `TBL-011` | DONE | 테이블 전체/셀 단위 지원 |
| 칸 내부 배경색 채우기 | `TBL-010` | DONE | 셀 배경색 설정 |
| 표 전체 배경색 채우기 | `TBL-011` | DONE | 전체 셀 일괄 적용 방식 |
| 병합 시 구조 뭉개짐 방지 | `TBL-004`, `TBL-012` | PARTIAL | 병합/분할 동작은 있으나 editor 회귀 테스트 보강 필요 |
| 글자 색/italic/bold/underline/취소선 | `FMT-001`, `FMT-003` | DONE | 단축키/툴바/사이드바 연동 |
| 왼쪽 마진/둘째 줄부터 마진(내어쓰기) | `FMT-006` | DONE | left indent + first-line indent |
| 번호/글머리표 계층 자동 정렬 | `FMT-007` | DONE | 번호/개요 레벨 및 들여쓰기 연동 구현 |
| 페이지 마진 | `PAG-001` | DONE | 상하좌우/머리말/꼬리말/제본 여백 |
| 열(다단) | `PAG-003`, `PAG-006` | DONE | 단 나누기 + 열 개수/간격 설정 지원 |

## 테스트 우선순위(추천)

- P0: `DOC-001~004`, `TXT-001~004`, `TBL-001~007`, `IMG-001`, `PAG-001~003`
- P1: `FMT-001~006`, `TBL-008~012`, `IMG-002~006`, `DIA-008`, `SYS-001~002`
- P2: `PAG-004~005`, `DIA-007`

## 다음 단계

1. 위 표 기준으로 실제 폴더 생성 (`features/<CODE>_<slug>/`).
2. 각 폴더에 `README.md`(기능 범위/완료조건) + `TESTCASES.md`(수동/자동 케이스) 생성.
3. `P0`부터 Playwright 또는 Vitest 기반 자동화 케이스 연결.

## 추적 문서

- 기능별 테스트 가능성/증빙 매트릭스: `/Users/jskang/nomadlab/packages/hwpx-ts/packages/hwpx-editor/features/FEATURE_TESTABILITY_MATRIX.md`
