# @ubermensch1218/hwpxcore

한글 워드프로세서 HWPX 문서를 읽고 편집하기 위한 TypeScript 라이브러리입니다.

[![npm version](https://img.shields.io/npm/v/@ubermensch1218/hwpxcore.svg)](https://www.npmjs.com/package/@ubermensch1218/hwpxcore)

## 설치

```bash
npm install @ubermensch1218/hwpxcore
```

## 주요 기능

- **HWPX 문서 로드/저장** - OPC 컨테이너 형식의 HWPX 파일을 메모리에 로드하고 수정 후 저장
- **문단 및 표 관리** - 섹션, 문단, 표, 셀 데이터를 조회하고 편집
- **이미지 지원** - 문서에 이미지 삽입
- **포맷 속성** - 문자(굵게, 기울임, 밑줄) 스타일 설정 및 조회
- **헤더 정보 접근** - 스타일, 글꼴, 문단 속성 등 헤더 참조 정보 파싱
- **템플릿 지원** - 내장 Skeleton.hwpx 템플릿으로 새 문서 생성

## 사용 예제

### 1. 문서 열기 및 텍스트 읽기

```typescript
import { HwpxDocument } from '@ubermensch1218/hwpxcore';

// 파일에서 읽기
const buffer = await fetch('document.hwpx').then(r => r.arrayBuffer());
const doc = await HwpxDocument.open(new Uint8Array(buffer));

// 모든 섹션의 문단 텍스트 추출
for (const section of doc.sections) {
  for (const para of section.paragraphs) {
    console.log(para.text);
  }
}
```

### 2. 새 문서 생성 및 편집

```typescript
import { HwpxDocument, loadSkeletonHwpx } from '@ubermensch1218/hwpxcore';

// Skeleton 템플릿으로 새 문서 생성 (Node.js)
const skeleton = loadSkeletonHwpx();
const doc = await HwpxDocument.open(skeleton);

// 문단 추가
doc.addParagraph('안녕하세요!');
doc.addParagraph('두 번째 문단입니다.');

// 저장 (Uint8Array 반환)
const bytes = await doc.save();
```

### 3. 표 편집

```typescript
const section = doc.sections[0];
const para = section.paragraphs[0];

// 문단에 표 추가 (2행 3열)
para.addTable(2, 3);

// 셀 텍스트 설정
const table = para.tables[0];
table.setCellText(0, 0, '항목');
table.setCellText(0, 1, '수량');
table.setCellText(0, 2, '금액');
table.setCellText(1, 0, '상품A');
table.setCellText(1, 1, '10');
table.setCellText(1, 2, '100,000');
```

### 4. 문자 스타일 설정

```typescript
// 굵게+기울임 스타일의 charPrIdRef 생성
const charPrIdRef = doc.ensureRunStyle({
  bold: true,
  italic: true,
  underline: false,
});

// 문단에 적용
const para = doc.sections[0].paragraphs[0];
para.charPrIdRef = charPrIdRef;
```

### 5. 헤더 XML 파싱

```typescript
import { parseHeaderXml, serializeXml } from '@ubermensch1218/hwpxcore';

// 헤더 요소에서 XML 추출 후 파싱
const header = doc.headers[0];
const xml = serializeXml(header.element);
const parsed = parseHeaderXml(xml);

// 스타일 정보 조회
for (const style of parsed.refList?.styles?.styles ?? []) {
  console.log(style.name, style.id);
}

// 문단 속성 조회
for (const prop of parsed.refList?.paraProperties?.properties ?? []) {
  console.log(prop.id, prop.align?.horizontal);
}
```

### 6. 이미지 삽입

```typescript
const imageData = new Uint8Array(/* 이미지 바이너리 */);

doc.addImage(imageData, {
  mediaType: 'image/png',
  widthMm: 50,
  heightMm: 30,
});
```

## API 요약

### HwpxDocument

| 메서드/속성 | 설명 |
|------------|------|
| `HwpxDocument.open(buffer)` | HWPX 파일을 로드하여 문서 객체 반환 |
| `doc.sections` | 모든 섹션 목록 (`HwpxOxmlSection[]`) |
| `doc.paragraphs` | 모든 섹션의 모든 문단 |
| `doc.headers` | 헤더 객체 목록 |
| `doc.addParagraph(text, opts?)` | 문단 추가 |
| `doc.addImage(data, opts)` | 이미지 삽입 |
| `doc.ensureRunStyle(opts)` | 문자 스타일 생성/조회 |
| `doc.charProperty(charPrIdRef)` | charPrIdRef로 RunStyle 조회 |
| `doc.save()` | 문서를 `Uint8Array`로 저장 |

### HwpxOxmlParagraph

| 메서드/속성 | 설명 |
|------------|------|
| `para.text` | 문단의 전체 텍스트 (get/set) |
| `para.runs` | 텍스트 실행 목록 (`HwpxOxmlRun[]`) |
| `para.tables` | 문단 내 표 목록 |
| `para.charPrIdRef` | 문자 속성 참조 ID |
| `para.paraPrIdRef` | 문단 속성 참조 ID |
| `para.addTable(rows, cols)` | 표 추가 |

### HwpxOxmlTable

| 메서드/속성 | 설명 |
|------------|------|
| `table.setCellText(row, col, text)` | 셀 텍스트 설정 |

## 의존성

- `@xmldom/xmldom` - XML 파싱 및 조작
- `jszip` - ZIP 파일 처리 (HWPX는 ZIP 기반)

## 라이선스

MIT License
