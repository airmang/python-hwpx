# API Reference

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
  - 보류 중인 업데이트를 적용한 뒤 editor-open safety 검증을 통과한 경우에만 대상 경로/스트림/바이트를 반환합니다. 대상이 제공되지 않으면 `bytes`를 반환하고, 경로나 스트림이 제공되면 검증된 임시 ZIP을 만든 뒤 대상에 반영합니다.
  - `verify_open_safety=False` 같은 우회 파라미터는 public API에서 지원하지 않습니다.
  - `_write_archive()`, `_write_zip_entry()`, `_write_mimetype()` 같은 raw ZIP writer는 save 내부 컨텍스트 전용입니다. 직접 호출하지 말고 `save()`를 사용해야 package validation, document validation, reopen 검증이 함께 실행됩니다.

***

## 모듈 `hwpx.document`

### 클래스 `HwpxDocument`

#### 생성자

- `open(source)`
  - HWPX 파일을 열고, `HwpxOxmlDocument`로 저수준 XML 트리를 빌드한 후 문서 래퍼(wrapper)를 반환합니다.
    *source*는 경로·바이트·이진 스트림, 또는 이미 연 `HwpxPackage`입니다(6.x의 `from_package(package)`는
    7.0에서 `open(package)`로 합쳤습니다).
- `new()`
  - 스켈레톤 템플릿 번들을 로드하여 새 문서를 생성합니다.

#### 패키지 및 XML 접근

- `package`
  - 내부의 `HwpxPackage` 컨테이너를 노출하는 프로퍼티입니다.
- `oxml`
  - 루트 `HwpxOxmlDocument` 트리를 반환하는 프로퍼티입니다.
- `sections`, `headers`
  - 섹션/헤더 래퍼 목록을 반환하는 프로퍼티입니다.

#### 메모 헬퍼 (`doc.notes`·`doc.styles`)

6.x 루트의 메모 이름(`doc.memo_shapes`·`doc.add_memo` …)은 7.0에서 없어졌다(부르면 새 자리를 알려 주는 오류).

- `doc.styles.memo_shapes`, `doc.styles.memo_shape(memo_shape_id_ref)`
  - 헤더의 메모 모양 정의(id 색인)와 그 하나. `doc.styles.ensure_memo_shape(...)`가 정의를 보장하고 id를 돌려준다.
- `doc.notes.memos`
  - 모든 구역의 메모(`Memo`)를 문서 순서의 tuple로 돌려주는 프로퍼티입니다.
- `doc.notes.add_memo(text, *, paragraph=None, section=None, ...) -> Memo`
  - 메모를 만들고, `paragraph=`(번호나 문단 객체)를 주면 그 문단에 한/글이 보이는 MEMO 필드를 붙입니다. 구역은 `section=`(번호나 구역 객체), 주지 않으면 마지막 구역입니다. 6.x의 `memo_shape_id_ref=`는 7.0에서 없어졌습니다(메모 모양은 구역마다).
- `doc.notes.set_memo_shape(memo_shape_id_ref, *, section=None)`
  - 구역의 메모 모양(`hp:secPr@memoShapeIDRef`)을 정합니다. 그 구역의 메모가 모두 이 모양으로 그려집니다. `section="all"`이면 모든 구역, `None` 모양이면 기본 모양(`"0"`). 없는 id는 `note-memo-shape-not-found`. 읽기는 `doc.sections[i].properties.memo_shape_id_ref`.
- `doc.notes.attach(paragraph, memo) -> Memo`, `doc.notes.remove_memo(memo)`
  - 이미 있는 메모를 문단에 붙이고, 메모를 지웁니다.

#### 텍스트 및 서식 헬퍼 (`doc.text`·`doc.styles`)

- `doc.paragraphs`
  - 본문의 모든 문단을 문서 순서의 tuple로 돌려주는 프로퍼티입니다. 표 칸·머리말까지는 `doc.text.iter_paragraphs()`.
- `doc.styles.char_properties`, `doc.styles.char_property(char_pr_id_ref)`
  - 글자 모양 정의(id 색인)와 그 하나(`RunStyle`).
- `doc.styles.ensure_run(..., base_char_pr_id_ref=None) -> str`
  - 기준 글자 모양(없으면 첫 글자 모양)에서 요청한 값만 바꾼 글자 모양의 id를 돌려줍니다. 내용이 같은 정의가 있으면 그것을, 없으면 기준을 복제해 만듭니다.
- `doc.text.iter_runs()`
  - 문서 본문의 모든 런을 차례로 내놓습니다(`Iterator[Run]`).
- `doc.text.find_runs(...) -> tuple[Run, ...]`
  - 색상, 밑줄 유형 또는 특정 글자 속성 참조와 같은 스타일 속성으로 런을 고릅니다.
- `doc.text.replace(search, replacement, ...) -> int`
  - 문자열을 바꿉니다. 교체 횟수를 제한할 수 있고, `everywhere=True`면 표 칸·머리말과 서식이 다른 런에 걸친 글도 바꿉니다.

#### 글꼴 표와 테두리 읽기 (`doc.styles`)

글꼴 id는 `hh:fontface` lang 블록마다 따로 매겨집니다. `hh:fontRef/@hangul`은 HANGUL 블록의 id, `@latin`은 LATIN 블록의 id입니다. 아래 호출은 모두 메모리의 첫 헤더를 읽으므로 `ensure_font()`·`ensure_border_fill()` 직후에도 맞습니다. *lang*은 HANGUL·LATIN·HANJA·JAPANESE·OTHER·SYMBOL·USER 중 하나(대소문자 무시)이고, 그 밖이면 `HwpxValueError`(`style-font-lang-invalid`)입니다.

- `styles.fonts(lang="HANGUL") -> dict[str, Font]`
  - 그 lang 블록의 `hh:font` 목록을 id 문자열 → `hwpx.oxml.Font`로 돌려줍니다. 블록이 없으면 `{}`입니다.
- `styles.font_face(char_pr_id_ref, lang="HANGUL") -> str | None`
  - 글자 모양의 `fontRef`가 그 lang 블록에서 가리키는 글꼴 이름입니다. 글자 모양·`fontRef`·속성·글꼴 id 중 하나라도 없으면 `None`입니다.
- `styles.ensure_run(..., font_by_lang={"HANGUL": "함초롬바탕", "LATIN": "Arial"}) -> str`
  - 언어마다 다른 글꼴을 쓰는 글자 모양의 id입니다. 기준 글자 모양을 복사해, 댄 언어마다 글꼴을 그 lang 블록에 등록하고(없으면 더함) 그 블록의 id를 `fontRef/@<lang 소문자>`에 씁니다. 대지 않은 언어와 다른 값은 기준을 따르고 기준 자체는 바뀌지 않습니다. 내용이 같은 글자 모양이 있으면 그 id를 돌려줍니다. `font`와 함께 주면 `font_by_lang`이 댄 언어는 `font_by_lang`을 따릅니다. 모르는 lang은 `style-font-lang-invalid`, 빈 이름은 `style-font-face-empty`, 매핑이 아니거나 같은 lang을 두 번 댄 값은 `style-run-font-by-lang-invalid`로 아무 글꼴도 등록하기 전에 거부합니다. 예제는 [실전 예제 6](examples.md)에 있습니다.
- `styles.ensure_run(..., letter_spacing_by_lang={"HANGUL": 0, "LATIN": -5}) -> str`
  - 언어마다 다른 자간(%)을 쓰는 글자 모양의 id입니다. 언어 이름과 검사는 `font_by_lang`과 같고 값은 -50 ~ 50의 `int`(OWPML `hh:spacing`의 범위)입니다. 기준 글자 모양을 복사해 댄 언어의 `hh:spacing/@<lang 소문자>`만 바꾸고, 대지 않은 언어는 기준 값을 따릅니다(기준에 `hh:spacing`이 없으면 일곱 언어를 모두 적고 대지 않은 언어는 기본값 0). `letter_spacing`과 함께 주면 `letter_spacing_by_lang`이 댄 언어는 그 값을 따릅니다. 모르는 lang은 `style-font-lang-invalid`, 매핑이 아니거나 같은 lang을 두 번 댔거나 `int`가 아니거나 범위 밖인 값은 `style-run-letter-spacing-by-lang-invalid`로 아무것도 바꾸기 전에 거부합니다.
- `styles.border_fill(border_fill_id_ref) -> BorderFillInfo | None`, `styles.border_fills -> dict[str, BorderFillInfo]`
  - `hh:borderFill` 하나를 `BorderFillInfo(id, left, right, top, bottom, diagonal, fill, fill_kinds)`로 읽습니다. 각 변은 `BorderLine(type, width_mm, color)`이고 직계 자식 `hh:leftBorder`·`hh:rightBorder`·`hh:topBorder`·`hh:bottomBorder`·`hh:diagonal`에서 저장된 값 그대로 읽습니다. 요소가 없으면 `BorderLine("NONE", 0.0, "#000000")`입니다. `fill`은 첫 `hc:winBrush`의 `faceColor`이고, 없거나 `none`이면 `None`입니다. `fill_kinds`는 `hc:fillBrush`가 담은 채움의 종류를 적힌 차례대로 돌려줍니다: `"color"`(`hc:winBrush`, 면 색·무늬. `faceColor="none"`이어도 적힌 대로 `"color"`), `"gradation"`(`hc:gradation`), `"image"`(`hc:imgBrush`), 그 밖은 `"unknown"`. `hc:fillBrush`가 아예 없으면 `()`(채움 없음)입니다. 그러데이션의 색·그림의 파일 같은 자세한 값은 아직 XML(`doc.oxml.headers[0].element`)로 읽습니다. 너비를 `"<숫자> mm"`로 읽을 수 없으면 `style-border-fill-width-invalid`, 없는 id면 `None`입니다. 6.x의 `border_fill_info()`는 7.0에서 `border_fill()`로 합쳤습니다.
- `styles.replace_font(src_face, dst_face, *, langs=None, font_type=None) -> FontReplaceReport`
  - 글꼴 하나를 문서 전체에서 다른 글꼴로 바꿉니다. lang 블록마다(`langs`를 주면 그 블록만) *src_face*가 없으면 건너뛰고, *dst_face*가 없으면 블록 끝에 *dst_face* 글꼴을 더하고(다른 블록에 *dst_face* 선언이 있으면 그 `hh:font`를 id만 바꿔 복사해 `type`·자식 요소가 같고, 어디에도 없으면 `<hh:font id=… face=… type="TTF" isEmbedded="0"/>`, *font_type*을 주면 더하는 글꼴의 `type`은 그 값), *src_face*를 가리키던 `fontRef`를 *dst_face*로 옮긴 뒤 *src_face*를 지우고 남은 글꼴 id를 순서대로 0..N-1로 다시 매깁니다(`fontCnt`도 맞춤). 다른 `fontRef`는 모두 전과 같은 글꼴 이름을 가리킵니다. 결과 `FontReplaceReport`의 `langs`는 바뀐 블록, `declared`는 *dst_face*를 새로 더한 블록, `repointed`는 옮긴 `fontRef` 속성 수입니다. 빈 이름은 `style-font-face-empty`, 같은 이름 둘은 `style-font-replace-same-face`로 바꾸기 전에 거부합니다.

#### 스타일·문단 모양·번호 정의 (`doc.styles`)

응용 계층이 헤더 내부(`_styles_element()`·`_allocate_ref_id()`·`_update_item_count()`)를 직접 만지지 않고 스타일을 만들 수 있게 하는 공개 동사입니다. id 할당·`itemCnt`·변경 표시는 core가 맡습니다. 헤더가 없으면 `HwpxStateError`(`document-header-missing`)입니다.

- `styles.ensure_style(name, *, style_type=None, eng_name=None, para_pr_id_ref=None, char_pr_id_ref=None, next_style_id_ref=None, lang_id=None, lock_form=None) -> str`
  - 이름이 *name*인 `hh:style`의 id입니다. 한/글은 스타일을 이름으로 구별하므로 같은 이름이 있으면 새로 만들지 않고 그 id를 돌려주며, `None`이 아닌 키워드만 덮어씁니다. 없으면 새 id로 만들고(`style_type` 기본 `"PARA"`) `itemCnt`를 맞춥니다. 같은 이름을 따로 두려면 `styles.names`(속성, 이름의 tuple)로 겹치지 않는 이름을 먼저 고릅니다. `nextStyleIDRef`를 자기 자신으로 두려면 돌려받은 id로 한 번 더 부릅니다.
- `styles.ensure_paragraph_format(*, base_para_pr_id_ref=None, alignment=None, margins=None, heading=None, border=None, break_setting=None, tab_pr_id_ref=None, line_spacing=None, condense=None) -> str`
  - `ensure_run`의 문단 쪽 짝입니다. 기준 `paraPr`(없으면 첫 문단 모양)을 복사해 요청한 값만 바꾼 문단 모양의 id를 돌려주고, 같은 것이 있으면 다시 씁니다. 문단에 적용하지는 않습니다. 값은 OWPML 그대로입니다(`margins`는 HWPUNIT, `heading`은 `type`·`idRef`·`level`). `line_spacing`은 퍼센트 수(`160`)나 `LineSpacing`입니다. 사람 단위로 문단에 바로 적용하려면 `styles.apply_paragraph_format()`을 씁니다.
- `styles.numberings -> dict[str, NumberingInfo]`, `styles.numbering(numbering_id_ref) -> NumberingInfo | None`
  - 첫 헤더의 번호 정의(`hh:numbering`)를 id 문자열로 찾아 `NumberingInfo`(수준마다 `NumberingLevel`)로 읽습니다. 문단 모양 `hh:heading@idRef`가 가리키는 정의입니다. 글머리표 정의는 `styles.bullets`입니다.

#### 콘텐츠 생성 헬퍼

- `add_paragraph(text="", ...) -> HwpxOxmlParagraph`
  - 대상 섹션에 단락을 추가합니다. 선택적으로 단락 및 런 서식 참조를 재정의하거나 추가 단락 속성을 주입할 수 있습니다.
- `paragraph.remove()`
  - 단락을 삭제합니다(6.x의 `doc.remove_paragraph(...)`). 모델 `doc.oxml.remove_paragraph(paragraph_or_index, *, section=None)`도 있습니다.
- `add_section(after=None) -> HwpxOxmlSection`
  - 새 섹션을 문서에 추가합니다. `after`로 삽입 위치를 지정합니다. manifest/spine에 자동 등록됩니다.
- `remove_section(section_or_index)`
  - 섹션을 삭제합니다. 인스턴스 또는 인덱스를 받습니다. 마지막 섹션 삭제 시 `ValueError`가 발생합니다.
- `add_table(rows, cols, ...) -> HwpxOxmlTable`
  - 기본적으로 앞 제목·목록 스타일을 상속하지 않는 중립 단락을 삽입하고 그 안에 표 인라인 객체를 생성한 후, 표 래퍼를 반환합니다. 표 앵커가 앞 단락 서식을 의도적으로 이어받아야 하면 `inherit_style=True` 또는 명시적 단락·스타일 참조를 사용합니다. `border_fill_id_ref`를 생략하면 헤더 참조 목록에 기본 실선 `borderFill`을 생성하고 표와 셀에 자동으로 연결합니다.
- `add_picture(image_data, image_format, *, width, height, width_mm, height_mm, alignment, brightness, contrast, effect, alpha, line_color, line_width_mm, crop, shadow, glow, soft_edge, reflection, ...) -> Picture`
  - 이미지를 이진 항목으로 넣고 새 단락에 그림을 글자처럼 둡니다. 크기는 HWPUNIT(`width`·`height`)나 mm(`width_mm`·`height_mm`)로 받습니다(너비를 빼면 14400). 높이를 빼면 PNG는 그 가로세로 비율을, 다른 형식은 너비와 같은 높이를 씁니다. `alignment`는 그림을 둔 단락의 정렬, `line_width_mm`은 테두리 굵기(mm, 기본 0.12)입니다.
  - 이미지 조정: `brightness`·`contrast`(-100~100, 기본 0), `effect`(`REAL_PIC` 원래 그림·`GRAY_SCALE` 회색조·`BLACK_WHITE` 흑백, 대소문자 무관), `alpha`(투명도, 0 불투명~255 보이지 않음)를 받습니다.
  - 테두리: `line_color`를 주면 `line_width`(HWPUNIT, 기본 33) 굵기의 실선 테두리를 그립니다.
  - 자르기: `crop=(왼쪽, 위, 오른쪽, 아래)`는 `width` x `height` 그림의 네 변에서 그만큼(HWPUNIT) 잘라 냅니다. 축척은 그대로라 그림이 그만큼 작게 그려집니다.
  - 효과(`hwpx.oxml`에서 가져옵니다):
    - `shadow=PictureShadow(color, alpha, blur, direction, distance, inside)`: 그림자. 방향은 오른쪽에서 시계 방향 0~359도입니다(0 오른쪽, 90 아래).
    - `glow=PictureGlow(color, alpha, radius)`: 빛남.
    - `soft_edge`(HWPUNIT): 부드러운 가장자리.
    - `reflection=PictureReflection(size, distance, alpha_start, alpha_end, blur)`: 그림 아래 반사. `size`는 그림 높이의 몫(0 초과 1 이하)입니다.
    - 투명도(`alpha`)는 0~1이고 길이는 HWPUNIT입니다. 한/글은 그림을 바깥 효과(빛남·바깥 그림자·반사)까지 합친 크기로 배치하므로, 그만큼 줄이 높아집니다.
  - 한/글이 그대로 그리지 않는 값은 이진 항목·단락을 더하기 전에 거부합니다: `shape-picture-image-value`(조정), `shape-picture-border-value`(테두리 굵기), `shape-picture-crop-value`(자르기), `shape-picture-effect-value`(효과), `style-color-invalid`(색).
  - 같은 조정·효과를 `paragraph.add_picture(item_id, *, alignment=, line_width_mm=, ...)`도 받습니다(이미 넣은 이진 항목을 쓸 때: `item_id`는 `doc.media.add_image`가 돌려준 `BinaryItem`이나 그 id, 테두리 굵기는 mm).
  - 회전·뒤집기 인자는 없습니다. 만든 뒤 `picture.rotation = 각도`로 돌리고 `picture.flip_horizontal = True`·`picture.flip_vertical = True`로 뒤집습니다.
- `get_table_map() -> dict`
  - 문서 순서대로 표를 스캔하고 `table_index`, `paragraph_index`, 행·열 수, 추정 헤더 텍스트, 첫 행 미리보기, 빈 표 여부를 반환합니다.
  - 라벨로 칸을 찾아 채우는 `find_cell_by_label`·`fill_by_path`는 7.0에서 `python-hwpx-automation`(`hwpx_automation.forms`)으로 옮겼습니다.
- `add_line(start_x, start_y, end_x, end_y, *, line_color, line_width, ...) -> HwpxOxmlShape`
  - 새 단락에 선을 삽입합니다. 좌표는 HWPUNIT(1인치 = 7200)입니다.
- `add_rectangle(width, height, *, ratio, line_color, line_width, fill_color, ...) -> HwpxOxmlShape`
  - 새 단락에 사각형을 삽입합니다. `ratio`는 모서리 둥글기(0 = 직각, 50 = 반원)입니다.
- `add_ellipse(width, height, *, line_color, line_width, fill_color, ...) -> HwpxOxmlShape`
  - 새 단락에 타원을 삽입합니다.
  - 위 세 헬퍼는 한컴이 요구하는 하위 요소(`offset`·`orgSz`·`curSz`·`sz`·`pos`·유형별
    기하)를 모두 생성하므로 산출물이 그대로 열립니다. 도형은 이 경로를 쓰세요.
- `add_shape(shape_type, ...) -> HwpxOxmlInlineObject`
  - **저수준 탈출구.** 새 단락에 태그 이름으로 인라인 그리기 요소를 삽입하되, 건네받은
    속성만 쓰고 필수 하위 요소는 만들지 않습니다. 호출자가 채우지 않은 채 저장하면
    한컴이 열지 못하는 문서가 되므로 호출 시 `UserWarning`이 납니다. 이 경고가 유일한
    신호입니다 — 저장은 실패하지 않고 `validate_package`·`validate_editor_open_safety`도
    통과합니다. 표준 도형은 위 전용 헬퍼를 쓰세요.
- `add_control(...) -> HwpxOxmlInlineObject`
  - **저수준 탈출구.** 새 단락에 인라인 컨트롤 객체(예: 양식 컨트롤)를 삽입합니다.
    `add_shape`와 같은 제약과 경고가 적용됩니다.

#### 영속성(Persistence)

- `save(target, *, format=None, mode="auto", fallback="error", quality=None) -> MutationReport`
  - 변경된 XML 파트를 *target*(경로 또는 파일과 유사한 바이너리 스트림)에 저장하고 영수증
    `MutationReport`를 반환합니다(저장한 경로는 `report.path`, 스트림이면 `None`). *format*이
    `None`이면 `.hwp`로 끝나는 경로는 HWP 5.0으로, 그 밖(스트림 포함)은 HWPX로 씁니다.
    `quality=`에 `QualityPolicy`를 주면 쓰기 전에 그 품질 게이트를 돌리고 보고를 `report.quality`에
    담습니다. 게이트가 막으면 쓰지 않고 `SaveError`(`quality-gate-failed`, 보고는 `.report`)가 납니다.
- `to_bytes(*, format="hwpx") -> bytes`
  - 변경된 XML 파트를 직렬화한 HWPX ZIP 바이트를 반환합니다. `format="hwp"`이면 HWP 5.0
    파일 바이트를 반환합니다.
- `conversion_report -> Hwp5ConversionReport | None`
  - `.hwp`를 열 때 문서 모델로 옮기지 못한 내용의 개수(`unconverted`·`dropped`, 읽기 전용).
    `.hwp`로 열지 않은 문서에서는 `None`입니다.
- 6.x의 `save_to_path()`·`save_to_stream()`·`save_report()`는 7.0에서 `save()` 하나로 합쳤습니다. 부르면 새 자리를 알려 주는 `HwpxAttributeError`가 납니다. 바이트에는 `to_bytes()`를 씁니다.

***

## 모듈 `hwpx.tools.package_validator`

- `validate_editor_open_safety(source) -> EditorOpenSafetyReport`
  - `from hwpx import validate_editor_open_safety` 또는 `from hwpx.tools.package_validator import validate_editor_open_safety`로 사용할 수 있습니다. package validation, document validation, 재오픈 검증을 함께 수행해 편집기 handoff 전에 확인할 수 있는 구조화 리포트를 반환합니다.
- `validate_package(source) -> PackageValidationReport`
  - `from hwpx import validate_package` 또는 `from hwpx.tools.package_validator import validate_package`로 사용할 수 있습니다. ZIP/OPC/HWPX 패키지 구조와 editor-open 관련 hard error를 검사합니다.

***

## 모듈 `hwpx.tools.archive_cli`

- `pack_hwpx(input_dir, output_path, *, overwrite=False) -> PackResult`
  - pack-ready 디렉터리를 HWPX로 재패킹하고, 검증된 임시 ZIP만 대상 경로로 교체합니다. `PackResult.open_safety`에는 `validate_editor_open_safety(...).to_dict()` 결과가 들어갑니다.
- `unpack_hwpx(source, output_dir, *, overwrite=False, pretty_xml=False) -> UnpackResult`
  - HWPX를 디렉터리로 풉니다. 이 함수는 HWPX 출력 파일을 만들지 않으며, 재패킹은 `pack_hwpx()`를 사용해야 합니다.

***

## 모듈 `hwpx.tools.repair`

- `repair_repack(source, output_path, *, overwrite=False, ...) -> RepairResult`
  - 기존 ZIP 중앙 디렉터리가 읽히는 HWPX를 재정렬/재패킹하고, CRC, package validation, editor-open safety 검증을 통과한 결과만 대상 경로로 교체합니다. `RepairResult.open_safety`는 handoff evidence입니다.
- `repair_from_recovered(source, output_path, *, overwrite=False, ...) -> RepairResult`
  - Local File Header 스캔으로 복구한 엔트리를 새 HWPX로 재구성하고, 같은 검증을 통과한 경우에만 출력합니다.
- `normalize_package_namespaces(source, *, output_path=None, ...) -> NamespaceNormalizeResult`
  - `repair_repack`의 namespace 부분만 합니다. 모든 `.xml` part를 파싱해 다시 쓰고, 구역·헤더 루트(`hs:sec`·`hh:head`)에는 한/글이 선언하는 namespace 전부(`HWPML_COMPAT_ROOT_NAMESPACES`)와 `standalone="yes"`를 줍니다. 파싱되지 않는 part는 바이트 그대로 두고 `unparsed_parts`에 적습니다. `.hpf`·바이너리 엔트리, 엔트리 순서, 구역 id, 줄 캐시는 바꾸지 않습니다(`repair_repack`은 이것들도 고칩니다). `mimetype`은 압축하지 않고 저장합니다. 결과는 open-safety 게이트를 거치고, `output_path`는 게이트를 통과할 때만 원자적으로 씁니다. 통과하지 못하면 기존 파일을 그대로 둡니다.

***

## 모듈 `hwpx.patch` — 패키지 전체 텍스트 치환

- `replace_package_text(source, replacements, *, output_path=None, part_suffixes=(".xml", ".hpf")) -> PackageTextReplaceResult`
  - 이름이 *part_suffixes*로 끝나는 part(대소문자 무시)의 **문자 데이터(텍스트 노드)만** 바꿉니다. 본문·표 칸·머리말·꼬리말과 `content.hpf` 메타데이터의 자리표시자를 한 번에 채울 때 씁니다. 요소·속성 이름, 속성 값, 주석, CDATA는 찾지 않습니다. 키와 값은 일반 텍스트이고 `&`·`<`는 알아서 이스케이프합니다. 두 런에 걸쳐 나뉜 키는 찾지 못합니다. 치환은 순서대로 앞 치환이 남긴 텍스트에 적용합니다.
  - 글이 바뀐 문단은 자기 `linesegarray` 줄 캐시를 잃습니다(한/글이 새 글을 다시 배치하게). 글은 그것을 둘러싼 가장 안쪽 문단의 것이라, 바깥 문단만 바뀌면 그 안 표 칸 문단의 캐시는 그대로이고 그 반대도 같습니다. 다른 문단·part·ZIP 엔트리는 바이트를 유지합니다(ZIP64 등 엔트리를 다시 압축해야 하는 파일도 엔트리 차례·`mimetype`의 자리와 압축·아카이브 주석은 그대로). 이름이 같은 엔트리가 둘 이상인 파일은 아무것도 쓰기 전에 `save-duplicate-entry-names`로 거부합니다. UTF-8이 아닌 part는 건드리지 않고 `undecodable_parts`에 적습니다. 결과는 open-safety 게이트를 거치고, `output_path`는 게이트를 통과할 때만(`ok`) 원자적으로 씁니다. 두 결과 모두 패키지의 ZIP 엔트리 이름 전체를 순서대로 `entries`에 담습니다.

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
- `DocumentNumbering`: 전체 문서의 기본 번호 매기기 값입니다.
- `RunStyle`: 확인된 런 서식을 캡슐화하며 다음을 제공합니다:
  - `color`: 런의 색상(설정된 경우)인 속성입니다(6.x의 `text_color()`).
  - `underline_type`·`underline_color`·`outline_type`: 밑줄 모양·밑줄 색·외곽선 모양 속성입니다(7.0부터 속성).
  - `superscript`·`subscript`·`emboss`·`engrave`: 위첨자·아래첨자·양각·음각 여부(bool) 속성입니다(6.x의 `is_*()`).
  - `matches(...)`: 색상/밑줄 일치를 위한 편의 술어(predicate)입니다.

### 클래스 `HwpxOxmlSectionHeaderFooter`

- `id`: 머리글/바닥글 식별자를 관리하며 변경 시 섹션을 dirty로 표시하는 getter/setter가 있는 프로퍼티입니다.
- `page_type`: 머리글/바닥글이 적용될 페이지 유형(양쪽/홀수/짝수)을 읽고 쓰는 프로퍼티입니다(6.x `apply_page_type`).
- `text`: 머리글/바닥글의 텍스트 내용을 읽거나 교체하는 프로퍼티입니다.
- `_initial_sublist_attributes()` / `_ensure_text_element()`: 텍스트가 처음 할당될 때 중첩된 단락 구조를 지연 생성하는 내부 헬퍼입니다.

### 클래스 `HwpxOxmlSectionProperties`

- `_page_pr_element(create=False)` / `_margin_element(create=False)`: 페이지 속성 및 여백 노드를 가져오거나 빌드하는 내부 헬퍼입니다.
- `page_size`: 섹션의 페이지 설정을 설명하는 `PageSize`를 반환하는 프로퍼티입니다.
- `set_page_size(...)`: 페이지 설정 값을 업데이트하고 변경 시 섹션을 dirty로 표시합니다.
- `page_margins`: 섹션의 `PageMargins` 객체를 반환하는 프로퍼티입니다.
- `set_page_margins(...)`: 음수가 아닌 값으로 여백 속성을 업데이트합니다.
- `start_numbers`: `<hp:startNum>`의 `hwpx.objects.StartNumbers`(`doc.page.start_numbers()`와 같은 값)를 반환하는 프로퍼티입니다.
- `set_start_numbers(...)`: 번호 매기기 카운터와 페이지 시작 동작을 수정하며, `<hp:startNum>` 엘리먼트가 없으면 생성합니다.
- `headers`, `footers`: 기존 머리글/바닥글 정의에 대한 래퍼를 tuple로 반환하는 프로퍼티입니다.
- `header(page_type="BOTH")` / `footer(...)`: 지정된 페이지 유형의 기존 머리글/바닥글 래퍼를 가져옵니다.
- `set_header_text(text, ...)` / `set_footer_text(...)`: 요청된 페이지 유형에 대한 머리글/바닥글이 있는지 확인하고 텍스트 내용을 교체합니다. 한/글처럼 첫 문단의 `<hp:ctrl>` 안에 한 번만 쓰고 `<hp:headerApply>`/`<hp:footerApply>`는 쓰지 않습니다(6.x가 `<hp:secPr>` 안에 따로 쓴 사본은 그 머리글을 다시 설정할 때 걷어 냅니다).
- `remove_header(page_type="BOTH")` / `remove_footer(...)`: 지정된 페이지 유형의 머리글/바닥글 노드가 있으면 제거하고, 연결된 apply 노드와 마스터 페이지 링크를 정리합니다.

### 클래스 `HwpxOxmlRun`

- `char_pr_id_ref`: 런의 글자 스타일 참조를 노출하며, XML과 섹션의 dirty 플래그를 업데이트하는 setter가 있는 프로퍼티입니다.
- `text`: 런 내의 연결된 텍스트 노드를 읽거나 교체하는 프로퍼티입니다.
- `style`: 문서를 참조하여 확인된 `RunStyle`을 반환하는 프로퍼티입니다.
- `replace_text(search, replacement, count=None)`: 일반 텍스트 노드에서 문자열을 교체하고 교체 횟수를 반환합니다.
- `remove()`: 부모 단락에서 런 엘리먼트를 삭제합니다.
- `bold`, `italic`, `underline`: 일치하는 런 스타일을 보장하여 서식 플래그를 토글하는 프로퍼티입니다.
- `content -> tuple[InlineItem, ...]`: 런이 담은 것을 파일에 적힌 차례대로 하나씩 돌려줍니다(아래 「적힌 차례대로 읽기」). `run.to_model()`과 달리 고정폭 빈칸·묶음 빈칸·하이픈 같은 글자 원자를 버리지 않고, 요소를 직렬화해 다시 파싱하지 않습니다.
- `_current_format_flags()`, `_apply_format_change(...)`, `_plain_text_nodes()`, `_ensure_plain_text_node()`: 서식 로직을 관리하는 내부 헬퍼입니다.

### 클래스 `HwpxOxmlMemoGroup`

- `memos`: 각 메모 자식에 대한 `HwpxOxmlMemo` 래퍼를 반환하는 프로퍼티입니다.
- `add_memo(...)`: 메모 노드를 추가하고, 텍스트를 초기화한 후, 래퍼를 반환합니다.
- `_cleanup()`: 메모 그룹 엘리먼트가 비어 있을 때 이를 제거하는 내부 헬퍼입니다.

### 클래스 `HwpxOxmlMemo`

- `id`: XML 속성을 업데이트하는 setter가 있는 메모 id 프로퍼티입니다. (6.x의 `memo_shape_id_ref`는 7.0에서 없어졌습니다. 6.x 문서에 적힌 값은 `attributes`로 읽습니다.)
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
- `attributes.get(name)` / `set_attribute(name, value)`: 속성 하나를 읽고, 바꾸면 단락을 dirty로 표시합니다(6.x의 `get_attribute(name)`은 7.0에서 `attributes.get(name)`).
- `width`·`height`: 개체 자신의, 돌리기 전 그려진 크기(HWPUNIT)입니다. `resize(width, height)`가 받는 크기와 같은 뜻이라 `obj.resize(obj.width, obj.height)`는 아무것도 바꾸지 않습니다. 돈 개체는 한/글이 적은 `curSz`(0인 축은 `orgSz`)를 읽고, 돌지 않은 개체는 `hp:sz`입니다. 그림·도형·묶음(`HwpxOxmlShape`)도 같습니다.
- `box_width`·`box_height`(읽기 전용): 개체가 문단에서 차지하는 상자(`hp:sz`, HWPUNIT)입니다. 돈 개체는 돈 모양을 감싸는 상자이고, 돌지 않은 개체는 `width`·`height`와 같습니다.
- `flip_horizontal`·`flip_vertical`·`rotation`: 높이나 너비가 0인 선(수평선·수직선)은 한/글처럼 뒤집어도 그림이 바뀌지 않게 저장합니다. 한/글은 뒤집기 표시와 반 바퀴 회전을 함께 적고(좌우 뒤집기면 각도 180, 행렬은 그대로) 화살표 끝도 그대로입니다(한/글 2024 저장본과 그 쪽 그림). 그래서 뒤집은 수평선은 `flip_horizontal == True`, `rotation == 180`으로 읽습니다. 다시 뒤집으면 표시 0, 각도 0입니다.
- `rotation`(떠 있는 개체의 자리): 떠 있는 개체를 돌리면 돌리는 가운데가 제자리에 있도록 `hp:pos` 오프셋을 옮깁니다(음수가 될 수 있고, `rotation = 0`이면 언제나 처음 오프셋). 개체가 걸린 문단은 바꾸지 않습니다. 한/글에서 직접 돌리면 한/글은 위로 올라간 개체를 그 높이의 문단에 다시 걸지만(한/글의 쪽 배치), 엔진은 그렇게 하지 않습니다. 쪽 영역 안으로 제한된 개체(`flowWithText`)의 위 끝이 걸린 줄보다 위로 가야 하면 한/글은 그 줄 위 끝에 맞춰 그립니다(근거: 한/글 2024가 30° 돌린 12000 수평선을 1400 아래에 그림, rotate12 check15 4번).

### 클래스 `HwpxOxmlTableCell`

- `address`: `<hp:cellAddr>`에서 파생된 `(행, 열)` 튜플을 반환하는 프로퍼티입니다.
- `span`: `<hp:cellSpan>`의 `(행 병합, 열 병합)` 값을 반환하는 프로퍼티입니다.
- `set_span(row_span, col_span)`: 병합 속성을 업데이트하고 표를 dirty로 표시합니다.
- `width`, `height`: `<hp:cellSz>`에서 캐시된 셀 크기를 노출하는 프로퍼티입니다.
- `set_size(width=None, height=None)`: 크기 속성을 0 또는 그 이상으로 업데이트합니다.
- `margins`: 한/글이 셀을 배치하는 안쪽 여백을 `CellMargins(left, right, top, bottom)`(HWPUNIT)로 반환하는 프로퍼티입니다. 셀의 `hasMargin`이 꺼져 있으면 표의 `<hp:inMargin>`, 켜져 있으면 셀의 `<hp:cellMargin>`을 읽습니다.
- `set_margins(*, left=None, right=None, top=None, bottom=None)`: 주지 않은 면은 지금 여백을 유지한 채 네 면을 `<hp:cellMargin>`에 쓰고 `hasMargin="1"`로 켠 뒤 새 `CellMargins`를 반환합니다. 잘못된 값은 `HwpxValueError`(`cell-margin-value`)로 거부합니다.
- `border_fill_id_ref`: 셀이 가리키는 `hh:borderFill` id(`hp:tc/@borderFillIDRef`). 쓰면 이 셀의 참조만 바뀝니다. 문서에 정의된 id(`doc.styles.ensure_border_fill(...)`이 돌려준 것, `str`·`int`)만 받고 없는 id는 아무것도 바꾸기 전에 `table-border-fill-not-found`로 거절합니다. 크기·여백이 그대로라 줄 배치 캐시를 지우지 않습니다. 이웃 칸과 공유하는 변까지 바꾸려면 `table.set_cell_borders`.
- `text`: 셀 내부의 첫 번째 텍스트 노드를 반환하는 프로퍼티입니다. setter는 텍스트를 할당하기 전에 중첩된 단락 구조를 보장하고, `<hp:lineSegArray>`와 같은 줄 배치 캐시를 제거하여 한/글이 줄바꿈을 다시 계산하도록 합니다.
- `remove()`: 행에서 셀 엘리먼트를 제거합니다.
- `_addr_element()`, `_span_element()`, `_size_element()`, `_ensure_text_element()`: 중첩된 XML 구조를 관리하는 내부 헬퍼입니다.

### 클래스 `HwpxOxmlTableRow`

- `cells`: 행에 대한 `HwpxOxmlTableCell` 래퍼 목록을 반환하는 프로퍼티입니다.

### 데이터 클래스 `HwpxTableGridPosition`

- `row`, `column`: 논리적 격자 좌표를 나타내는 정수입니다.
- `cell`: 해당 위치를 커버하는 실제 `HwpxOxmlTableCell` 래퍼입니다.
- `anchor`: 병합 셀의 대표 좌표 `(row, column)`을 담은 튜플입니다.
- `span`: `row_span`, `col_span`을 포함한 튜플로 병합 크기를 제공합니다.
- `is_anchor`: 현재 좌표가 대표 좌표인지 여부를 반환하는 편의 프로퍼티입니다.
- `row_span`, `col_span`: 병합된 크기를 개별 프로퍼티로 노출합니다.

### 클래스 `HwpxOxmlTable`

- `create(rows, cols, ...)`: 분배된 셀 크기, 여백, 초기 텍스트 노드를 포함하는 완전한 표 엘리먼트를 생성하는 클래스 메서드입니다.
- `mark_dirty()`: 표가 변경되었음을 소유한 섹션에 알립니다.
- `row_count`, `column_count`: 저장된 행/열 수를 확인하거나 XML 구조에서 파생하는 프로퍼티입니다.
- `rows`: `HwpxOxmlTableRow` 래퍼의 tuple을 반환하는 프로퍼티입니다.
- `cell(row, col)`: 병합 정보를 고려하여 요청된 그리드 좌표를 포함하는 셀을 찾습니다.
- `iter_grid()`: 각 논리 좌표에 대한 `HwpxTableGridPosition`을 순회하여 병합 상태와 실제 셀을 동시에 확인할 수 있게 합니다.
- `cell_map`: `row_count x column_count` 크기의 tuple의 tuple로 격자 맵을 반환합니다. 각 항목은 `HwpxTableGridPosition`입니다.
- `set_cell_text(row, col, text, logical=False, split_merged=False)`: 셀의 텍스트 내용을 업데이트하는 단축 메서드입니다. `logical=True`를 지정하면 논리적 격자 좌표로 셀을 찾고, `split_merged=True`일 때는 병합을 자동으로 해제한 뒤 값을 씁니다. 내부적으로 줄 배치 캐시를 비워 한/글에서 셀 텍스트 변경 후 줄바꿈이 재계산되도록 합니다.
- `split_merged_cell(row, col)`: 지정한 논리 좌표를 포함하는 병합 셀을 해제하고, 해당 위치에 독립적인 셀을 생성한 뒤 래퍼를 반환합니다.
- `merge_cells(start_row, ...)`: 직사각형 영역의 유효성을 검사하고, 종속 셀을 제거하며, 병합 및 크기 값을 업데이트한 후, 살아남은 대상 셀을 반환합니다. 종속 셀 중 글이나 개체가 있는 셀의 문단은 읽기 순서로 대상 셀에 옮기고, 빈 셀은 아무것도 보태지 않습니다.
- `repeat_header`: 제목 줄이 쪽마다 반복되는지(`hp:tbl/@repeatHeader`, 한/글 표 속성 → 제목 줄 자동 반복). 쓰면 이 값만 바뀌고 제목 칸(`cell.is_header`)은 그대로입니다(한/글이 만든 표도 제목 칸 없이 `repeatHeader="1"`을 적습니다). `True`/`False`만 받고(`table-header-rows-value`), 바뀌면 표를 담은 문단의 줄 배치 캐시를 지웁니다. 제목 행과 함께 정하려면 `set_header_rows(count, repeat=)`.
- `insert_rows(ref_row, count=1, side="below", copy_content=False)`: 물리 행 `ref_row` 아래(`side="above"`면 위)에 한/글처럼 빈 행을 넣습니다. 새 칸은 같은 열 기준 칸의 서식(칸 속성·테두리/배경·여백·크기·문단 모양·글자 모양)만 받고 빈 문단 하나를 둡니다. `copy_content=True`면 기준 칸의 글·개체까지 복사합니다. 새 행을 가로지르는 합친 칸은 늘어납니다.
- `insert_columns(ref_col, count=1, side="right", copy_content=False)`: 격자 열 `ref_col` 오른쪽(`side="left"`면 왼쪽)에 빈 열을 넣고, 표는 새 열만큼 넓어집니다. `copy_content=True`면 기준 칸의 글·개체까지 복사합니다.
- `delete_rows(rows)`, `delete_columns(cols)`: 행·열(번호 하나나 여럿)을 지웁니다. 열을 지우면 그 폭을 남은 열에 나눠 표 폭을 지킵니다. 모든 행·열은 지울 수 없습니다.
- `split_cell(row, col, rows=1, cols=1)`: 칸을 줄·칸(각 2~63)으로 나눕니다(한/글의 셀 나누기). 글은 첫 칸에 남습니다.
- 위 다섯 메서드는 `hwpx.table_patch.apply_table_ops`의 같은 편집과 같은 규칙을 따르고, 칸 영역(`hp:cellzone`)도 함께 옮깁니다. 편집 전에 얻은 셀·행 객체는 더 이상 표에 속하지 않으니 다시 얻습니다. `doc.tables`에도 같은 이름의 메서드가 있습니다(첫 인자로 표).

### 클래스 `HwpxOxmlParagraph`

- `runs`: 각 런에 대한 `HwpxOxmlRun` 래퍼를 반환하는 프로퍼티입니다.
- `text`: 런들의 텍스트를 연결하는 프로퍼티입니다. setter는 다른 자식 노드를 보존하면서 텍스트 내용을 교체합니다.
- `add_run(text="", ...)`: 새 런을 추가하고, 선택적으로 소유 문서를 통해 일치하는 글자 스타일을 생성한 후, 래퍼를 반환합니다. `tab_widths=[...]`(HWPUNIT, 글의 탭마다 하나, 차례대로)를 주면 탭을 한/글 저장 꼴 `<hp:tab width="N" leader="0" type="1"/>`로 씁니다 — 줄을 직접 배치해 탭 폭을 잰 쪽이 넘기는 값입니다. 없으면 전처럼 `<hp:tab/>`이고 폭은 한/글이 정합니다. 개수가 탭 수와 다르거나 0~2**31-1 정수가 아니면 `paragraph-tab-widths`.
- `remove()`: 단락을 소유 섹션에서 삭제합니다. 섹션의 마지막 단락이면 `ValueError`가 발생합니다.
- `tables`: 단락 내에 포함된 `HwpxOxmlTable` 래퍼를 반환하는 프로퍼티입니다.
- `add_table(...)`, `add_line(...)`, `add_rectangle(...)`, `add_ellipse(...)`, `add_arc(...)`, `add_polygon(...)`, `add_curve(...)`, `add_connector(...)`, `add_container(...)`: 적절한 런을 생성하여 인라인 객체(표, 도형, 묶음)를 삽입하고 래퍼 객체를 반환합니다. 도형 헬퍼는 한컴이 요구하는 하위 요소까지 생성합니다.
- `add_shape(...)`, `add_control(...)`: 같은 자리에 임의의 요소를 넣는 저수준 탈출구입니다. 필수 하위 요소를 만들지 않아 호출 시 `UserWarning`이 나므로, 표준 도형은 위 전용 헬퍼를 쓰세요.
- `para_pr_id_ref`, `style_id_ref`, `char_pr_id_ref`: 단락 수준의 서식 재정의를 허용하는 setter가 있는 프로퍼티입니다.
- `id`: 파일에 적힌 문단 id(`hp:p/@id`, 읽기 전용). 한/글도 `"0"`이나 같은 id를 적을 수 있어 고유 키가 아닙니다. 문단을 다시 찾을 때는 객체끼리 견줍니다(아래 「같은 요소의 객체」).
- `replace_range(start, end, text)`: `paragraph.text`로 센 글자 `[start, end)`를 *text*로 바꿉니다. 런은 그대로이고, 새 글자는 같은 자리의 옛 글자의 런(글자 모양)에 들어갑니다(`doc.text.replace`·한/글 찾아 바꾸기와 같은 규칙). 남는 새 글자는 범위 끝 글자를 따르고, `start == end`면 앞 글자의 런에 끼웁니다. 범위가 탭·줄 바꿈·컨트롤·개체를 건너면 `paragraph-range-crosses-element`로 거절합니다. 줄 배치 캐시를 지웁니다.
- `copy_to(paragraph, *, before=False) -> Paragraph`: 이 문단의 사본을 *paragraph* 뒤(`before=True`면 앞)에 넣고 돌려줍니다. *paragraph*는 다른 문서의 문단(본문·칸·글상자·각주·머리말)이어도 됩니다. 이때 글자·문단 모양, 스타일, 테두리, 탭, 번호·글머리표, 글꼴 정의를 받는 문서에 새로 만들고, 그림·차트의 파트를 함께 옮기며, 누름틀·책갈피·개체·문단 id를 새로 매깁니다(`insert_document`와 같은 규칙, 같은 거부). 구역 설정은 따라가지 않고, 구역 첫 문단 앞에 넣으면 그 구역의 설정을 넘겨받습니다. 같은 문서 안에서는 `insert_after()` 사본과 같습니다.
- `nested_text(*, where=None) -> str`: 이 문단의 글에 문단 안 표 칸(칸 안 표까지)·글상자·캡션·묶음·각주·메모 문단의 글을 문서 차례로 더해 읽습니다. 문단의 글은 안쪽 문단을 품은 개체가 있는 자리에서 끊기고, 그 자리에 안쪽 문단의 글(같은 방식으로 읽음)이 들어가며, 글이 있는 토막을 `"\n"`으로 잇습니다. 토막마다 `text`처럼 읽고(탭 `"\t"`, 줄 바꿈 `"\n"`, 특수 빈칸은 그 글자), 공백을 접지 않습니다. *where*(`doc.text.iter_paragraphs()`의 자리 값)로 글을 읽을 안쪽 문단을 고르고, 문단 자신의 글은 늘 읽습니다. 안에 문단이 없으면 `text`와 같습니다. `text`의 뜻은 바뀌지 않습니다.
- `iter_paragraphs(*, where=None) -> Iterator[ParagraphPlace]`: 이 문단 안의 모든 문단(표 칸·칸 안 표·캡션·글상자·묶음·각주·메모)을 깊이와 상관없이 문서 차례로 내놓습니다. `doc.text.iter_paragraphs()`를 이 문단으로 좁힌 것과 같고(값과 `where`도 같습니다), 문단 자신은 들지 않습니다. 안에 문단이 없으면 아무것도 내놓지 않습니다. 문단 자신의 XML과 조상만 읽습니다.
- `iter_objects(*, kinds=None, where=None) -> Iterator[ObjectPlace]`: 이 문단 안의 모든 개체를 깊이와 상관없이 문서 차례로 내놓습니다. 문단 자신의 개체와 그 표 칸·글상자·캡션·묶음·각주·메모 안의 개체까지입니다. `doc.text.iter_objects()`를 이 문단으로 좁힌 것과 같고(값과 `kinds`·`where`도 같습니다), `paragraph.objects`·`paragraph.pictures`는 바로 아래 것만입니다. `place.object`는 `paragraph.objects`가 주는 모델과 같은 종류입니다: 그림은 `item_id`가 있는 `Picture`, 수식은 `script`가 있는 `Equation`(둘 다 `InlineObject`이기도 합니다). 문단 자신의 XML과 조상만 읽습니다.
- `_run_elements()`, `_ensure_run()`, `_create_run_for_object()`: 위 작업들을 위해 런 생성 및 접근을 관리하는 내부 헬퍼입니다.

### 같은 요소의 객체

문단·런·표·행·칸·각주/미주·메모·개체(그림·수식·도형 등)·머리말/꼬리말 객체는 같은 XML 요소를 감싸면 같습니다(`==`). 해시도 같아 dict 키나 set 원소로 쓸 수 있고, `doc.paragraphs.index(paragraph)`가 그 문단을 찾습니다. 부를 때마다 새 객체가 만들어지므로 `is`는 쓰지 않습니다. 다른 종류의 값(요소 자체, 글자열)과는 같지 않습니다. 6.x 메모를 누름틀로 옮기는 것처럼 요소가 바뀐 객체는 그 뒤로 다른 키입니다.

### 값 형식 `FormField` (`doc.fields.all`)

- `filled`: 한/글이 누름틀에 남기는 "내용을 넣었음" 표시(`hp:fieldBegin/@dirty`, 읽기 전용). 안내문 대신 넣은 내용을 보이는 누름틀이면 `True`입니다. 파일에 적힌 지금 값을 읽고, 채우기(`field.value = ...`, `doc.fields.fill`)가 켭니다. 적히지 않았으면 스키마 기본값 `False`.

### 명령 단추 `Button` (`doc.fields.buttons`)

- `caption`: 단추에 적힌 글(`hp:btn/@caption`, 읽기 전용). `name`·`paragraph`·`section`·`index`는 다른 양식 개체와 같습니다. 엔진은 명령 단추를 만들지 않습니다.

### 글맵시·숨은 설명

- 글맵시의 글: `doc.text.iter_objects(kinds="textart")`의 `place.object.attributes["text"]`(한/글이 `hp:textart/@text`에 적은 그대로).
- 숨은 설명(`hp:hiddenComment`)의 문단은 `doc.text.iter_paragraphs()`에서 자리 `where="hidden_comment"`로 나옵니다.

### 적힌 차례대로 읽기 — `run.content`, `InlineItem`

`run.content`의 값 `InlineItem`(`hwpx.objects`, 고정된 값)은 `kind`·`name`(XML 요소의 지역 이름, 글자는 `""`)·`container`(`"t"`·`"ctrl"`·`"run"`: 파일에서 적힌 곳)·`text`·`attributes`(요소의 속성을 적힌 차례대로 `(이름, 값)`의 tuple, `item.attribute("type")`)·`object`·`element`·`child_index`를 가집니다. `child_index`는 조각이 적힌 런 자식 요소의 차례(0부터, 주석은 세지 않음)입니다: 그 조각의 `hp:t`·`hp:ctrl`, 런의 자식이면 그 조각 자신. 한 `hp:t`(한 `hp:ctrl`)의 조각은 같은 값이라, 한 `hp:ctrl`에 적힌 컨트롤 둘과 `hp:ctrl` 둘에 적힌 컨트롤을 가를 수 있습니다.

- `hp:t` 안: `"text"`(글자), `"tab"`, `"line_break"`, `"nb_space"`(묶음 빈칸), `"fw_space"`(고정폭 빈칸), `"hyphen"`, `"markpen_begin"`·`"markpen_end"`, `"title_mark"`, `"insert_begin"`·`"insert_end"`·`"delete_begin"`·`"delete_end"`. 글자 원자의 `text`는 그 글자(`"	"`, `"
"`, `" "`, `"　"`, `"­"`)이고 표시는 `""`라서, `container == "t"`인 조각의 `text`를 이으면 `run.text`입니다.
- `hp:ctrl` 안: `"field_begin"`, `"field_end"`, `"footnote"`, `"endnote"`, `"bookmark"`, `"auto_number"`, `"page_number"`, `"page_number_ctrl"`, `"number_restart"`, `"page_hiding"`, `"column_definition"`, `"header"`, `"footer"`, `"index_mark"`, `"hidden_comment"`.
- 런의 자식: 개체는 `doc.text.iter_objects()`의 종류 이름(`"table"`·`"picture"`·`"equation"`·`"shape"`·`"textart"`·`"ole"`·`"chart"`·`"video"`)과 `"form"`, 그리고 `"ruby"`(덧말), `"composed_character"`(글자 겹치기), `"section_properties"`(`hp:secPr`), `"switch"`.
- 모르는 요소는 버리지 않고 `"unknown"`과 그 `name`으로 내놓습니다. 빈 `hp:t`·`hp:ctrl`은 담은 것이 없어 조각이 없습니다.
- `object`는 조각에 맞는 모델 객체입니다: 개체(`paragraph.objects`와 같은 객체), 각주·미주(`paragraph.footnotes`와 같은 객체), `HYPERLINK` 누름틀의 `Hyperlink`, 글을 품은 `MEMO` 누름틀의 메모, `Ruby`·`ComposedCharacter`, 그리고 `AutoNumber`·`PageNumberControl`·`NumberRestart`·`PageHiding`·`ColumnDefinition`, 머리말·꼬리말 컨트롤의 머리말·꼬리말(`doc.page.headers()`가 주는 것과 같은 모델, `paragraphs`로 읽고 고친다), 그 밖의 누름틀 시작의 `FieldControl`(`field_type`·`field_id`·`name`·`parameters`). `Hyperlink`와 메모도 `parameters`를 읽습니다. 없으면 `None`입니다. `element`는 탈출구입니다. `object`·`element`·`child_index`는 `==`와 `to_dict()`에 들지 않습니다.

```python
for paragraph in doc.paragraphs:
    for run in paragraph.runs:
        for item in run.content:
            if item.kind == "field_begin" and item.attribute("type") == "HYPERLINK":
                print("link", item.object.url)
            elif item.container == "t":
                print(repr(item.text))
```

도형 안의 문단은 `shape.iter_paragraphs(*, where=None) -> Iterator[ParagraphPlace]`로 읽습니다: 글상자(`"text_box"`)·캡션(`"caption"`)·묶음 구성원·안쪽 표 칸(`"cell"`)의 문단을 깊이와 상관없이 문서 차례로, `doc.text.iter_paragraphs()`와 같은 값으로 내놓습니다.

### 클래스 `HwpxOxmlSection`

- `properties`: `<hp:secPr>` 계층이 필요할 때 이를 생성하며 `HwpxOxmlSectionProperties` 래퍼를 반환하는 프로퍼티입니다.
- `element`: 원시 섹션 `Element`를 반환하는 프로퍼티입니다.
- `document`: 소유 `HwpxOxmlDocument`를 참조하는 프로퍼티입니다. `attach_document()`는 섹션을 문서 인스턴스와 연결합니다.
- `paragraphs`: 문서 순서대로 단락 래퍼의 tuple을 반환하는 프로퍼티입니다.
- `blocks -> tuple[Paragraph | Table, ...]`: 구역의 문단과 구역 바로 아래 놓인 표를 파일에 적힌 차례로 돌려줍니다. 한/글은 표를 늘 문단 안에 두므로 한/글 파일에서는 `paragraphs`와 같습니다. 다른 프로그램이 구역 바로 아래 쓴 표(`hp:tbl`)는 그 자리에 `paragraph`가 `None`인 표 객체로 나옵니다. 글은 `hwpx.tools.exporter.table_grid_text(table)`, 캡션은 `table.caption`으로 읽습니다. `hp:memogroup`(→ `memo_group`) 같은 다른 자식은 들어가지 않습니다.
- `memo_group`: 메모 그룹이 존재할 때 `HwpxOxmlMemoGroup` 래퍼를 반환하는 프로퍼티입니다.
- `memos`: 섹션의 메모 래퍼의 tuple을 반환하는 프로퍼티입니다.
- `add_memo(...)`: 메모 그룹이 있는지 확인한 후 `HwpxOxmlMemoGroup.add_memo()`에 위임하는 편의 메서드입니다.
- `add_paragraph(text="", *, style=, para_pr_id_ref=, char_pr_id_ref=, include_run=, inherit_style=)`: 단락을 추가하고 그 래퍼를 반환합니다. 그 밖의 값(쪽 나눔 등)은 돌려받은 단락의 속성으로 씁니다(7.0에서 `run_attributes=`·`inherit_outline=`·XML 속성 인자는 없어졌습니다).
- `remove_paragraph(paragraph_or_index)`: 단락 인스턴스 또는 인덱스로 단락을 삭제합니다. 마지막 단락 삭제 시 `ValueError`가 발생합니다.
- `clear_body(*, on_control_content="raise", keep_headers=True) -> ClearBodyReport`: 본문을 비우고 첫 문단의 구역 설정(`hp:secPr`)과 단·머리말·꼬리말·쪽 번호 컨트롤을 남깁니다. `keep_headers=False`면 머리말·꼬리말을 글이 있든 없든 지우고(`hp:secPr`에 쓴 사본과 그 apply도), 구역 설정·단·쪽 번호와 빈 줄 하나만 남깁니다(한/글 새 문서처럼 머리말 컨트롤이 없는 꼴). `on_control_content`는 남는 컨트롤만 봅니다.
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
- `sections`, `headers`: 섹션 및 헤더 래퍼의 tuple을 반환하는 프로퍼티입니다.
- `char_properties`: 글자 스타일 ID를 `RunStyle` 객체에 매핑한 읽기 전용 `Mapping`(`CharPropertyView`)을 반환합니다. 사본이 아니라 읽을 때마다 머리를 그때 모습으로 읽는 보기이며, ID 하나 찾기는 글자 모양 수와 상관없이 그 하나만 견줍니다. 그대로 남는 사본은 `dict(...)`로 뜹니다.
- `char_property(char_pr_id_ref)`: 문자열 또는 숫자 값을 받아 ID로 `RunStyle`을 조회합니다.
- `ensure_run_style(...)`: 기준 글자 모양(`base_char_pr_id`, 없으면 첫 글자 모양)에서 요청한 값만 바꾼 런 스타일을 첫 번째 헤더에서 찾고, 없으면 기준을 복제해 만듭니다.
- `memo_shapes`: 모든 헤더의 메모 모양을 하나의 딕셔너리로 병합하는 프로퍼티입니다.
- `memo_shape(memo_shape_id_ref)`: ID로 메모 모양을 가져옵니다.
- `paragraphs`: 모든 섹션의 단락 래퍼를 연결한 tuple을 반환하는 프로퍼티입니다.
- `add_paragraph(...)`: `section`(번호나 섹션)으로 대상 섹션을 골라 단락을 추가하도록 섹션에 위임합니다. 기본값은 마지막 섹션입니다.
- `remove_paragraph(paragraph_or_index, *, section=None)`: 단락을 삭제합니다. 인스턴스 또는 인덱스를 받습니다.
- `add_section(after=None) -> HwpxOxmlSection`: 새 섹션을 추가합니다. manifest에 `<opf:item>`과 `<opf:itemref>`를 자동 등록합니다.
- `remove_section(section_or_index)`: 섹션을 삭제합니다. 인스턴스 또는 인덱스를 받으며, 마지막 섹션 삭제 시 `ValueError`가 발생합니다.
- `serialize() -> dict[str, bytes]`: 변경된(dirty) 섹션/헤더에 대한 업데이트된 파트 페이로드 딕셔너리를 반환합니다. manifest가 변경된 경우 함께 포함됩니다.
- `reset_dirty()`: 저장 후 모든 섹션과 헤더를 깨끗한(clean) 상태로 표시합니다.
- 내부 헬퍼는 캐시된 런 스타일을 유지 관리합니다.

***

## 모듈 `hwpx.opc.package`

### 예외

- `HwpxPackageError`: 패키지 조작 오류에 대한 기본 예외입니다.
- `HwpxStructureError`: HWPX 패키지의 필수 구조 구성 요소가 없거나 일치하지 않을 때 발생합니다. 아래 셋의 부모입니다.
- `HwpxArchiveError`: ZIP이 아니거나 잘린 입력. `zipfile.BadZipFile`도 상속합니다.
- `HwpxCompressedDataError`: 압축 데이터가 손상된 입력. `zlib.error`도 상속합니다.
- `HwpxXmlSyntaxError`: XML 파트가 깨진 입력. `lxml.etree.XMLSyntaxError`도 상속하고 `part_name`에 파트 이름을 담습니다.

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
- `save(pkg_file)`: 패키지를 디스크나 파일과 유사한 객체에 씁니다. `mimetype`이 압축되지 않은 상태로 저장되도록 하고, 변경된 `version.xml`을 직렬화하며, 구조 검증과 editor-open safety 검증을 통과한 결과만 대상에 반영합니다.
- raw ZIP writer 메서드는 내부 구현 세부사항입니다. 직접 호출하면 safety 검증을 건너뛸 수 있으므로 public 사용 경로가 아니며, 현재 구현은 save 내부 컨텍스트 밖의 직접 호출을 거부합니다.

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

- `load_default_schemas(schema_dir=None)`: 번들로 제공되는 헤더 및 섹션 XSD 파일을 로드하며, 스키마 디렉토리가 없을 때 예외를 발생시킵니다. 두 스키마는 루트 요소만 선언하고 나머지를 `<xs:any processContents="lax"/>`로 받는 느슨한 구조 스키마이므로, 통과했다고 해서 OWPML 전체가 검증된 것도 한컴이 문서를 연다는 뜻도 아닙니다.
- `_iter_parts(document)`: `HwpxDocument`의 모든 헤더와 섹션에 대해 `(파트 이름, XML 바이트, 헤더 여부)`를 순회하는 내부 헬퍼입니다.
- `_issues_from_error(part_name, exc)`: `lxml` 유효성 검사 오류를 `ValidationIssue` 인스턴스로 정규화합니다.
- `validate_document(source, ..., full_schema=True)`: 문서를 열고, 제공되지 않은 경우 기본 스키마를 로드하며, 각 헤더 및 섹션 파트를 적절한 파서로 검증하고 이슈를 집계합니다. `full_schema`(기본 `True`)면 번들된 전체 OWPML 스키마(`owpml-*.xsd`)로도 검사해, 한/글이 여는 문서에도 있는 편차를 뺀 위반을 경고(`OWPML schema: …`)로 더합니다. `ok`는 하드 오류만 봅니다(`docs/owpml-deviations.md`). 파트가 없는 매니페스트 항목(패키지 밖 파일을 잇는 항목은 빼고)과 매니페스트 항목이 없는 `BinData/` 파트도 경고로 알립니다. `HwpxDocument.validate()`는 이 함수와 같은 검사를 합니다. 파트가 없는 매니페스트 항목을 오류로 보는 것은 패키지 검사(`validate_package`)입니다.

***

## 모듈 `hwpx.oxml.namespaces`

OWPML 스키마에서 반복적으로 사용되는 네임스페이스 URI와 Clark 표기 접두사를 공유 상수로 제공합니다.

### 상수

| 상수 | 값 | 용도 |
|------|-----|------|
| `HP_NS` | `http://www.hancom.co.kr/hwpml/2011/paragraph` | 단락 네임스페이스 URI |
| `HP` | `{http://www.hancom.co.kr/hwpml/2011/paragraph}` | Clark 표기 접두사 |
| `HH_NS` | `http://www.hancom.co.kr/hwpml/2011/head` | 헤더 네임스페이스 URI |
| `HH` | `{http://www.hancom.co.kr/hwpml/2011/head}` | Clark 표기 접두사 |
| `HC_NS` | `http://www.hancom.co.kr/hwpml/2011/core` | 코어 네임스페이스 URI |
| `HC` | `{http://www.hancom.co.kr/hwpml/2011/core}` | Clark 표기 접두사 |
| `HS_NS` | `http://www.hancom.co.kr/hwpml/2011/section` | 섹션 네임스페이스 URI |
| `HS` | `{http://www.hancom.co.kr/hwpml/2011/section}` | Clark 표기 접두사 |
| `HP_2016_NS` | `http://www.hancom.co.kr/hwpml/2016/paragraph` | 2016 단락 네임스페이스 |
| `HH_2016_NS` | `http://www.hancom.co.kr/hwpml/2016/head` | 2016 헤더 네임스페이스 |
| `HC_2016_NS` | `http://www.hancom.co.kr/hwpml/2016/core` | 2016 코어 네임스페이스 |

***

## 공개 심볼 (`hwpx.__init__`)
- `main(argv=None)`: 인자를 파싱하고, 문서를 검증하며, 결과를 출력하는 명령줄 진입점입니다. 성공 시 0을, 이슈 발생 시 0이 아닌 값을 반환합니다.

***

## 모듈 `hwpx.__init__`

이 패키지는 편의를 위해 다음과 같은 재내보내기(re-exports)를 노출합니다:

- `hwpx.tools.text_extractor` 모듈의 `DEFAULT_NAMESPACES`, `ParagraphInfo`, `SectionInfo`, `TextExtractor`
- `hwpx.tools.object_finder` 모듈의 `FoundElement`, `ObjectFinder`

## Proposal presets — 5.0에서 이동

`hwpx.presets`는 5.0에서 제거됐고 `hwpx_automation.office.authoring.presets`가
소유합니다. 대체표는 [5.0 마이그레이션 가이드](migration-5.0.md)에 있습니다.
