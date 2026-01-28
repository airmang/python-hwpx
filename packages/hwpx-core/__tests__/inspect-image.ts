import { readFileSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";
import { HwpxPackage } from "../src/package.js";
import { parseXml, childElements, serializeXml } from "../src/xml/dom.js";

const __dirname = dirname(fileURLToPath(import.meta.url));

async function main() {
  // Pass file path as CLI argument or use skeleton
  const filePath = process.argv[2] || resolve(__dirname, "..", "assets", "Skeleton.hwpx");
  const data = new Uint8Array(readFileSync(filePath));
  const pkg = await HwpxPackage.open(data);

  // 1. BinData 파트 확인
  const binParts = pkg.partNames().filter(p => p.startsWith("BinData/"));
  console.log("=== BinData parts ===");
  for (const p of binParts) {
    const d = pkg.getPart(p);
    console.log(` ${p}: ${d.byteLength} bytes`);
  }

  // 2. header.xml에서 binData 참조 확인
  const headerXml = pkg.getText("Contents/header.xml");
  const headerDoc = parseXml(headerXml);

  // binData 관련 요소 찾기
  const findAll = (node: Element, targetName: string): Element[] => {
    const results: Element[] = [];
    const walk = (el: Element) => {
      const ln = el.localName ?? el.tagName.split(":").pop() ?? "";
      if (ln === targetName) results.push(el);
      for (const child of childElements(el)) walk(child);
    };
    walk(node);
    return results;
  };

  const binItems = findAll(headerDoc.documentElement, "binItemEmbedding");
  console.log("\n=== header.xml binItemEmbedding ===");
  for (const item of binItems) {
    console.log(serializeXml(item));
  }

  // 3. section0.xml에서 pic 요소 찾기
  const secXml = pkg.getText("Contents/section0.xml");
  const secDoc = parseXml(secXml);

  const pics = findAll(secDoc.documentElement, "pic");
  console.log("\n=== section0.xml <pic> elements (first 3) ===");
  for (let i = 0; i < Math.min(3, pics.length); i++) {
    const pic = pics[i]!;
    console.log(`\n--- pic[${i}] ---`);
    console.log(serializeXml(pic).substring(0, 2000));
  }

  // 4. content.hpf에서 BinData manifest 항목 확인
  const hpfXml = pkg.getText("Contents/content.hpf");
  console.log("\n=== content.hpf (manifest) ===");
  console.log(hpfXml.substring(0, 3000));
}

main().catch(console.error);
