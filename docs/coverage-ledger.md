# OWPML 커버리지 원장

`scripts/coverage_ledger.py`가 OWPML 2024 스키마(`DevDoc/OWPML SCHEMA/`) · 실코퍼스 census(`scripts/build_element_census.py`) · `src/hwpx/` 코드 참조 · 지원 매트릭스 · v4~v9 openrate 실한컴 코퍼스에서 결정론적으로 재산출하는 원장이다. 손으로 쓴 지원 주장이 아니라 기계 판독 [coverage-ledger.json](coverage-ledger.json)의 사람용 요약이며, `python scripts/coverage_ledger.py --check`가 드리프트를 게이트한다.

**주의**: `capabilityArea`는 지원 매트릭스 산문에 명시적으로 언급된 요소만 근사 매핑했다(무근거 승격 금지). `null`은 "미지원"이 아니라 "매트릭스 행과 요소가 1:1로 대응되지 않음"을 뜻한다 — 저수준 공용 요소(fieldBegin·autoNum·좌표류)가 대표적이다.

## 수리 기록 (2026-08-04 독립 감사 §3 실증 → 같은 사이클 내 수리)

이 원장은 2026-08-04 독립 감사에서 "결정론은 재현되지만 정확도는 불합격" 판정을 받았다([감사 판정문 §3](2026-08-04-completeness-audit-verdict.md)). 아래는 그 §3 결론 4항목을 그대로 수리한 기록이다 — 무엇이 어떻게 고쳐졌고, 되돌리면 감사가 인용한 오판이 그대로 재현됨을 확인했다(양방향 실행 로그는 커밋 메시지·리뷰 기록 참조).

**1) 분류기 — 위양성(주석/독스트링) 수리.** 스캔 전에 `tokenize`로 주석을, `ast`로 베어 문자열 문(독스트링 포함)을 블랭크 처리한다(`_strip_non_code_text`). 감사가 실측한 13개 요소 판정 뒤집힘(codeWriteApi 134→123, codeRead 192→186)이 이 텍스트에서 재현됨을 확인했다 — 예: `hp:case`/`hp:switch`는 `table_patch.py`의 독스트링이 태그를 언급한 덕에 read=True로 잘못 집계돼 있었고, `hp:lineseg`/`hp:seg`는 `patch.py`/`objects.py` 주석의 예시 태그 표기(`<hp:lineseg>`, `<hp:seg>`)가 여는 태그 리터럴로 오인됐다.
**2) 분류기 — 위음성(`etree.Element(` 별칭) 수리.** `_WRITE_MARKERS`에 `etree.Element(`를 추가했다(`ET.Element(`/`LET.Element(`만 있었다) — `oxml/body.py`·`header.py`가 이 별칭으로 방출하는 자리를 넓게 잡는다.
**3) 분류기 — 함수-인자 태그 전달 수리(신규 리졸버 + 명시 화이트리스트).** 두 갈래로 다뤘다:
   - **일반 리졸버**(`_resolve_argument_tag_literals`, 3c절): 함수 파라미터가 자기 본문에서 `f"{_HP}{param}"` 형태로 태그 조립에 쓰이는 자리를 찾고, 그 파라미터가 리터럴 없이 다른 함수에 그대로 전달되는 자리(예: `_note_shape(tag) → _note_pr_element(tag)`)를 고정점까지 전파한 뒤, 실제 리터럴 인자가 있는 호출부에서 해석한다. 감사가 지목한 `hh:ratio`/`hh:spacing`(장평/자간, `document_parts.py`) 외에 같은 관용구로 저평가돼 있던 `hh:relSz`/`hh:offset`(첨자), `hh:margin`/`hh:lineSpacing`(`header_part.py`의 문단 서식 setter), `hp:footNotePr`/`endNotePr`(`section_format.py`, 2단계 전달), `hp:header`/`footer`/`footNote`/`endNote`, `hp:booleanParam`(`toc_author.py`)까지 같은 결함 계열로 실측·수리됐다 — 감사는 앞의 둘만 스팟체크했지만 결함 자체는 훨씬 넓었다.
   - **명시 화이트리스트**(`_MANUAL_CODE_USAGE_OVERRIDES`, 3d절): `hp:insertBegin`/`insertEnd`/`deleteBegin`/`deleteEnd`(변경추적 마크)는 태그가 런타임 dict 값 문자열 연결로 조립돼(`body.py`의 `create_track_change_mark`) 어떤 정적 분석으로도 못 잡는다 — 근거 파일:라인을 필수로 요구하는 화이트리스트로 처리했고, 생성기가 시작 시점에 근거 문자열의 존재·형식을 검증한다(근거 없는 항목은 `ValueError`).
**4) census 재구축.** 생성 스크립트를 `scripts/build_element_census.py`로 신설·커밋했다(기존 census는 생성기 미보존이 결함이었다). 전 파트·전 네임스페이스를 스캔한다 — `ha:*`(settings.xml)·`hv:HCFVersion`(version.xml)이 이제 1급 요소 행이고, `hs:sec`도 실제 관측 빈도로 잡힌다. 모집단은 **명시적으로 재정의**했다: 레거시 166파일(그 중 hwpxlib 47은 지금도 이 레포에 남아 있고 검증 가능하다 — 나머지 119는 이 워크트리 어디에도 원본이나 목록이 보존돼 있지 않아 정체를 확인할 수 없다)은 재현·확장이 불가능했다 — 조용히 계승하는 대신 접근 가능한 새 모집단으로 바꿨다. 상세는 `generatedFrom.corpusPopulationNote`.
   unknown 파일: 0건 (전량 유효한 zip으로 열림).
**5) 속성 축.** 요소별 관측 속성 **이름** 집합을 census가 함께 기록한다(`observedAttributes` 컬럼, 값 빈도까지는 이번 사이클 범위 밖 — 생성기 독스트링에 명시).
**6) openrate 코퍼스 환류(v4~v9).** `docs/openrate/report-v{4,5,6,7,8,9}.json`의 스트라타별 실한컴 수용(`render_checked>0`·`render_failed==0`, 구세대 스키마는 `opened==requested>0`도 함께)을 `verificationBasis`로 환류한다(`by-openrate-corpus`/`by-capability-area+openrate-corpus`) — 2026-08-04 감사 R4가 지목한 v4 배선(원 이름 `by-v4-corpus`)을 2026-08 사이클 6.5 트레인⑰에서 v8까지, 사이클 6.6 트레인⑳에서 v9까지 확장하며 버전-중립 이름으로 바꿨다. 두 경로로 매핑한다: 이미 등록된 capabilityArea와 1:1 대응하는 스트라타는 `_OPENRATE_STRATUM_TO_CAPABILITY_AREA`(차트·체크박스·수식·각주 2종·테두리채우기·하이라이트·메모·그룹컨테이너), capabilityArea가 아직 없거나 있어도 혼합 지원 영역이라 요소만 지목해야 하는 신규 능력(글꼴·탭·도형텍스트·캡션·쪽번호제어·문자서식·필드파라미터·arc/polygon·인라인 원자 3종)은 `_OPENRATE_STRATUM_TO_ELEMENTS`로 요소를 직접 지목한다 — 둘 다 근거는 각 생성기 스크립트 독스트링이 실제로 부른다고 명시하는 것뿐(무근거 매핑 금지, `fieldBegin`을 일부러 안 매핑한 것과 같은 원칙).

**전 vs 후 (감사가 하한을 인용한 것과 같은 슬라이스 — corpusFileCount>0인 요소만)**: 감사 인용 하한은 관측 228건 중 write=none **70** · read=none **56** · frozen-template **28**([감사 판정문](2026-08-04-completeness-audit-verdict.md) 요약표). 이 원장 재생성 기준으로는 관측 229건 중 write=none **40** · read=none **25** · frozen-template **19**. **주의**: 두 population이 다르다(모집단을 재정의했다 — 위 4항목) — 이 비교는 "같은 잣대로 다시 잰 정확한 델타"가 아니라 분류기 수리가 방향대로 움직였는지의 참고 신호다. 분류기 수리 자체의 정확도 증거는 위 1~3항의 요소별 재현 로그가 1차 근거다.

## 전체 통계

| 지표 | 값 | 비율 |
|---|---|---|
| 요소 총수 | 345 | — |
| 스키마 선언 | 307 | 89.0% |
| 코퍼스에만 있음(스키마 미대응) | 38 | 11.0% |
| 실코퍼스에서 관측(빈도>0) | 229 | 66.4% |
| 코드 읽기 | 239 | 69.3% |
| 코드 쓰기(api) | 177 | 51.3% |
| 쓰기 frozen-template | 19 | 5.5% |
| 쓰기 none | 149 | 43.2% |
| 능력 영역 매핑됨 | 76 | 22.0% |
| Render-verified(매핑 근거) | 78 | 22.6% |
| ..중 openrate 코퍼스(v4~v9) 환류분 | 47 | 13.6% |
| 속성 이름 축 관측됨 | 193 | 55.9% |

실코퍼스 표본: 실문서 237개.

> real = every *.hwpx under the committed roots this generator was invoked with, deduplicated by content hash. This repo's committed snapshot was produced with the vendored tests/fixtures/hwpxlib_corpus (47 files, reproducible by anyone) plus the maintainer's private real-world Hancom-authored documents (school administrative and review paperwork -- not this pipeline's output) as a second --corpus root. That second root is not committed and its path is not recorded here (privacy); only the aggregate counts are. The legacy 166/84 split this census previously reported traced to a population that was never committed anywhere reachable from this workspace -- it could not be reproduced or extended, so this generator does not carry it forward. See docs/2026-08-04-completeness-audit-verdict.md §3-C1 and docs/coverage-ledger.md's repair notes.

임베드/외부 네임스페이스(OWPML 요소 스키마 밖 — per-element 행이 아니라 여기 파일수로만 가시화): `http://schemas.haansoft.com/office/8.0` 1건, `http://schemas.microsoft.com/office/drawing/2007/8/2/chart` 1건, `http://schemas.openxmlformats.org/drawingml/2006/chart` 1건, `http://schemas.openxmlformats.org/drawingml/2006/main` 1건, `http://schemas.openxmlformats.org/markup-compatibility/2006` 1건, `http://schemas.openxmlformats.org/officeDocument/2006/bibliography` 1건, `http://www.hancom.co.kr/hwpml/2016/meta/pkg#` 199건, `http://www.hancom.co.kr/hwpml/2021/extended` 1건, `http://www.idpf.org/2007/opf/` 237건, `http://www.w3.org/1999/02/22-rdf-syntax-ns#` 199건, `urn:oasis:names:tc:opendocument:xmlns:config:1.0` 132건, `urn:oasis:names:tc:opendocument:xmlns:container` 237건, `urn:oasis:names:tc:opendocument:xmlns:manifest:1.0` 236건.

네임스페이스 접두 없이 방출된 요소(스키마는 네임스페이스를 선언하나 실문서 어휘가 접두를 안 씀 — `hc:pt0` vs `hp:pt0`류와 같은 편차): `masterPage` 1건 — `docs/owpml-deviations.md` 후보.

## 실코퍼스 빈도 상위인데 frozen-template 또는 none인 요소

코퍼스에서 실제로 자주 관측되지만(구조는 통과) 코드에서 독립적으로 만들거나 편집할 API가 없는 요소 — Q3b 작업 목록 후보.

| 네임스페이스:요소 | 코퍼스 빈도 | 파일수 | codeRead | codeWrite | 능력 영역 |
|---|---|---|---|---|---|
| `ha:CaretPosition` | 1.0000 | 237 | True | frozen-template | — |
| `ha:HWPApplicationSetting` | 1.0000 | 237 | True | frozen-template | — |
| `hc:intent` | 1.0000 | 237 | True | frozen-template | — |
| `hc:left` | 1.0000 | 237 | True | frozen-template | — |
| `hc:next` | 1.0000 | 237 | True | frozen-template | — |
| `hc:prev` | 1.0000 | 237 | True | frozen-template | — |
| `hc:right` | 1.0000 | 237 | True | frozen-template | — |
| `hh:autoSpacing` | 1.0000 | 237 | True | frozen-template | — |
| `hh:compatibleDocument` | 1.0000 | 237 | True | frozen-template | — |
| `hh:docOption` | 1.0000 | 237 | True | frozen-template | — |
| `hh:head` | 1.0000 | 237 | True | frozen-template | — |
| `hh:layoutCompatibility` | 1.0000 | 237 | True | frozen-template | — |
| `hh:linkinfo` | 1.0000 | 237 | True | frozen-template | — |
| `hp:case` | 0.9958 | 236 | True | frozen-template | — |
| `hp:default` | 0.9958 | 236 | True | frozen-template | — |
| `hp:switch` | 0.9958 | 236 | True | frozen-template | — |
| `hh:typeInfo` | 0.9747 | 231 | True | frozen-template | — |
| `hp:lineseg` | 0.8987 | 213 | True | frozen-template | 문단·표 저작/편집 |
| `hp:label` | 0.2700 | 64 | False | none | — |
| `hh:metaTag` | 0.0422 | 10 | True | frozen-template | — |
| `hh:forbiddenWord` | 0.0127 | 3 | True | none | — |
| `hh:forbiddenWordList` | 0.0127 | 3 | True | none | — |
| `hp:compose` | 0.0127 | 3 | True | none | — |
| `hc:extent` | 0.0084 | 2 | False | none | — |
| `hp:connectLine` | 0.0084 | 2 | True | none | arc·polygon·curve·connectLine |
| `hp:endPt` | 0.0084 | 2 | False | none | — |
| `hp:ole` | 0.0084 | 2 | True | none | — |
| `hp:startPt` | 0.0084 | 2 | False | none | — |
| `hp:alpha` | 0.0042 | 1 | False | none | — |
| `hp:btn` | 0.0042 | 1 | False | none | 체크박스 양식개체 |
| `hp:comboBox` | 0.0042 | 1 | True | none | — |
| `hp:controlPoints` | 0.0042 | 1 | False | none | — |
| `hp:curve` | 0.0042 | 1 | True | none | arc·polygon·curve·connectLine |
| `hp:dutmal` | 0.0042 | 1 | False | none | — |
| `hp:edit` | 0.0042 | 1 | True | none | — |
| `hp:effect` | 0.0042 | 1 | False | none | — |
| `hp:effectsColor` | 0.0042 | 1 | False | none | — |
| `hp:glow` | 0.0042 | 1 | False | none | — |
| `hp:hiddenComment` | 0.0042 | 1 | False | none | — |
| `hp:listItem` | 0.0042 | 1 | True | none | — |

(총 59건 중 상위 40건만 표시 — 전체는 coverage-ledger.json의 `elements` 참조.)

## 네임스페이스별 표

| 네임스페이스 | 요소 수 | 스키마 선언 | 코퍼스 관측 | 읽기 | 쓰기 api | frozen-template | 쓰기 none |
|---|---|---|---|---|---|---|---|
| `ha` | 2 | 0 | 2 | 2 | 0 | 2 | 0 |
| `hc` | 31 | 7 | 29 | 30 | 23 | 5 | 3 |
| `hh` | 126 | 125 | 64 | 74 | 57 | 8 | 61 |
| `hhs` | 10 | 10 | 0 | 10 | 0 | 0 | 10 |
| `hm` | 2 | 2 | 0 | 2 | 0 | 0 | 2 |
| `hp` | 171 | 161 | 132 | 118 | 95 | 4 | 72 |
| `hs` | 1 | 1 | 1 | 1 | 1 | 0 | 0 |
| `hv` | 2 | 1 | 1 | 2 | 1 | 0 | 1 |

## 방법론 메모

- **접두 규약**: `hwpx.oxml.namespaces.HWPML_COMPAT_ROOT_NAMESPACES`에서 파생(hp=paragraph, hh=head, hc=core, hs=section, hm=master-page, hhs=history). `hv`(version)만 예외 — 그 레지스트리 자체에 `version` 패밀리가 없어(실결함) 코드 리터럴에서 확인한 값을 하드코딩했다.
- **스키마 vs 코퍼스 접두 불일치는 의도적으로 병합하지 않았다**: 예를 들어 `ParaList XML schema.xml`은 `pt0`을 자신의 타깃 네임스페이스(hp)에 선언하지만 실문서는 `hc:pt0`을 쓴다(`hp:line`은 `hc:startPt`를, `hp:connectLine`은 `hp:startPt`를 쓰는 것과 같은 종류의 드리프트 — `src/hwpx/opc/package.py`의 `_SHAPE_POINT_LOCAL_NAMES` 주석 참조). 두 항목 다 원장에 남아 있으며, 이런 드리프트 자체가 `docs/owpml-deviations.md`(Q4 편차 레지스트리)의 입력 후보다.
- **codeRead/codeWrite는 정적 패턴 매칭 + 두 단계 ast 리졸버**다. 1단계(평문, 스캔 전 주석·독스트링 블랭크): 한정 태그 리터럴/QName 조립, 접두 없는 `local_name()` 계열 비교 디스패치, `for name in TABLE:` 형태로 루프 변수가 태그가 되는 자리(`ast`로 `TABLE`을 정적 평가). 2단계(원본 텍스트, `_resolve_argument_tag_literals`): 태그가 함수 파라미터로 전달되는 자리 — 파라미터가 자기 본문에서 태그 조립에 쓰이는 함수를 찾고, 그 파라미터를 리터럴 없이 그대로 전달하는 호출 체인을 고정점까지 추적한 뒤, 실제 리터럴이 있는 호출부에서 해석한다 (2026-08-04 감사 §3-C2 수리 — 전엔 이 부류가 통째로 과소 집계됐다). **남은 한계**: 이 2단계 리졸버는 단일 파일 안에서만 동작한다(모듈 간 호출은 안 쫓는다) — 다른 파일의 함수로 전달되는 태그가 있다면 여전히 놓칠 수 있다. 완전히 동적으로 조립되는 태그(런타임 문자열 연결 등)는 `_MANUAL_CODE_USAGE_OVERRIDES`의 근거-필수 화이트리스트로 다룬다.
- **capabilityArea**는 지원 매트릭스 산문에 명시적으로 나온 요소만 매핑했다. 여러 능력 영역이 공유하는 저수준 요소(예: `fieldBegin`은 누름틀·TOC·하이퍼링크가 다 쓴다)는 일부러 매핑하지 않았다. `verificationBasis`는 두 독립 출처를 결합한다 — 지원 매트릭스 산문의 "Render-verified" 표기(`by-capability-area`)와 `docs/openrate/report-v{4,5,6,7,8,9}.json` 실한컴 openrate 코퍼스의 스트라타별 수용 receipt(`by-openrate-corpus`) — capabilityArea 경로는 매핑이 명확한 스트라타에 한해서만, capabilityArea가 아직 없는 스트라타는 생성기 독스트링이 명시하는 요소에 직접.
- **census 생성기**(`scripts/build_element_census.py`)는 전 파트·전 네임스페이스를 스캔하고, unknown 파일은 사유와 함께 기록하며, OWPML 요소 스키마 밖의 임베드/외부 네임스페이스와 비네임스페이스 요소는 별도 버킷(`foreignNamespaces`/`unnamespacedElements`)으로 가시화한다(삼키지 않는다). 두 번 실행하면 바이트까지 같은 출력을 낸다(결정론) — 단, 이 레포가 vendoring한 census 스냅샷은 소유자의 비공개 실문서 코퍼스를 포함해 생성됐으므로, 그 서브셋은 소유자만 재현 가능하다(`generatedFrom.corpusPopulationNote` 참조) — 이는 감사가 지적한 "생성기 자체가 없다"는 결함과는 다른 종류다: 생성기는 있고 커밋돼 있고 결정론적이다, 다만 입력 중 하나가 공개 레포 밖에 있을 뿐이다.

