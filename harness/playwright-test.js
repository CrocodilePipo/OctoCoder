const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  
  await page.goto('https://example.com');
  
  // 获取页面文本内容
  const pageContent = await page.evaluate(() => {
    return document.body.innerText;
  });
  
  console.log('=== Page Content ===');
  console.log(pageContent);
  
  // 截取页面快照
  const screenshot = await page.screenshot({ fullPage: true });
  console.log('\n=== Screenshot taken ===');
  console.log('Screenshot size:', screenshot.length, 'bytes');
  
  // 获取页面结构信息
  const pageStructure = await page.evaluate(() => {
    const elements = [];
    const traverse = (element, depth = 0) => {
      if (element.tagName && depth < 10) {
        const text = element.textContent?.trim().substring(0, 50);
        if (text) {
          elements.push('  '.repeat(depth) + `${element.tagName}: ${text}`);
        }
        for (const child of element.children) {
          traverse(child, depth + 1);
        }
      }
    };
    traverse(document.body);
    return elements;
  });
  
  console.log('\n=== Page Structure ===');
  console.log(pageStructure.join('\n'));
  
  await browser.close();
})();