# python-docx / openpyxl 와의 비교

`python-docx` 는 이 라이브러리의 **벤치마크**다. 복사 대상이 아니라 "파이썬
문서 라이브러리가 어느 정도로 손에 붙어야 하는가"의 기준선이다.

이 표의 대조군 숫자는 **핀 고정된 휠을 받아 그 자리에서 리플렉션으로 잰 값**
이다(`scripts/measure_control_surfaces.py`, 원본 `docs/control-surfaces.json`).
우리가 손으로 적은 값이 아니다 — 우리가 만들지 않은 입력으로 채점받는다는
원칙 때문이다.

측정 대상은 각 라이브러리의 "문서 객체" 하나이고, 세는 규칙은 세 곳 모두
같다: `vars(cls)` 의 공개 멤버(상속 제외) + 지원 dunder 4종.

| | python-docx 1.2.0 | openpyxl 3.1.5 | python-hwpx 6.0 |
|---|---:|---:|---:|
| 문서 객체 | `docx.document.Document` | `openpyxl.…Workbook` | `hwpx.document.HwpxDocument` |
| 공개 멤버 수 | **19** | **29** | **34** |
| 최상위 `__all__` | 1 | 0 | 34 |
| 파이썬 모듈 수 | 95 | 190 | 131 |
| 소스 LOC | 16,081 | 29,137 | 45,188 |
| 콘솔 스크립트 | 0 | 0 | 8 |
| deprecation shim | 0 | 0 | 79 |

## 우리가 지는 칸

숨기지 않는다. 다섯 줄 전부 위 표에서 그대로 읽힌다.

**① 문서 객체가 아직 제일 크다 — 34 대 19.** 6.0 이 102 → 34 로 줄였지만
`python-docx` 보다 **15개 많다.** HWPX 고유 구조(섹션·양식개체·변경추적)가
일부를 설명하지만 전부는 아니다. 다음 감축 대상은 루트에 남은 IO 동사
(`save_to_path`/`save_to_stream`/`to_bytes`/`save_report` 4종)다.

**② 최상위 이름이 34개다 — `python-docx` 는 1개.** `python-docx` 는
`Document()` 하나로 시작하고 나머지는 객체를 타고 들어간다. 우리는 도구·리포트·
검증기를 최상위에 얹어 두었다. 이건 표면 축소가 아직 파사드에만 닿았고
패키지 최상위에는 닿지 않았다는 뜻이다.

**③ 코드가 2.8배 크다 — 45,188 대 16,081 LOC.** HWPX 는 OWPML 스키마가 크고
한컴 편차 대응이 붙지만, 그것만으로 이 차이가 정당화되지는 않는다.

**④ 콘솔 스크립트가 8개 — 두 대조군 모두 0개.** 라이브러리에 CLI 를 얹는 것은
사용자에게 "이건 도구인가 라이브러리인가"를 묻게 만든다. 신규 추가는 동결했다.

**⑤ 이주 shim 을 79개 지고 있다 — 대조군은 0.** 6.0 이 연 이주 창의 대가다.
7.0 에서 0 이 되며, 그때까지 `tests/data/document_legacy_shims.json` 이
감소만 허용하는 ratchet 으로 센다.

## 우리가 이기는 칸

**① 스타일 오타를 호출 시점에 잡는다.** 실측(`python-docx` 1.2.0):

```python
document.add_paragraph("t", style="Heading1")   # 'Heading 1' 의 오타
# → 예외 없음. UserWarning 하나만 나오고 문단은 기본 스타일로 만들어진다.
```

같은 오타를 6.0 은 그 줄에서 멈춘다:

```python
document.add_paragraph("t", style="개요1")
# HwpxLookupError: 스타일 '개요1' 을(를) 찾을 수 없습니다.
#   code:       style-not-found
#   context:    {'closest': ['개요 1', '개요 10'], 'availableCount': 46, …}
#   suggestion: 가장 가까운 이름: '개요 1', '개요 10'. 전체 목록: doc.styles.names()
```

**② 실패가 기계가 읽는 형태다.** 공개 경로의 모든 실패는 `code`·`context`·
`suggestion` 을 싣는다(70종, `docs/error-codes.md`). `python-docx` 의
`add_heading(level=99)` 은 `ValueError("level must be in range 0-9, got 99")`
— 사람은 읽지만 호출자가 분기할 값은 없다.

**③ 저장이 무엇을 했는지 영수증을 낸다.** 버전드 `hwpx.mutation-report/v1` 이
바뀐 파트·보존 등급·검증 결과를 담는다. 두 대조군 모두 이런 계약이 없다.

**④ 시각 주장에 오라클 출처가 붙는다.** "한컴에서 열린다"는 실한컴이 판정했을
때만 하고, 오라클이 없으면 `unverified` 로 남긴다.

## 비긴 칸 — 6.0 이 따라잡은 것

이 셋은 `python-docx` 에 원래 있었고 5.x 우리에게 없었다. 6.0 이 메웠을 뿐
앞선 것이 아니다.

| | python-docx | python-hwpx 5.x | python-hwpx 6.0 |
|---|---|---|---|
| `add_heading` | 있음 (level 0–9) | **없음** | 있음 (level 1–10) |
| 스타일 이름 지정 | 있음 | 저장 시점에만 해석 | 호출 시점 해석 |
| 컬렉션형 `styles` | 있음 | `dict` 반환 | Mapping 네임스페이스 |

`level` 범위가 다른 이유: `python-docx` 의 0 은 Title 스타일이고, HWPX 개요는
정확히 10수준이며 Skeleton 에 "제목" 스타일이 없다. 없는 스타일을 만들어 넣으면
한컴의 개요 번호가 어긋난 문서가 나오므로 흉내내지 않는다.

## 재측정

```bash
python scripts/measure_control_surfaces.py           # 네트워크 필요(휠 수신)
python scripts/measure_control_surfaces.py --check   # CI: 우리 쪽만 재측정·대조
```
