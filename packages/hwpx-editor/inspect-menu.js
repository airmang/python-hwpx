const { chromium } = require('playwright');

(async()=>{
  const browser = await chromium.launch({headless: true});
  const page = await browser.newPage({ viewport:{width:1366,height:900}});
  await page.goto('http://127.0.0.1:3098/editor', {waitUntil:'domcontentloaded'});
  await page.waitForTimeout(1200);
  await page.locator('button', { hasText: '표' }).nth(0).click();
  await page.waitForTimeout(300);
  const data = await page.evaluate(() => {
    const candidates = Array.from(document.querySelectorAll('button')).filter((b) => b.textContent?.trim());
    const menuRoots = candidates
      .filter((btn) => [
        '표 속성…',
        '셀 합치기',
        '줄 삽입 (아래)',
        '칸 삽입 (오른쪽)',
      ].includes(btn.textContent.trim()))
      .map((btn) => {
        const parent = btn.closest('div');
        const nearest = btn.closest('div.absolute') || parent?.closest('div');
        return {
          label: btn.textContent.trim(),
          parentTag: nearest?.tagName,
          parentClass: nearest?.className,
          rect: (() => {
            const r = btn.getBoundingClientRect();
            return {x:r.x,y:r.y,w:r.width,h:r.height};
          })(),
        };
      });
    const menuDivs = Array.from(document.querySelectorAll('div')).filter((d) => /absolute/.test(d.className) && /top-full/.test(d.className));
    return {
      menuRoots,
      countMenuDivs: menuDivs.length,
      samples: menuDivs.slice(0,10).map((d) => ({class:d.className, top:d.getBoundingClientRect().top, left:d.getBoundingClientRect().left})),
      totalButtons: document.querySelectorAll('button').length,
    };
  });
  console.log(JSON.stringify(data, null, 2));
  await browser.close();
})();
