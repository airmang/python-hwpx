import { chromium } from 'playwright';

const browser = await chromium.launch({headless:true});
const page = await browser.newPage({viewport:{width:1600,height:1200}});
await page.goto('http://127.0.0.1:3098/editor',{waitUntil:'domcontentloaded'});
await page.waitForTimeout(1200);
await page.locator('button[title="표 삽입"]').click();
await page.locator('button', {name:'삽입'}).click();
await page.waitForSelector('td', {state:'visible',timeout:5000});
// open table menu property
await page.locator('button', {hasText:'표'}).nth(0).click();
await page.locator('div.absolute.left-0.top-full.bg-white.border.border-gray-200.shadow-lg.rounded-b.min-w-\[220px\].py-1.z-50 >> button', { hasText:'표 속성…'}).click();
await page.waitForTimeout(400);
// locate sidebar open and section headers
const data = await page.evaluate(() => {
  const root = document.querySelector('[data-hwpx-editor-root="true"]');
  const openBtn = document.querySelector('button[title="서식 사이드바 열기"]');
  const sidebar = document.querySelector('div[class*="w-72"][class*="FormatSidebar"], .w-72');
  const secs = Array.from(document.querySelectorAll('button')).filter(b=>b.getAttribute('aria-label')==='표 크기').map(b=>b.textContent?.trim() || '');
  const buttons = Array.from(document.querySelectorAll('aside div button')).map((b)=>({t:b.textContent?.trim(),aria:b.getAttribute('aria-label')||'',title:b.getAttribute('title')||'',class:b.className,disabled:b.disabled}));
  const tabButtons = Array.from(document.querySelectorAll('aside button')).filter((b)=>['표','셀','문단','이미지','테두리'].includes(b.textContent?.trim())).map(b=>b.textContent?.trim());
  const inputs = Array.from(document.querySelectorAll('input[type="number"]')).map((i)=>({v:i.value,parent:i.parentElement?.textContent?.slice(0,80)})).slice(0,20);
  return {openBtn: !!openBtn, sidebar: !!sidebar, sections: secs, tabButtons, inputCount: inputs.length, inputs};
});
console.log(JSON.stringify(data,null,2));
await browser.close();
