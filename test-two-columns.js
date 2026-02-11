/**
 * 2단 설정 테스트
 *
 * 이 코드는 긴 텍스트를 2단으로 설정하는 방법을 보여줍니다.
 * secPr이 이제 마지막 paragraph에 생성되므로 한컴오피스에서
 * 올바르게 2단 레이아웃이 표시됩니다.
 */

import { HwpxDocument } from "./packages/hwpx-core/dist/index.js";
import { readFileSync, writeFileSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const SKELETON_PATH = resolve(__dirname, "packages", "hwpx-core", "assets", "Skeleton.hwpx");
const skeletonBytes = new Uint8Array(readFileSync(SKELETON_PATH));

async function testTwoColumns() {
  // 스켈레톤 문서 로드
  const doc = await HwpxDocument.open(skeletonBytes);

  // 첫 번째 섹션 가져오기
  const section = doc.sections[0];

  // 엄청나게 긴 텍스트 생성
  const longText = `
    Lorem ipsum dolor sit amet, consectetur adipiscing elit.
    Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.
    Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris.
    Duis aute irure dolor in reprehenderit in voluptate velit esse cillum.
    Excepteur sint occaecat cupidatat non proident sunt in culpa qui.
  `.repeat(50); // 50번 반복 = 엄청나게 긴 텍스트

  // 텍스트를 여러 paragraph로 나누어 추가
  const paragraphs = longText.split('\n').filter(line => line.trim());
  for (const text of paragraphs) {
    const para = doc.addParagraph();
    para.addRun(text.trim());
  }

  // 2단 설정 (핵심 부분!)
  section.properties.setColumnLayout({
    type: "NEWSPAPER",  // 신문 스타일 단
    layout: "LEFT",     // 왼쪽부터 균형
    colCount: 2,        // 2단
    sameGap: 10000,     // 단 간격 (HWP 단위: 1/100 mm, 10000 = 10cm)
  });

  // 저장
  const saved = await doc.save();
  writeFileSync(resolve(__dirname, "test-two-columns.hwpx"), Buffer.from(saved));

  console.log("2단 설정된 문서가 생성되었습니다!");
  console.log("섹션 속성:", section.properties.columnLayout);
  console.log("저장된 파일: test-two-columns.hwpx");

  return doc;
}

// 실행
testTwoColumns().catch(console.error);
