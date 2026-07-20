# OPC/ZIP 컨테이너 재패킹

HWPX는 OPC(Open Packaging Conventions) 규약을 따르는 ZIP 컨테이너입니다 — 안에 여러 XML 파트(본문 섹션, 헤더, 매니페스트, 버전 정보)와 바이너리(이미지 등)가 들어갑니다. 겉보기엔 평범한 ZIP이지만, **한/글이 파일을 인식하려면 지켜야 하는 재패킹 규칙**이 몇 가지 있습니다. 이 규칙을 어기면 한/글이 파일을 열지 못하거나 손상으로 판단합니다.

## mimetype는 첫 엔트리, 그리고 STORED

가장 중요한 규칙입니다. **`mimetype` 파트는 ZIP의 첫 번째 엔트리여야 하고, 압축하지 않고(STORED) 저장해야 합니다.** OPC 계열 포맷(ODF, EPUB 등)이 공유하는 관례로, ZIP 헤더만 읽어도 파일 종류를 판별할 수 있게 하기 위함입니다.

라이브러리의 상수와 쓰기 경로가 이를 강제합니다 — `src/hwpx/opc/package.py`:

```python
MIMETYPE_PATH = "mimetype"
DEFAULT_MIMETYPE = "application/hwp+zip"
```

`_write_archive`가 mimetype을 항상 먼저 쓰고, 나머지는 원래 순서를 보존한 뒤 새 파트를 뒤에 붙입니다. mimetype만 `ZIP_STORED`, 나머지는 `ZIP_DEFLATED`로 씁니다:

```python
def _write_archive(self, zf: ZipFile) -> None:
    self._write_mimetype(zf)          # 항상 첫 엔트리
    ...
    for name in [*ordered_names, *new_names]:
        self._write_zip_entry(zf, name, self._files[name], ZIP_DEFLATED)
```

원본이 mimetype을 압축해서 저장했더라도, 저장 시 무조건 STORED로 다시 씁니다. 검증기 `src/hwpx/tools/package_validator.py`는 세 조건을 하드 에러로 잡습니다: mimetype 값이 `application/hwp+zip`인가, mimetype이 첫 엔트리인가, `ZIP_STORED`인가.

수리 경로도 같습니다 — `src/hwpx/tools/repair.py`의 `_ordered_entries`가 mimetype을 맨 앞으로 옮기고, 없거나 중복이면 거부합니다. `repair_repack`은 mimetype이 STORED가 아니었으면 "재정렬됨"으로 리포트합니다.

이 계약은 `tests/test_opc_package.py`, `tests/test_repair_repack.py`가 검증합니다(예: `test_save_rewrites_mimetype_as_stored_even_when_source_was_compressed`).

## 미편집 바이트를 지키는 부분 패치

한/글이 파일을 "변조되지 않았다"고 인식하게 하려면, 손대지 않은 파트는 원본 그대로 두는 것이 안전합니다. 저장 시 라이브러리는 **원래 ZIP 엔트리 순서와 메타데이터(압축 방식, create_system, external_attr 등)를 보존**하고, 편집한 파트만 다시 씁니다(`test_save_preserves_existing_archive_order_and_entry_metadata`). 바이트 보존 편집 경로는 여기에 더해, 섹션 XML의 바이트를 부분 스플라이스해 미편집 영역을 한 바이트도 건드리지 않습니다.

## version.xml 관리

`version.xml`은 한/글 버전 정보를 담는 선택적이지만 중요한 파트입니다(`src/hwpx/opc/package.py`의 `VersionInfo`). 실전에서 알아 둘 점:

- **없어도 열린다.** 파싱 시 version.xml이 없으면 에러가 아니라 경고를 내고 기본값을 씁니다(`_parse_version`). 단, 한번 열린 문서에서는 `mimetype`·`container.xml`·`version.xml`을 필수·삭제 불가 파트로 취급합니다.
- **dirty일 때만 다시 쓴다.** 저장 시 version 정보가 변경(dirty)된 경우에만 재직렬화하고, XML 선언(`<?xml ...?>`)은 원본을 보존합니다.
- **한컴의 오타까지 보존.** 기본 version.xml의 루트 속성 이름은 `tagetApplication`입니다(`targetApplication`의 오타). 한/글이 실제로 그렇게 쓰므로 라이브러리도 그대로 재현합니다.

## manifest와 container 관계

HWPX의 매니페스트는 ODF식 `META-INF/manifest.xml`이 아니라 **OPF 형식의 `Contents/content.hpf`** 입니다(`src/hwpx/opc/relationships.py`의 `MAIN_ROOTFILE_MEDIA_TYPE = "application/hwpml-package+xml"`).

- `META-INF/container.xml`이 rootfile을 선언합니다. 없으면 하드 에러(`_parse_container`), rootfile이 하나도 없어도 에러입니다.
- 메인 rootfile(`content.hpf`)의 `<opf:manifest>/<opf:item>`들이 각 파트를 id로 매핑하고, `<opf:spine>/<opf:itemref>`가 본문 파트 순서를 정합니다. `parse_manifest_relationships`가 헤더/마스터페이지/히스토리/버전 파트를 여기서 분류합니다.

## 네임스페이스 정규화: 2016 → 2011

HWPML 네임스페이스는 연도별 변종이 있습니다(2011, 2016, 2024). 라이브러리는 다양한 연도로 저작된 문서를 하나의 상수 집합으로 다루기 위해, **파싱 직전에 2016 네임스페이스 URI를 2011 등가물로 치환**합니다 — `src/hwpx/opc/xml_utils.py`:

```python
_HWPML_2016_TO_2011 = (
    (b".../hwpml/2016/paragraph", b".../hwpml/2011/paragraph"),
    (b".../hwpml/2016/head",      b".../hwpml/2011/head"),
    (b".../hwpml/2016/section",   b".../hwpml/2011/section"),
    (b".../hwpml/2016/core",      b".../hwpml/2011/core"),
    (b".../hwpml/2016/master-page", b".../hwpml/2011/master-page"),
    (b".../hwpml/2016/history",   b".../hwpml/2011/history"),
    (b".../hwpml/2016/app",       b".../hwpml/2011/app"),
)

def normalize_hwpml_namespaces(data: bytes) -> bytes:
    for old, new in _HWPML_2016_TO_2011:
        if old in data:
            data = data.replace(old, new)
    return data
```

7개 계열(paragraph, head, section, core, master-page, history, app)이 대상입니다. 덕분에 하위 코드는 2011 URI 하나로만 요소를 찾으면 됩니다.

**주의할 정직한 한계**: 이 정규화는 *파싱한 트리*에만 영향을 줍니다. 편집하지 않은 파트는 원본 저장 바이트 그대로 저장되므로, 예컨대 2024 네임스페이스 문서는 편집 후에도 2024 URI가 보존됩니다(`tests/test_namespace_handling.py::test_open_to_bytes_preserves_source_namespace_after_edit`). 열기는 2011/2016/2024를 모두 수용합니다.

수리 경로는 섹션/헤더 루트를 한/글이 쓰는 것과 같은 폭넓은 네임스페이스 선언(`hp10`이 2016 paragraph URI를 가리키는 것 포함)으로 다시 감싸고, `standalone="yes"` 선언을 재발행합니다(`src/hwpx/tools/repair.py`의 `_serialize_hwpml_compat_root`). 이는 read-modify-save 왕복이 "변조된 것처럼 보이지 않게" 하려는 것입니다.

## 실전 요약

- HWPX ZIP을 직접 재패킹한다면 **mimetype을 첫 엔트리·STORED**로 넣으세요. 이 하나만 어겨도 한/글이 인식하지 못할 수 있습니다.
- 미편집 파트는 순서·메타데이터·바이트를 그대로 보존하는 편이 안전합니다.
- 매니페스트는 `Contents/content.hpf`(OPF)이고, `META-INF/container.xml`이 그것을 rootfile로 선언합니다.
- 손상된 파일은 `hwpx.tools.repair`(CLI `hwpx-validate-package`와 함께)로 재정렬·정규화할 수 있습니다.
