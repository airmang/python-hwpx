# HWPX 스키마 구조와 파이썬 모델 현황

## DevDoc 스키마 자료 한눈에 보기
| 스키마 파일 | 대상 네임스페이스 | 루트 요소 | 주요 역할 |
| --- | --- | --- | --- |
| Body XML schema | `http://www.owpml.org/owpml/2024/section` | `<sec>` | 구역(section) 루트로서 문단 목록을 정의하며 ParaList 스키마의 `SectionType`을 참조합니다. |
| ParaList XML schema | `http://www.owpml.org/owpml/2024/paragraph` | `<hp:p>` (문단), `<hp:run>`, `<hp:t>` 등 | 문단과 런, 컨트롤, 개체, 텍스트 마크의 세부 구조를 정의하며 Core 스키마 타입을 가져옵니다. |
| Header XML schema | `http://www.owpml.org/owpml/2024/head` | `<head>` | 문서 전역 설정(번호 시작값, 서식 매핑 테이블, 금칙어, 문서 옵션, 변경 추적 등)을 정의합니다. |
| Core XML schema | `http://www.owpml.org/owpml/2024/core` | (여러 단순/복합 타입) | 번호 모양, 색상, 스타일 등의 공통 타입을 제공해 다른 스키마에서 재사용합니다. |
| MasterPage XML schema | `http://www.owpml.org/owpml/2024/master-page` | `<masterPage>` | 바탕쪽(머리말·꼬리말) 정의와 문단 리스트를 관리합니다. |
| Document History XML schema | `http://www.owpml.org/owpml/2024/history` | `<history>` | 히스토리 엔트리와 변경(diff) 정보를 저장합니다. |
| Version XML schema | `http://www.owpml.org/owpml/2024/version` | `<version>` | 대상 애플리케이션 및 버전 메타데이터를 기록합니다. |

## 주요 스키마 세부 구조
### Header (head.xml)
* `<head>`는 버전과 구역 수(`secCnt`)를 속성으로 두고 번호 시작값, 참조 목록, 금칙어, 호환 문서, 문서 옵션, 메타 태그, 변경 추적 설정을 자식으로 둡니다.
* `MappingTableType`은 글꼴, 테두리/채움, 글자·문단·스타일 속성, 번호·글머리표 정의, 메모 모양, 변경 추적 항목 등을 한꺼번에 관리합니다.
* `DocOption`에는 문서 링크 정보와 저작권 마크를 배치하고, `trackchangeConfig`는 암호화 키를 포함해 변경 추적 정책을 설정합니다.

### Body 및 ParaList (section/paragraph)
* 본문 논리 구조는 "본문 → 구역(`<sec>`) → 문단(`<p>`)" 계층이며, 구역마다 문단이 최소 한 개 이상 존재해야 합니다.
* `<hp:p>` 문단은 식별자, 문단/스타일 참조, 쪽·단 나눔 여부 등 속성과 `<run>`·`<metaTag>` 하위 요소를 가집니다.
* `<hp:run>`은 `secPr`, `ctrl`, `t`, 표·그림·컨트롤·동영상 등 다양한 객체 요소를 포함하는 선택 집합으로, 텍스트 노드(`<hp:t>`)는 마크업(형광펜, 제목표시, 탭, 추적 태그 등)을 복합 콘텐츠로 섞을 수 있습니다.
* 구역 속성(`<secPr>`)은 페이지 설정, 번호 매기기 시작값, 줄격자, 감춤/보이기, 바탕쪽 연결 등 페이지 레이아웃 정보를 포괄합니다.

### Core 타입
* `NumberType1`, `NumberType2` 등 다양한 번호 모양 열거형을 정의해 번호 매기기와 페이지 번호 표현에 활용합니다.
* 이 외에도 색상, 선/채움, 점 좌표 등 문단·개체 서식을 구성하는 공통 자료형이 포함되어 다른 스키마에 의해 import 됩니다.

### MasterPage, Document History, Version
* `masterPage`는 ParaList의 문단 서브리스트를 한 쪽에 적용하며, 적용 위치(type)와 특정 쪽 번호, 복제 여부를 속성으로 가집니다.
* `history`는 변경 이력을 `historyEntry`로 축적하고, 각 엔트리는 패키지·머리말·본문·꼬리말의 diff 묶음과 수정자/날짜·자동 저장 여부 등을 기록합니다.
* `version` 요소는 대상 애플리케이션과 버전(major/minor/micro/build)을 속성으로 제공하여 문서 호환성을 명시합니다.

## 파이썬 구현 현황 요약
### 패키지 및 파트 로딩
* `HwpxPackage`는 OPC 스타일 컨테이너를 전부 메모리에 적재하고, manifest 기반으로 섹션·헤더 경로를 캐싱합니다. 저장 시 업데이트된 파트만 다시 ZIP에 작성합니다.

### 저수준 OXML 래퍼
* `HwpxOxmlDocument`는 콘텐츠 매니페스트와 섹션/헤더 파트만 수집하며, 문단 추가 시 2011 네임스페이스를 사용해 `<hp:p>` 요소를 생성합니다.
* 본문 파서는 `Section`·`Paragraph`·`Run`·`TextSpan` 데이터클래스로 구역과 문단을 읽지만, `ctrl`이나 대부분의 인라인 개체는 `GenericElement`에 남깁니다.
* 헤더 파서는 번호 시작값, 글꼴/테두리/글자 속성, 금칙어, 문서 옵션, 변경 추적 설정 등을 구조화하지만 나머지 리스트 항목은 `other_collections`로 보관합니다.

### 파싱 및 도구 유틸리티
* `_ELEMENT_FACTORY`는 head/sec/p/run/t 정도만 전용 파서로 연결하고, 기타 요소는 제네릭 요소로 반환합니다.
* `TextExtractor`와 `ObjectFinder`는 2011/2016 네임스페이스 프리셋을 사용해 섹션과 문단을 순회하며 텍스트/객체를 찾습니다.
* 단위 테스트는 샘플 헤더/섹션 파싱과 텍스트 마크, 스키마 로딩 정도를 검증합니다.

## 주요 누락 요소 및 확장 필요 영역
* **런/컨트롤 세부 모델링:** ParaList 스키마에는 표, 컨트롤, 텍스트 장식, 변경 추적 등 수십 가지 요소가 정의돼 있지만 현재 파서는 대부분을 `GenericElement`로만 유지합니다. 표, 필드 코드, 폼 컨트롤 등은 전용 데이터클래스를 추가해야 합니다.
* **헤더 매핑 테이블 확장:** `MappingTableType`의 bullets, paraProperties, styles, memoProperties, trackChanges 등은 아직 파서에서 분리되지 않아 `other_collections`에 묶입니다. 각 리스트에 대한 구조화와 상호참조 지원이 필요합니다.
* **추가 파트 지원:** 현재 OXML 래퍼는 섹션과 헤더만 다루므로 바탕쪽(`masterPage`), 문서 이력, 버전 파트는 로딩·편집 대상에서 제외됩니다. 매니페스트 스캔과 래퍼 클래스를 확장해 해당 파트를 노출해야 합니다.
* **네임스페이스 및 버전 정비:** 코드가 2011/2016 네임스페이스를 기본값으로 사용해 2024 스키마와 어긋납니다. 패키지/도구 전반에서 최신 네임스페이스를 기본으로 맞추고, 구버전 문서 호환 전략을 정리해야 합니다.
* **스키마 검증·테스트 범위 강화:** 파서는 선택적으로만 XSD를 검증하고, 상위 API(`HwpxDocument`)에서는 스키마 검사를 호출하지 않습니다. 헤더·섹션 외 파트에 대한 파서와 테스트 케이스도 비어 있어 통합 검증 루프 구성이 필요합니다.
