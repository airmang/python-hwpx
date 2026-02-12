# hwpx-ts

한글 워드프로세서 HWPX 문서를 읽고, 편집, 자동화하기 위한 TypeScript 라이브러리 모음입니다.

## 개요

`hwpx-ts`는 한컴 오피스 HWPX 문서 형식을 완벽하게 지원하는 TypeScript/React 도구 세트입니다. OPC 컨테이너 기반의 HWPX 파일을 메모리에 로드하고, 문단·표·이미지·포맷 정보를 조회 및 수정한 뒤 다시 저장할 수 있습니다. 또한 React 기반의 에디터 UI 컴포넌트 라이브러리를 제공하여 웹 애플리케이션에 한글 워드프로세서 경험을 쉽게 구현할 수 있습니다.

## 패키지

이 모노레포는 두 개의 주요 패키지로 구성되어 있습니다.

| 패키지 | 설명 | npm |
|--------|------|-----|
| **@ubermensch1218/hwpxcore** | HWPX 문서 읽기/편집 TypeScript 라이브러리 | [![npm version](https://img.shields.io/npm/v/@ubermensch1218/hwpxcore.svg)](https://www.npmjs.com/package/@ubermensch1218/hwpxcore) |
| **@ubermensch1218/hwpxeditor** | React 에디터 UI 컴포넌트 라이브러리 | [![npm version](https://img.shields.io/npm/v/@ubermensch1218/hwpxeditor.svg)](https://www.npmjs.com/package/@ubermensch1218/hwpxeditor) |

### @ubermensch1218/hwpxcore

HWPX 문서 조작을 위한 핵심 라이브러리입니다.

**주요 기능:**
- HWPX 파일 열기/저장
- 섹션, 문단, 표, 이미지 관리
- 문자 및 문단 포맷 속성 편집
- 메모 추가
- 헤더 정보(스타일, 글꼴, 테두리/채우기 등) 접근

**설치:**
```bash
npm install @ubermensch1218/hwpxcore
```

**빠른 시작:**
```typescript
import { HwpxDocument } from '@ubermensch1218/hwpxcore';

// 문서 열기
const buffer = await fetch('document.hwpx').then(r => r.arrayBuffer());
const doc = await HwpxDocument.open(new Uint8Array(buffer));

// 문단 읽기
for (const section of doc.sections) {
  for (const para of section.paragraphs) {
    console.log(para.text);
  }
}

// 문단 추가
doc.addParagraph('새 문단');

// 저장
const bytes = await doc.save();
```

### @ubermensch1218/hwpxeditor

한글 워드프로세서 스타일의 React 에디터 컴포넌트입니다.

**주요 기능:**
- 리본 툴바 (Ribbon toolbar)
- 문자/문단 포맷 사이드바
- 수평 자 (Horizontal ruler)
- WYSIWYG 페이지 편집
- 테이블, 이미지 지원

**설치:**
```bash
npm install @ubermensch1218/hwpxeditor react react-dom
```

**빠른 시작:**
```typescript
import { Editor } from '@ubermensch1218/hwpxeditor';

export default function App() {
  return <Editor />;
}
```

자세한 사용법은 각 패키지의 README를 참고하세요:
- [hwpxcore README](./packages/hwpx-core/README.md)
- [hwpxeditor README](./packages/hwpx-editor/README.md)

## 개발 설정

이 프로젝트는 pnpm 워크스페이스 모노레포입니다.

### 설치

```bash
pnpm install
```

### 빌드

```bash
pnpm run build
```

### 개발 모드

각 패키지별로 개발 모드를 실행할 수 있습니다:

```bash
# hwpxcore 개발 모드
pnpm --filter @ubermensch1218/hwpxcore run dev

# hwpxeditor 개발 모드 (Next.js 데모 앱)
pnpm --filter @ubermensch1218/hwpxeditor run dev
```

### 테스트

```bash
pnpm run test
```

## 저장소

GitHub: https://github.com/ubermensch1218/hwpx-ts

## 라이선스

Non-Commercial License - 비상업적 용도로 자유롭게 사용, 수정, 배포할 수 있습니다. 상업적 사용은 별도 협의가 필요합니다.

자세한 내용은 [LICENSE](./LICENSE) 파일을 참고하세요.
