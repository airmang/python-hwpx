# HWPUNIT 좌표계

HWPX 문서의 거의 모든 기하 값 — 용지 크기, 여백, 표 셀 너비, 글자 크기, 개체 위치 — 은 **HWPUNIT**이라는 단일 정수 단위로 저장됩니다. 이 단위를 이해하면 XML을 직접 들여다볼 때 숫자가 무엇을 뜻하는지 바로 읽을 수 있습니다.

## 기본 환산

HWPUNIT은 인치를 7,200등분한 단위입니다. 라이브러리의 변환 상수가 이를 그대로 정의합니다 (`src/hwpx/_document/_units.py`):

```python
_HWP_UNITS_PER_MM = 7200 / 25.4
_HWP_UNITS_PER_PT = 100
```

여기서 세 가지 환산이 도출됩니다.

| 단위 | HWPUNIT | 유래 |
|---|---|---|
| 1 inch | 7,200 | 정의 |
| 1 pt | 100 | 7,200 / 72 (1 inch = 72 pt) |
| 1 mm | 약 283.46 | 7,200 / 25.4 |

`src/hwpx/form_fit/measure.py`, `src/hwpx/form_fit/seal.py`의 헤더 주석도 같은 관계를 못 박아 둡니다: `1 pt = 100 HWPUNIT, 1 inch = 7200 HWPUNIT`, `1 PDF point = 7200/72 = 100 HWPUNIT`. PDF 좌표(1 pt)와 HWPUNIT이 정확히 100:1로 대응하므로, 한/글이 export한 PDF의 좌표를 HWPUNIT으로 되돌릴 때 실수 오차 없이 정수배로 환산됩니다.

## HWPUNIT이 나타나는 곳

같은 단위가 여러 요소에 걸쳐 재사용됩니다.

- **용지·여백**: 섹션 정의의 `<hp:sz width height>`, 여백 값. `src/hwpx/_document/layout.py`가 mm 입력을 `_mm_to_hwp_units()`로 변환해 채웁니다.
- **표 셀 너비/높이**: `<hp:cellSz>`, `<hp:sz>`. 기본 셀 너비 상수도 HWPUNIT입니다 — `src/hwpx/oxml/_document_primitives.py`의 `_DEFAULT_CELL_WIDTH = 7200`(= 1 inch).
- **글자 크기**: 문자 속성 `<hh:charPr height>`. 글자 높이도 같은 스케일이라 **100 HWPUNIT = 1 pt**입니다. 실제 한컴이 저장한 문서를 보면 10 pt 글자는 `height="1000"`, 9 pt는 `height="900"`, 11 pt는 `height="1100"`으로 나옵니다. `src/hwpx/form_fit/measure.py` 헤더가 지적하듯 "글자 높이와 셀 너비가 같은 단위를 공유"하기 때문에, 글자의 진행폭(advance)을 글자 높이의 분수(em)로 바로 계산할 수 있고 별도의 DPI/포인트 변환이 필요 없습니다.
- **개체 위치·크기**: 그림·도형의 `<hp:pos>`, `<hp:sz>` 좌표. `src/hwpx/document.py`, `src/hwpx/_document/shapes.py`의 시그니처가 `height: int = 7200`처럼 HWPUNIT 기본값을 그대로 노출합니다(주석: `Coordinates are in HWPUNIT (7200 per inch)`).
- **이미지 크기**: `src/hwpx/_document/media.py`가 mm 입력을 `_mm_to_hwp_units()`로 변환하고, 기본값은 `14400`(= 2 inch) 같은 HWPUNIT 상수입니다.

## 예외: 줄 간격은 퍼센트

모든 것이 HWPUNIT은 아닙니다. **줄 간격(line spacing)** 은 퍼센트 값으로 저장됩니다. `src/hwpx/_document/layout.py`의 문단 서식 함수 주석이 이를 명시합니다:

> Millimetre inputs are converted to HWP units; paragraph spacing uses points; line spacing is stored as a percent value.

즉 문단 위/아래 간격(`spacing_before_pt`, `spacing_after_pt`)은 pt → HWPUNIT으로 변환되지만, `line_spacing_percent`는 `<hp:lineSpacing type="%">`로 퍼센트 그대로 들어갑니다. 단위를 하나로 뭉뚱그리면 틀리는 지점입니다.

## 공개 API가 사람 단위를 쓰는 이유

HWPUNIT은 XML 저장 형식으로는 정확하지만, 사람이 직접 다루기엔 불편합니다("10 pt 글자"를 매번 1000으로 환산해야 함). 그래서 이 라이브러리의 고수준 API는 **사람 단위(pt/mm/%)를 입력받아 내부에서 HWPUNIT으로 변환**합니다.

- 문단 서식: `indent_left_mm`, `first_line_indent_mm`, `spacing_before_pt`, `line_spacing_percent` (`src/hwpx/_document/layout.py`)
- 이미지: `width_mm`, `height_mm` (`src/hwpx/_document/media.py`)
- 페이지·표: `pageWidthMm`, `heightMm` 등 (`src/hwpx/agent/commands.py`)

변환은 항상 `round()`로 정수화됩니다(HWPUNIT은 정수). 반대로 문서를 분석해 사람에게 보여줄 때는 HWPUNIT → mm로 되돌립니다 — `src/hwpx/tools/style_profile.py`, `src/hwpx/tools/layout_preview.py`가 `value / _HWP_UNITS_PER_MM`으로 역변환해 리포트합니다.

정리하면: **저장 형식은 HWPUNIT, 사용자 표면은 pt/mm/%.** 저수준 `hwpx.oxml` 데이터클래스를 직접 조작할 때는 HWPUNIT 정수를 직접 다루게 되므로, 위 환산표를 곁에 두고 작업하면 됩니다.
