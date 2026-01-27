import { describe, it, expect } from "vitest";
import { readFileSync, writeFileSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";
import { HwpxDocument } from "../src/document.js";
import { HwpxPackage } from "../src/package.js";
import { TextExtractor } from "../src/tools/text-extractor.js";
import { ObjectFinder } from "../src/tools/object-finder.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const SKELETON_PATH = resolve(__dirname, "..", "assets", "Skeleton.hwpx");
const skeletonBytes = new Uint8Array(readFileSync(SKELETON_PATH));

const SAMPLE_PATH = "/Users/jskang/Downloads/평가원 영어 양식.hwpx";
let sampleBytes: Uint8Array | null = null;
try {
  sampleBytes = new Uint8Array(readFileSync(SAMPLE_PATH));
} catch {
  // sample file not available
}

// ── 표 (Table) ────────────────────────────────────────────────────────

describe("표 생성 및 편집", () => {
  it("빈 문서에 3x3 표를 추가할 수 있다", async () => {
    const doc = await HwpxDocument.open(skeletonBytes);
    const borderFillId = doc.ensureBasicBorderFill();
    const para = doc.addParagraph();

    const table = para.addTable(3, 3, { borderFillIdRef: borderFillId });
    expect(table).toBeDefined();
    expect(table.rows.length).toBe(3);
    expect(table.rows[0]!.cells.length).toBe(3);
  });

  it("표 셀에 텍스트를 입력할 수 있다", async () => {
    const doc = await HwpxDocument.open(skeletonBytes);
    const borderFillId = doc.ensureBasicBorderFill();
    const para = doc.addParagraph();
    const table = para.addTable(2, 2, { borderFillIdRef: borderFillId });

    table.setCellText(0, 0, "이름");
    table.setCellText(0, 1, "점수");
    table.setCellText(1, 0, "홍길동");
    table.setCellText(1, 1, "95");

    expect(table.cell(0, 0).text).toBe("이름");
    expect(table.cell(0, 1).text).toBe("점수");
    expect(table.cell(1, 0).text).toBe("홍길동");
    expect(table.cell(1, 1).text).toBe("95");
  });

  it("표가 포함된 문서를 저장 후 다시 열 수 있다", async () => {
    const doc = await HwpxDocument.open(skeletonBytes);
    const borderFillId = doc.ensureBasicBorderFill();
    const para = doc.addParagraph();
    const table = para.addTable(2, 3, { borderFillIdRef: borderFillId });

    table.setCellText(0, 0, "번호");
    table.setCellText(0, 1, "제목");
    table.setCellText(0, 2, "내용");
    table.setCellText(1, 0, "1");
    table.setCellText(1, 1, "테스트");
    table.setCellText(1, 2, "HWPX 표 테스트");

    const saved = await doc.save();
    const doc2 = await HwpxDocument.open(saved);

    expect(doc2.tables.length).toBeGreaterThanOrEqual(1);
    const tbl2 = doc2.tables[doc2.tables.length - 1]!;
    expect(tbl2.rows.length).toBe(2);
    expect(tbl2.cell(1, 2).text).toBe("HWPX 표 테스트");
  });
});

// ── 스타일 (Style) ─────────────────────────────────────────────────────

describe("스타일 지정", () => {
  it("볼드 스타일을 생성할 수 있다", async () => {
    const doc = await HwpxDocument.open(skeletonBytes);
    const boldId = doc.ensureRunStyle({ bold: true });
    expect(boldId).toBeTruthy();
    expect(typeof boldId).toBe("string");
  });

  it("이탤릭 스타일을 생성할 수 있다", async () => {
    const doc = await HwpxDocument.open(skeletonBytes);
    const italicId = doc.ensureRunStyle({ italic: true });
    expect(italicId).toBeTruthy();
  });

  it("밑줄 스타일을 생성할 수 있다", async () => {
    const doc = await HwpxDocument.open(skeletonBytes);
    const underlineId = doc.ensureRunStyle({ underline: true });
    expect(underlineId).toBeTruthy();
  });

  it("볼드+이탤릭 복합 스타일을 생성할 수 있다", async () => {
    const doc = await HwpxDocument.open(skeletonBytes);
    const boldItalicId = doc.ensureRunStyle({ bold: true, italic: true });
    expect(boldItalicId).toBeTruthy();
  });

  it("스타일이 적용된 런을 추가할 수 있다", async () => {
    const doc = await HwpxDocument.open(skeletonBytes);
    const boldId = doc.ensureRunStyle({ bold: true });

    const para = doc.addParagraph();
    const run = para.addRun("볼드 텍스트", { charPrIdRef: boldId });

    expect(run.text).toBe("볼드 텍스트");
    expect(run.charPrIdRef).toBe(boldId);
  });

  it("같은 스타일을 두 번 요청하면 같은 ID가 반환된다", async () => {
    const doc = await HwpxDocument.open(skeletonBytes);
    const id1 = doc.ensureRunStyle({ bold: true });
    const id2 = doc.ensureRunStyle({ bold: true });
    expect(id1).toBe(id2);
  });
});

// ── 텍스트 치환 ────────────────────────────────────────────────────────

describe("텍스트 치환", () => {
  it("단순 텍스트 치환", async () => {
    const doc = await HwpxDocument.open(skeletonBytes);
    doc.addParagraph("Hello World");
    doc.addParagraph("Hello TypeScript");

    const count = doc.replaceText("Hello", "안녕");
    expect(count).toBe(2);
    expect(doc.text).toContain("안녕 World");
    expect(doc.text).toContain("안녕 TypeScript");
  });

  it("횟수 제한 치환", async () => {
    const doc = await HwpxDocument.open(skeletonBytes);
    doc.addParagraph("AAA");
    doc.addParagraph("AAA");
    doc.addParagraph("AAA");

    const count = doc.replaceText("AAA", "BBB", 2);
    expect(count).toBe(2);

    const lines = doc.text.split("\n").filter(l => l === "BBB" || l === "AAA");
    const bCount = lines.filter(l => l === "BBB").length;
    const aCount = lines.filter(l => l === "AAA").length;
    expect(bCount).toBe(2);
    expect(aCount).toBe(1);
  });

  it("치환 후 저장/재열기", async () => {
    const doc = await HwpxDocument.open(skeletonBytes);
    doc.addParagraph("원본 텍스트입니다.");
    doc.replaceText("원본", "수정된");

    const saved = await doc.save();
    const doc2 = await HwpxDocument.open(saved);
    expect(doc2.text).toContain("수정된 텍스트입니다.");
  });
});

// ── 패키지 레벨 ────────────────────────────────────────────────────────

describe("패키지 레벨 조작", () => {
  it("파트를 추가/수정할 수 있다", async () => {
    const pkg = await HwpxPackage.open(skeletonBytes);
    pkg.setPart("custom/data.txt", "Hello custom part");
    expect(pkg.hasPart("custom/data.txt")).toBe(true);
    expect(pkg.getText("custom/data.txt")).toBe("Hello custom part");

    const saved = await pkg.save();
    const pkg2 = await HwpxPackage.open(saved);
    expect(pkg2.hasPart("custom/data.txt")).toBe(true);
    expect(pkg2.getText("custom/data.txt")).toBe("Hello custom part");
  });
});

// ── TextExtractor / ObjectFinder ────────────────────────────────────

describe("도구 (Tools)", () => {
  it("TextExtractor: 추가한 텍스트를 추출할 수 있다", async () => {
    const doc = await HwpxDocument.open(skeletonBytes);
    doc.addParagraph("첫 번째 문단");
    doc.addParagraph("두 번째 문단");

    const saved = await doc.save();
    const pkg = await HwpxPackage.open(saved);
    const extractor = new TextExtractor(pkg);

    const text = extractor.extractText();
    expect(text).toContain("첫 번째 문단");
    expect(text).toContain("두 번째 문단");

    const paragraphs = extractor.extractParagraphs();
    expect(paragraphs.length).toBeGreaterThanOrEqual(2);
  });

  it("ObjectFinder: 표를 찾을 수 있다", async () => {
    const doc = await HwpxDocument.open(skeletonBytes);
    const borderFillId = doc.ensureBasicBorderFill();
    const para = doc.addParagraph();
    para.addTable(2, 2, { borderFillIdRef: borderFillId });

    const saved = await doc.save();
    const pkg = await HwpxPackage.open(saved);
    const finder = new ObjectFinder(pkg);

    const tables = finder.findTables();
    expect(tables.length).toBeGreaterThanOrEqual(1);
  });
});

// ── 평가원 양식 라운드트립 ─────────────────────────────────────────────

describe.skipIf(!sampleBytes)("평가원 영어 양식 라운드트립", () => {
  it("열고 저장 후 다시 열 수 있다", async () => {
    const doc = await HwpxDocument.open(sampleBytes!);
    expect(doc.sectionCount).toBe(1);
    expect(doc.paragraphs.length).toBe(318);
    expect(doc.tables.length).toBe(18);

    const saved = await doc.save();
    expect(saved.byteLength).toBeGreaterThan(0);

    const doc2 = await HwpxDocument.open(saved);
    expect(doc2.sectionCount).toBe(1);
    expect(doc2.paragraphs.length).toBe(318);
    expect(doc2.tables.length).toBe(18);
  });

  it("텍스트를 추출할 수 있다", async () => {
    const pkg = await HwpxPackage.open(sampleBytes!);
    const extractor = new TextExtractor(pkg);
    const text = extractor.extractText();

    expect(text).toContain("다음을 듣고");
    expect(text.length).toBeGreaterThan(1000);
  });

  it("표와 그림을 찾을 수 있다", async () => {
    const pkg = await HwpxPackage.open(sampleBytes!);
    const finder = new ObjectFinder(pkg);

    expect(finder.findTables().length).toBeGreaterThan(0);
    expect(finder.findPictures().length).toBeGreaterThan(0);
  });

  it("이미지 바이너리가 포함되어 있다", async () => {
    const pkg = await HwpxPackage.open(sampleBytes!);
    const parts = pkg.partNames().filter(p => p.startsWith("BinData/"));
    expect(parts.length).toBeGreaterThan(0);

    // 이미지 데이터가 실제로 있는지 확인
    const imgData = pkg.getPart(parts[0]!);
    expect(imgData.byteLength).toBeGreaterThan(100);
  });

  it("저장 후 한/글에서 열 수 있는 파일을 생성한다", async () => {
    const doc = await HwpxDocument.open(sampleBytes!);

    // 텍스트 치환
    doc.replaceText("다음을 듣고", "[수정됨] 다음을 듣고");

    const saved = await doc.save();
    writeFileSync("/Users/jskang/Desktop/평가원-수정본.hwpx", saved);
    console.log(`평가원 수정본 저장: ${saved.byteLength} bytes`);

    // 재열기 검증
    const doc2 = await HwpxDocument.open(saved);
    expect(doc2.text).toContain("[수정됨] 다음을 듣고");
    expect(doc2.tables.length).toBe(18);
    expect(doc2.paragraphs.length).toBe(318);
  });
});
