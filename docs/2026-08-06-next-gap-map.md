# 차기 갭 지도 — 사이클 6.5 트레인 ⑯ 원장 재스캔

> 작성: 사이클 6.5 트레인 ⑯ (2026-08-06). 브랜치 `feat/cycle-6.1`.
> 전제: `docs/2026-08-04-completeness-audit-verdict.md`의 갭 지도 #1~#15는
> 사이클 6.1~6.4에서 소진됐다(구현 또는 근거 기반 보류). 이 문서는 그 뒤를
> 잇는 새 지도다 — "측정기(원장)가 일감을 정의한다"는 방향 원칙 그대로,
> **원장을 먼저 수리하고 그 위에서 다음 갭을 다시 읽는다.**

## 요약 (TL;DR)

| 항목 | 결과 |
|---|---|
| 분류기 수리 | 위음성 2건, 요소 6개(`hhs:insert/update/delete/position`, `hh:trackChange`/`trackChangeAuthor`) — 둘 다 결함-부활 테스트로 증명 |
| 원장 상태 | 재생성 `--check` in sync. 전체 345요소 중 코드 읽기 229→**233**, 쓰기(api) 171→**173** |
| 사이클 6.1~6.4 산출물 환류 | 전수 대조 **50건** 전부 정합(46건 기존 정합 + 4건 이번 수리로 정합화) |
| 실코퍼스(237파일) 잔여 갭 | write≠api 이거나 read=False인 요소 **63개**(corpusFileCount>0 슬라이스) |
| 회귀 | 전 스위트 2561→**2563 passed**(+2, 신규 테스트), 실패 0 |
| 정적 검사 | mypy 0 · pyright 0 |
| 사이클 6.5 트레인 제안 | 상위 3건 — §4 |

---

## Part A. 원장 정밀화 (측정기 수리)

### A.1 분류기 위음성 2건 수리

**① `hhs:insert`/`update`/`delete`/`position`(read=False → True).** 이관 요청에서
지목된 결함. `history_part.py:103-112`의 `_parse_diff_op`는 범용 재귀
파서다 — `local_name(node)`를 `==`/`in` 비교 없이 곧바로 `DiffNode.op`에
담는다. 그래서 이 코드베이스 전역의 "`name = local_name(child)` 뒤
`if name == "xxx":`" 디스패치 관용구(원장이 이미 인식하는 패턴)와 다르게,
비교 지점 자체가 없어 어떤 정적 스캐너도 못 잡는다. 실제로 파싱되는
것인지는 `tests/test_part_hierarchy_read_models.py:179`의
`test_parse_history_handles_a_schema_shaped_synthetic_fixture`가
`DiffNode(op="insert", ...)` 같은 실제 어서션으로 이미 증명하고 있었다 —
이번 수리는 그 실재를 원장에 반영만 한 것이다. `code_write`는 그대로
`False`다(`hhs:insert` 등을 쓰는 코드는 grep 전수로 0건 확인).

수리는 기존 `_MANUAL_CODE_USAGE_OVERRIDES`(근거-필수 화이트리스트) 관용구
그대로 4개 항목을 추가했다 — `hp:insertBegin` 등 기존 항목과 같은 방식,
새 리졸버는 만들지 않았다(하나의 코드 자리에서만 나타나는 패턴이라 일반화가
과설계).

**② `hh:trackChange`/`trackChangeAuthor`(codeWrite=none → api) — 이번
재스캔이 독자적으로 찾은 두 번째 위음성.** 팀 리드가 지목한 항목은 아니지만,
차기 갭 지도를 정확히 뽑으려면 원장이 "이미 출하된 기능을 갭으로 잘못
보고"하지 않아야 한다는 같은 이유로 수리했다(방치했다면 이 문서의 §3이
이미 2026-06-30에 실한컴 COM으로 검증된 변경추적 기능을 "미착수 갭"으로
잘못 보고할 뻔했다). `header.py:1599-1629`의 `track_change_to_xml`/
`track_change_author_to_xml`은 `etree.Element("{http://www.hancom.co.kr/
hwpml/2011/head}trackChange", ...)`처럼 **전체 네임스페이스 URI를 문자열
리터럴로 직접 박아 넣는다** — 코드베이스 전역이 쓰는 `{_HH}trackChange`
별칭 관용구가 아니라서, 원장의 패턴 3(`_?HH(?:10)?\}name`)이 `}` 바로 앞
글자("head")가 "HH"가 아니므로 못 잡는다. 이 idiom은 전체 `src/`에서 이
두 자리(`header.py:1610`, `:1626`)뿐이라(grep 전수 확인) 화이트리스트로
처리했다. 배선은 실재한다: `header_part.py:870-893 add_track_change` →
`_document/ns/tracking.py:114-127 TrackingNamespace.add_change`
(`doc.tracked.add_change`) → `add_tracked_insert/delete/replace`의 저수준
동사, 2026-06-30 실 Windows 한컴 COM `IsTrackChange=1` 검증을 받은 코드다.
(`codeRead`는 원래도 정확했다 — `header.py:1469`의
`local_name(child) == "trackChange"` 직접비교가 디스패치 윈도로 이미
잡혔다. 틀렸던 건 쓰기 쪽뿐이다.)

**게이트 ① 증거(결함-부활)**: 두 항목 모두 `tests/test_coverage_ledger.py`에
전용 회귀 테스트가 있다 — 화이트리스트 딕셔너리를 몽키패치로 비운 뒤
**실제 소스 파일**(`history_part.py`/`header.py`, 스트립·디스패치윈도
동일 파이프라인)을 재분류해 위음성이 재현됨을 확인하고, 원복 후 고쳐짐을
확인한다:
- `test_manual_override_reproduces_hhs_diff_op_family_read`
- `test_manual_override_reproduces_track_change_family_write`

### A.2 원장 전 vs 후

| 지표 | 수리 전 | 수리 후 |
|---|---|---|
| 코드 읽기(전체 345요소) | 229 | **233**(+4, hhs:) |
| 코드 쓰기 api(전체 345요소) | 171 | **173**(+2, trackChange) |
| write=none(corpusFileCount>0 슬라이스, 229요소) | 46 | **44**(-2) |
| read=none(같은 슬라이스) | 31 | 31(불변 — hhs: 4요소는 corpusFileCount=0이라 이 슬라이스 밖) |

`python scripts/coverage_ledger.py --check` → `in sync`.

### A.3 사이클 6.1~6.4 산출물 원장 환류 전수 대조표

방법: 원장 수리 직후 커밋(`d45d072`, 사이클 6.1의 0번째 커밋)의
`docs/coverage-ledger.json`을 기준선으로 잡고, 현재(HEAD)와 요소별
`(codeRead, codeWrite)` 튜플을 전부 diff했다 — **표본이 아니라 두 시점의
전체 345요소 대조**다. 결과: **50개 요소**가 전환됐다. (이관 요청은
"36종"으로 어림했으나, 실측 전수는 50이다 — 46개는 사이클 6.1~6.4의
14개 기능 트레인이 낸 산출물이고, 4개는 §A.1①의 이번 수리분이다. 추정치와
실측치가 다른 것 자체를 숨기지 않는 것이 이 문서의 원칙이다.)

각 트레인은 커밋 메시지가 감사 판정문 §2의 갭 번호를 직접 인용하는
경우가 많아(`Audit gap #N`), 그 인용과 코드의 실제 태그 리터럴 위치
비교로 귀속을 확정했다. 표본 3건은 독립 재확인했다(아래 "직접 확인"
표시) — `_HH`/`_HP` 별칭이 아닌 실제 `_append_child`/`makeelement`
호출을 직접 읽어, 원장의 자기 판정과 다른 방법으로 검증했다.

| 트레인(커밋) | 감사 갭# | 전환 요소(빈도) | 검증 |
|---|---|---|---|
| `7914b18` doc.styles.ensure_font | #1 글꼴 선언 | `hh:font`(237)·`fontface`(237)·`fontfaces`(237): frozen→api · `substFont`(177): none→api | 직접 확인 — `header_part.py:153,1103,1183`의 `makeelement`/`append` |
| `a144733` tab-stop 저작 | #2 탭 정의 | `hh:tabItem`(182): none→api · `tabPr`(237)·`tabProperties`(237): frozen→api | 커밋 메시지(`apply_paragraph_format(tab_stops=)`) |
| `c38bf07` 옵션·호환성 읽기 | #13(R1 후속) | `ha:CaretPosition`(237)·`HWPApplicationSetting`(237): frozen read False→True · `hh:layoutCompatibility`(237): frozen read False→True | 커밋 메시지 — R1 반증이 지목한 정확히 그 요소들 |
| `3d4e038` 도형텍스트·캡션 | #3·#4 | `hp:caption`(27)·`drawText`(42)·`textMargin`(42): none→api | 커밋 메시지 |
| `e1fad75` 형광펜 저작 | #5 | `hp:markpenBegin`(23)·`markpenEnd`(23): none→api | 기존 화이트리스트(`_MANUAL_CODE_USAGE_OVERRIDES`, 감사 트레인에서 이미 등재) |
| `37ebd2d` 이미지·그라데이션 채우기 | #6 | `hc:color`(2)·`gradation`(2)·`imgBrush`(100): none→api | 직접 확인 — 커밋 메시지 "Ledger flips imgBrush/gradation/color/img to api" |
| `530d75a` 메모 모양 저작 | #9 | `hh:memoPr`(59)·`memoProperties`(59): none→api | 커밋 메시지(`ensure_memo_shape`) |
| `300ef8d` 쪽번호 심부 | #10 | `hp:newNum`(13)·`pageHiding`(3): none→api | 직접 확인 — `paragraph.py:843-848,872-877`의 `_append_child(ctrl, f"{_HP}newNum", ...)` |
| `eea22c7` 문자서식 잔여 | #8 | `hh:emboss`(0)·`engrave`(0)·`outline`(222)·`subscript`(0)·`supscript`(10): none/frozen→api | 커밋 메시지(실코퍼스 charPr id=513 리버스) |
| `f114414` ParameterList 범용화 | #11 | `hp:floatParam`(0)·`listParam`(1)·`unsignedintegerParam`(1): none→api · `listItem`(1): read만 True(write는 여전히 none — 조회 전용) | 커밋 메시지 + DEV-011(`docs/owpml-deviations.md`) |
| `6f88e2e` hp:compose 타입화 | #14 부분 | `hp:charPr`(3): none→api · `compose`(3): read만 True(write는 여전히 none — 타입 있는 읽기 모델만 추가, 저작 API는 다음 사이클 몫) | 커밋 메시지 |
| `20d95d2` 다각형 저작 | #7 부분 | `hp:polygon`(2): none→api · `hc:pt`(2, 폴리곤/호 공유): none→api | 커밋 메시지 + 지원 매트릭스 |
| `2ed6df5` 호(arc) 저작 | #7 부분 | `hp:arc`(1): none→api(`curve`/`connectLine`은 정직 보류 유지, §4 아님) | 커밋 메시지 |
| `1e9c0c8` 파트 계층 읽기모델 | #15 | `hm:masterPage`(0)·`subList`(0) · `hp:masterPage`(1) · `hv:version`(0) · `hhs:bodyDiff/headDiff/history/historyEntry/packageDiff/tailDiff`(0×6): none→read True(write는 구조상 계속 none — 읽기 전용 파트) | 커밋 메시지 + DEV-007/DEV-015(`docs/owpml-deviations.md`) |
| **(이번 세션 수리)** | — | `hhs:insert/update/delete/position`(0×4): read False→True | §A.1① — 트레인 15가 실제로 구현했으나 원장이 놓쳤던 4요소, 이번에 환류 완결 |

**대조 결론**: 14개 트레인이 낸 46개 전환 + 트레인 15가 실제로 구현했지만
원장이 놓쳤던 4개(§A.1①) = 50개 전부, 코드 실재와 원장 판정이 지금
일치한다. 감사 §2가 나열한 15개 기능군 중 #12(개체 시각효과)와 "기능
축"(차트 확장·문서병합·암호화)을 제외한 전부가 이번 사이클에서 처리됐다
(#12·잔여 기능축은 원래도 "저빈도 후순위 타당"으로 재검증 통과했던
항목이라 미착수가 정상 상태다).

---

## Part B. 차기 갭 지도

### B.1 요소 축 — 실코퍼스(237파일) 잔여 갭 63건

수리된 원장 기준, `corpusFileCount>0`이면서 `codeWrite≠api` 이거나
`codeRead=False`인 요소 전부를 파일수 내림차순으로 정리했다. "가산 경로"는
감사 판정문 §1.3의 4갈래(① 라이브 객체에 속성 추가 ② 네임스페이스에 메서드
추가 ③ 기존 ensure_*/apply_*에 kwarg 추가 ④ 파트 접근자 추가)를 그대로
쓴다.

| 요소군 | 대표 요소(빈도) | 가산 경로 | 난이도 | 상태 |
|---|---|---|---|---|
| 시스템/호환성 설정값(저작) | `ha:CaretPosition`/`HWPApplicationSetting`(237)·`hc:intent/left/right/prev/next`(237, margin 좌표계 공유)·`hh:autoSpacing/compatibleDocument/docOption/head/layoutCompatibility/linkinfo`(237)·`hh:typeInfo`(231)·`hh:metaTag`(10) | ①/④ | 중 | **읽기 완료(c38bf07), 저작 미착수.** §4-③ 후보 |
| **`hp:switch`/`case`/`default`(236/237) — 버전호환 분기 wrapper** | 위 3요소 | ① | 중 | **낮은 위험으로 재분류.** 스키마 미선언(census-only), `hp:case@hp:required-namespace`로 게이트된 신버전 값과 `hp:default`의 구버전 폴백을 담는 `hh:paraPr` 내부 구조 — 근본값(`hh:margin`/`hh:lineSpacing`)은 이미 `header_part.py:605-635`의 `_descendants_by_local`이 **두 분기 모두** 정확히 갱신한다(`table_patch.py:1341` 주석이 같은 사실을 다른 자리에서 재확인). 남은 갭은 wrapper 자체를 1급 타입으로 노출하는 것뿐 — 저작 정확성 버그는 아니다 |
| **그룹 개체(컨테이너)** | `hp:container`(67) | ① | 중 | **미착수, 신규 발견.** 다른 도형을 묶는 그룹 컨테이너(실측: `error__20230818__test.hwpx`, `hp:connectLine`을 자식으로 가짐) — 지원 매트릭스가 이미 "그룹·효과 등 복잡 개체 생성은 미지원"으로 명시한 항목. §4-① 후보 |
| 라벨 인쇄 레이아웃 | `hp:label`(64, 오너 사설 코퍼스 전용 — 벤더드 47파일엔 0건) | ① | 중~상(실물 확보 필요) | **미착수, 신규 발견.** 스키마상 `topmargin/leftmargin/boxwidth/boxlength/labelcols/labelrows/landscape` — Avery류 라벨시트 인쇄 레이아웃(mail-merge형 문서와 연계 가능성). 재현 가능한 실물이 이 레포 밖(오너 사설 코퍼스)에만 있어 우선순위는 다음 순번 |
| 특수 인라인 텍스트 원자 | `hp:fwSpace`(45)·`hp:nbSpace`(21)·`hp:lineBreak`(32) | ③ | 하 | **미착수, 신규 발견.** `hp:RunChoice`에서 `hyphen`/추적변경 마크와 같은 자리에 있는 형제 원자(전각공백/비분리공백/줄바꿈) — 읽기(추출)는 되지만 저작 API가 없어, 저작된 텍스트에 사용자가 비분리공백을 요청해도 평문 공백으로만 방출된다(내용 충실도 리스크). §4-② 후보 |
| `hp:lineseg`(213)·`seg`(1) | 렌더 캐시 | — | — | **frozen 유지가 정답.** 한컴이 저장 시 계산해 넣는 줄배치 캐시 — 우리가 독립 저작하면 오히려 위험(감사가 이미 이 성격을 인지). 조치 불필요 |
| `hp:case`/`default`/`switch` 형제인 `hp:compose`(3) 저작 | 트레인 6f88e2e가 읽기만 완결 | ① | 하 | 타입 읽기 모델 있음, 저작(신규 `hp:compose` 삽입 API)만 남음. 저빈도(3파일)라 후순위 |
| 곡선류 잔여 | `hc:extent`(2)·`hp:connectLine`(2)·`endPt`(2)·`startPt`(2)·`curve`(1)·`controlPoints`(1) | ② | 상 | **의도적 보류 유지(재검증 통과).** 지원 매트릭스가 명시: curve는 앵커점 밖으로 부풀어 실측 근거 없음, connectLine은 유일 정본이 스마트연결(`subjectIDRef`)이라 자유선 계약 불명 |
| 체크박스류 잔여 | `hp:btn`(1)·`radioBtn`(1) | ② | — | **오너 결정 보류 유지**(방향 문서 §6, 빈도 컷) |
| 개체 시각효과 | `hp:glow/reflection/softEdge/skew/scale/rgb/effect/effectsColor`(각 1) | ① | 상 | **감사 판정 유지 — 저빈도 후순위 타당.** 재센서스에서도 여전히 각 1파일 |
| 필드 파라미터 잔여 | `hp:parameterset`(1, read=False) | ①/④ | — | **재검증 플래그**(수리 아님): DEV-011(`docs/owpml-deviations.md`)이 "implemented"로 표기하지만, `parse_parameter_list_element`(`body.py:793`)는 유닛테스트(`tests/test_coverage_promotion.py`)에서만 직접 호출되고 `parse_preserved_element`(`body.py:813-846`)의 실 디스패치 체인엔 없다 — 실 문서를 파싱할 때 이 경로를 실제로 타는지 다음 세션에서 확인 필요 |
| 신규 발견 저빈도 | `hh:forbiddenWord/forbiddenWordList`(3, 금칙어 교정설정)·`hp:alpha/dutmal/edit/effect/effectsColor/glow/hiddenComment/mainText/metaTag/point/presentation/reflection/rgb/scale/skew/softEdge/subText/text/textartPr/titleMark/comboBox/textart/video/ole`(각 1~2) | 다양 | 다양 | 전부 corpus 1~2파일 — 빈도컷 기준 후순위 타당. 문서화만 하고 다음 사이클로 이연 |

### B.2 요소 너머 — 기능군 관점 (원장이 못 재는 축)

원장은 "요소를 읽는가/쓰는가"만 잰다. 아래는 기존 문서 3종(감사 §2 기능
축 행·지원 매트릭스의 명시적 미지원·capabilities 레지스트리의 fail-closed
목록)을 종합한, 요소 단위가 아닌 갭이다.

1. **저수준 도형·컨트롤 탈출구의 무음 위험** (지원 매트릭스 §"저수준
   도형·컨트롤 탈출구"). `add_shape`/`add_control`은 받은 속성만 쓰고
   OWPML 필수 하위요소(`offset`/`orgSz`/`curSz`/`sz`/`pos`/유형별 기하)를
   만들지 않는다 — 그대로 저장한 문서를 실한컴 12.30.0이 **거부**한다(음성
   대조로 확인됨). 신호는 생성 시점 `UserWarning` 하나뿐이고
   `validate_package`/`validate_editor_open_safety`는 둘 다 통과시킨다
   (`ok=True`인데 실한컴은 거부). 이것은 요소 커버리지 문제가 아니라
   **탈출구 API의 안전장치 갭**이다 — 저장 시점 검증에 이 특정 위험을
   추가하는 게 다음 사이클 후보다.
2. **openrate v5~v8 실한컴 검증 증거가 원장에 환류되지 않음.** 원장의
   `verificationBasis` 메커니즘은 `docs/openrate/report-v4.json`만
   읽는다(`OPENRATE_V4_PATH` 상수 하드코딩). 그런데 이 사이클 자체가
   `report-v5.json`(캡션·drawText·fontface·tabstops, 감사 §2 #1~#4 실증)·
   `v6.json`(fill·highlight·memoshape·pagecontrol, #5·#6·#9·#10 실증)·
   `v7.json`(charformat·fieldparams, #8·#11 실증)·`v8.json`(arc·polygon,
   #7 실증)을 이미 실한컴으로 측정해 커밋해 뒀다 — 이 지도 §A.3의 트레인
   14개 중 대다수가 이미 render-verified인데, 원장의 `renderVerified`
   요약(48개)과 지원 매트릭스 산문("실한컴 렌더 검증은 사이클 말 배치로
   미뤘다") 둘 다 이 사실을 반영 못 한다. **측정 정밀화 축으로는 최우선
   후보**(§4-④) — v4 배선을 그대로 확장하면 되는 저난이도 작업이다.
3. **암호화 HWPX·HWP 5.x 바이너리 — fail-closed 확인, 조치 불필요.**
   `capabilities.py:207-217`이 `namespace: None`(저작 표면 자체가 없음)으로
   등재하고 있고, 지원 매트릭스도 "무음으로 잘못된 문서를 만들지 않음"으로
   명시한다 — 의도된 거부이지 갭이 아니다.
4. **곡선/연결선·체크박스 라디오·개체효과** — B.1에서 이미 표기한 대로
   전부 기존 보류 근거가 재검증에서 살아남았다. 요소 축과 기능군 축이
   같은 결론에 수렴한다.

---

## Part C. 사이클 6.5 트레인 제안

빈도 × 실코퍼스 근거 × 이번 감사 실증을 기준으로, 저작 가능성이 실물로
뒷받침되는 항목만 골랐다.

### 트레인 제안 ① — 그룹 개체(컨테이너) 저작

- **대상**: `hp:container`(67파일) — `doc.shapes.group()`류 API, 자식
  도형 id 목록을 받아 컨테이너로 묶는다.
- **실물 근거**: `tests/fixtures/hwpxlib_corpus/error__20230818__test.hwpx`
  (그룹 컨테이너가 `hp:connectLine`을 자식으로 가짐 — 벤더드, 재현 가능).
- **가산 경로**: ①(Shape 계열에 새 서브타입 추가, 기존 시그니처 무영향).
- **게이트 초안**: (a) 실 컨테이너 문서 리버스로 자식 배치 규칙 확정
  (b) `add_container`/`doc.shapes.group` 왕복 테스트 (c) 실한컴 오라클
  스모크(render-verified) (d) 지원 매트릭스 "그룹·효과 등 복잡 개체 생성은
  미지원" 문구 갱신.

### 트레인 제안 ② — 특수 인라인 텍스트 원자 저작

- **대상**: `hp:fwSpace`(45)·`hp:nbSpace`(21)·`hp:lineBreak`(32) — 이미
  읽기(추출)는 되므로, `ensure_run`류에 특수문자 삽입 kwarg 또는 헬퍼
  추가.
- **실물 근거**: 세 요소 모두 `hp:RunChoice`(`ParaList XML
  schema.xml:290-297`)에 이미 스키마 선언돼 있고 실코퍼스 다건 관측.
- **가산 경로**: ③(기존 run 저작 경로에 kwarg 추가, 하위호환 보장).
- **게이트 초안**: (a) 세 원자를 텍스트 삽입 API에서 지정 가능하게
  (b) 왕복 시 평문 공백/개행으로 오염되지 않음을 바이트 비교로 증명
  (c) 실한컴 렌더 확인.

### 트레인 제안 ③ — openrate v5~v8 검증 증거 원장 환류 (측정 정밀화)

- **대상**: 원장 코드(`OPENRATE_V4_PATH`/`_V4_STRATUM_TO_CAPABILITY_AREA`)를
  v5~v8까지 확장 — **새 기능 없음, 이미 존재하는 실한컴 증거를 원장·지원
  매트릭스에 정확히 반영**.
- **난이도**: 하 — v4 배선 패턴을 그대로 재사용.
- **가치**: `renderVerified` 요약과 지원 매트릭스 "검증 미뤘다" 문구가
  실제로는 이미 검증된 사이클 6.1~6.4 트레인 다수를 과소 보고 중인 것을
  바로잡는다 — Q1이 복구한 "진실 축" 원칙과 직결.
- **게이트 초안**: (a) v5~v8 strata → capabilityArea 매핑 근거 문서화
  (b) 원장 재생성 후 `renderVerified` 수 증가를 커밋 메시지에 실측 기록
  (c) 지원 매트릭스 "사이클 말 배치로 미뤘다" 문구를 실제 상태로 갱신.

### 보류/다음 순번 (실물 확보 또는 오너 결정 필요)

- **`hp:label`(라벨 인쇄 레이아웃, 64파일)**: 벤더드 코퍼스에 실물이 없어
  구조 확정이 사설 코퍼스에 의존 — 실물 1건 이상 확보 후 착수.
- **문서 옵션·호환성 저작 마감**(`hh:layoutCompatibility` 등, 237파일):
  읽기는 끝났고 저작만 남았으나, 사용자가 실제로 이 값을 프로그램적으로
  바꿀 수요가 낮다(시스템/앱 설정값) — 엔진 완전성 표면상 마지막 "code-blind
  0" 잔여를 닫는 상징적 가치는 있으나 다음 순번.
- **`hp:parameterset` 배선 재검증**: B.1에 기록한 DEV-011 정확성 질문 —
  버그인지 확인 우선, 그 결과에 따라 후속 트레인 여부 결정.

---

## 부록 — 게이트 증거

- **① 결함-부활**: `tests/test_coverage_ledger.py::test_manual_override_reproduces_hhs_diff_op_family_read`,
  `::test_manual_override_reproduces_track_change_family_write` — 둘 다
  실 소스파일 재분류로 OFF/ON 재현.
- **② `--check`**: `coverage ledger in sync`.
- **③ 36(실측 50)종 환류 대조**: §A.3.
- **④ 전 스위트**: `2563 passed, 18 skipped, 1 xfailed`(기준 2561, +2 신규
  테스트, 실패 0) — `HWPX_ORACLE_STRUCTURAL_ONLY=1`.
- **⑤ 정적 검사**: `mypy` — `Success: no issues found in 81 source files`.
  `pyright`(올바른 venv 파이썬 지정) — `0 errors, 0 warnings, 0
  informations`.
- **⑥ 본 문서**.
