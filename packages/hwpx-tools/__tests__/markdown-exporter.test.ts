import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { HwpxDocument, HwpxPackage } from "@ubermensch1218/hwpxcore";
import { exportToMarkdown, exportToMarkdownBundle } from "../src/exporters/markdown.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const SKELETON_PATH = resolve(__dirname, "..", "..", "hwpx-core", "assets", "Skeleton.hwpx");
const skeletonBytes = new Uint8Array(readFileSync(SKELETON_PATH));

// 1x1 red pixel PNG
const RED_PIXEL_PNG = new Uint8Array([
  0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a,
  0x00, 0x00, 0x00, 0x0d, 0x49, 0x48, 0x44, 0x52,
  0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
  0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,
  0xde, 0x00, 0x00, 0x00, 0x0c, 0x49, 0x44, 0x41,
  0x54, 0x08, 0xd7, 0x63, 0xf8, 0xcf, 0xc0, 0x00,
  0x00, 0x00, 0x02, 0x00, 0x01, 0xe2, 0x21, 0xbc,
  0x33, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4e,
  0x44, 0xae, 0x42, 0x60, 0x82,
]);

async function createSamplePackage() {
  const doc = await HwpxDocument.open(skeletonBytes);
  doc.addParagraph("  첫 문단   텍스트  ");

  const tablePara = doc.addParagraph("");
  const table = tablePara.addTable(2, 2);
  table.setCellText(0, 0, "항목");
  table.setCellText(0, 1, "값");
  table.setCellText(1, 0, "A");
  table.setCellText(1, 1, "10");

  doc.addImage(RED_PIXEL_PNG, {
    mediaType: "image/png",
    widthMm: 30,
    heightMm: 20,
  });

  const saved = await doc.save();
  return HwpxPackage.open(saved);
}

describe("markdown exporter", () => {
  it("token-efficient placeholder mode keeps image manifest and compact markdown", async () => {
    const pkg = await createSamplePackage();
    const result = exportToMarkdownBundle(pkg, {
      tokenEfficient: true,
      imageMode: "placeholder",
    });

    expect(result.markdown).toContain("[IMAGE:1");
    expect(result.markdown).toContain("| 항목 | 값 |");
    expect(result.markdown).not.toContain("binaryItemIDRef");
    expect(result.images).toHaveLength(1);
    expect(result.images[0]?.href).toMatch(/^BinData\/image\d+\.png$/);
    expect(result.stats.images).toBe(1);
  });

  it("markdown image mode renders markdown image links", async () => {
    const pkg = await createSamplePackage();
    const result = exportToMarkdownBundle(pkg, {
      imageMode: "markdown",
      imageBasePath: "assets/images",
    });

    expect(result.markdown).toContain("![image 1](assets/images/image");
    expect(result.images[0]?.markdownPath).toMatch(/^assets\/images\/image\d+\.png$/);
  });

  it("omit image mode removes image token but keeps manifest entries", async () => {
    const pkg = await createSamplePackage();
    const result = exportToMarkdownBundle(pkg, {
      tokenEfficient: true,
      imageMode: "omit",
    });

    expect(result.markdown).not.toContain("[IMAGE:");
    expect(result.markdown).not.toContain("![image");
    expect(result.images).toHaveLength(1);
  });

  it("exportToMarkdown returns markdown string from bundle pipeline", async () => {
    const pkg = await createSamplePackage();
    const result = exportToMarkdownBundle(pkg, {
      tokenEfficient: true,
      imageMode: "placeholder",
    });
    const markdown = exportToMarkdown(pkg, {
      tokenEfficient: true,
      imageMode: "placeholder",
    });

    expect(markdown).toBe(result.markdown);
  });
});
