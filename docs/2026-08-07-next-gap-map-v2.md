# 차기 갭 지도 v2 — 사이클 6.7 트레인 ㉔ 원장 재스캔

> 작성: 사이클 6.7 트레인 ㉔ (2026-08-07). 브랜치 `feat/cycle-6.1`. HEAD
> `d64a5ec`(v10 실한컴 배치) + 트레인㉔a(v10 원장 환류, `ba94f82`).
> 전제: `docs/2026-08-06-next-gap-map.md`(사이클 6.5 트레인⑯ 작성)의 갭
> 지도는 사이클 6.5~6.6(트레인⑰~㉓ + 두 정리 트레인)에서 부분 소진됐다 —
> 이 문서가 그 뒤를 잇는다. 옛 문서의 Part D(트레인㉑ 발견, tabPr 부록)는
> 별도 절이 아니라 이 문서 본문(§B.3)에 통합했다 — 이미 트레인㉕로
> 승격됐으므로 "부록"이 아니라 "다음 트레인 스펙"으로 읽혀야 한다.

## 요약 (TL;DR)

| 항목 | 결과 |
|---|---|
| 분류기 재검토 | 고빈도 갭 후보 5종 정밀 점검(`hh:forbiddenWord(List)`·`hp:compose`·`hc:margin` 자식 4종·form 컨트롤류·`hp:masterPage`) — **신규 위음성 0건**, 전부 정확한 분류로 판명(근거 §A) |
| 원장 상태 | 재생성 `--check` in sync. 345요소 중 코드 읽기 233(트레인⑯ 시점)→**239**, 쓰기(api) 173→**182** |
| openrate 환류 | v10 배선 완료(트레인㉔a, `ba94f82`) — `renderVerified` 78→**83**, `renderVerifiedByOpenrateCorpus` 47→**52** |
| 실코퍼스(237파일) 잔여 갭 | write≠api 이거나 read=False인 요소 **63→54개**(-9: `hp:container`+원자 3종+문서옵션 5종 완전 해소, `hp:parameterset`·`hp:switch`/`case`/`default`는 읽기만 승격돼 여전히 슬라이스 안 — 의도적) |
| 최우선 실결함(이미 트레인㉕로 승격) | `hh:tabPr`의 `hp:switch` 중첩 시 실 소비 경로(`doc.styles.tab_properties`)도 탭 스톱을 조용히 빈 값으로 오판(§B.3) |
| 회귀 | 전 스위트 2701 유지(트레인㉔a는 순수 배선, 신규 테스트 불필요) |
| 정적 검사 | mypy(공식 게이트, 82파일) 0 · pyright 0 |

---

## Part A. 분류기 재검토 (사이클 6.5 트레인⑯ 방법론)

같은 방법론: 갭 슬라이스 상위 후보를 코드 직접 읽기로 점검하고, 위음성
의심이면 결함-부활(끄고 재현→켜고 수리 확인)로 증명한다. 이번 라운드는
**신규 위음성을 찾지 못했다** — 아래 5개 후보 전부 원장의 기존 분류가
정확했다. "버그를 못 찾았다"는 것 자체가 이 라운드의 실측 결과다(찾은
척 안 한다).

### A.1 `hh:forbiddenWord`/`forbiddenWordList` (3파일, read=True·write=none)

`parse_forbidden_word_list`(`header.py:1193`)가 `parse_header_element`의
조립 체인에 실제로 배선돼 있다(`header.py:1656`,
`header.forbidden_word_list = parse_forbidden_word_list(child)`) — 원장의
`read=True` 판정이 정확하다. 저작 API(`add_forbidden_word` 류)는 어디에도
없다 — `write=none`도 정확. **결론: 정확한 분류, 위음성 아님.**

### A.2 `hp:compose`(3파일, read=True·write=none)

`_composed_character_to_xml`(`body.py:1110`)가
`etree.Element(_qualified_tag(composed.tag, "compose"), attrs)`로 요소를
**만들기는** 한다 — 얼핏 write=api로 잡혀야 할 것처럼 보인다. 하지만
`_qualified_tag(tag, name)`(`body.py:353`)는 `tag`(파싱 때 보존된 원본
태그)가 있으면 그걸 그대로 쓰고, 없을 때만 `f"{_DEFAULT_HP}{name}"`으로
새로 짓는다 — 즉 이 함수는 **이미 파싱된 개체를 왕복 보존**하는 경로에서만
실제로 호출된다(`_preserved_element_to_xml`의 `isinstance` 디스패치,
저장 시 전 개체에 일괄 적용). "빈 데서 `ComposedCharacter`를 새로 만들어
붙이는" 공개 API(`add_composed_character` 류)는 어디에도 없다 — 즉
코드는 태그를 구성하지만 **그 경로가 실제로 새 태그를 짓는 경우는 없다**
(항상 원본 태그를 재사용). 원장의 write 판정 철학("태그를 만드는가")은
정적 패턴 기준이라 이 구분까지는 못 잡지만, 실제 저작 표면 유무로 보면
`write=none`이 실상과 맞다. **결론: 결이 다른 이유로 신중한 판정이 맞았다
(위양성 방지 쪽으로), 수리 대상 아님.**

### A.3 `hc:intent`/`left`/`next`/`prev`/`right`(237파일, read=True·write=frozen-template)

`_apply_paragraph_margins`(`header_part.py:605`)가 이 값들을 실제로
**갱신**한다(`_set_margin_unit_value`가 `element.set("value", ...)`)길래
write=api로 보일 수 있다. 하지만 이 원장의 write 정의는 명시적으로 "태그를
**만드는가**"이지 "속성을 바꾸는가"가 아니다(모듈독스트링: "makeelement/
SubElement/_append_child/etree.Element(/여는 태그 리터럴 근방이면 쓰기").
`_apply_paragraph_margins`의 실제 생성 경로(`margin.makeelement(f"{_HH}
{name}", {})`)는 `hh:` 네임스페이스로만 새 자식을 짓는다 — 기존
`hc:left` 등을 찾으면 그건 그대로 재사용(속성만 덮어쓰기)하고, 없을 때만
`hh:` 이름으로 새로 짓는다. 즉 `hc:` 네임스페이스 자체를 코드가 **지은
적은 없다**(항상 Skeleton.hwpx나 원본 문서에서 물려받은 것만 변형) —
`write=frozen-template`이 정확히 이 상황을 위한 등급이다. **결론: 정확한
분류, 위음성 아님(속성-변형과 태그-구성을 구분하는 원장 철학이 의도대로
작동).**

### A.4 form 컨트롤류(`hp:edit`/`comboBox`/`listItem`, 각 1파일, read=True·write=none)

`FormEditControl`/`FormComboBoxControl`/`ListItem` 읽기 모델은 있고
(`header.py`/`body.py`), `add_form_field`(누름틀 저작, 5.1.0+)는 **다른**
메커니즘(`hp:fieldBegin` 기반 CLICKHERE 계약)으로 저작한다 — `hp:edit`/
`hp:comboBox`류 원시 컨트롤을 직접 짓는 공개 API는 없다. **결론: 정확한
분류, 위음성 아님(누름틀 저작 표면과 이 원시 컨트롤 읽기 모델은 서로
다른 것을 가리킨다).**

### A.5 `hp:masterPage`(1파일, read=True·write=none)

`MasterPage`/`parse_master_page` 읽기 모델은 있지만(`master_page.py`),
`grep -rn "master_page.*to_xml\|def add_.*master"`가 전무 — 직렬화기 자체가
없다. **결론: 정확한 분류, 위음성 아님(순수 읽기 전용, 저작 표면 자체가
부재).**

---

## Part B. 요소 축 — 실코퍼스(237파일) 잔여 갭 54건

`corpusFileCount > 0`이면서 `codeWrite != "api"` 또는 `codeRead == False`인
슬라이스. 트레인⑯ 시점 63건에서 **-9**: `hp:container`(트레인⑱)+
`hp:lineBreak`/`nbSpace`/`fwSpace`(트레인⑲)+`hh:compatibleDocument`/
`layoutCompatibility`/`docOption`/`linkinfo`/`hh:autoSpacing`(트레인㉓)
전부 write=api로 전환돼 슬라이스에서 빠졌다. `hp:parameterset`·
`hp:switch`/`case`/`default`는 **읽기만** True로 승격했을 뿐(트레인⑳·㉑)
쓰기는 의도적으로 `none`/`frozen-template`에 남아 있어 슬라이스에 그대로
있다 — 이건 결함이 아니라 각 DEV 항목(DEV-011·DEV-018)이 이미 문서화한
설계다.

### B.1 고빈도 잔여(≥10파일)

| 요소 | 파일수 | read | write | 비고 |
|---|---:|---|---|---|
| `ha:CaretPosition` | 237 | True | frozen-template | settings.xml, 정확한 분류(§A.3와 같은 철학) |
| `ha:HWPApplicationSetting` | 237 | True | frozen-template | settings.xml 루트, 상동 |
| `hc:intent`/`left`/`next`/`prev`/`right` | 237 | True | frozen-template | §A.3에서 재검토·정확 확인 |
| `hh:head` | 237 | True | frozen-template | 문서 루트 자체, 코드가 직접 짓지 않음(항상 Skeleton 유래) |
| `hp:switch`/`case`/`default` | 236 | True | frozen-template | DEV-018 — 읽기 모델 구현됨(트레인㉑), 저작은 의도적 미제공(저작 경로는 이미 안전) |
| `hh:typeInfo` | 231 | True | frozen-template | 폰트 타입 메타, 미조사(다음 라운드 후보) |
| `hp:lineseg` | 213 | True | frozen-template | 레이아웃 산출값(한컴이 계산), 코드가 지을 대상이 아님 — 정확 |
| `hp:label` | 64 | **False** | none | **§B.2 최우선** — 유일한 read=False 고빈도 요소, 사설 코퍼스 필요(트레인㉖) |
| `hh:metaTag` | 10 | True | frozen-template | 미조사(다음 라운드 후보) |

### B.2 `hp:label`(라벨 인쇄 레이아웃, 64파일·27%) — read=False인 유일 고빈도 요소

벤더드 코퍼스(47파일)엔 실물이 없어 구조 확정이 사설 코퍼스에 의존한다.
**트레인㉖로 이미 배정**: `topmargin`/`leftmargin`/`boxwidth`/`boxlength`/
`labelcols`/`labelrows`/`landscape` 실측 분포를 사설 코퍼스에서 리버스하고,
합성 픽스처(사설 파일 자체는 벤더드 픽스처에 편입 금지)로 읽기 모델 +
왕복 보존 테스트. 저작 API는 계약 확신이 서면 포함.

### B.3 `hh:tabPr`의 `hp:switch` 중첩 — 실 소비 경로도 탭 스톱을 잃는다(최우선 실결함, 트레인㉕로 승격)

트레인㉑이 `hh:paraPr`의 `hp:switch` 중첩(DEV-018)을 읽기 모델에서
수리하며 같은 패턴이 다른 곳에도 있는지 확인하다 발견 — `hp:switch`는
`hh:paraPr`뿐 아니라 `hh:tabPr`도 감싼다:

```
{'tabPr': 449, 'paraPr': 1803, 'run': 1}  # hp:switch의 부모 태그별 실측(47파일)
```

`hp:run` 1건은 DEV-021로 별도 등재(§B.4) — `hp:chart`/`hp:ole` 대안 선택,
구조가 전혀 다르다. **`hh:tabPr` 449건은 이번 사이클(6.6) 범위 밖이라
손 안 댔다.**

처음엔 "`TabDefinition`/`parse_tab_definitions`가 애초에 안 쓰인다"는
DEV-011류 미배선 가설을 세웠으나 **grep으로 확인하니 틀렸다** — 정정한다:

- `Header.to_model()`의 전체 스냅샷 경로(`parse_header_element` →
  `parse_ref_list`)는 확실히 미배선이다: `RefList.tab_properties` 필드는
  `TabProperties.tabs: List[GenericElement]`(불투명)를 쓰고,
  `TabDefinitionList`/`parse_tab_definitions`는 `header.py`에 정의·
  `__all__` export만 될 뿐 `parse_ref_list` 어디에서도 호출되지 않는다.
- 하지만 **별도의, 실제로 쓰이는 접근자**가 있다:
  `HwpxOxmlHeader.tab_properties`(프로퍼티, `header_part.py:1438`)가
  `parse_tab_definitions`를 직접 호출해 `TabDefinition`을 만들고,
  `doc.styles.tab_properties`/`tab_property()`(`_document/ns/styles.py`)로
  공개 노출돼 있다. **실 소비 경로가 있다.**

그런데 **이 실제로 쓰이는 접근자도 switch 중첩 앞에서 조용히 진다** —
실측 확인(`error__20230413__test.hwpx`, id=1~4 tabPr 전부 `hp:switch`의
`hp:case`/`hp:default` 양쪽에 `hh:tabItem`을 가짐):

```python
doc = HwpxDocument.open("error__20230413__test.hwpx")
tab_props = doc.styles.tab_properties
# {'0': TabDefinition(tab_stops=[]), '1': TabDefinition(tab_stops=[]), ...}
# 전부 tab_stops=0 -- 실제로는 각 분기에 hh:tabItem이 있는데도
```

원인은 `parse_tab_definition`(`header.py`)의 `tab_stops` 계산이 **직속
자식만** 훑기 때문 — DEV-018 수리 전 `parse_paragraph_property`의
margin/lineSpacing과 정확히 같은 모양의 결함이지만, 이번엔 **값이 아예
사라진다**는 점에서 더 나쁘다(margin/lineSpacing은 `None`이 됐을 뿐인데,
`tab_stops=[]`는 "탭 스톱이 없다"는 것과 "switch 안에 있어서 못 찾았다"를
구분 못 해 호출자가 커스텀 탭 스톱이 전혀 없다고 잘못 믿게 된다).

**트레인㉕ 스펙(이미 배정, 순서상 다음)**:
1. `parse_tab_definition`이 DEV-018 수리와 같은 자손-순회(또는 switch
   case/default 인지)로 tabItem을 찾도록 배선 — 결함-부활:
   `error__20230413__test.hwpx` id=1~4 재현(5/5 빈 값)→수리 후 실값
   확인(원시 tabItem 116건 대조).
2. **저작 쪽도 판정**: `ensure_paragraph_format(tab_stops=)`류가 switch로
   감싸인 기존 tabPr을 편집할 때 margin처럼 양 분기를 갱신하는지 실측 —
   아니면 갱신 경로도 같이 수리(이 경우 저작 표면 변화이므로 v11 스트라텀
   후보로 보고).
3. 수리 후 DEV-018/DEV-019 계열로 정식 등재(직속 vs 중첩 비율, 양쪽 분기
   값이 갈리는 실사례 유무까지).

### B.4 `hp:switch`의 세 번째 맥락 — `hp:run` 안에서 개체 대안 선택(DEV-021, 이미 등재됨)

정리 트레인(사이클 6.6)에서 이미 DEV-021로 등재·프로브 완료
(`probes/dev021_switch_as_inline_object_alternate.py`). 요약만: `hp:run`
직속 자식으로 `hp:switch`가 등장(`error__20230426__HwpxTest1.hwpx`, 1건)
— `hp:case`가 `hp:chart`(2016 OOXML), `hp:default`가 `hp:ole`(레거시)를
감싼다. DEV-018/B.3(같은 값 두 벌)과 달리 **같은 개체의 다른 표현 두
종**. 무손실 재확인됨, 타입 읽기 모델은 다음 사이클 후보(이번엔 안 만듦
— `add_chart` 저작 경로가 이 분기를 안 쓰고, 실측 1건뿐이라 계약 확정
근거 부족).

### B.5 저빈도 잔여(1~2파일, 32개) — 빈도컷 후순위 유지

`hc:extent`(2)·`hp:connectLine`(2, DEV-013 정직 보류 유지)·`hp:endPt`/
`startPt`(2, 각각 다른 도형에서 이미 대응됨 — DEV-012)·`hp:ole`(2)·
`hp:alpha`/`btn`/`comboBox`/`controlPoints`/`curve`/`dutmal`/`edit`/
`effect`/`effectsColor`/`glow`/`hiddenComment`/`listItem`/`mainText`/
`masterPage`/`metaTag`/`parameterset`/`point`/`presentation`/`radioBtn`/
`reflection`/`rgb`/`scale`/`seg`/`skew`/`softEdge`/`subText`/`text`/
`textart`/`textartPr`/`titleMark`/`video`(각 1) — 전부 corpus 1~2파일,
빈도컷 기준 후순위 타당. 이 중 `btn`/`radioBtn`은 지원 매트릭스 자신이
"읽기·보존만, 저작 API 없음"이라고 명시(체크박스 양식개체 행) — 정직
보류이지 갭 아님.

---

## Part C. 요소 너머 — 기능군 관점 (원장이 못 재는 축)

옛 지도(§B.2)의 판정이 재검토에서도 그대로 살아남았다 — 요소 축과 기능군
축이 같은 결론에 수렴한다:

1. **저수준 도형·컨트롤 탈출구의 무음 위험** — **트레인㉒로 이미 수리됨**
   (`ec9079d`, 사이클 6.6). `validate_package`/`validate_editor_open_
   safety`가 이제 이 위험을 warning으로 표면화한다(fail-closed 아님).
2. **openrate v5~v10 실한컴 검증 증거의 원장 환류** — **트레인⑰·⑳·㉔a로
   전부 완료됨**. `renderVerified` 요약이 이제 실제 상태를 정확히
   반영한다.
3. **암호화 HWPX·HWP 5.x 바이너리** — fail-closed 확인, 조치 불필요
   (변화 없음).
4. **곡선/연결선·체크박스 라디오/명령단추·개체효과** — 전부 기존 보류
   근거가 재검토에서도 살아남았다(§B.5).

---

## Part D. 다음 사이클 후보 (이 사이클 4트레인 이후)

- **`hp:typeInfo`/`hh:metaTag`**: 고빈도(231·10파일)인데 이번 라운드에서
  미조사 — 다음 재스캔 우선순위.
- **`hh:tabPr` 배선(§B.3)**: 이미 트레인㉕로 확정, 이 문서 작성 시점
  기준 "다음"이 아니라 "지금 진행 중".
- **`hp:label`(§B.2)**: 이미 트레인㉖로 확정.
- **워크스페이스 편차 레지스트리 이식**: 이미 트레인㉗로 확정
  (`python-hwpx-s120` specs/063 17항목 중 공개 미등재분).
- **`hp:switch`의 네 번째 맥락 존재 가능성**: 이번 재스캔이 확인한 맥락은
  `hh:paraPr`(DEV-018)·`hh:tabPr`(§B.3)·`hp:run`(DEV-021) 3종뿐이다 —
  전수 스캔은 안 했으므로(위 3종은 각 발견 과정에서 우연히 나온 것) 다음
  재스캔 라운드에서 `hp:switch`의 부모 태그 전체 분포를 한 번 더 정밀
  집계할 가치가 있다.

---

## 부록 — 게이트 증거

- **① 분류기 재검토**: §A, 신규 위음성 0건(5개 후보 코드 직접 확인).
- **② `--check`**: `coverage ledger in sync`.
- **③ v10 환류**: `renderVerified` 78→83(+5), `renderVerifiedByOpenrateCorpus`
  47→52(+5) — `ba94f82`.
- **④ 전 스위트**: `2701 passed, 18 skipped, 1 xfailed`(트레인㉔a는 순수
  배선, 신규 테스트 없음, 실패 0).
- **⑤ 정적 검사**: `mypy`(공식 게이트) — `Success: no issues found in 82
  source files`. `pyright`(올바른 venv 파이썬 지정) — `0 errors, 0
  warnings, 0 informations`.
- **⑥ 본 문서**.
