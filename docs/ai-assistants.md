# AI 채팅 환경에서 쓰기 (ChatGPT · Claude · Codex)

ChatGPT 채팅의 파이썬 실행 환경은 PyPI 접근이 막혀 있어 `pip install python-hwpx`가
실패합니다. python-hwpx는 순수 파이썬 wheel(`py3-none-any`) 하나로 설치되므로,
wheel 파일을 문서와 함께 올리면 같은 작업을 오프라인으로 할 수 있습니다.
Claude나 Codex 같은 다른 샌드박스에서 네트워크가 막혔을 때도 절차는 같습니다.

## 사람이 할 일 — 3단계

1. [최신 Release](https://github.com/airmang/python-hwpx/releases/latest)에서
   `python_hwpx-<버전>-py3-none-any.whl` 파일을 내려받습니다.
2. 작업할 `.hwpx` 문서와 그 wheel을 채팅에 **함께** 첨부합니다.
3. 다음처럼 부탁합니다.

```text
첨부한 python_hwpx-*.whl 을 pip 로 설치한 다음(pip install /mnt/data/python_hwpx-*.whl),
이 .hwpx 파일을 python-hwpx 라이브러리로 열어서 작업해줘.
양식과 서식은 그대로 두고, ○○만 바꿔서 새 파일로 돌려줘.
```

새 문서를 만들 때는 `.hwpx` 없이 wheel만 올리고 "python-hwpx로 ○○ 문서를
만들어 `.hwpx`로 돌려줘"라고 부탁하면 됩니다.

`/mnt/data`는 ChatGPT가 첨부 파일을 두는 경로입니다. 다른 환경에서는 첨부
파일이 놓인 경로로 바꿔 말하거나, 경로를 빼고 "첨부한 wheel을 설치해줘"라고만
해도 됩니다.

## 의존성 — lxml

wheel의 유일한 의존성은 `lxml`입니다. 실행 환경에 lxml이 이미 있으면 wheel만으로
설치가 끝나고, 없으면 `pip install`이 lxml을 찾지 못해 실패합니다. 그 경우
[PyPI의 lxml 파일 목록](https://pypi.org/project/lxml/#files)에서 실행 환경의
플랫폼과 파이썬 버전에 맞는 wheel(예: `manylinux` · `cp312`)을 받아 함께 올리고,
두 파일을 같은 명령으로 설치합니다.

```bash
pip install /mnt/data/lxml-*.whl /mnt/data/python_hwpx-*.whl
```

## 첨부 없이 가져오기 — GitHub Actions artifact (실험)

ChatGPT의 GitHub 커넥터는 Release 자산의 바이너리는 내려받지 못하지만 GitHub
Actions **artifact**(ZIP)는 가져올 수 있는 것으로 확인됐습니다. 그래서 같은
wheel을 두 곳에 더 둡니다.

- 릴리스 워크플로가 wheel과 `SHA256SUMS`를 artifact `python-hwpx-wheel`로도 올립니다.
- [`wheel-artifact.yml`](https://github.com/airmang/python-hwpx/actions/workflows/wheel-artifact.yml)이
  매달, 그리고 릴리스마다 최신 Release의 wheel을 해시 검증 후 같은 이름으로 다시
  올립니다. artifact는 90일 뒤 만료되므로 이 갱신이 없으면 끊깁니다.

에이전트는 이 워크플로의 최신 성공 run에서 artifact `python-hwpx-wheel`을 받아
ZIP을 풀고 안의 `.whl`을 설치하면 됩니다. ZIP에는 `SHA256SUMS`와 `RELEASE_TAG`가
같이 들어 있어 어느 릴리스의 어떤 bytes인지 대조할 수 있습니다.

이 경로는 커넥터의 artifact 다운로드 기능이 확인된 단계이며, 채팅 런타임까지
wheel이 실제로 도달해 설치되는 전 과정은 아직 실측하지 않았습니다. 확실한
경로는 위의 사용자 첨부입니다.

## AI 어시스턴트를 위한 지시문

아래 블록은 에이전트가 그대로 따르도록 쓴 것입니다. 사용자가 이 페이지 링크를
함께 주면 에이전트가 설치 방법을 스스로 판단할 수 있습니다.

```text
Instructions for AI assistants running python-hwpx in a sandboxed Python
environment where PyPI is unavailable:

1. Look for an uploaded file matching python_hwpx-*.whl (ChatGPT places
   uploads under /mnt/data). Do not try to reach PyPI. If nothing was
   uploaded and you can fetch GitHub Actions artifacts, take the artifact
   named python-hwpx-wheel from the latest successful run of the
   "Wheel artifact" workflow in airmang/python-hwpx, unzip it, and use the
   .whl inside (SHA256SUMS in the same zip lets you verify it).
2. Check the only dependency first: `python -c "import lxml"`. If it fails,
   look for an uploaded lxml-*.whl; if there is none, ask the user to upload
   an lxml wheel for this platform and Python version before continuing.
3. Install with the local path: `pip install /mnt/data/python_hwpx-*.whl`
   (add the lxml wheel path to the same command when needed).
4. Use the real API from https://airmang.github.io/python-hwpx/llms.txt —
   `from hwpx import HwpxDocument`; open with `HwpxDocument.open(path)`,
   create with `HwpxDocument.new()`, save with `document.save_to_path(path)`.
   There is no `document.save()`.
5. Never overwrite the user's uploaded document. Write results to a new file
   in the runtime's output location (ChatGPT: /mnt/data) and hand that file
   back to the user.
6. Before returning, reopen the saved file with `HwpxDocument.open()` and
   confirm the requested change is present.
```

## 최소 예제

wheel 설치 뒤 새 문서를 만들어 돌려주는 가장 짧은 코드입니다.

```python
from hwpx import HwpxDocument

document = HwpxDocument.new()
document.add_heading("보고서", level=1)
document.add_paragraph("본문입니다.")
document.save_to_path("/mnt/data/report.hwpx")
```

기존 문서를 고칠 때는 열고, 바꾸고, **다른 이름으로** 저장합니다.

```python
from hwpx import HwpxDocument

document = HwpxDocument.open("/mnt/data/form.hwpx")
count = document.text.replace("○○", "새 값")
document.save_to_path("/mnt/data/form-filled.hwpx")
print("바뀐 run 수:", count)
```

손대지 않은 부분은 바이트 그대로 보존되고, 저장은 원자적이며 보존 등급을
지킬 수 없으면 아무것도 쓰지 않고 실패합니다. 자세한 API는
[5분 빠른 시작](quickstart.md)과 [변경 의미론](mutation-semantics.md)을 보세요.

## 어디까지 되나

- 이 절차는 python-hwpx 코어 라이브러리(읽기·편집·생성)에 해당합니다. 라벨로
  양식 채우기, `hwpx` CLI, MCP 서버 같은 상위 워크플로는 companion 패키지
  [`python-hwpx-automation`](https://github.com/airmang/python-hwpx-automation)에
  있습니다. 그 패키지는 pydantic·cryptography·anyio에도 의존하므로 오프라인
  설치에는 그 wheel들까지 함께 올려야 하며, 채팅 환경에서는 코어만 쓰는 편이
  현실적입니다.
- 생성된 파일이 실제 한컴오피스에서 열리는지는 코퍼스 실측으로 확인하지만,
  채팅 환경 안에서 화면을 확인할 수는 없습니다. 최종 확인은 한글에서 열어 보세요.
- 파이썬 실행 가능 여부, 첨부 경로, 파일 반환 방식은 서비스와 플랜에 따라
  다릅니다. 이 문서의 경로는 ChatGPT 기준입니다.
