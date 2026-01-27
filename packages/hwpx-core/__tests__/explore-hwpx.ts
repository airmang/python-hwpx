import { readFileSync } from "fs";
import { HwpxDocument } from "../src/document.js";
import { HwpxPackage } from "../src/package.js";
import { TextExtractor } from "../src/tools/text-extractor.js";
import { ObjectFinder } from "../src/tools/object-finder.js";

async function main() {
  const data = new Uint8Array(readFileSync("/Users/jskang/Downloads/평가원 영어 양식.hwpx"));

  // 패키지 구조
  const pkg = await HwpxPackage.open(data);
  console.log("=== Parts ===");
  const parts = pkg.partNames().sort();
  for (const p of parts) console.log(" ", p);

  console.log("\n=== Sections ===", pkg.sectionPaths());
  console.log("=== Headers ===", pkg.headerPaths());
  console.log("=== MasterPages ===", pkg.masterPagePaths());

  // 문서 열기
  const doc = await HwpxDocument.open(data);
  console.log("\n=== Document Info ===");
  console.log("Sections:", doc.sectionCount);
  console.log("Paragraphs:", doc.paragraphs.length);
  console.log("Tables:", doc.tables.length);
  console.log("Memos:", doc.memos.length);

  // 텍스트 추출
  const extractor = new TextExtractor(pkg);
  const text = extractor.extractText();
  console.log("\n=== Text (first 500 chars) ===");
  console.log(text.substring(0, 500));

  // 오브젝트 탐색
  const finder = new ObjectFinder(pkg);
  const tables = finder.findTables();
  const pics = finder.findPictures();
  console.log("\n=== Objects ===");
  console.log("Tables found:", tables.length);
  console.log("Pictures found:", pics.length);

  // 표 구조
  if (doc.tables.length > 0) {
    const tbl = doc.tables[0]!;
    console.log("\n=== First Table ===");
    console.log("Rows:", tbl.rows.length);
    if (tbl.rows.length > 0) {
      console.log("Cols (row 0):", tbl.rows[0]!.cells.length);
    }
    // 셀 텍스트
    try {
      const cell00 = tbl.cell(0, 0);
      console.log("Cell(0,0) text:", JSON.stringify(cell00.text));
    } catch (e: any) {
      console.log("Cell(0,0) error:", e.message);
    }
  }

  // 저장 테스트
  const saved = await doc.save();
  console.log("\n=== Save ===");
  console.log("Saved bytes:", saved.byteLength);

  // 다시 열기
  const doc2 = await HwpxDocument.open(saved);
  console.log("Re-opened sections:", doc2.sectionCount);
  console.log("Re-opened paragraphs:", doc2.paragraphs.length);
  console.log("Re-opened tables:", doc2.tables.length);
}

main().catch(console.error);
