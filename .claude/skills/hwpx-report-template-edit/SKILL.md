---
name: hwpx-report-template-edit
description: >-
  [한글] HWPX 관제보고서 템플릿 편집 가이드. cctv_daily_report 렌더러로
  HWPX 문단 텍스트 치환·줄바꿈(<hp:lineBreak/>)·표/도형 안 텍스트 교체·빈 양식
  생성을 할 때 참고. "템플릿 수정", "줄바꿈", "보고서 양식 편집", "report_template
  편집", "renderer 고쳐줘" 같은 요청에 사용.
---

# HWPX 관제보고서 템플릿 편집 가이드

`src/cctv_daily_report/` 파이프라인의 HWPX 보고서 템플릿/렌더러를 편집할 때 쓰는
실전 노하우. HWPX 문서 구조 특성상 "그냥 텍스트 바꾸기"가 안 되는 함정이 많아서
이 가이드의 패턴을 따른다.

## 0. 핵심 파일 위치

| 파일 | 역할 |
|---|---|
| `templates/report_template_blank.hwpx` | 빈 양식 (placeholder). 렌더링 베이스. `config.py`가 가리킴 |
| `templates/report_template_filled.hwpx` | 채워진 완성 예시 (참고용) |
| `src/cctv_daily_report/config.py` | `TEMPLATE_PATH` = blank 템플릿 경로 (env `CCTV_REPORT_TEMPLATE`로 오버라이드) |
| `src/cctv_daily_report/renderer.py` | 템플릿에 데이터 주입하는 본체 |

실행 환경: conda env `python-hwpx`, 코어 라이브러리는 `src/hwpx` (editable install).

## 1. 절대 규칙 (어기면 깨진다)

1. **문단 개수를 바꾸지 마라.** 렌더러는 `section.paragraphs[idx]`처럼 **인덱스로
   문단에 접근**한다. 문단을 추가/삭제하면 13/23/31/.../45 인덱스 맵이 전부 어긋난다.
   줄을 늘리고 싶으면 문단 추가가 아니라 **문단 내 줄바꿈(`<hp:lineBreak/>`)**을 써라.
2. **표/도형 안 텍스트는 "내용 비의존"으로 치환하라.** 직전 실행 데이터(예:
   `"일일 보고 (2026-05-11)"`)에 정확히 일치시키면 빈 양식에선 매칭이 깨진다.
   접두/위치 기반으로 매칭한다 (아래 §4).
3. **빈 양식과 채워진 양식 둘 다에서 동작해야 한다.** 렌더러 수정 후 반드시
   blank 템플릿으로 fallback 렌더링 테스트를 돌려라 (§5).

## 2. 문단 인덱스 맵 (report_template, section 0)

top-level 문단 — `section.paragraphs[idx]`로 접근, 인덱스 치환:

```
13 날짜        23 관제센터      24 부서명(유지)
30 헤더 "1. 기본 정보"(유지)
31 본문 보고일자/관제센터        32 본문 보고대상시간        33 본문 CCTV 통계
34 헤더 "2. 일일 탐지 현황"(유지)   35 본문 통계 한 줄
36 헤더 "3. 주요 탐지 이벤트"(유지) 37 본문 이벤트 1~3
38 헤더 "4. 금일 관제 요약"(유지)   39 본문 daily_summary
40 헤더 "배경"(유지)               41 본문 main_event_description
43 본문 VLM visual_summary 합본
44 헤더 "5. 특이사항..."(유지)      45 본문 special+review
```

표/도형 안(nested) 문단 — lxml로 직접 t 노드 수정, **내용 비의존 치환**:

```
p[0]  표 1×1  "○○시 CCTV 통합관제센터" (정확 일치) → 관제센터명
p[4]  표 5×1  제목(정확 일치) + "일일 보고 (" 접두 일치 → 날짜 자막
p[26] 도형    제목(정확 일치)
p[27] 표 1×1  개요 박스 본문 t 전부 → daily (현재 텍스트 무시)
```

> 인덱스가 의심되면 직접 확인: `list(doc.sections[0].element)` 순회하며 각 문단의
> `<hp:t>` 텍스트를 덤프 (§6 스니펫).

## 3. 패턴 A — 단순 문단 텍스트 치환

```python
section = doc.sections[0]
for idx, new_text in {13: date, 23: center, 35: stats_line}.items():
    if idx < len(section.paragraphs):
        section.paragraphs[idx].text = new_text   # 세터가 run/charPr 보존 + mark_dirty
```

`paragraph.text` 세터는 **스타일(paraPrIDRef/charPrIDRef) 보존**하고 자동으로
`mark_dirty()`까지 호출한다. 탭은 `\t` → `<hp:tab/>`로 변환. 단, **줄바꿈은
처리 못 한다**(§4 참고).

## 4. 패턴 B — 문단 내 줄바꿈 (★가장 중요한 함정)

`paragraph.text = "a\nb"`로 넣으면 raw `\n`이 `<hp:t>` 안에 그대로 들어가
한컴에서 줄바꿈으로 안 보일 수 있다. **한컴 정식 표현은 `<hp:lineBreak/>` 요소**이며,
`<hp:t>` 안의 자식으로 들어간다:

```xml
<hp:t>- 전체 CCTV : 120대<hp:lineBreak/>- 분석 대상 CCTV : 80대<hp:lineBreak/>- 보고서 생성 : ...</hp:t>
```

이를 만드는 헬퍼 (renderer.py에 이미 존재, `_set_multiline`):

```python
_HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"

def _set_multiline(paragraph, lines: list[str]) -> None:
    """문단을 여러 줄로. 줄 구분은 <hp:lineBreak/> (Hancom 정식 표현)."""
    if not lines:
        paragraph.text = ""
        return
    paragraph.text = lines[0]          # 첫 줄 + 스타일 보존 + run 정리 + mark_dirty
    if len(lines) == 1:
        return
    t_el = next((el for el in paragraph.element.iter()
                 if etree.QName(el).localname == "t"), None)
    if t_el is None:
        return
    for line in lines[1:]:
        lb = t_el.makeelement(f"{{{_HP_NS}}}lineBreak", {})
        lb.tail = line                 # lineBreak 뒤 텍스트는 tail에
        t_el.append(lb)
```

쓰는 쪽:
```python
for idx, lines in ((31, basic1_lines), (33, basic3_lines)):
    if idx < len(section.paragraphs):
        _set_multiline(section.paragraphs[idx], lines)
```

> 줄바꿈을 추가/제거하려면 **문단을 쪼개지 말고** 해당 문단에 줄 리스트를 넘기는
> 방식으로 바꾼다. 예) 기본정보 한 줄에 묶인 "보고일자+관제센터"를 두 줄로:
> `["- 보고 일자 : ...", "- 관제센터 : ..."]`.

## 5. 패턴 C — 표/도형 안 텍스트 치환 (내용 비의존)

```python
def _iter_t(p_element):
    for el in p_element.iter():
        if etree.QName(el).localname == "t" and el.text and el.text.strip():
            yield el

def _replace_nested(section_element, *, center_name, title, date_subtitle, daily):
    paragraphs = list(section_element)
    for p_idx in (0, 4, 26):
        if p_idx >= len(paragraphs):
            continue
        for el in _iter_t(paragraphs[p_idx]):
            if el.text == title:
                el.text = title
            elif el.text == "○○시 CCTV 통합관제센터":
                el.text = center_name
            elif el.text.startswith("일일 보고 ("):   # ← 접두 매칭 (날짜 무관)
                el.text = date_subtitle
    if 27 < len(paragraphs):                          # 개요 박스: 위치 기반
        for el in _iter_t(paragraphs[27]):
            el.text = daily
```

핵심: **정확 문자열 일치 대신 접두(`startswith`)·위치(문단 인덱스) 기반**으로
매칭해서 빈 양식/채워진 양식 어디서나 동작하게 한다. lxml 직접 수정이므로 끝에
`section.mark_dirty()` 호출 필수.

## 6. 빈 양식(blank) 만들기

채워진 템플릿에서 데이터를 placeholder로 비운다. top-level 본문은 세터로,
표/도형 안은 lxml로:

```python
from hwpx import HwpxDocument
from lxml import etree
doc = HwpxDocument.open("templates/report_template_filled.hwpx")
sec = doc.sections[0]
PH = "내용을 입력하세요"
for idx, text in {13:"0000-00-00", 23:"○○시 CCTV 통합관제센터",
                  31:PH,32:PH,33:PH,35:PH,37:PH,39:PH,41:PH,43:PH,45:PH}.items():
    if idx < len(sec.paragraphs):
        sec.paragraphs[idx].text = text
paras = list(sec.element)
for el in (e for e in paras[4].iter() if etree.QName(e).localname=="t" and e.text):
    if el.text.startswith("일일 보고 ("):
        el.text = "일일 보고 (0000-00-00)"
for el in (e for e in paras[27].iter() if etree.QName(e).localname=="t" and (e.text or "").strip()):
    el.text = PH
sec.mark_dirty()
doc.save_to_path("templates/report_template_blank.hwpx")
```

## 7. 검증 루틴 (수정 후 반드시)

```bash
cd <repo>
conda activate python-hwpx   # 또는 conda run -n python-hwpx ...

# 1) blank 템플릿으로 fallback 렌더 (vLLM 없이)
PYTHONPATH=src python -m cctv_daily_report.cli \
    --report-date 2026-06-05 --output /tmp/render_test --skip-vlm --skip-llm

# 2) 패키지 정합성 검증 (warnings는 정상 — version 파트 누락 알림)
hwpx-validate-package /tmp/render_test/CCTV_AI_Daily_Report_20260605.hwpx

# 3) 텍스트 추출로 placeholder 잔존/줄바꿈 확인
python -c "from hwpx import HwpxDocument; print(HwpxDocument.open('/tmp/render_test/CCTV_AI_Daily_Report_20260605.hwpx').export_text())"
```

section XML 직접 확인 (lineBreak 위치·구조):
```python
import zipfile
data = zipfile.ZipFile("<file>.hwpx").read("Contents/section0.xml").decode("utf-8")
print(data.count("lineBreak"))
i = data.find("전체 CCTV"); print(repr(data[i-15:i+110]))
```

문단 인덱스 덤프 (구조 파악용):
```python
from hwpx import HwpxDocument; from lxml import etree
sec = HwpxDocument.open("<file>.hwpx").sections[0]
for i, p in enumerate(sec.element):
    ts = [e.text for e in p.iter() if etree.QName(e).localname=="t" and e.text and e.text.strip()]
    if ts: print(i, ts[:2])
```

## 8. 자주 하는 실수 체크리스트

- [ ] 문단을 추가/삭제해서 인덱스 맵을 깨뜨렸다 → 줄바꿈은 `<hp:lineBreak/>`로 해결
- [ ] `paragraph.text = "a\nb"` 로 줄바꿈을 기대했다 → `_set_multiline` 사용
- [ ] 표/도형 안 텍스트를 직전 데이터 문자열로 정확 일치시켰다 → 접두/위치 매칭으로
- [ ] lxml 직접 수정 후 `section.mark_dirty()` 안 했다 → 저장에 반영 안 됨
- [ ] 검증을 채워진 템플릿으로만 했다 → blank 템플릿으로도 렌더 테스트
- [ ] conda env 활성화 안 함 → `conda run -n python-hwpx` 또는 `conda activate`

## 9. 참고

- 코어 라이브러리 텍스트 세터: `src/hwpx/oxml/document.py`의 `HwpxOxmlParagraph.text`
  (`_append_text_with_tabs`, `_sanitize_text` — `\n`은 보존하나 한컴 줄바꿈은 lineBreak)
- 줄바꿈 추출 처리: `src/hwpx/tools/text_extractor.py` (`lineBreak` → `\n`)
- HWPX = OPC(zip) 컨테이너. 본문은 `Contents/section0.xml`.
