import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { mkdtemp, readFile, rm } from "fs/promises";
import { resolve, dirname } from "path";
import { tmpdir } from "os";
import { fileURLToPath } from "url";
import JSZip from "jszip";
import { HwpxDocument } from "../src/document.js";
import { HwpxPackage } from "../src/package.js";
import { TextExtractor } from "../src/tools/text-extractor.js";
import { __version__, resolveLibraryVersion } from "../src/version.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const SKELETON_PATH = resolve(__dirname, "..", "assets", "Skeleton.hwpx");
const skeletonBytes = new Uint8Array(readFileSync(SKELETON_PATH));

function firstLocalFileHeader(zipBytes: Uint8Array): { fileName: string; compressionMethod: number } {
  const view = new DataView(zipBytes.buffer, zipBytes.byteOffset, zipBytes.byteLength);
  const signature = view.getUint32(0, true);
  if (signature !== 0x04034b50) {
    throw new Error("invalid zip local header signature");
  }

  const compressionMethod = view.getUint16(8, true);
  const fileNameLength = view.getUint16(26, true);
  const extraFieldLength = view.getUint16(28, true);
  const fileNameStart = 30;
  const fileNameEnd = fileNameStart + fileNameLength;
  const fileName = new TextDecoder().decode(zipBytes.slice(fileNameStart, fileNameEnd));

  if (fileNameEnd + extraFieldLength > zipBytes.byteLength) {
    throw new Error("invalid zip local header lengths");
  }

  return { fileName, compressionMethod };
}

async function buildZipForOpen(parts: Record<string, string | Uint8Array>): Promise<Uint8Array> {
  const zip = new JSZip();
  for (const [name, value] of Object.entries(parts)) {
    zip.file(name, value);
  }
  return zip.generateAsync({ type: "uint8array", compression: "DEFLATE" });
}

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

  it("저장 시 mimetype 파트가 첫 엔트리이며 무압축이다", async () => {
    const pkg = await HwpxPackage.open(skeletonBytes);
    const saved = await pkg.save();
    const header = firstLocalFileHeader(saved);

    expect(header.fileName).toBe("mimetype");
    expect(header.compressionMethod).toBe(0);
  });

  it("saveToBuffer로 저장한 결과를 다시 열 수 있다", async () => {
    const doc = await HwpxDocument.open(skeletonBytes);
    doc.addParagraph("saveToBuffer 테스트");

    const saved = await doc.saveToBuffer();
    expect(saved).toBeInstanceOf(Uint8Array);
    expect(saved.byteLength).toBeGreaterThan(0);

    const reopened = await HwpxDocument.open(saved);
    expect(reopened.text).toContain("saveToBuffer 테스트");
  });

  it("saveToBlob으로도 문서를 저장하고 다시 열 수 있다", async () => {
    const doc = await HwpxDocument.open(skeletonBytes);
    doc.addParagraph("saveToBlob 테스트");

    const blob = await doc.saveToBlob();
    expect(blob.type).toBe("application/hwp+zip");

    const bytes = new Uint8Array(await blob.arrayBuffer());
    const reopened = await HwpxDocument.open(bytes);
    expect(reopened.text).toContain("saveToBlob 테스트");
  });

  it("새로 생성한 문단 직렬화에서 ns0 접두사가 생기지 않는다", async () => {
    const doc = await HwpxDocument.open(skeletonBytes);
    doc.addParagraph("namespace-prefix 테스트");

    const saved = await doc.saveToBuffer();
    const pkg = await HwpxPackage.open(saved);
    const sectionPath = pkg.sectionPaths()[0]!;
    const sectionXml = pkg.getText(sectionPath);

    expect(sectionXml).toContain("<hp:p");
    expect(sectionXml).not.toContain("<ns0:p");
  });

  it("문서 요약 표현(toJSON/toString)을 제공한다", async () => {
    const doc = await HwpxDocument.open(skeletonBytes);
    doc.addParagraph("요약 표현 테스트");

    const summary = doc.toJSON();
    expect(summary.sectionCount).toBeGreaterThan(0);
    expect(summary.paragraphCount).toBeGreaterThan(0);
    expect(summary.textPreview).toContain("요약 표현 테스트");

    const asString = doc.toString();
    expect(asString).toContain("HwpxDocument(");
    expect(asString).toContain("sections=");
  });

  it("패키지 요약 표현(toJSON/toString)을 제공한다", async () => {
    const pkg = await HwpxPackage.open(skeletonBytes);

    const summary = pkg.toJSON();
    expect(summary.partCount).toBeGreaterThan(0);
    expect(summary.hasManifest).toBe(true);

    const asString = pkg.toString();
    expect(asString).toContain("HwpxPackage(");
    expect(asString).toContain("parts=");
  });

  it("container rootfiles를 읽고 main rootfile을 선택한다", async () => {
    const pkg = await HwpxPackage.open(skeletonBytes);
    const rootfiles = pkg.rootfiles();
    const main = pkg.mainRootFile();

    expect(rootfiles.length).toBeGreaterThan(0);
    expect(main.fullPath).toBe("Contents/content.hpf");
    expect(main.mediaType).toBe("application/hwpml-package+xml");
  });

  it("container rootfile 비표준 속성명을 fallback으로 읽고 경고한다", async () => {
    const pkg = await HwpxPackage.open(skeletonBytes);
    const warnings: string[] = [];
    HwpxPackage.setWarningHandler((message) => warnings.push(message));

    try {
      pkg.setPart(
        HwpxPackage.CONTAINER_PATH,
        '<?xml version="1.0" encoding="UTF-8"?><ocf:container xmlns:ocf="urn:oasis:names:tc:opendocument:xmlns:container"><ocf:rootfiles><ocf:rootfile fullPath="Contents/content.hpf" mediaType="application/hwpml-package+xml"/></ocf:rootfiles></ocf:container>',
      );
      const main = pkg.mainRootFile();

      expect(main.fullPath).toBe("Contents/content.hpf");
      expect(warnings.some((w) => w.includes("non-standard full-path"))).toBe(true);
      expect(warnings.some((w) => w.includes("non-standard media-type"))).toBe(true);
    } finally {
      HwpxPackage.setWarningHandler(null);
    }
  });

  it("mimetype가 없는 패키지는 open에서 실패한다", async () => {
    const bytes = await buildZipForOpen({
      "META-INF/container.xml": '<?xml version="1.0" encoding="UTF-8"?><ocf:container xmlns:ocf="urn:oasis:names:tc:opendocument:xmlns:container"><ocf:rootfiles><ocf:rootfile full-path="Contents/content.hpf" media-type="application/hwpml-package+xml"/></ocf:rootfiles></ocf:container>',
      "Contents/content.hpf": '<?xml version="1.0" encoding="UTF-8"?><opf:package xmlns:opf="http://www.idpf.org/2007/opf/"></opf:package>',
    });

    await expect(HwpxPackage.open(bytes)).rejects.toThrow("mandatory mimetype");
  });

  it("manifest spine 누락 시 section fallback 경고를 전달한다", async () => {
    const pkg = await HwpxPackage.open(skeletonBytes);
    const warnings: string[] = [];

    HwpxPackage.setWarningHandler((message) => {
      warnings.push(message);
    });

    try {
      pkg.setPart(
        HwpxPackage.MANIFEST_PATH,
        '<?xml version="1.0" encoding="UTF-8"?><opf:package xmlns:opf="http://www.idpf.org/2007/opf/"><opf:manifest></opf:manifest><opf:spine></opf:spine></opf:package>',
      );

      const sections = pkg.sectionPaths();
      expect(sections.length).toBeGreaterThan(0);
      expect(warnings.some((w) => w.includes("sectionPaths fallback"))).toBe(true);
    } finally {
      HwpxPackage.setWarningHandler(null);
    }
  });

  it("누락 파트 접근 시 경고를 전달한다", async () => {
    const pkg = await HwpxPackage.open(skeletonBytes);
    const warnings: string[] = [];

    HwpxPackage.setWarningHandler((message) => {
      warnings.push(message);
    });

    try {
      expect(() => pkg.getPart("missing/part.xml")).toThrow();
      expect(warnings.some((w) => w.includes("missing part: missing/part.xml"))).toBe(true);
    } finally {
      HwpxPackage.setWarningHandler(null);
    }
  });

  it("라이브러리 버전 해석이 메타데이터 값을 우선 사용한다", () => {
    const resolved = resolveLibraryVersion({
      metadataVersion: "9.9.9",
      envVersion: "1.2.3",
      injectedVersion: "4.5.6",
    });

    expect(resolved).toBe("9.9.9");
  });

  it("라이브러리 버전 해석이 입력값이 없으면 fallback을 반환한다", () => {
    const resolved = resolveLibraryVersion({
      metadataVersion: "",
      envVersion: "",
      injectedVersion: "",
    });

    expect(resolved).toBe("0+unknown");
  });

  it("공개 버전 문자열이 비어 있지 않다", () => {
    expect(__version__.trim().length).toBeGreaterThan(0);
  });

  it("문서 버전 메타데이터를 노출한다", async () => {
    const doc = await HwpxDocument.open(skeletonBytes);
    const info = doc.documentVersionInfo;

    expect(info).not.toBeNull();
    expect(info?.path).toBe("version.xml");
    expect(info?.major).toBe(5);
    expect(info?.minor).toBe(1);
    expect(info?.application).toContain("Hancom Office");
  });

  it("문서 close 이후 저장을 막는다", async () => {
    const doc = await HwpxDocument.open(skeletonBytes);
    doc.close();

    expect(doc.closed).toBe(true);
    await expect(doc.save()).rejects.toThrow("HwpxDocument is closed");
  });

  it("saveToPath로 파일을 저장할 수 있다", async () => {
    const doc = await HwpxDocument.open(skeletonBytes);
    doc.addParagraph("saveToPath 테스트");

    const dir = await mkdtemp(resolve(tmpdir(), "hwpx-core-"));
    const outPath = resolve(dir, "saved.hwpx");

    try {
      await doc.saveToPath(outPath);
      const bytes = new Uint8Array(await readFile(outPath));
      const reopened = await HwpxDocument.open(bytes);
      expect(reopened.text).toContain("saveToPath 테스트");
    } finally {
      await rm(dir, { recursive: true, force: true });
    }
  });

  it("패키지 close 이후 접근을 막는다", async () => {
    const pkg = await HwpxPackage.open(skeletonBytes);
    pkg.close();

    expect(pkg.closed).toBe(true);
    expect(() => pkg.partNames()).toThrow("HwpxPackage is closed");
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
