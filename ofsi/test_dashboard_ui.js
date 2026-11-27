// Test UI du tableau de bord (Chromium headless via Playwright) : bannière, notifications, visualiseur de parties. Usage : node ofsi/test_dashboard_ui.js [port]
const { chromium } = require('playwright'); const port = process.argv[2] || 8798; let ok = 0, n = 0;
const check = (name, c) => { n++; if (c) ok++; console.log((c ? 'PASS ' : 'FAIL ') + name); };
(async () => {
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1200, height: 1500 } }); const errs = []; p.on('pageerror', e => errs.push(String(e))); p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  await p.goto(`http://127.0.0.1:${port}/`); await p.waitForTimeout(2500);
  const banner = (await p.textContent('#banner')).trim(); check('banniere affichee (' + banner + ')', /ENTRAÎNEMENT EN COURS|VALIDATION PARTIELLE|VALIDÉE/.test(banner));
  check('la banniere n\'affiche JAMAIS « validee » sans docs/validation.json', !/VALIDÉE/.test(banner) || false);
  const opts = await p.$$eval('#rp option', o => o.map(x => x.textContent)); check('rejeux listes (' + opts.join(',') + ')', opts.length >= 1);
  const info0 = await p.textContent('#rpInfo'); check('1re image chargee', /image 1\/\d+/.test(info0));
  const colors = async () => p.evaluate(() => { const c = document.getElementById('rpCanvas'), d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data, s = new Set(); for (let i = 0; i < d.length; i += 4 * 97) s.add(d[i] + ',' + d[i + 1] + ',' + d[i + 2]); return s.size; });
  const c0 = await colors(); await p.click('#rpPlay'); await p.waitForTimeout(2500); const info1 = await p.textContent('#rpInfo'); const c1 = await colors();
  check('la lecture avance (' + info0.slice(0, 22) + ' -> ' + info1.slice(0, 22) + ')', info1 !== info0);
  check('le canvas n\'est pas vide (couleurs distinctes: ' + c1 + ')', c1 >= 3);
  await p.fill('#rpSlider', '0').catch(() => {}); await p.evaluate(() => { const s = document.getElementById('rpSlider'); s.value = s.max; s.dispatchEvent(new Event('input')); }); await p.waitForTimeout(300);
  const infoEnd = await p.textContent('#rpInfo'); check('curseur a la fin : issue affichee', /issue : (win|dead|timeout|loss_winner_other)/.test(infoEnd) && /image (\d+)\/\1 /.test(infoEnd));
  check('aucune erreur JavaScript (' + errs.length + ')', errs.length === 0);
  await p.screenshot({ path: process.env.SHOT || '/tmp/claude-0/dashboard_ui.png', fullPage: true }); await b.close(); console.log(`${ok}/${n} PASS`); process.exit(ok === n ? 0 : 1);
})();
