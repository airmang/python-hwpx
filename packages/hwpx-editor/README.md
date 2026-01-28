# @ubermensch1218/hwpxeditor

한글 워드프로세서 스타일의 UI를 제공하는 React 에디터 컴포넌트 라이브러리입니다.

[![npm version](https://img.shields.io/npm/v/@ubermensch1218/hwpxeditor.svg)](https://www.npmjs.com/package/@ubermensch1218/hwpxeditor)

## 설치

```bash
npm install @ubermensch1218/hwpxeditor react react-dom
```

또는 yarn:

```bash
yarn add @ubermensch1218/hwpxeditor react react-dom
```

### 동료 의존성 (Peer Dependencies)

- `react` >= 18
- `react-dom` >= 18

## 주요 기능

- **리본 툴바** - MS Word 스타일의 리본 인터페이스로 자주 사용하는 기능에 빠르게 접근
- **문자/문단 포맷 사이드바** - 오른쪽 사이드바에서 세밀한 포맷 설정 가능
- **수평 자** - 문단 들여쓰기와 탭 위치 시각화 및 조정
- **WYSIWYG 편집** - 실제 출력 형태 그대로 보며 편집
- **표 지원** - 표 생성, 셀 병합, 행/열 추가/삭제
- **이미지 삽입** - 문서에 이미지 삽입 가능
- **내장 상태 관리** - Zustand를 기반한 통합 상태 관리
- **RSC 호환** - Next.js App Router 지원 ("use client" 배너 포함)

## 사용 예제

### 기본 사용 (Full Editor)

```typescript
import { Editor } from '@ubermensch1218/hwpxeditor';

export default function App() {
  return (
    <div className="w-full h-screen">
      <Editor />
    </div>
  );
}
```

### Next.js App Router에서 사용

```typescript
'use client';

import { Editor } from '@ubermensch1218/hwpxeditor';

export default function EditorPage() {
  return <Editor />;
}
```

### Tailwind CSS 설정

이 라이브러리는 Tailwind CSS 유틸리티 클래스를 사용합니다. Tailwind CSS를 설정한 후 `tailwind.config.js`의 `content` 배열에 라이브러리 경로를 추가하세요:

```javascript
// tailwind.config.js
export default {
  content: [
    './src/**/*.{js,ts,jsx,tsx}',
    './node_modules/@ubermensch1218/hwpxeditor/dist/**/*.js',
  ],
  theme: {
    extend: {},
  },
  plugins: [],
};
```

**중요:** `content` 설정이 없으면 에디터의 스타일이 적용되지 않습니다.

## 개별 컴포넌트 사용

전체 에디터를 사용하지 않고 개별 컴포넌트만 사용할 수도 있습니다:

### 에디터 컴포넌트

```typescript
import {
  PageView,
  ParagraphBlock,
  TableBlock
} from '@ubermensch1218/hwpxeditor';

export function CustomEditor() {
  return (
    <div className="flex gap-4">
      <div className="flex-1">
        <PageView />
      </div>
    </div>
  );
}
```

### 툴바 컴포넌트

```typescript
import {
  RibbonToolbar,
  SecondaryToolbar,
  ToolbarButton,
  ToolbarDropdown
} from '@ubermensch1218/hwpxeditor';

export function MyToolbar() {
  return (
    <div>
      <RibbonToolbar />
      <SecondaryToolbar />
    </div>
  );
}
```

### 사이드바 컴포넌트

```typescript
import { FormatSidebar } from '@ubermensch1218/hwpxeditor';

export function MySidebar() {
  return <FormatSidebar />;
}
```

### 자 컴포넌트

```typescript
import { HorizontalRuler } from '@ubermensch1218/hwpxeditor';

export function MyRuler() {
  return <HorizontalRuler />;
}
```

## 주요 내보내기 (Exports)

### 에디터 컴포넌트

- `Editor` - 전체 에디터 (완전 통합)
- `PageView` - 페이지 뷰
- `Page` - 단일 페이지
- `ParagraphBlock` - 문단 렌더링
- `RunSpan` - 텍스트 실행 (문자 속성)
- `ImageBlock` - 이미지 렌더링
- `TableBlock` - 표 렌더링
- `TableCell` - 표 셀

### 툴바 컴포넌트

- `RibbonToolbar` - 리본 툴바
- `SecondaryToolbar` - 2차 포맷 툴바
- `ToolbarButton` - 툴바 버튼
- `ToolbarDropdown` - 드롭다운 메뉴
- `ColorPicker` - 색상 선택기
- `RibbonGroup` - 리본 그룹
- `ClipboardGroup` - 복사/붙여넣기 그룹
- `InsertGroup` - 삽입 그룹
- `StyleSelector` - 스타일 선택
- `FontSelector` - 글꼴 선택
- `FontSizeInput` - 글자 크기 입력
- `CharFormatButtons` - 문자 포맷 버튼 (굵게, 기울임 등)
- `AlignmentButtons` - 정렬 버튼
- `LineSpacingControl` - 줄간격 제어

### 사이드바 컴포넌트

- `FormatSidebar` - 포맷 사이드바
- `SidebarSection` - 사이드바 섹션
- `SidebarField` - 사이드바 필드
- `CharFormatPanel` - 문자 포맷 패널
- `ParaFormatPanel` - 문단 포맷 패널
- `BorderSettings` - 테두리 설정
- `BackgroundSettings` - 배경 설정

### 기타

- `HorizontalRuler` - 수평 자
- `FileUpload` - 파일 업로드
- `NewDocumentButton` - 새 문서 버튼
- `useEditorStore` - 에디터 상태 관리 훅
- `buildViewModel` - 뷰 모델 생성

### 상수 및 유틸리티

```typescript
import {
  FONT_FAMILIES,        // 사용 가능한 글꼴 목록
  FONT_SIZES,          // 사용 가능한 글자 크기
  STYLE_PRESETS,       // 스타일 프리셋
  ALIGNMENT_OPTIONS,   // 정렬 옵션
  LINE_SPACING_OPTIONS,// 줄간격 옵션
  UNDERLINE_TYPES,     // 밑줄 종류
  COLOR_PRESETS,       // 색상 프리셋
  HIGHLIGHT_COLORS,    // 형광펜 색상
} from '@ubermensch1218/hwpxeditor';

import {
  hwpToPx,            // hwp 단위를 픽셀로 변환
  pxToHwp,            // 픽셀을 hwp 단위로 변환
  hwpToMm,            // hwp 단위를 mm로 변환
  mmToHwp,            // mm를 hwp 단위로 변환
  extractImages,      // 문서에서 이미지 추출
  ensureSkeletonLoaded,// 템플릿 미리로드
  createNewDocument,  // 새 문서 생성
} from '@ubermensch1218/hwpxeditor';
```

## 상태 관리 (Store)

에디터는 `useEditorStore` 훅으로 상태를 관리합니다:

```typescript
import { useEditorStore } from '@ubermensch1218/hwpxeditor';

export function MyComponent() {
  const doc = useEditorStore((s) => s.doc);
  const loading = useEditorStore((s) => s.loading);
  const selection = useEditorStore((s) => s.selection);
  const toggleBold = useEditorStore((s) => s.toggleBold);
  const saveDocument = useEditorStore((s) => s.saveDocument);

  return (
    <div>
      {loading && <p>로딩 중...</p>}
      {doc && <p>문서 로드됨: {doc.sections.length} 섹션</p>}
    </div>
  );
}
```

### Store 주요 메서드

- `setDocument(doc)` - HwpxDocument 설정
- `saveDocument()` - 문서 저장 (hwpx 파일 다운로드)
- `addParagraph(text)` - 문단 추가
- `addTable(sectionIndex, paragraphIndex, rows, cols)` - 표 추가
- `insertImage(data, mediaType, widthMm, heightMm)` - 이미지 삽입
- `toggleBold()`, `toggleItalic()`, `toggleUnderline()` - 스타일 토글
- `toggleSidebar()`, `setSidebarTab(tab)` - UI 상태 관리

## 의존성

### 직접 의존성

- `@ubermensch1218/hwpxcore` - HWPX 문서 처리 (같은 모노레포)
- `lucide-react` - 아이콘 라이브러리
- `zustand` - 상태 관리 라이브러리

### 개발 의존성 (필요시만)

- `react` >= 18
- `react-dom` >= 18
- `tailwindcss` >= 4
- `next` >= 16 (Next.js 사용 시)

## 라이선스

MIT License
