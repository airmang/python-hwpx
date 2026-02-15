# 변경 로그

모든 중요한 변경 사항은 이 문서에 기록됩니다. 형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)과 [Semantic Versioning](https://semver.org/lang/ko/)을 따릅니다.

## [Unreleased]
### 추가
- 토큰 효율 중심의 HWPX → Markdown 변환을 위한 `hwpxtool hwpx-to-md` 커맨드를 추가했습니다.
  - 이미지 처리 모드: `--image-mode markdown|placeholder|omit`
  - 이미지 파일 추출: `--images-dir <dir>`
  - 이미지 메타데이터(manifest) 출력: `--manifest <file>`
  - 토큰 효율 모드 기본값 `ON`, 비활성화는 `--no-token-efficient`
- HWP(한글 5.x 바이너리) → HWPX(best-effort) 변환을 위한 `hwpxtool hwp-to-hwpx` 커맨드를 추가했습니다.
- 기존 `hwpxtool export`의 마크다운 출력에 토큰 효율/이미지 옵션을 확장했습니다: `--token-efficient`, `--image-mode`, `--images-dir`, `--manifest`
- 라이브러리 API로 `exportToMarkdownBundle()`를 추가해, `markdown` 문자열과 `images` manifest를 함께 얻을 수 있습니다.

### 사용법 (CLI)
- 전제: `.hwpx`는 `hwpx-to-md`로 바로 변환할 수 있고, `.hwp`는 먼저 `hwp-to-hwpx`로 HWPX로 만든 다음 변환합니다.

#### 설치
```bash
# npm (패키지가 배포되어 있다면)
npm i -g @ubermensch1218/hwpx-cli

# pnpm
pnpm add -g @ubermensch1218/hwpx-cli
```

#### HWP → HWPX
```bash
hwpxtool hwp-to-hwpx input.hwp -o output.hwpx
```

#### 변환 (권장)
```bash
# 토큰 효율 Markdown + 이미지 manifest
hwpxtool hwpx-to-md output.hwpx \\
  -o output.md \\
  --image-mode placeholder \\
  --manifest output.images-manifest.json
```

#### 이미지 파일까지 추출
```bash
hwpxtool hwpx-to-md input.hwpx \\
  -o output.md \\
  --image-mode placeholder \\
  --images-dir ./images \\
  --manifest output.images-manifest.json
```

#### 이미지 링크로 내보내기
```bash
hwpxtool hwpx-to-md input.hwpx \\
  -o output.md \\
  --image-mode markdown \\
  --images-dir ./images
```

#### 토큰 효율 모드 끄기
```bash
hwpxtool hwpx-to-md input.hwpx \\
  -o output.md \\
  --no-token-efficient
```

## [0.1.0] - 2025-09-17
### 추가
- `hwpx.opc.package.HwpxPackage`와 `hwpx.document.HwpxDocument`를 포함한 핵심 API를 공개했습니다.
- 텍스트 추출, 객체 탐색, 문서 유효성 검사 등 도구 모듈과 `hwpx-validate` CLI를 제공합니다.
- HWPX 스키마 리소스와 예제 스크립트를 번들링해 바로 사용할 수 있도록 했습니다.
- 설치 가이드, 사용 예제, 스키마 개요 등 배포 문서를 정리했습니다.
