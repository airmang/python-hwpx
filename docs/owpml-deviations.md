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

각 항목은 4필드로 기록한다 — **스키마 주장**(`DevDoc/OWPML SCHEMA/*.xml`이
선언한 것) · **실문서 실측**(hwpxlib 코퍼스 또는 명시된 다른 코퍼스에서
관찰한 것) · **우리 처리**(코드가 실제로 어느 쪽을 따르는지, 파일:함수) ·
**프로브**(`probes/`의 재실행 가능한 스크립트 — 실행하면 실측과 우리 처리를
둘 다 다시 검증한다). 근거 파일이 `.gitignore` 대상(사설 코퍼스)이면 항목에
명시하고, 프로브는 그 파일이 없을 때 SKIP으로 정직하게 물러난다.

| ID | 스키마 주장 | 실문서 실측 | 우리 처리 | 프로브 | 상태 |
|---|---|---|---|---|---|
| DEV-001 | 2024 네임스페이스 중심 스키마 | 2011 본체 + 2016 확장 네임스페이스 문서가 hwpxlib 47개 코퍼스와 hancom-io/hwpx-owpml-model current HEAD에서 실사용됨 | `hwpx.oxml.namespaces`가 2011/2016/2024 registry SSOT — 읽기는 local-name traversal, 신규 생성은 2011 본체+2016 확장 유지 | (없음 — 최초 항목, 후속 프로브 전환 대상) | implemented |
| DEV-002 | `hh:tabPr`의 `hh:tabItem` 자식은 `minOccurs="0"`만 선언되고 `maxOccurs` 생략 — XSD 기본값 1이라 tabPr 하나에 tabItem 최대 1개 | `error__20240626__no_manifest.hwpx`(vendored) 한 `hh:tabPr`에 **31개** `hh:tabItem`. 사설 코퍼스(국세청 공문, `.gitignore` 대상)에서도 4개 독립 관찰 — 다른 생성 워크플로에서도 재현 | `hwpx.oxml.header.TabDefinition.tab_stops`가 무제한 리스트, `HwpxOxmlHeader.ensure_tab_definition`(header_part.py)이 순서까지 dedupe 키로 취급 | `probes/dev002_tabitem_maxoccurs.py` | implemented (6.1 트레인③, 커밋 a144733) |
| DEV-003 | `AbstractDrawingObjectType` 시퀀스: `lineShape, fillBrush, drawText, shadow` (선언 순서) | `reader_writer__SimpleRectangle.hwpx`(vendored) `hp:rect`: `lineShape, fillBrush, shadow, drawText` — shadow가 drawText보다 먼저 | `objects.py::_write_draw_text`가 "shadow 다음"이 아니라 "지오메트리(pt0류) 앞"에 앵커 — `_reposition_child_before_any`로 사이드 존재 여부에 안 기댐 | `probes/dev003_drawtext_child_order.py` | implemented (6.1 트레인⑤, 커밋 3d4e038) |
| DEV-004 | 없음 — `DevDoc/OWPML SCHEMA/`에 Settings 스키마 자체가 없다(7종 벤더링: Header/Body/Core/History/MasterPage/ParaList/Version) | `settings.xml`(`ha:HWPApplicationSetting`)이 코퍼스 100%에 존재. `config:config-item-set`/`config-item`은 Hancom 고유가 아니라 **OASIS ODF 1.0 config 스키마**(`urn:oasis:...:config:1.0`) 재사용 | `hwpx.oxml.settings`(신규 모듈) — 스키마 없이 실문서 177파일 역설계, config-item 이름·타입을 하드코딩 없이 보존 | `probes/dev004_settings_xml_no_schema.py` | implemented (6.1 트레인④, 커밋 c38bf07) |
| DEV-005 | `hh:layoutCompatibility`가 48개 플래그 이름을 전부 선언(`minOccurs="0"` 마커 자식) | 도달 가능한 코퍼스 전수(47/47) `<hh:layoutCompatibility/>` — 플래그 0개. 완전성 감사 §4-R1이 "코드가 단어조차 모르는" 유일 전수 요소로 지목했던 자리 | `hwpx.oxml.header.LayoutCompatibility.flags: frozenset[str]` — 48종 하드코딩 열거 대신 실제 존재하는 자식 이름만 보존(스키마 밖 미래 플래그도 무손실) | `probes/dev005_layout_compatibility_empty.py` | implemented (6.1 트레인④, 커밋 c38bf07) |
| DEV-006 | `hh:font/@isEmbedded`·`hh:tabPr/@autoTab*`는 `xs:boolean`(XSD 어휘상 true/false와 1/0 둘 다 유효) | 코퍼스 전수(6741건 font/substFont, 142건 tabPr) `"0"`/`"1"`만 관측 — `"true"`/`"false"` 0건(다른 OWPML 불리언 관행과 이원). 비임베드 `hh:font`는 `binaryItemIDRef` 속성 자체가 없고(1682/1682), `hh:substFont`는 항상 있되 빈 문자열로 남는다(284/284) | `_document_primitives._zero_one_bool_str`(범용 `_bool_str`과 분리) + `_build_font_element`의 조건부 `binaryItemIDRef` | `probes/dev006_fontface_write_conventions.py` | implemented (6.1 트레인②, 커밋 7914b18) |
| DEV-007 | MasterPage 파트 루트는 `hm:masterPage`(마스터페이지 네임스페이스 접두) | `error__20250808__...hwpx`(vendored) `Contents/masterpage0.xml` 루트가 `xmlns:hm` 선언은 갖되 그 자신에는 접두를 안 붙인 **맨 `masterPage`**. 자식(`hp:subList` 등)은 정상 접두. 완전성 감사 census의 `corpusUnnamespacedElements` 발견과 일치 | `HwpxOxmlMasterPage`는 요소 래퍼일 뿐 네임스페이스에 안 기대 — 이미 관용적으로 견딤(대응 코드 변경 없음, 관찰 기록만) | `probes/dev007_masterpage_unnamespaced_root.py` | observed (대응 불필요 — 읽기 경로가 이미 무관) |

각 편차는 `증거:` 또는 표의 실측 칸으로 코퍼스, 캡처, 또는 재현 파일 경로를
명시한다. 확정 편차를 `_schemas`에 반영하면 관련 패치 커밋을 상태 칸에
남긴다. 프로브는 모두 `python probes/devNNN_*.py`로 단독 실행 가능하며,
근거 파일이 로컬에 없으면(`.gitignore` 대상 등) SKIP으로 종료한다(exit 0).
