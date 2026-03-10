# 변경 로그

모든 중요한 변경 사항은 이 문서에 기록됩니다. 형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)과 [Semantic Versioning](https://semver.org/lang/ko/)을 따릅니다.

## [2.8.3] - 2026-03-10
### 변경
- 저장소와 배포 메타데이터의 라이선스 표기를 실제 `LICENSE` 파일과 일치하도록 정렬했습니다.
- `pyproject.toml`을 PEP 639 방식의 `LicenseRef-python-hwpx-NonCommercial` + `license-files` 구성으로 갱신하고, 잘못된 MIT 분류자를 제거했습니다.
- README 라이선스 배지/섹션을 커스텀 비상업적 라이선스 기준으로 수정하고, wheel/sdist 산출물의 라이선스 메타데이터를 검증하는 회귀 테스트를 추가했습니다.

## [2.8.2] - 2026-03-08
### 변경
- README를 현재 공개 API와 CLI 범위에 맞춰 정리했습니다. Quick start, 텍스트 추출, 객체 검색 예시를 실제 호출 방식 기준으로 수정했습니다.
- `add_memo()`/`add_memo_with_anchor()`가 `HwpxDocument.new()`로 만든 실제 `lxml` 기반 문서에서도 동작하도록 memo XML 생성 경로를 엔진 호환 방식으로 정리했습니다.
- 실제 빈 문서 템플릿에서 메모 추가 후 roundtrip 되는 회귀 테스트를 추가했습니다.

## [2.8.1] - 2026-03-08
### 추가
- 템플릿 자동화 회귀 스위트를 추가했습니다 (`tests/template_automation/`). 단순 토큰, 반복 토큰, split-run, 공백 정규화, 표/머리글/바닥글/다중 섹션, 체크박스 토글, extract-repack, 비표준 rootfile 패턴을 대표 fixture + 시나리오 계약으로 점검합니다.
- `DevDoc/template-automation-regression-suite.md`를 추가해 스위트의 보장 범위, 한계, fixture 추가 절차를 문서화했습니다.

### 변경
- 실제 `lxml` 기반 문서에서 `set_header_text()`/`set_footer_text()`가 동작하도록 header/footer 생성 경로를 XML 엔진 호환 방식으로 정리했습니다.
- 섹션 속성(`secPr`)이 비어 있을 때 보강 생성하는 경로를 XML 엔진 호환 방식으로 정리했습니다.
- `add_section()`이 새 섹션을 잘못된 네임스페이스로 만들던 문제를 수정했습니다.
- mypy/pyright gradual scope에 이번에 추가한 template automation helper/generator 모듈을 포함했습니다.
## [2.8] - 2026-03-08
### 변경
- `HwpxPackage`와 OXML 로딩/저장이 rootfile/manifest-relative 경로를 실제로 따르도록 정렬했습니다.
- `hwpx-analyze-template --extract-dir`가 재구성에 바로 쓸 수 있는 작업 디렉터리와 `.hwpx-pack-metadata.json`을 생성하도록 확장했습니다.
- `hwpx-validate-package`를 엔진 정합 기준으로 재작성해 dynamic rootfile/manifest 관계, CRC, fallback warning을 구분하도록 했습니다.
- `hwpx-unpack` 기본값을 raw-byte preserving으로 바꾸고 `--pretty-xml` opt-in을 추가했습니다.
- tooling/OPC 회귀 테스트를 확대하고, coverage threshold를 60으로 올렸으며, pyright는 touched OPC/tooling 범위에서 `basic`으로 상향했습니다.

## [2.7.1] - 2026-03-08
### 변경
- 공개 저장소와 배포 산출물에서 내부 감사 문서를 제거했습니다.

## [2.7] - 2026-03-08
### 추가
- `hwpx-unpack`, `hwpx-pack`, `hwpx-analyze-template` CLI를 추가했습니다.
- `src/hwpx/tools/archive_cli.py`를 추가해 unpack/pack 워크플로를 패키지 레벨 도구로 승격했습니다.
- unpack 시 `.hwpx-pack-metadata.json`을 기록하고, pack 시 이를 사용해 원본 ZIP 엔트리 순서/압축 방식을 가능한 범위에서 보존하도록 했습니다.
- `src/hwpx/tools/template_analyzer.py`를 추가했습니다.

### 변경
- `scripts/office/unpack.py`, `scripts/office/pack.py`, `scripts/analyze_template.py`를 패키지 도구 래퍼로 정리했습니다.
- `page_guard`에 shape/control count 및 히스토그램 비교를 추가하고, 실제 페이지 수 계산기가 아니라 구조 변화 징후 점검 도구임을 문서와 CLI 설명에 명시했습니다.
- README와 `docs/usage.md`에 새 CLI 사용 예시를 추가했습니다.
- 새 tooling에 대한 CLI/추출/overwrite/page-guard 회귀 테스트를 강화했습니다.

## [2.6] - 2026-03-08
### 추가
- `hwpx-validate-package` CLI와 `hwpx.tools.package_validator`를 추가해 ZIP/OPC/HWPX 패키지 구조, `mimetype`, `container.xml`, manifest/spine 참조, XML well-formedness를 점검할 수 있게 했습니다.
- `hwpx-page-guard` CLI와 `hwpx.tools.page_guard`를 추가해 섹션 수, 단락 수, page/column break, 표 구조, 텍스트 길이 변화량을 기준으로 문서 드리프트를 비교할 수 있게 했습니다.
- `hwpx-text-extract` CLI를 추가해 기존 `TextExtractor` 기능을 plain/markdown 형태로 바로 사용할 수 있게 했습니다.
- `scripts/office/unpack.py`, `scripts/office/pack.py`, `scripts/analyze_template.py`를 추가해 XML-first HWPX 작업 흐름을 지원합니다.
- gap-closure 반영분에 대한 테스트를 추가했습니다 (`tests/test_gap_closure_tools.py`).

### 수정
- `HwpxDocument.validate()`가 내부 직렬화 과정에서 dirty 상태를 지워 버리던 부작용을 제거해, 검증 이후에도 저장 필요 상태가 유지되도록 수정했습니다.

## [2.3.1] - 2026-02-28
### 추가
- **단락 삭제 API**: `paragraph.remove()`, `section.remove_paragraph()`, `document.remove_paragraph()` 메서드를 추가했습니다. 마지막 단락 삭제 시 `ValueError`가 발생합니다.
- **섹션 추가/삭제 API**: `document.add_section(after=)`, `document.remove_section()` 메서드를 추가했습니다. 새 섹션은 manifest/spine에 자동 등록되며, 마지막 섹션 삭제 시 `ValueError`가 발생합니다.
- **네임스페이스 상수 모듈**: `hwpx.oxml.namespaces` 모듈을 추가하여 HP, HH, HC 등 공유 네임스페이스 상수를 제공합니다.
- 새 API에 대한 16개 테스트 케이스를 추가했습니다 (`test_paragraph_section_management.py`).

### 수정
- `import hwpx`만으로 `DeprecationWarning`이 발생하던 문제를 수정했습니다. `hwpx.package` 경고는 이제 사용자가 직접 해당 모듈을 import할 때만 표시됩니다.
- `HwpxOxmlTableCell.text`가 셀에 여러 단락이 있을 때 첫 번째 텍스트만 반환하던 버그를 수정했습니다. 모든 `<hp:t>` 요소의 텍스트를 결합하여 반환합니다.
- `add_hyperlink()` 메서드에서 사용되지 않는 `field_inst_id` 변수를 제거했습니다.
- deprecated `save()` 호출을 사용하던 테스트 코드를 `save_to_path()`/`save_to_stream()`으로 업데이트했습니다.

## [1.9] - 2026-02-18
### 변경
- `hwpx.__version__` 하드코딩 값을 제거하고 `importlib.metadata.version("python-hwpx")` 기반으로 노출하도록 정리했습니다.
- editable/로컬 소스 실행처럼 배포 메타데이터가 없는 환경에서도 동작하도록 `PackageNotFoundError` fallback(`0+unknown`)을 추가했습니다.

## [0.1.0] - 2025-09-17
### 추가
- `hwpx.opc.package.HwpxPackage`와 `hwpx.document.HwpxDocument`를 포함한 핵심 API를 공개했습니다.
- 텍스트 추출, 객체 탐색, 문서 유효성 검사 등 도구 모듈과 `hwpx-validate` CLI를 제공합니다.
- HWPX 스키마 리소스와 예제 스크립트를 번들링해 바로 사용할 수 있도록 했습니다.
- 설치 가이드, 사용 예제, 스키마 개요 등 배포 문서를 정리했습니다.
