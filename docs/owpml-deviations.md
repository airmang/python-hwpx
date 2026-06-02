# OWPML 편차 레지스트리

공식 OWPML 스키마(de jure)와 한컴오피스 실동작(de facto) 사이의 확인된
편차와 호환 전략을 기록한다. 스키마 검증은 하드 게이트가 아니라 수렴 lint다.
확인된 편차는 로컬 `_schemas`를 한컴 현실에 맞게 패치할 때 근거가 된다.

## 네임스페이스 정합 (2011/2016 ↔ 2024)

- 구현 전략: `hwpx.oxml.namespaces`가 2011/2016/2024 OWPML namespace
  registry의 SSOT다. 읽기 경로는 namespace URI를 단일 2011 값으로 가정하지
  않고 local-name traversal과 registry helper로 2011/2016/2024 입력을
  수용한다.
- 쓰기 전략: 기존 문서를 편집할 때 paragraph/run/text 계층은 source element의
  namespace를 따라 새 element를 만든다. 따라서 2011/2016/2024 입력 문서는
  `HwpxDocument.open()` 후 `to_bytes()`에서 해당 문서 namespace를 보존한다.
- 신규 생성 전략: 현 코퍼스와 `hancom-io/hwpx-owpml-model` current HEAD가
  모두 2011 본체 namespace와 2016 확장 namespace를 사용하므로, 신규
  `HwpxDocument.new()` skeleton은 2011 본체 namespace를 유지한다.
- 코퍼스 증거: `tests/fixtures/hwpxlib_corpus/manifest.json`의 47개 샘플은
  `Contents/header.xml`과 `Contents/section0.xml` root 선언 기준 모두
  2011 본체 namespace + 2016 확장 namespace(`hp10`, `HwpUnitChar`) 조합이다.
  2024 namespace 실문서 샘플은 이 코퍼스에 없으므로 합성 fixture로 회귀
  테스트한다.

## 확인된 편차

현재 이 Stage에서 확정한 1차 레지스트리 항목은 네임스페이스 정합 전략이다.
개별 요소/속성 편차는 hwpxlib 코퍼스 또는 한컴 Computer Use 관찰로
재현된 뒤 아래 표에 추가한다.

| ID | 공식 스키마 | 한컴 실동작 | 증거 샘플 | 상태 |
|---|---|---|---|---|
| DEV-001 | 2024 네임스페이스 중심 스키마 | 2011 본체 + 2016 확장 네임스페이스 문서가 hwpxlib 47개 코퍼스와 hancom-io/hwpx-owpml-model current HEAD에서 실사용됨 | `tests/fixtures/hwpxlib_corpus/manifest.json`; `hancom-io/hwpx-owpml-model` HEAD `1453388` namespace constants | implemented |

각 편차는 `증거:` 또는 표의 `증거 샘플`로 코퍼스, 캡처, 또는 재현 파일
경로를 명시한다. 확정 편차를 `_schemas`에 반영하면 관련 패치 커밋을
상태 칸에 남긴다.
