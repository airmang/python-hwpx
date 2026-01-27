import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";
import { HwpxDocument } from "../src/document.js";
import { HwpxPackage } from "../src/package.js";
import { TextExtractor } from "../src/tools/text-extractor.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const SKELETON_PATH = resolve(__dirname, "..", "assets", "Skeleton.hwpx");
const skeletonBytes = new Uint8Array(readFileSync(SKELETON_PATH));

describe("HWPX roundtrip", () => {
  it("Skeleton.hwpx를 열고 다시 저장할 수 있다", async () => {
    const doc = await HwpxDocument.open(skeletonBytes);
    expect(doc.sections.length).toBeGreaterThan(0);

    const saved = await doc.save();
    expect(saved).toBeInstanceOf(Uint8Array);
    expect(saved.byteLength).toBeGreaterThan(0);

    // 다시 열기
    const doc2 = await HwpxDocument.open(saved);
    expect(doc2.sections.length).toBe(doc.sections.length);
  });

  it("텍스트를 추가하고 저장 후 다시 읽을 수 있다", async () => {
    const doc = await HwpxDocument.open(skeletonBytes);
    const testText = "안녕하세요 HWPX 테스트입니다";

    // 문단 추가
    doc.addParagraph(testText);

    // 저장
    const saved = await doc.save();
    expect(saved.byteLength).toBeGreaterThan(0);

    // 다시 열어서 텍스트 확인
    const doc2 = await HwpxDocument.open(saved);
    const allText = doc2.text;
    expect(allText).toContain(testText);
  });

  it("텍스트 치환 후 저장/재열기가 가능하다", async () => {
    const doc = await HwpxDocument.open(skeletonBytes);
    doc.addParagraph("Hello World");

    const saved1 = await doc.save();
    const doc2 = await HwpxDocument.open(saved1);

    const replaced = doc2.replaceText("Hello", "Goodbye");
    expect(replaced).toBeGreaterThan(0);

    const saved2 = await doc2.save();
    const doc3 = await HwpxDocument.open(saved2);
    expect(doc3.text).toContain("Goodbye World");
    expect(doc3.text).not.toContain("Hello World");
  });

  it("패키지 레벨에서 파트를 읽고 쓸 수 있다", async () => {
    const pkg = await HwpxPackage.open(skeletonBytes);

    expect(pkg.sectionPaths().length).toBeGreaterThan(0);
    expect(pkg.headerPaths().length).toBeGreaterThan(0);

    // XML 파트 읽기
    const sectionPath = pkg.sectionPaths()[0]!;
    const sectionXml = pkg.getXml(sectionPath);
    expect(sectionXml).toBeDefined();
    expect(sectionXml.tagName).toBeDefined();

    // 저장
    const saved = await pkg.save();
    expect(saved.byteLength).toBeGreaterThan(0);
  });

  it("TextExtractor로 텍스트를 추출할 수 있다", async () => {
    const doc = await HwpxDocument.open(skeletonBytes);
    doc.addParagraph("추출 테스트 문장");

    const saved = await doc.save();
    const pkg = await HwpxPackage.open(saved);
    const extractor = new TextExtractor(pkg);

    const sections = extractor.sections();
    expect(sections.length).toBeGreaterThan(0);

    const text = extractor.extractText();
    expect(text).toContain("추출 테스트 문장");
  });
});
