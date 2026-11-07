const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const url = process.argv[2], out = process.argv[3], w = +process.argv[4] || 390, h = +process.argv[5] || 844;
  const p = await b.newPage({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
  const logs = [];
  p.on('console', m => logs.push(m.type() + ': ' + m.text()));
  p.on('pageerror', e => logs.push('ERR ' + e.message));
  await p.goto(url, { waitUntil: 'networkidle' });
  await p.waitForTimeout(2500);
  await p.screenshot({ path: out });
  console.log(logs.join('\n') || 'no console output');
  await b.close();
})();
