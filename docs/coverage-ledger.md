# OWPML 커버리지 원장

`scripts/coverage_ledger.py`가 OWPML 2024 스키마(`DevDoc/OWPML SCHEMA/`) · 실코퍼스 census · `src/hwpx/` 코드 참조 · 지원 매트릭스에서 결정론적으로 재산출하는 원장이다. 손으로 쓴 지원 주장이 아니라 기계 판독 [coverage-ledger.json](coverage-ledger.json)의 사람용 요약이며, `python scripts/coverage_ledger.py --check`가 드리프트를 게이트한다.

**주의**: `capabilityArea`는 지원 매트릭스 산문에 명시적으로 언급된 요소만 근사 매핑했다(무근거 승격 금지). `null`은 "미지원"이 아니라 "매트릭스 행과 요소가 1:1로 대응되지 않음"을 뜻한다 — 저수준 공용 요소(fieldBegin·autoNum·좌표류)가 대표적이다.

## 전체 통계

| 지표 | 값 | 비율 |
|---|---|---|
| 요소 총수 | 345 | — |
| 스키마 선언 | 307 | 89.0% |
| 코퍼스에만 있음(스키마 미대응) | 38 | 11.0% |
| 실코퍼스에서 관측(빈도>0) | 228 | 66.1% |
| 코드 읽기 | 192 | 55.7% |
| 코드 쓰기(api) | 134 | 38.8% |
| 쓰기 frozen-template | 28 | 8.1% |
| 쓰기 none | 183 | 53.0% |
| 능력 영역 매핑됨 | 70 | 20.3% |
| Render-verified(매핑 근거) | 47 | 13.6% |

실코퍼스 표본: 실문서 166개 (저작 충실도 감사 census).

## 실코퍼스 빈도 상위인데 frozen-template 또는 none인 요소

코퍼스에서 실제로 자주 관측되지만(구조는 통과) 코드에서 독립적으로 만들거나 편집할 API가 없는 요소 — Q3b 작업 목록 후보.

| 네임스페이스:요소 | 코퍼스 빈도 | 파일수 | codeRead | codeWrite | 능력 영역 |
|---|---|---|---|---|---|
| `hc:intent` | 1.0000 | 166 | True | frozen-template | — |
| `hc:left` | 1.0000 | 166 | True | frozen-template | — |
| `hc:next` | 1.0000 | 166 | True | frozen-template | — |
| `hc:prev` | 1.0000 | 166 | True | frozen-template | — |
| `hc:right` | 1.0000 | 166 | True | frozen-template | — |
| `hh:autoSpacing` | 1.0000 | 166 | True | frozen-template | — |
| `hh:compatibleDocument` | 1.0000 | 166 | True | frozen-template | — |
| `hh:docOption` | 1.0000 | 166 | True | frozen-template | — |
| `hh:font` | 1.0000 | 166 | True | frozen-template | — |
| `hh:fontface` | 1.0000 | 166 | True | frozen-template | — |
| `hh:fontfaces` | 1.0000 | 166 | True | frozen-template | — |
| `hh:head` | 1.0000 | 166 | True | frozen-template | — |
| `hh:layoutCompatibility` | 1.0000 | 166 | False | frozen-template | — |
| `hh:lineSpacing` | 1.0000 | 166 | True | frozen-template | — |
| `hh:linkinfo` | 1.0000 | 166 | True | frozen-template | — |
| `hh:margin` | 1.0000 | 166 | True | frozen-template | — |
| `hh:offset` | 1.0000 | 166 | True | frozen-template | — |
| `hh:ratio` | 1.0000 | 166 | False | frozen-template | — |
| `hh:relSz` | 1.0000 | 166 | False | frozen-template | — |
| `hh:spacing` | 1.0000 | 166 | False | frozen-template | — |
| `hh:tabPr` | 1.0000 | 166 | True | frozen-template | — |
| `hh:tabProperties` | 1.0000 | 166 | True | frozen-template | — |
| `hh:typeInfo` | 1.0000 | 166 | True | frozen-template | — |
| `hp:case` | 0.9880 | 164 | True | frozen-template | — |
| `hp:default` | 0.9880 | 164 | False | frozen-template | — |
| `hp:switch` | 0.9880 | 164 | True | frozen-template | — |
| `hh:outline` | 0.9759 | 162 | False | frozen-template | — |
| `hh:metaTag` | 0.4096 | 68 | True | frozen-template | — |
| `hh:tabItem` | 0.2349 | 39 | False | none | — |
| `hh:substFont` | 0.1627 | 27 | True | none | — |
| `hp:fwSpace` | 0.1627 | 27 | False | none | — |
| `hp:drawText` | 0.0964 | 16 | False | none | — |
| `hp:textMargin` | 0.0964 | 16 | False | none | — |
| `hh:memoPr` | 0.0783 | 13 | True | none | 메모(코멘트) |
| `hh:memoProperties` | 0.0783 | 13 | True | none | 메모(코멘트) |
| `hh:supscript` | 0.0723 | 12 | False | none | — |
| `hp:newNum` | 0.0723 | 12 | False | none | — |
| `hp:nbSpace` | 0.0602 | 10 | False | none | 문단·표 저작/편집 |
| `hp:pageHiding` | 0.0602 | 10 | False | none | — |
| `hc:imgBrush` | 0.0482 | 8 | False | none | 그림 삽입/치환 |

(총 98건 중 상위 40건만 표시 — 전체는 coverage-ledger.json의 `elements` 참조.)

## 네임스페이스별 표

| 네임스페이스 | 요소 수 | 스키마 선언 | 코퍼스 관측 | 읽기 | 쓰기 api | frozen-template | 쓰기 none |
|---|---|---|---|---|---|---|---|
| `hc` | 31 | 7 | 29 | 26 | 19 | 5 | 7 |
| `hh` | 128 | 125 | 66 | 66 | 37 | 20 | 71 |
| `hhs` | 10 | 10 | 0 | 0 | 0 | 0 | 10 |
| `hm` | 2 | 2 | 0 | 0 | 0 | 0 | 2 |
| `hp` | 172 | 161 | 133 | 99 | 77 | 3 | 92 |
| `hs` | 1 | 1 | 0 | 1 | 1 | 0 | 0 |
| `hv` | 1 | 1 | 0 | 0 | 0 | 0 | 1 |

## 방법론 메모

- **접두 규약**: `hwpx.oxml.namespaces.HWPML_COMPAT_ROOT_NAMESPACES`에서 파생(hp=paragraph, hh=head, hc=core, hs=section, hm=master-page, hhs=history). `hv`(version)만 예외 — 그 레지스트리 자체에 `version` 패밀리가 없어(실결함) 코드 리터럴에서 확인한 값을 하드코딩했다.
- **스키마 vs 코퍼스 접두 불일치는 의도적으로 병합하지 않았다**: 예를 들어 `ParaList XML schema.xml`은 `pt0`을 자신의 타깃 네임스페이스(hp)에 선언하지만 실문서는 `hc:pt0`을 쓴다(`hp:line`은 `hc:startPt`를, `hp:connectLine`은 `hp:startPt`를 쓰는 것과 같은 종류의 드리프트 — `src/hwpx/opc/package.py`의 `_SHAPE_POINT_LOCAL_NAMES` 주석 참조). 두 항목 다 원장에 남아 있으며, 이런 드리프트 자체가 `docs/owpml-deviations.md`(Q4 편차 레지스트리)의 입력 후보다.
- **codeRead/codeWrite는 정적 패턴 매칭**이다 — 한정 태그 리터럴/QName 조립, 접두 없는 `local_name()` 계열 비교 디스패치, `for name in TABLE:` 형태로 루프 변수가 태그가 되는 자리(`ast`로 `TABLE`을 정적 평가) 세 경로를 합친다. `makeelement`/`SubElement`/`_append_child`/여는 태그 리터럴 근방이면 쓰기, 그 밖은 읽기로 분류한다. **알려진 한계**: 태그가 함수 인자로 넘어오는 자리(예: `section_format.py`의 header/footer `tag` 매개변수)는 호출부 인자까지 추적하지 않아 못 잡는다 — 이런 요소는 실제로는 코드가 다루는데도 `codeRead/codeWrite`가 과소 집계될 수 있다.
- **capabilityArea**는 지원 매트릭스 산문에 명시적으로 나온 요소만 매핑했다. 여러 능력 영역이 공유하는 저수준 요소(예: `fieldBegin`은 누름틀·TOC·하이퍼링크가 다 쓴다)는 일부러 매핑하지 않았다.

