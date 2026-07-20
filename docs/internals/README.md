# HWPX/OWPML 내부 실전 가이드

```{toctree}
:maxdepth: 1
:hidden:

units
lineseg
toc-dirty
opc-packaging
memo-structure
oracle-limits
```

코드만으로는 알 수 없는, **실제 한/글 동작에서 확인된** HWPX/OWPML 실전 지식을 모은 문서입니다.

HWPX는 [KS X 6101 OWPML](https://www.kssn.net/search/stddetail.do?itemNo=K001010119985) 표준 위에 세워진 ZIP+XML 포맷이지만, 표준 문서에도 한컴 공식 문서에도 적혀 있지 않은 동작이 많습니다. 파일을 만들어 실제 한/글에서 열어 보면서만 알 수 있는 것들 — 저장 시점에 캐시되는 조판 결과, 필드 재계산 트리거, OPC 재패킹 규칙, 메모의 참조 구조, 렌더 기반 검증의 한계 같은 것들이 그렇습니다.

이 가이드는 그런 지식을 정리해, 기여자가 "왜 이렇게 처리해야 하는가"를 코드와 함께 이해하도록 돕는 것을 목표로 합니다. 각 문서의 모든 주장은 이 저장소의 코드·테스트(`src/hwpx/...`, `tests/...`)나 공개 표준으로 검증할 수 있는 것만 담았고, 실측으로 관찰한 한/글 동작은 "실제 한/글에서 확인된 동작"으로 명시했습니다.

## 문서 목록

| 주제 | 문서 | 한 줄 요약 |
|---|---|---|
| 좌표 단위 | [units.md](units.md) | HWPUNIT 좌표계(1 inch = 7,200)와 라이브러리가 pt/mm/%를 내부에서 변환하는 이유 |
| 조판 캐시 | [lineseg.md](lineseg.md) | `hp:linesegarray`는 한/글이 저장 시점에 캐시한 줄나눔 결과 — 편집 후 stale로 남기면 글자 겹침 |
| 목차 필드 | [toc-dirty.md](toc-dirty.md) | `TABLEOFCONTENTS` 필드의 `dirty="1"`이 여는 시점 재계산을 트리거하는 메커니즘 |
| OPC 패키징 | [opc-packaging.md](opc-packaging.md) | `mimetype` 첫 엔트리·STORED 규칙, version.xml/manifest, 2016→2011 네임스페이스 정규화 |
| 메모 구조 | [memo-structure.md](memo-structure.md) | 메모 본문·MEMO 필드·`MemoShapeIDRef` 참조가 맞아야 한/글이 메모를 표시하는 이유 |
| 오라클 한계 | [oracle-limits.md](oracle-limits.md) | 한/글 export 기반 검증이 침묵 실패할 수 있는 경우와 픽셀 검증이 필요한 이유 |

## 읽는 순서

처음이라면 [units.md](units.md) → [opc-packaging.md](opc-packaging.md) → [lineseg.md](lineseg.md) 순서를 권합니다. 좌표 단위와 컨테이너 구조를 먼저 잡으면 나머지 주제의 코드가 훨씬 잘 읽힙니다.

## 전제

- 이 가이드는 HWPX(OWPML/OPC) 포맷을 다룹니다. HWP v5 바이너리 포맷은 대상이 아닙니다.
- 인용된 코드 경로는 이 저장소 기준입니다(`src/hwpx/...`). 버전에 따라 줄 번호는 달라질 수 있으니 함수·클래스 이름으로 찾으세요.
- "실제 한/글에서 확인된 동작"은 실제 한컴오피스로 파일을 열거나 저장해 관찰한 결과를 뜻합니다. 표준에 명문화되어 있지 않을 수 있습니다.
