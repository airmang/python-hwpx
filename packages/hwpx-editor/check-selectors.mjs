import { chromium } from 'playwright';

const browser = await chromium.launch({headless:true});
const page = await browser.newPage({ viewport:{width:1440,height:960} });
await page.goto('http://127.0.0.1:3098/editor', { waitUntil:'domcontentloaded' });
await page.waitForTimeout(800);
const labels = await page.evaluate(() => {
  const names=['표', '표 삽입', '표 삽입 (3x3)', '표 속성…'];
  const out={};
  names.forEach((n)=>{
    out[n] = {
      byTitle: Array.from(document.querySelectorAll('button')).filter(b=>b.getAttribute && b.getAttribute('title')?.trim()===n).length,
      byNameExact: Array.from(document.querySelectorAll('button')).filter(b=>b.textContent?.trim()===n).length,
    };
  });
  const titleButton = Array.from(document.querySelectorAll('button')).filter(b=>b.getAttribute('title')?.includes('표') && b.textContent?.trim());
  return {out, tableInsertTitle: titleButton.map(b=>({text:b.textContent?.trim(),title:b.getAttribute('title'),rect:b.getBoundingClientRect()})), totalButtons: document.querySelectorAll('button').length};
});
console.log(JSON.stringify(labels,null,2));
await browser.close();
