import { readFileSync, writeFileSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";
import { HwpxDocument } from "../src/document.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const skeleton = new Uint8Array(readFileSync(resolve(__dirname, "..", "assets", "Skeleton.hwpx")));

async function main() {
  const doc = await HwpxDocument.open(skeleton);

  doc.addParagraph("안녕하세요! HWPX 테스트 문서입니다.");
  doc.addParagraph("TypeScript로 생성된 문서입니다.");
  doc.addParagraph("");
  doc.addParagraph("정상적으로 저장되었습니다.");

  const saved = await doc.save();
  const outPath = "/Users/jskang/Desktop/test-output.hwpx";
  writeFileSync(outPath, saved);
  console.log(`저장 완료: ${saved.byteLength} bytes → ${outPath}`);
}

main().catch(console.error);
