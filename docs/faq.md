# 자주 묻는 질문 (FAQ)

## `ModuleNotFoundError: No module named 'hwpx'` 오류가 발생합니다.

PyPI에서 설치했다면 가상 환경을 활성화하고 `pip install python-hwpx`만 실행해도 됩니다. 저장소를 직접 클론해 개발 중이라면 루트 `src` 디렉터리를 `PYTHONPATH`에 추가해야 합니다. 다음 명령을 참고하세요.

```bash
export PYTHONPATH="$(pwd)/src:${PYTHONPATH}"
```

PowerShell을 사용한다면:

```powershell
$env:PYTHONPATH = "$(Get-Location)\src;" + $env:PYTHONPATH
```

보다 자세한 절차는 [설치 가이드](installation.md)를 참고하세요.

## `HwpxStructureError` 예외가 발생하는 이유는 무엇인가요?

`HwpxStructureError`는 패키지 내 필수 파일이 누락되거나 `META-INF/container.xml`에 선언된 루트 파일을 찾지 못했을 때 발생합니다. 문제가 되는 HWPX 파일이 규격을 따르는지 다음 항목을 확인하세요.

1. ZIP 루트에 `mimetype` 파일이 존재하며 내용이 `application/hwp+zip`인지 확인합니다.
2. `META-INF/container.xml`에 선언된 경로가 실제 파트와 일치하는지 검사합니다.
3. `version.xml`이 포함되어 있고, `Contents/` 디렉터리에 문서 본문(`section*.xml`)이 있는지 확인합니다.

파일이 손상되었다면 Hancom Office에서 다시 저장하거나, `HwpxPackage.open()` 호출 시 예외를 잡아 사용자에게 오류를 알리면 됩니다.

## `hwpx.package.HwpxPackage`와 `hwpx.opc.package.HwpxPackage`의 차이는 무엇인가요?

두 클래스 모두 HWPX 패키지를 나타내지만 역할이 다릅니다.

- `hwpx.opc.package.HwpxPackage`는 OPC 구조 검증과 파트 로딩에 초점을 맞춘 저수준 컨테이너입니다.
- `hwpx.package.HwpxPackage`는 `HwpxDocument`가 사용하는 상위 래퍼로, 수정된 XML 파트를 직렬화하고 저장하는 기능을 제공합니다.

패키지를 직접 다룰 때는 일반적으로 `hwpx.opc.package.HwpxPackage`를 사용하고, 문서 편집 API와 함께 작업할 때는 `HwpxDocument.package` 속성으로 제공되는 고수준 패키지를 사용하세요.

## 파일을 메모리 버퍼나 HTTP 응답으로부터 열 수 있나요?

네. `HwpxPackage.open()`과 `HwpxDocument.open()`은 파일 경로뿐 아니라 바이트열과 파일 객체도 지원합니다.

```python
from io import BytesIO
from hwpx.document import HwpxDocument

with open("sample.hwpx", "rb") as fp:
    data = fp.read()

document = HwpxDocument.open(BytesIO(data))
print(len(document.paragraphs))
```

수정된 결과를 바이트로 받고 싶다면 `document.save()` 호출 시 경로를 생략하면 됩니다.

## 중첩 문단을 제외하거나 특정 섹션만 순회하려면 어떻게 해야 하나요?

`TextExtractor.iter_document_paragraphs(include_nested=False)`를 호출하면 표/컨트롤 내부 문단을 건너뛸 수 있습니다. 섹션별로 처리하려면 `iter_sections()` 결과를 필터링한 뒤 `iter_paragraphs()`를 호출하세요.

```python
from hwpx.tools.text_extractor import TextExtractor

with TextExtractor("sample.hwpx") as extractor:
    for section in extractor.iter_sections():
        if section.index != 0:
            continue
        for paragraph in extractor.iter_paragraphs(section, include_nested=False):
            print(section.name, paragraph.index, paragraph.text())
```

## 저장 시 원본 파일을 덮어쓰지 않고 새 파일로 만들고 싶습니다.

`HwpxDocument.save("output.hwpx")`처럼 경로를 지정하면 해당 경로로 새 ZIP 아카이브가 생성됩니다. 이미 열린 파일 객체나 `BytesIO` 버퍼를 전달해도 되며, 반환값으로 새 경로 또는 버퍼가 제공됩니다.
