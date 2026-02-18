# 설치 가이드

이 문서는 PyPI에서 바로 패키지를 설치하는 방법과 저장소를 클론해 개발 환경을 구성하는 방법을 정리합니다. 대부분의 사용자는 PyPI 패키지를 설치한 뒤 제공되는 템플릿(`hwpx.templates.blank_document_bytes`)으로 바로 실습할 수 있습니다. 저장소에 포함된 예제 HWPX 파일이 필요한 경우에는 깃 클론 후 `examples/` 디렉터리를 활용하세요.

## 요구 사항

- Python 3.10 이상 (프로젝트 테스트는 CPython 3.11 기준)
- `pip`, `venv` 모듈이 포함된 표준 Python 배포판
- Git 2.30 이상 (소스 설치 시)

## PyPI에서 설치

```bash
python -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install python-hwpx
```

설치 후 다음 명령으로 기본 모듈과 내장 템플릿이 정상 동작하는지 빠르게 확인할 수 있습니다.

```bash
python - <<'PY'
from io import BytesIO

from hwpx import HwpxDocument
from hwpx.templates import blank_document_bytes

doc = HwpxDocument.open(BytesIO(blank_document_bytes()))
print("sections:", len(doc.sections))
PY
```

## 소스 코드에서 개발용 설치

1. 저장소를 클론합니다.
   ```bash
   git clone <repository-url>
   cd python-hwpx
   ```
2. 가상 환경을 만들고 활성화합니다.
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   ```
3. 편집 가능한 설치와 개발 도구를 한 번에 구성합니다.
   ```bash
   python -m pip install -e .[dev]
   ```

`pip install -e`를 사용하면 추가적인 `PYTHONPATH` 수정 없이도 `hwpx` 패키지를 바로 가져올 수 있습니다. 저장소 예제(`examples/FormattingShowcase.hwpx`)는 개발용 설치를 진행한 경우에만 사용할 수 있습니다.

## 설치 검증

다음 스니펫을 실행해 핵심 모듈이 정상적으로 로드되는지 확인하세요.

```bash
python - <<'PY'
from hwpx import HwpxPackage
print("Package class loaded:", hasattr(HwpxPackage, "open"))
PY
```

PyPI 패키지에는 예제 HWPX 파일이 포함되지 않으므로, 직접 확보한 문서를 대상으로 테스트하거나 저장소의 `examples/` 디렉터리를 사용하세요.

## 테스트 실행 (선택 사항)

개발 환경을 준비했다면 단위 테스트로 기본 동작을 검증하세요.

```bash
python -m pytest
```

테스트가 모두 통과하면 라이브러리를 사용할 준비가 완료된 것입니다.
