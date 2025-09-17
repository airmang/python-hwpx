
## 모듈 `hwpx.templates`

### 함수

- `blank_document_bytes() -> bytes`
  - 기본 빈 HWPX 템플릿의 바이너리 페이로드를 반환합니다. 이 헬퍼는 먼저 선택적 `hwpx.data` 패키지에서 `Skeleton.hwpx` 파일을 로드하려고 시도하고, 실패 시 저장소의 `examples` 디렉토리에서 찾습니다. 두 위치 모두에서 파일을 찾을 수 없으면 `FileNotFoundError`를 발생시킵니다.

***

## 모듈 `hwpx.package`

### 함수

- `_ensure_bytes(value: bytes | str | ET.Element) -> bytes`
  - 파트(part) 페이로드를 UTF-8로 인코딩된 바이트로 정규화하는 내부 헬퍼입니다.

### 클래스 `HwpxPackage`

#### 생성

- `open(source) -> HwpxPackage`
  - 경로, `PathLike`, 바이트, 바이트 스트림 또는 파일과 유사한 객체를 인자로 받아 OPC zip 아카이브에서 모든 파트를 읽어 패키지 인스턴스를 반환하는 클래스 메서드입니다.

#### 패키지 검사

- `part_names() -> Iterable[str]`
  - 현재 패키지에 저장된 파트 이름의 목록을 반환합니다.
- `has_part(part_name: str) -> bool`
  - 요청된 파트가 존재하는지 확인합니다.
- `get_part(part_name: str) -> bytes`
  - 파트의 원시 바이트(raw bytes)를 가져옵니다. 파트가 없으면 `KeyError`를 발생시킵니다.
- `set_part(part_name: str, payload) -> None`
  - 파트 페이로드를 저장합니다. 매니페스트 자체가 변경되면 매니페스트 캐시를 재설정합니다.
- `get_xml(part_name: str) -> ET.Element`
  - 파트를 파싱하여 `ElementTree` 엘리먼트로 반환합니다.
- `set_xml(part_name: str, element: ET.Element) -> None`
  - 엘리먼트를 직렬화하여 파트 페이로드로 저장합니다.
- `get_text(part_name: str, encoding: str = "utf-8") -> str`
  - 요청된 인코딩으로 파트 내용을 디코딩합니다.

#### 매니페스트 헬퍼

- `manifest_tree() -> ET.Element`
  - `content.hpf`를 지연 파싱(lazily parse)하고 캐시하여 매니페스트 메타데이터를 노출합니다.
- `_resolve_spine_paths() -> list[str]`
  - 매니페스트 스파인(spine)에서 읽기 순서를 추출하는 내부 캐시 빌더입니다. 필요한 경우 휴리스틱 탐지를 통해 순서를 결정합니다.
- `section_paths() -> list[str]`
  - 캐시된 섹션 XML 파트 경로를 반환합니다. 스파인 데이터를 재사용하거나 `section*.xml` 항목을 휴리스틱하게 식별합니다.
- `header_paths() -> list[str]`
  - 캐시된 헤더 XML 파트 경로를 반환합니다. 매니페스트에 명시적인 참조가 없는 경우 `Contents/header.xml`을 기본값으로 사용합니다.

#### 영속성(Persistence)

- `save(path_or_stream=None, updates=None)`
  - 보류 중인 업데이트를 영구 저장하고 대상 경로/스트림/바이트를 반환합니다. 대상이 제공되지 않으면 원본 소스를 재사용하고, 그렇지 않으면 요청된 파일 시스템 위치나 스트림에 zip 아카이브를 작성합니다.
- `_write_to_stream(stream)` 및 `_write_archive(archive)`
  - `save()` 메서드를 위해 zip 직렬화를 처리하는 내부 유틸리티입니다.

***

## 모듈 `hwpx.document`

### 클래스 `HwpxDocument`

#### 생성자

- `open(source)`
  - HWPX 파일을 열고, `HwpxOxmlDocument`로 저수준 XML 트리를 빌드한 후 문서 래퍼(wrapper)를 반환합니다.
- `new()`
  - 스켈레톤 템플릿 번들을 로드하여 새 문서를 생성합니다.
- `from_package(package)`
  - 기존 `HwpxPackage` 인스턴스를 감싸는 문서 래퍼를 빌드합니다.

#### 패키지 및 XML 접근

- `package`
  - 내부의 `HwpxPackage` 컨테이너를 노출하는 프로퍼티입니다.
- `oxml`
  - 루트 `HwpxOxmlDocument` 트리를 반환하는 프로퍼티입니다.
- `sections`, `headers`
  - 섹션/헤더 래퍼 목록을 반환하는 프로퍼티입니다.

#### 메모 헬퍼

- `memo_shapes`
  - 헤더에 있는 모든 메모 모양 정의를 병합한 딕셔너리를 반환합니다.
- `memo_shape(memo_shape_id_ref)`
  - 특정 메모 모양 정의를 가져옵니다. ID는 문자열 또는 숫자 형식과 일치시킵니다.
- `memos`
  - 모든 섹션에 걸쳐 있는 메모 항목들을 단일 목록으로 펼쳐서 반환하는 프로퍼티입니다.
- `add_memo(...) -> HwpxOxmlMemo`
  - 섹션에 메모 항목을 추가합니다. 대상 섹션은 `section`이나 `section_index` 인자로 지정하거나, 지정하지 않으면 마지막 섹션을 기본값으로 사용합니다.
- `remove_memo(memo)`
  - 메모 엘리먼트를 소유한 섹션에서 제거합니다.
- `attach_memo_field(paragraph, memo, ...) -> str`
  - 주어진 메모가 한/글에서 보이도록 `paragraph`에 MEMO 필드 컨트롤 런(run)을 삽입합니다. ID를 생성하고 작성자, 생성 타임스탬프, 번호 매기기 같은 주석 메타데이터를 처리합니다.
- `add_memo_with_anchor(...) -> tuple[HwpxOxmlMemo, HwpxOxmlParagraph, str]`
  - 메모를 생성하고, MEMO 필드를 포함할 단락이 있는지 확인한 후, 필드를 부착하고, (메모, 단락, 필드 ID) 튜플을 반환하는 편의 헬퍼입니다.

#### 텍스트 및 서식 헬퍼

- `paragraphs`
  - 문서 순서대로 모든 단락 래퍼를 반환하는 프로퍼티입니다.
- `char_properties`
  - 확인된(resolved) 글자 스타일 정의를 노출하는 프로퍼티입니다.
- `char_property(char_pr_id_ref)`
  - ID를 사용하여 `RunStyle`을 조회합니다.
- `ensure_run_style(...) -> str`
  - 요청된 굵게/기울임/밑줄 플래그와 일치하는 런 스타일이 헤더에 정의되어 있는지 확인하고 해당 스타일 ID를 반환합니다. 필요한 경우 기존 스타일을 복제합니다.
- `iter_runs()`
  - 문서 전체의 모든 `HwpxOxmlRun`을 순회(yield)합니다.
- `find_runs_by_style(...) -> list[HwpxOxmlRun]`
  - 색상, 밑줄 유형 또는 특정 글자 속성 참조와 같은 스타일 속성으로 런을 필터링합니다.
- `replace_text_in_runs(search, replacement, ...) -> int`
  - `find_runs_by_style()`을 사용하여 런을 찾고 문자열을 교체합니다. 선택적으로 교체 횟수를 제한할 수 있습니다.

#### 콘텐츠 생성 헬퍼

- `add_paragraph(text="", ...) -> HwpxOxmlParagraph`
  - 대상 섹션에 단락을 추가합니다. 선택적으로 단락 및 런 서식 참조를 재정의하거나 추가 단락 속성을 주입할 수 있습니다.
- `add_table(rows, cols, ...) -> HwpxOxmlTable`
  - 단락을 삽입하고 그 안에 표 인라인 객체를 생성한 후, 표 래퍼를 반환합니다.
- `add_shape(shape_type, ...) -> HwpxOxmlInlineObject`
  - 새 단락에 태그 이름을 사용하여 인라인 그리기 요소를 삽입합니다.
- `add_control(...) -> HwpxOxmlInlineObject`
  - 새 단락에 인라인 컨트롤 객체(예: 양식 컨트롤)를 삽입합니다.

#### 영속성(Persistence)

- `save(path_or_stream=None)`
  - 변경된(dirty) XML 파트를 내부 패키지를 통해 직렬화하고, 변경 사항을 원본 소스, 새 경로 또는 파일과 유사한 객체에 씁니다.

***

## 모듈 `hwpx.oxml.common`

### 클래스 `GenericElement`

- 특화된 파서가 없는 엘리먼트를 나타내는 데이터클래스입니다.

### 함수

- `parse_generic_element(node) -> GenericElement`
  - XML 노드와 그 자식들을 재귀적으로 `GenericElement` 구조로 변환하며 속성과 텍스트를 보존합니다.

***

## 모듈 `hwpx.oxml.body`

### 데이터 클래스

- `TextSpan`
  - 텍스트 런, 수집된 마크 엘리먼트 및 속성을 캡처합니다.
- `Run`
  - 글자 참조, 중첩된 컨트롤, 인라인 객체 및 추가 자식을 포함하는 `<hp:run>`을 나타냅니다.
- `Paragraph`
  - 런 컬렉션과 속성을 포함하는 `<hp:p>` 단락을 나타냅니다.
- `Section`
  - 단락과 추가 노드를 포함하는 `<hs:sec>` 문서 섹션을 나타냅니다.

### 파싱 함수

- `parse_text_span(node) -> TextSpan`
  - `<hp:t>` 엘리먼트로부터 `TextSpan`을 빌드하며, 중첩된 마크를 보존합니다.
- `parse_run_element(node) -> Run`
  - `<hp:run>` 엘리먼트를 `Run` 데이터클래스로 변환하며, 컨트롤 및 인라인 객체와 같은 자식 엘리먼트를 분류합니다.
- `parse_paragraph_element(node) -> Paragraph`
  - `<hp:p>` 엘리먼트를 `Paragraph` 데이터클래스로 변환합니다.
- `parse_section_element(node) -> Section`
  - `<hs:sec>` 엘리먼트를 `Section` 데이터클래스로 변환합니다.

***

## 모듈 `hwpx.oxml.header`

### 데이터 클래스 및 메서드

- `BeginNum`: 헤더 수준 카운터의 시작 번호를 저장합니다.
- `LinkInfo`: 연결된 외부 콘텐츠에 대한 메타데이터를 포함합니다.
- `LicenseMark`: 라이선스 플래그 정보를 나타냅니다.
- `DocOption`: `LinkInfo`와 선택적인 `LicenseMark` 데이터를 묶습니다.
- `KeyDerivation`: 암호 파생 알고리즘 매개변수를 저장합니다.
- `KeyEncryption`: 파생 설정 및 base64로 디코딩된 해시 바이트를 저장합니다.
- `TrackChangeConfig`: 변경 내용 추적 플래그 및 선택적 암호화 블록을 설명합니다.
- `FontSubstitution`: 대체 글꼴 데이터를 캡처합니다.
- `FontTypeInfo`: 보조 글꼴 속성을 저장합니다.
- `Font`: 대체/유형 정보가 포함된 개별 글꼴 정의를 나타냅니다.
- `FontFace` / `FontFaceList`: 그룹화된 글꼴 정의를 위한 컨테이너입니다.
- `BorderFillList`: 테두리 채우기 정의를 수집합니다.
- `TabProperties`: 탭 정지 컬렉션을 캡처합니다.
- `NumberingList`: 번호 매기기 정의를 저장합니다.
- `CharProperty`: 런 스타일 속성과 중첩된 자식 엘리먼트를 캡슐화합니다.
- `CharPropertyList`: `CharProperty` 정의를 집계합니다.
- `ForbiddenWordList`: 금칙어를 저장합니다.
- `MemoShape`: 메모 말풍선 모양을 설명하고, 문자열 또는 숫자 식별자를 비교하는 `matches_id()`를 구현합니다.
- `MemoProperties`: ID를 통해 모양을 가져오는 `shape_by_id()`와 ID를 `MemoShape` 인스턴스에 매핑하는 `as_dict()`를 제공합니다.
- `RefList`: 글꼴, 테두리 채우기, 메모 속성과 같은 참조 목록을 수집합니다.
- `Header`: 헤더 메타데이터를 래핑하고 모양을 확인하는 `memo_shape()`를 노출합니다.

### 파싱 유틸리티

각 파서는 특정 XML 하위 트리를 해당 데이터클래스로 변환하며, 속성 유형을 정규화합니다(예: `parse_int` 및 `parse_bool` 호출). 이를 통해 상위 수준 코드가 구조화된 데이터에 의존할 수 있습니다.

- `parse_begin_num(node) -> BeginNum`
- `parse_link_info(node) -> LinkInfo`
- `parse_license_mark(node) -> LicenseMark`
- `parse_doc_option(node) -> DocOption`
- `_decode_base64(value) -> Optional[bytes]`
- `parse_key_encryption(node) -> Optional[KeyEncryption]`
- `parse_track_change_config(node) -> TrackChangeConfig`
- `parse_font_substitution(node) -> FontSubstitution`
- `parse_font_type_info(node) -> FontTypeInfo`
- `parse_font(node) -> Font`
- `parse_font_face(node) -> FontFace`
- `parse_font_faces(node) -> FontFaceList`
- `parse_border_fills(node) -> BorderFillList`
- `parse_char_property(node) -> CharProperty`
- `parse_char_properties(node) -> CharPropertyList`
- `parse_tab_properties(node) -> TabProperties`
- `parse_numberings(node) -> NumberingList`
- `parse_forbidden_word_list(node) -> ForbiddenWordList`
- `memo_shape_from_attributes(attrs) -> MemoShape`
- `parse_memo_shape(node) -> MemoShape`
- `parse_memo_properties(node) -> MemoProperties`
- `parse_ref_list(node) -> RefList`
- `parse_header_element(node) -> Header`

***

## 모듈 `hwpx.oxml.utils`

### 함수

- `local_name(node) -> str`
  - 노드의 네임스페이스가 제거된 태그 이름을 반환합니다.
- `parse_int(value, allow_none=True) -> Optional[int]`
  - 속성 문자열을 정수로 변환하며, 선택적으로 `None`을 지원합니다.
- `parse_bool(value, default=None) -> Optional[bool]`
  - 일반적인 참/거짓 문자열을 불리언으로 변환하며, 예상치 못한 토큰이 발견되면 예외를 발생시킵니다.
- `text_or_none(node) -> Optional[str]`
  - 공백이 제거된 노드 텍스트를 반환하거나, 비어 있으면 `None`을 반환합니다.
- `coerce_xml_source(source) -> tuple[etree._Element, etree._ElementTree]`
  - XML 문자열, 바이트, 경로 또는 `lxml` 객체를 받아 루트 엘리먼트와 이를 소유한 트리를 반환합니다. 이는 스키마 유효성 검사에 필수적입니다.

***

## 모듈 `hwpx.oxml.schema`

### 함수

- `load_schema(path) -> etree.XMLSchema`
  - 디스크에서 XML 스키마를 로드합니다. 이 헬퍼는 상대적 임포트(import) 경로를 스키마 디렉토리 기준으로 재작성하는 리졸버(resolver)를 설치하여 복잡한 XSD 계층 구조가 올바르게 로드되도록 합니다.

***

## 모듈 `hwpx.oxml.parser`

### 함수

- `element_to_model(node) -> object`
  - 노드의 로컬 이름을 기반으로 특화된 파서에 작업을 위임하고, 매핑이 없으면 데이터클래스 모델 또는 `GenericElement`를 반환합니다.
- `parse_header_xml(source, schema_path=None, schema=None) -> header.Header`
  - XML 소스를 정규화하고, 선택적으로 제공되거나 확인된 스키마에 대해 유효성을 검사한 후, 구조화된 헤더 모델을 반환합니다.
- `parse_section_xml(source, schema_path=None, schema=None) -> body.Section`
  - `parse_header_xml`과 동일하지만 섹션 페이로드를 대상으로 합니다.

***

## 모듈 `hwpx.oxml.document`

### 독립형 헬퍼

- `_serialize_xml(element) -> bytes`: `ElementTree` 엘리먼트를 XML 선언과 함께 UTF-8로 직렬화합니다.
- `_paragraph_id()`, `_object_id()`, `_memo_id()`: 단락, 인라인 객체, 메모 노드를 위한 고유 식별자를 생성합니다.
- `_create_paragraph_element(text, ...)`: 선택적 서식 재정의를 포함하여 단일 런과 텍스트 노드를 포함하는 단락 엘리먼트를 빌드합니다.
- `_element_local_name(node)`: 메모 파싱에서 사용되는 네임스페이스가 제거된 태그 헬퍼입니다.
- `_distribute_size(total, parts)`: 표의 행 또는 열에 걸쳐 크기를 균등하게 분배합니다.
- `_default_cell_attributes(border_fill_id_ref)`: 표 셀의 기본 속성 집합을 반환합니다.
- `_default_sublist_attributes()`: `<hp:subList>` 컨테이너의 기본 속성을 제공합니다.
- `_default_cell_paragraph_attributes()`: 표 셀 단락의 기본 단락 속성을 생성합니다.
- `_default_cell_margin_attributes()`: 표 셀에 대한 여백이 0인 속성을 제공합니다.
- `_get_int_attr(element, name, default=0)`: 정수 속성을 안전하게 파싱하며, 실패 시 기본값을 사용합니다.
- `_char_properties_from_header(element)`: 헤더 파트에서 글자 스타일 정의 매핑을 빌드합니다.

### 데이터 클래스

- `PageSize`: 페이지 너비, 높이, 방향, 제본 여백 유형을 저장합니다.
- `PageMargins`: 왼쪽, 오른쪽, 위, 아래, 머리글, 바닥글, 제본 여백 간격을 저장합니다.
- `SectionStartNumbering`: 섹션 수준의 카운터와 페이지 시작 동작을 추적합니다.
- `DocumentNumbering`: 전체 문서의 기본 번호 매기기 값입니다.
- `RunStyle`: 확인된 런 서식을 캡슐화하며 다음을 제공합니다:
  - `text_color()`: 런의 색상 (설정된 경우)을 반환합니다.
  - `underline_type()`: 밑줄 스타일을 확인합니다.
  - `underline_color()`: 밑줄 색상을 확인합니다.
  - `matches(...)`: 색상/밑줄 일치를 위한 편의 술어(predicate)입니다.

### 클래스 `HwpxOxmlSectionHeaderFooter`

- `id`: 머리글/바닥글 식별자를 관리하며 변경 시 섹션을 dirty로 표시하는 getter/setter가 있는 프로퍼티입니다.
- `apply_page_type`: 머리글/바닥글이 적용될 페이지 유형(양쪽/홀수/짝수)을 제어하는 프로퍼티입니다.
- `text`: 머리글/바닥글의 텍스트 내용을 읽거나 교체하는 프로퍼티입니다.
- `_initial_sublist_attributes()` / `_ensure_text_element()`: 텍스트가 처음 할당될 때 중첩된 단락 구조를 지연 생성하는 내부 헬퍼입니다.

### 클래스 `HwpxOxmlSectionProperties`

- `_page_pr_element(create=False)` / `_margin_element(create=False)`: 페이지 속성 및 여백 노드를 가져오거나 빌드하는 내부 헬퍼입니다.
- `page_size`: 섹션의 페이지 설정을 설명하는 `PageSize`를 반환하는 프로퍼티입니다.
- `set_page_size(...)`: 페이지 설정 값을 업데이트하고 변경 시 섹션을 dirty로 표시합니다.
- `page_margins`: 섹션의 `PageMargins` 객체를 반환하는 프로퍼티입니다.
- `set_page_margins(...)`: 음수가 아닌 값으로 여백 속성을 업데이트합니다.
- `start_numbering`: `<hp:startNum>`의 `SectionStartNumbering` 스냅샷을 반환하는 프로퍼티입니다.
- `set_start_numbering(...)`: 번호 매기기 카운터와 페이지 시작 동작을 수정하며, `<hp:startNum>` 엘리먼트가 없으면 생성합니다.
- `headers`, `footers`: 기존 머리글/바닥글 정의에 대한 래퍼를 반환하는 프로퍼티입니다.
- `get_header(page_type="BOTH")` / `get_footer(...)`: 지정된 페이지 유형의 기존 머리글/바닥글 래퍼를 가져옵니다.
- `set_header_text(text, ...)` / `set_footer_text(...)`: 요청된 페이지 유형에 대한 머리글/바닥글이 있는지 확인하고 텍스트 내용을 교체합니다.
- `remove_header(page_type="BOTH")` / `remove_footer(...)`: 지정된 페이지 유형의 머리글/바닥글 노드가 있으면 제거합니다.

### 클래스 `HwpxOxmlRun`

- `char_pr_id_ref`: 런의 글자 스타일 참조를 노출하며, XML과 섹션의 dirty 플래그를 업데이트하는 setter가 있는 프로퍼티입니다.
- `text`: 런 내의 연결된 텍스트 노드를 읽거나 교체하는 프로퍼티입니다.
- `style`: 문서를 참조하여 확인된 `RunStyle`을 반환하는 프로퍼티입니다.
- `replace_text(search, replacement, count=None)`: 일반 텍스트 노드에서 문자열을 교체하고 교체 횟수를 반환합니다.
- `remove()`: 부모 단락에서 런 엘리먼트를 삭제합니다.
- `bold`, `italic`, `underline`: 일치하는 런 스타일을 보장하여 서식 플래그를 토글하는 프로퍼티입니다.
- `_current_format_flags()`, `_apply_format_change(...)`, `_plain_text_nodes()`, `_ensure_plain_text_node()`: 서식 로직을 관리하는 내부 헬퍼입니다.

### 클래스 `HwpxOxmlMemoGroup`

- `memos`: 각 메모 자식에 대한 `HwpxOxmlMemo` 래퍼를 반환하는 프로퍼티입니다.
- `add_memo(...)`: 메모 노드를 추가하고, 텍스트를 초기화한 후, 래퍼를 반환합니다.
- `_cleanup()`: 메모 그룹 엘리먼트가 비어 있을 때 이를 제거하는 내부 헬퍼입니다.

### 클래스 `HwpxOxmlMemo`

- `id`, `memo_shape_id_ref`: XML 속성을 업데이트하는 setter가 있는 메모 메타데이터를 노출하는 프로퍼티입니다.
- `attributes`: 메모의 속성 집합 복사본을 딕셔너리로 반환합니다.
- `set_attribute(name, value)`: 임의의 속성을 추가하거나 제거합니다.
- `paragraphs`: 메모 텍스트에 포함된 단락 래퍼를 반환하는 프로퍼티입니다.
- `text`: 단락 텍스트를 줄 바꿈 문자로 결합하는 프로퍼티입니다. setter는 `set_text()`에 위임합니다.
- `set_text(value, char_pr_id_ref=None)`: 제공된 텍스트와 스타일로 메모 단락 목록을 다시 빌드합니다.
- `_infer_char_pr_id_ref()`: 기존 메모 단락을 검사하여 스타일을 추측하는 내부 헬퍼입니다.
- `remove()`: 부모 그룹에서 메모를 제거하고 정리를 트리거합니다.

### 클래스 `HwpxOxmlInlineObject`

- `tag`: 엘리먼트의 정규화된 태그를 반환하는 프로퍼티입니다.
- `attributes`: 인라인 객체 속성의 복사본을 반환하는 프로퍼티입니다.
- `get_attribute(name)` / `set_attribute(name, value)`: 변경이 발생하면 단락을 dirty로 표시하는 개별 속성 접근자입니다.

### 클래스 `HwpxOxmlTableCell`

- `address`: `<hp:cellAddr>`에서 파생된 `(행, 열)` 튜플을 반환하는 프로퍼티입니다.
- `span`: `<hp:cellSpan>`의 `(행 병합, 열 병합)` 값을 반환하는 프로퍼티입니다.
- `set_span(row_span, col_span)`: 병합 속성을 업데이트하고 표를 dirty로 표시합니다.
- `width`, `height`: `<hp:cellSz>`에서 캐시된 셀 크기를 노출하는 프로퍼티입니다.
- `set_size(width=None, height=None)`: 크기 속성을 0 또는 그 이상으로 업데이트합니다.
- `text`: 셀 내부의 첫 번째 텍스트 노드를 반환하는 프로퍼티입니다. setter는 텍스트를 할당하기 전에 중첩된 단락 구조가 있는지 확인합니다.
- `remove()`: 행에서 셀 엘리먼트를 제거합니다.
- `_addr_element()`, `_span_element()`, `_size_element()`, `_ensure_text_element()`: 중첩된 XML 구조를 관리하는 내부 헬퍼입니다.

### 클래스 `HwpxOxmlTableRow`

- `cells`: 행에 대한 `HwpxOxmlTableCell` 래퍼 목록을 반환하는 프로퍼티입니다.

### 클래스 `HwpxOxmlTable`

- `create(rows, cols, ...)`: 분배된 셀 크기, 여백, 초기 텍스트 노드를 포함하는 완전한 표 엘리먼트를 생성하는 클래스 메서드입니다.
- `mark_dirty()`: 표가 변경되었음을 소유한 섹션에 알립니다.
- `row_count`, `column_count`: 저장된 행/열 수를 확인하거나 XML 구조에서 파생하는 프로퍼티입니다.
- `rows`: `HwpxOxmlTableRow` 래퍼를 반환하는 프로퍼티입니다.
- `cell(row_index, col_index)`: 병합 정보를 고려하여 요청된 그리드 좌표를 포함하는 셀을 찾습니다.
- `set_cell_text(row_index, col_index, text)`: 셀의 텍스트 내용을 업데이트하는 단축 메서드입니다.
- `merge_cells(start_row, ...)`: 직사각형 영역의 유효성을 검사하고, 종속 셀을 제거하며, 병합 및 크기 값을 업데이트한 후, 살아남은 대상 셀을 반환합니다.

### 클래스 `HwpxOxmlParagraph`

- `runs`: 각 런에 대한 `HwpxOxmlRun` 래퍼를 반환하는 프로퍼티입니다.
- `text`: 런들의 텍스트를 연결하는 프로퍼티입니다. setter는 다른 자식 노드를 보존하면서 텍스트 내용을 교체합니다.
- `add_run(text="", ...)`: 새 런을 추가하고, 선택적으로 소유 문서를 통해 일치하는 글자 스타일을 생성한 후, 래퍼를 반환합니다.
- `tables`: 단락 내에 포함된 `HwpxOxmlTable` 래퍼를 반환하는 프로퍼티입니다.
- `add_table(...)`, `add_shape(...)`, `add_control(...)`: 적절한 런을 생성하여 인라인 객체(표, 도형, 컨트롤)를 삽입하고 래퍼 객체를 반환합니다.
- `para_pr_id_ref`, `style_id_ref`, `char_pr_id_ref`: 단락 수준의 서식 재정의를 허용하는 setter가 있는 프로퍼티입니다.
- `_run_elements()`, `_ensure_run()`, `_create_run_for_object()`: 위 작업들을 위해 런 생성 및 접근을 관리하는 내부 헬퍼입니다.

### 클래스 `HwpxOxmlSection`

- `properties`: `<hp:secPr>` 계층이 필요할 때 이를 생성하며 `HwpxOxmlSectionProperties` 래퍼를 반환하는 프로퍼티입니다.
- `element`: 원시 섹션 `Element`를 반환하는 프로퍼티입니다.
- `document`: 소유 `HwpxOxmlDocument`를 참조하는 프로퍼티입니다. `attach_document()`는 섹션을 문서 인스턴스와 연결합니다.
- `paragraphs`: 문서 순서대로 단락 래퍼를 반환하는 프로퍼티입니다.
- `memo_group`: 메모 그룹이 존재할 때 `HwpxOxmlMemoGroup` 래퍼를 반환하는 프로퍼티입니다.
- `memos`: 섹션의 메모 래퍼를 반환하는 프로퍼티입니다.
- `add_memo(...)`: 메모 그룹이 있는지 확인한 후 `HwpxOxmlMemoGroup.add_memo()`에 위임하는 편의 메서드입니다.
- `add_paragraph(text="", ...)`: 선택적 서식 재정의와 함께 단락 엘리먼트를 추가하고 그 래퍼를 반환합니다.
- `mark_dirty()`, `dirty`, `reset_dirty()`: 섹션을 저장해야 하는지 여부를 추적합니다.
- `to_bytes() -> bytes`: `_serialize_xml()`을 사용하여 섹션 엘리먼트를 직렬화합니다.

### 클래스 `HwpxOxmlHeader`

- `element`: 원시 헤더 `Element`를 반환하는 프로퍼티입니다.
- `document`: 소유 문서를 참조하는 프로퍼티입니다. `attach_document()`로 할당합니다.
- `ensure_char_property(...)`: `predicate`와 일치하는 `<hh:charPr>` 항목이 있는지 확인합니다. 일치하는 항목이 없으면 기존 항목을 복제(또는 빈 항목 생성)하고, `modifier`를 적용하며, 고유 ID를 할당하고, `itemCnt`를 업데이트한 후, 문서의 글자 스타일 캐시를 무효화합니다.
- `begin_numbering`: `<hh:beginNum>`에서 생성된 `DocumentNumbering` 스냅샷을 반환하는 프로퍼티입니다.
- `set_begin_numbering(...)`: 음수가 아닌 카운터 값으로 `<hh:beginNum>` 엘리먼트를 업데이트하거나 생성합니다.
- `memo_shapes`: 헤더의 참조 목록에서 추출한 메모 모양 딕셔너리를 반환하는 프로퍼티입니다.
- `memo_shape(memo_shape_id_ref)`: ID로 메모 모양을 가져옵니다.
- `dirty`, `mark_dirty()`, `reset_dirty()`: 저장 작업을 위해 보류 중인 변경 사항을 추적합니다.
- `to_bytes()`: `_serialize_xml()`로 헤더 엘리먼트를 직렬화합니다.
- 내부 헬퍼들은 위의 공개 작업을 지원합니다.

### 클래스 `HwpxOxmlDocument`

- `from_package(package)`: `HwpxPackage`에서 매니페스트, 섹션 XML 파트, 헤더 XML 파트를 읽고 래핑하는 클래스 메서드입니다.
- `manifest`: 원시 매니페스트 엘리먼트를 노출하는 프로퍼티입니다.
- `sections`, `headers`: 섹션 및 헤더 래퍼 목록의 복사본을 반환하는 프로퍼티입니다.
- `char_properties`: 글자 스타일 ID를 `RunStyle` 객체에 매핑한 딕셔너리를 반환하며, 모든 헤더의 결과를 캐시합니다.
- `char_property(char_pr_id_ref)`: 문자열 또는 숫자 값을 받아 ID로 `RunStyle`을 조회합니다.
- `ensure_run_style(...)`: 요청된 굵게, 기울임, 밑줄 플래그를 가진 런 스타일이 첫 번째 헤더에 존재하는지 확인하며, 필요에 따라 항목을 생성하거나 복제합니다.
- `memo_shapes`: 모든 헤더의 메모 모양을 하나의 딕셔너리로 병합하는 프로퍼티입니다.
- `memo_shape(memo_shape_id_ref)`: ID로 메모 모양을 가져옵니다.
- `paragraphs`: 모든 섹션의 단락 래퍼를 연결하여 반환하는 프로퍼티입니다.
- `add_paragraph(...)`: `section` 또는 `section_index`를 사용하여 대상 섹션을 선택하여 단락을 추가하도록 섹션에 위임합니다. 기본값은 마지막 섹션입니다.
- `serialize() -> dict[str, bytes]`: 변경된(dirty) 섹션/헤더에 대한 업데이트된 파트 페이로드 딕셔너리를 반환합니다.
- `reset_dirty()`: 저장 후 모든 섹션과 헤더를 깨끗한(clean) 상태로 표시합니다.
- 내부 헬퍼는 캐시된 런 스타일을 유지 관리합니다.

***

## 모듈 `hwpx.opc.package`

### 예외

- `HwpxPackageError`: 패키지 조작 오류에 대한 기본 예외입니다.
- `HwpxStructureError`: HWPX 패키지의 필수 구조 구성 요소가 없거나 일치하지 않을 때 발생합니다.

### 데이터 클래스

- `RootFile`: `META-INF/container.xml` 내의 `<rootfile>` 항목을 나타내며, 참조된 경로가 아카이브에 있는지 확인하는 `ensure_exists(files)`를 제공합니다.

### 클래스 `VersionInfo`

- `from_bytes(data)`: `version.xml`을 파싱하여 네임스페이스 선언과 선택적 XML 선언 헤더를 캡처하는 클래스 메서드입니다.
- `_collect_namespaces(data)`: `iterparse()`를 사용하여 네임스페이스 접두사를 기록하는 내부 헬퍼입니다.
- `_extract_declaration(data)`: 직렬화 시 XML 선언을 보존하는 내부 헬퍼입니다.
- `attributes`: 루트 엘리먼트 속성의 얕은 복사본을 반환하는 프로퍼티입니다.
- `get(key, default=None)`: 속성에 대한 편의 접근자입니다.
- `set(key, value)`: 속성을 업데이트하고 객체를 dirty로 표시합니다.
- `tag`: 루트 엘리먼트 태그 이름을 반환하는 프로퍼티입니다.
- `to_bytes()`: 엘리먼트를 다시 바이트로 직렬화하며, 네임스페이스를 다시 등록하고 원래 XML 선언이 있으면 다시 앞에 추가합니다.
- `dirty`: 변경 사항이 있었는지 여부를 나타내는 프로퍼티입니다.
- `mark_clean()`: 패키지가 `version.xml`을 저장한 후 dirty 플래그를 재설정합니다.

### 클래스 `HwpxPackage`

#### 생성 헬퍼

- `open(pkg_file)`: zip 아카이브를 읽고, 필수 항목의 유효성을 검사하며, `container.xml`과 `version.xml`을 파싱한 후, 패키지 래퍼를 반환하는 클래스 메서드입니다.
- `_parse_container(data)`: `<rootfile>` 선언을 추출하고 필수 속성을 강제하며 오류 시 `HwpxStructureError`를 발생시키는 내부 파서입니다.
- `_parse_version(data)`: `VersionInfo` 인스턴스를 생성하거나 파일이 없을 때 예외를 발생시키는 내부 파서입니다.
- `_validate_structure()`: 필수 파일이 존재하고, 최소 하나의 콘텐츠 항목이 `Contents` 디렉토리 아래에 있는지 확인합니다.

#### 패키지 메타데이터

- `mimetype`: 현재 패키지 mimetype 문자열을 노출하는 프로퍼티입니다.
- `rootfiles`: `container.xml`에 선언된 `RootFile` 항목들의 튜플을 반환하는 프로퍼티입니다.
- `iter_rootfiles()`: 선언 순서대로 루트 파일을 순회하는 이터레이터입니다.
- `main_content`: 미디어 유형이 주 HWPML 패키지를 나타내는 루트 파일을 반환하며, 기본값은 첫 번째 항목입니다.
- `version_info`: 변경 가능한 `VersionInfo` 인스턴스를 노출하는 프로퍼티입니다.

#### 파일 조작

- `read(path)`: 메모리 내 파일 딕셔너리에서 정규화된 경로의 데이터를 가져오거나, 없으면 `HwpxPackageError`를 발생시킵니다.
- `write(path, data)`: 경로에 대한 바이트를 저장하며, 구조적 파일을 자동으로 파싱하고 업데이트 후 패키지를 다시 검증합니다.
- `delete(path)`: 필수가 아닌 파일을 제거하고 패키지를 다시 검증합니다.
- `_normalize_path(path)`: 일관성을 위해 백슬래시를 슬래시로 변환하는 내부 헬퍼입니다.
- `files()`: 패키지에 포함된 파일 이름의 정렬된 목록을 반환합니다.
- `save(pkg_file)`: 패키지를 디스크나 파일과 유사한 객체에 씁니다. mimetype이 압축되지 않은 상태로 저장되도록 하고, 변경된 `version.xml`을 직렬화하며, 구조를 검증하고, 다른 파일들은 deflate 압축으로 씁니다.
- `_write_mimetype(zf)`: OPC 사양에 따라 `ZIP_STORED`를 사용하여 mimetype 항목을 쓰는 내부 헬퍼입니다.

***

## 모듈 `hwpx.tools.text_extractor`

### 상수

- `DEFAULT_NAMESPACES`: HWPX XML 페이로드 쿼리 시 사용되는 네임스페이스 접두사 매핑입니다.
- `_SECTION_PATTERN`: 섹션 XML 파일 이름(`Contents/section*.xml`)과 일치하는 정규 표현식입니다.
- `_OBJECT_CONTAINERS`: 중첩된 객체 컨테이너로 취급되는 엘리먼트 이름 집합입니다.

### 타입 별칭

- `_ObjectBehavior`, `HighlightBehavior`, ...: 인라인 주석이 렌더링되는 방식을 설명하는 리터럴 유니언입니다.

### 데이터클래스

- `AnnotationOptions`: 텍스트 추출 중 하이라이트, 메모, 하이퍼링크, 컨트롤이 표현되는 방식을 제어하는 설정입니다. `highlight_start`, `note_inline_format`과 같은 필드는 마커 템플릿을 정의합니다.
- `SectionInfo`: 섹션 인덱스, 아카이브 경로, 파싱된 루트 엘리먼트를 기록합니다.
- `ParagraphInfo`: 소유 섹션, 단락 인덱스, 엘리먼트, 계산된 경로, 조상 계층, 그리고 이를 생성한 추출기를 참조합니다. 다음을 제공합니다:
  - `tag`: 로컬 태그 이름을 반환하는 프로퍼티입니다.
  - `ancestors`: 부모 태그의 튜플을 반환하는 프로퍼티입니다.
  - `is_nested`: 단락이 객체 내에 중첩되어 있는지 여부를 나타내는 프로퍼티입니다.
  - `text(...)`: `TextExtractor.paragraph_text()`에 위임하는 메서드입니다.

### 클래스 `TextExtractor`

- `__init__(source, ...)`: 데이터 소스(경로, zip 파일, `ZipFile` 인스턴스)를 저장하고, 사용자 정의 네임스페이스를 기본값과 병합하며, 필요할 때까지 아카이브 열기를 지연시킵니다.
- `open()`: 필요한 경우 내부 아카이브를 열고 `ZipFile` 핸들을 반환하며, 제공된 객체가 있으면 재사용합니다.
- `close()`: 추출기가 소유한 경우 아카이브를 닫습니다.
- `__enter__()`, `__exit__()`: 확정적인 리소스 관리를 위한 컨텍스트 관리자 지원입니다.
- `iter_sections()`: 각 섹션 XML 항목을 읽고 파싱하여 섹션 메타데이터를 순회(yield)합니다.
- `iter_paragraphs(section, ...)`: 주어진 섹션 내의 모든 단락에 대한 `ParagraphInfo`를 순회합니다. 재귀적으로(`include_nested=True`) 또는 최상위 단락만 순회할 수 있습니다.
- `iter_document_paragraphs(...)`: 모든 섹션의 모든 단락을 순회합니다.
- `paragraph_text(paragraph, ...)`: 단락 엘리먼트를 텍스트로 변환합니다. 런을 순회하고 제공된 동작 플래그와 주석 옵션에 따라 중첩된 엘리먼트(줄 바꿈, 탭, 메모 등)를 처리합니다.
- `_handle_object(...)`, `_handle_note(...)` 등: `paragraph_text()`에서 중첩된 객체, 주석, 컨트롤 구조를 렌더링하거나 건너뛰기 위해 사용하는 내부 헬퍼입니다.
- `extract_text(paragraph_separator="\n", ...)`: 문서의 모든 단락을 순회하고 렌더링된 텍스트를 요청된 구분 기호로 결합하는 편의 메서드입니다.
- `_iter_section_files(archive)`: `content.hpf`를 사용하거나 매니페스트가 불완전할 경우 아카이브를 스캔하여 섹션 파일 이름을 열거하는 내부 헬퍼입니다.

### 모듈 수준 헬퍼

- `_resolve_note_text(...)`: 제공된 추출기를 사용하여 메모 `subList` 컨테이너에서 단락 텍스트를 수집합니다.
- `_resolve_control_nested_text(...)`: 주석이 중첩 렌더링을 허용할 때 컨트롤 엘리먼트의 중첩된 단락 텍스트를 추출합니다.
- `_resolve_hyperlink_target(...)`: `fieldBegin` 매개변수에서 하이퍼링크 대상을 추출합니다.
- `strip_namespace(tag)`: 태그 이름에서 네임스페이스 접두사를 제거합니다.
- `tag_matches(...)`: 후보 태그가 쿼리 문자열 또는 시퀀스와 일치하는지 네임스페이스 접두사를 존중하며 테스트합니다.
- `build_parent_map(root)`: 자식 엘리먼트를 부모에 매핑하는 딕셔너리를 빌드하여 엘리먼트 경로 구성에 유용합니다.
- `describe_element_path(...)`: 섹션 내에서 엘리먼트를 식별하는 XPath와 유사한 문자열을 생성합니다.
- `_section_sort_key(name)`: 섹션 이름이 숫자 순서로 처리되도록 보장하는 정렬 헬퍼입니다.

***

## 모듈 `hwpx.tools.object_finder`

### 타입 별칭 및 데이터클래스

- `AttrMatcher`: 문자열, 시퀀스, 정규식 패턴 또는 호출 가능 객체를 허용하는 속성 매처 타입 별칭입니다.
- `FoundElement`: 섹션, 엘리먼트 경로, 그리고 내부 엘리먼트를 기록합니다. 다음을 제공합니다:
  - `tag`: 로컬 태그 이름을 반환하는 프로퍼티입니다.
  - `hierarchy`: 경로를 세그먼트로 나눈 것을 반환하는 프로퍼티입니다.
  - `text`: `element.text`를 대리하는 프로퍼티입니다.
  - `get(name, ...)`: 속성 접근 헬퍼입니다.
- `AnnotationMatch`: `ObjectFinder.iter_annotations()`에 의해 발견된 주석을 나타내며, 주석 종류, 엘리먼트 위치, 렌더링된 값을 저장합니다.

### 클래스 `ObjectFinder`

- `__init__(source, ...)`: 데이터 소스와 네임스페이스 매핑을 저장합니다.
- `iter(tag=None, attrs=None, ...)`: 태그 기준, 속성 술어, 선택적 XPath 선택자 및 섹션 필터와 일치하는 `FoundElement` 객체를 순회(yield)하는 제너레이터입니다. `limit`이 제공되면 해당 수만큼 찾은 후 중지합니다.
- `find_first(...)`: `iter()`에 `limit=1`을 위임하여 첫 번째 일치하는 엘리먼트 또는 `None`을 반환합니다.
- `find_all(...)`: `iter()`를 즉시 소비하여 모든 일치 항목의 목록을 반환합니다.
- `iter_annotations(kinds=None, ...)`: 하이라이트, 메모, 하이퍼링크, 컨트롤 주석을 문서에서 검색하여, 제공된 `AnnotationOptions`에 따라 서식이 지정된 `AnnotationMatch` 객체를 순회합니다.
- `_format_note_annotation(...)`: 동작 설정에 따라 메모 주석을 정규화하는 내부 헬퍼입니다.
- `_match_attributes(element, expected)`: `iter()`를 위한 속성 일치 규칙을 평가하는 정적 헬퍼입니다.

***

## 모듈 `hwpx.tools.validator`

### 데이터 클래스

- `DocumentSchemas`: 로드된 헤더 및 섹션 XML 스키마 객체를 저장합니다.
- `ValidationIssue`: 유효성 검사 실패를 나타냅니다. 파트 이름, 위치, 오류 메시지를 결합한 사람이 읽기 쉬운 `__str__` 구현을 제공합니다.
- `ValidationReport`: 유효성 검사 결과를 집계하며, 검증된 파트 이름과 이슈를 저장합니다. `ok` 프로퍼티(및 진리값)는 모든 검사가 통과했는지 여부를 나타냅니다.

### 함수

- `load_default_schemas(schema_dir=None)`: 번들로 제공되는 헤더 및 섹션 XSD 파일을 로드하며, 스키마 디렉토리가 없을 때 예외를 발생시킵니다.
- `_iter_parts(document)`: `HwpxDocument`의 모든 헤더와 섹션에 대해 `(파트 이름, XML 바이트, 헤더 여부)`를 순회하는 내부 헬퍼입니다.
- `_issues_from_error(part_name, exc)`: `lxml` 유효성 검사 오류를 `ValidationIssue` 인스턴스로 정규화합니다.
- `validate_document(source, ...)`: 문서를 열고, 제공되지 않은 경우 기본 스키마를 로드하며, 각 헤더 및 섹션 파트를 적절한 파서로 검증하고 이슈를 집계합니다.
- `main(argv=None)`: 인자를 파싱하고, 문서를 검증하며, 결과를 출력하는 명령줄 진입점입니다. 성공 시 0을, 이슈 발생 시 0이 아닌 값을 반환합니다.

***

## 모듈 `hwpx.__init__`

이 패키지는 편의를 위해 다음과 같은 재내보내기(re-exports)를 노출합니다:

- `hwpx.tools.text_extractor` 모듈의 `DEFAULT_NAMESPACES`, `ParagraphInfo`, `SectionInfo`, `TextExtractor`
- `hwpx.tools.object_finder` 모듈의 `FoundElement`, `ObjectFinder`
