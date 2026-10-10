// Renders brand/avatar.svg to the PNG sizes the site's icons need.
const puppeteer = require('puppeteer'); const fs = require('fs');
(async () => {
  const b = await puppeteer.launch(); const p = await b.newPage();
  const svg = fs.readFileSync('avatar.svg', 'utf8').replace('<svg ', '<svg width="100%" height="100%" ');
  for (const n of [32, 64, 180]) {
    await p.setViewport({width: n, height: n});
    await p.setContent(`<style>html,body{margin:0;width:${n}px;height:${n}px}</style>${svg}`);
    await p.screenshot({path: `icon-${n}.png`, clip: {x: 0, y: 0, width: n, height: n}});
  }
  await b.close();
})();
