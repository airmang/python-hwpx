# 설치 가이드

이 문서는 python-hwpx PyPI 또는 소스 코드에서 설치하는 방법을 정리합니다. 일반 사용자는 PyPI 패키지를 이용하면 되며, 기능 개발이나 디버깅 목적이라면 저장소를 클론해 편집 가능한 설치를 수행하세요.

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

설치 후 `python -c "import hwpx"` 명령이 오류 없이 종료되면 환경 구성이 완료된 것입니다.

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

`pip install -e`를 사용하면 추가적인 `PYTHONPATH` 수정 없이도 `hwpx` 패키지를 바로 가져올 수 있습니다.

## 설치 검증

다음 스니펫을 실행해 핵심 모듈이 정상적으로 로드되는지 확인하세요.

```bash
python - <<'PY'
from hwpx.opc.package import HwpxPackage
print("Package class loaded:", hasattr(HwpxPackage, "open"))
PY
```

또는 텍스트 추출 도구를 호출해 문단 수를 빠르게 확인할 수 있습니다.

```bash
python - <<'PY'
from hwpx.tools.text_extractor import TextExtractor

with TextExtractor("examples/FormattingShowcase.hwpx") as extractor:
    paragraphs = list(extractor.iter_document_paragraphs())

print("Paragraphs:", len(paragraphs))
PY
```

## 테스트 실행 (선택 사항)

개발 환경을 준비했다면 단위 테스트로 기본 동작을 검증하세요.

```bash
python -m pytest
```

테스트가 모두 통과하면 라이브러리를 사용할 준비가 완료된 것입니다.
