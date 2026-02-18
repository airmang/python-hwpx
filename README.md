# python-hwpx

`python-hwpx`는 Hancom HWPX 문서를 읽고, 편집하고, 자동화 스크립트로 재가공하기 위한 파이썬 도구 모음입니다. Open Packaging Convention(OPC) 컨테이너를 검사하는 저수준 도구부터 문단·표·메모를 쉽게 다루는 고수준 API, 텍스트 추출과 객체 검색 유틸리티까지 하나로 제공합니다.

## 특징 요약

- **패키지 로딩과 검증** – `hwpx.opc.package.HwpxPackage`로 `mimetype`, `container.xml`, `version.xml`을 확인하며 모든 파트를 메모리에 적재합니다.
- **문서 편집 API** – `hwpx.document.HwpxDocument`는 문단과 표, 메모, 헤더 속성을 파이썬 객체로 노출하고 새 콘텐츠를 손쉽게 추가합니다. 섹션 머리말·꼬리말을 수정하면 `<hp:headerApply>`/`<hp:footerApply>`와 마스터 페이지 링크도 함께 갱신합니다.
- **타입이 지정된 본문 모델** – `hwpx.oxml.body`는 표·컨트롤·인라인 도형·변경 추적 태그를 데이터 클래스에 매핑하고, `HwpxOxmlParagraph.model`/`HwpxOxmlRun.model`로 이를 조회·수정한 뒤 XML로 되돌릴 수 있도록 지원합니다.
- **메모와 필드 앵커** – `add_memo_with_anchor()`로 메모를 생성하면서 MEMO 필드 컨트롤을 자동 삽입해 한/글에서 바로 표시되도록 합니다.
- **헤더 참조 목록 탐색** – 글머리표, 문단 속성, 테두리 채우기, 스타일, 변경 추적 항목, 작성자 정보를 데이터클래스로 파싱하고 `document.border_fills`·`document.bullets`·`document.styles` 같은 조회 헬퍼로 ID 기반 검색을 단순화했습니다.
- **바탕쪽·이력·버전 파트 제어** – 매니페스트에 포함된 master-page/history/version 파트를 `document.master_pages`, `document.histories`, `document.version`으로 직접 편집하고 저장합니다.
- **스타일 기반 텍스트 치환** – 런 서식(색상, 밑줄, `charPrIDRef`)으로 필터링해 텍스트를 선택적으로 교체하거나 삭제합니다. 하이라이트
  마커나 태그로 분리된 문자열도 서식을 유지한 채 치환합니다.
- **텍스트 추출 파이프라인** – `hwpx.tools.text_extractor.TextExtractor`는 하이라이트, 각주, 컨트롤을 원하는 방식으로 표현하며 문단 텍스트를 반환합니다.
- **풍부한 문서** – 빠른 시작, 50개의 사용 패턴, 설치/FAQ/스키마 개요를 Sphinx 기반 웹 문서로 제공합니다.

## 설치

PyPI에서 최신 버전을 바로 설치할 수 있습니다.

```bash
python -m pip install python-hwpx
```

개발 버전이나 문서 빌드를 직접 수정하려면 저장소를 클론한 뒤 편집 가능한 설치를 사용하세요.

```bash
git clone https://github.com/<your-org>/python-hwpx.git
cd python-hwpx
python -m pip install -e .[dev]
```

Sphinx 문서는 `docs/` 아래에 있으며, `python -m pip install -r docs/requirements.txt` 후 `make -C docs html`로 로컬 미리보기가 가능합니다.

## 5분 안에 맛보기

```python
from io import BytesIO

from hwpx import HwpxDocument
from hwpx.templates import blank_document_bytes

# 1) 빈 템플릿으로 문서 열기
source = BytesIO(blank_document_bytes())
document = HwpxDocument.open(source)
print("sections:", len(document.sections))

# 2) 문단과 표, 메모 추가
section = document.sections[0]
paragraph = document.add_paragraph("자동 생성한 문단", section=section)
# 표에 사용할 기본 실선 테두리 채우기가 없으면 add_table()이 자동으로 생성합니다.
table = document.add_table(rows=2, cols=2, section=section)
table.set_cell_text(0, 0, "항목")
table.set_cell_text(0, 1, "값")
table.set_cell_text(1, 0, "문단 수")
table.set_cell_text(1, 1, str(len(document.paragraphs)))
document.add_memo_with_anchor("배포 전 검토", paragraph=paragraph, memo_shape_id_ref="0")

# 3) 다른 이름으로 저장
document.save("output/example.hwpx")
```

`HwpxDocument.add_table()`은 문서에 정의된 테두리 채우기가 없으면 헤더 참조 목록에 "기본 실선" `borderFill`을 만들어 표와 모든 셀에 참조를 연결합니다.

표 셀 텍스트를 편집하는 `table.set_cell_text()`는 기존 단락에 남아 있는 `lineSegArray`와 같은 줄 배치 캐시를 제거하여 한/글이 문서를 다시 열 때 줄바꿈을 새로 계산하도록 합니다. 병합된 표 구조를 다뤄야 한다면 `table.iter_grid()` 또는 `table.get_cell_map()`으로 논리 격자와 실제 셀의 매핑을 확인하고, `set_cell_text(..., logical=True, split_merged=True)`로 논리 좌표 기반 편집과 자동 병합 해제를 동시에 처리할 수 있습니다.

더 많은 실전 패턴은 [빠른 시작](docs/quickstart.md)과 [사용 가이드](docs/usage.md)의 "빠른 예제 모음"에서 확인할 수 있습니다.

## 문서
 [사용법](https://airmang.github.io/python-hwpx/)

## 예제와 도구

- `examples/` 디렉터리는 텍스트 추출, 객체 검색, QA 체크리스트 생성 예제를 제공합니다. PyPI 패키지에는 포함되지 않으므로 필요하면 저장소를 클론하거나 웹 문서의 코드 스니펫을 활용하세요.
- `hwpx.templates.blank_document_bytes()`는 추가 리소스 없이 빈 HWPX 문서를 만들 수 있는 내장 템플릿을 제공합니다.

## 알려진 제약

- `add_shape()`/`add_control()`은 한/글이 요구하는 모든 하위 요소를 생성하지 않으므로, 복잡한 개체를 추가할 때는 편집기에서 열어 검증해 주세요.

## 기여하기

버그 리포트와 개선 제안은 언제나 환영합니다. 개발 환경 설정과 테스트 방법은 [CONTRIBUTING.md](CONTRIBUTING.md)를 참고하세요.

## 라이선스와 연락처

- 라이선스: [LICENSE](LICENSE)
- 문의: 이슈 트래커 또는 kokyuhyun@hotmail.com
