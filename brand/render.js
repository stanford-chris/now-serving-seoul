const puppeteer = require('puppeteer'); const fs = require('fs'); const path = require('path');
(async () => {
  const b = await puppeteer.launch(); const p = await b.newPage();
  const files = process.argv.slice(2);
  for (const f of files) {
    await p.setViewport({width: 1000, height: 1000});
    await p.setContent(`<style>body{margin:0}</style>${fs.readFileSync(f,'utf8')}`);
    await p.screenshot({path: f.replace('.svg','.png'), clip:{x:0,y:0,width:1000,height:1000}});
  }
  const cells = files.map(f => { const s = fs.readFileSync(f,'utf8').replace('<svg ','<svg width="100%" height="100%" ');
    return `<div class="c"><div class="big">${s}</div><div class="sm">${s}</div><div class="sm dark">${s}</div><p>${path.basename(f,'.svg')}</p></div>`; }).join('');
  await p.setViewport({width: 1200, height: 520});
  await p.setContent(`<style>body{margin:0;padding:20px;font:18px system-ui;display:flex;gap:30px;background:#fff}
   .big{width:320px;height:320px;border-radius:50%;overflow:hidden}.sm{width:44px;height:44px;border-radius:50%;overflow:hidden;display:inline-block;margin:14px 10px 0 0}
   .dark{outline:20px solid #161e27;margin-left:20px}p{margin:8px 0}</style>${cells}`);
  await p.screenshot({path: 'preview.png'}); await b.close();
})();
