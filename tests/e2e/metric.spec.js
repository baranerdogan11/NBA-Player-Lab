// Units: heights and shot distances read in metric (cm, m) or imperial (feet, inches) units. With no pick the language
// decides (metric in Turkish, imperial in English); the header's units button picks one, kept between visits and across a
// change of language. Every value is worked out here from the files with the site's one rounding rule, rounded once from
// the exact totals (never from the rounded feet).
/* global get */
import {test, expect} from '@playwright/test';
import {DESKTOP, PHONE, prepare, settled, go, noSidewaysScroll} from './site.js';

const half = (n, d, k = 1) => Math.floor((2 * n * 10 ** k + d) / (2 * d));
const dec = (q, lang) => { const s = (q / 10).toFixed(1); return lang === 'tr' ? s.replace('.', ',') : s; };
const inches = h => { const m = /^(\d+)\D+(\d+)/.exec(h || ''); return m ? 12 * +m[1] + +m[2] : null; };
const BANDS = {
  ft: {en: ['0-3 ft', '3-10 ft', '10-16 ft', '16 ft to the arc', 'Arc to 27 ft', '27-30 ft', '30+ ft'], tr: ['0-3 fit', '3-10 fit', '10-16 fit', '16 fit - üçlük çizgisi', 'Çizgi - 27 fit', '27-30 fit', '30+ fit']},
  m: {en: ['0-0.9 m', '0.9-3.0 m', '3.0-4.9 m', '4.9 m to the arc', 'Arc to 8.2 m', '8.2-9.1 m', '9.1+ m'], tr: ['0-0,9 m', '0,9-3,0 m', '3,0-4,9 m', '4,9 m - üçlük çizgisi', 'Çizgi - 8,2 m', '8,2-9,1 m', '9,1+ m']},
};

// the Player page of a BOS player with a roster height, his shot rows for the season, and the club's height on the floor
async function facts(page) {
  return page.evaluate(async () => {
    const club = await get('BOS.json'), shots = await get('shots/BOS.json'), pid = document.querySelector('#player').value;
    const p = club.players.find(x => x.pid === pid);
    const tall = {};
    for (const x of club.players) { const m = /^(\d+)\D+(\d+)/.exec(x.height || ''); if (m) tall[x.pid] = 12 * +m[1] + +m[2]; }
    let hin = 0, hsec = 0;
    for (const g of (await get('games.json')).games.filter(g => g.hs != null && (g.home === 'BOS' || g.away === 'BOS'))) {
      for (const x of (await get(`games/${g.gid}.json`)).box.BOS) if (tall[x.pid] != null) { hin += tall[x.pid] * x.sec; hsec += x.sec; }
    }
    return {pid, height: p.height, rows: shots.players[pid] || [], hin, hsec};
  });
}

async function check(page, lang, metric, what) {
  await go(page, '#BOS', () => document.querySelector('#hero [data-k="height"]') && document.querySelectorAll('#sc-dist tr[data-band]').length === 7);
  await expect(page.locator('#units'), `${what}: the button`).toHaveAttribute('aria-pressed', String(metric));
  await expect(page.locator('#units')).toHaveText(metric ? 'M' : 'FT');
  const f = await facts(page);
  const h = inches(f.height);
  expect(h, 'the fixture player has a roster height').not.toBeNull();
  await expect(page.locator('#hero [data-k="height"] b'), `${what}: height`).toHaveText(metric ? `${half(254 * h, 100, 0)} cm` : f.height);
  expect(await page.$$eval('#sc-dist tr[data-band] td.l', tds => tds.map(td => td.textContent)), `${what}: bands`).toEqual(BANDS[metric ? 'm' : 'ft'][lang]);
  const sum = f.rows.reduce((a, r) => a + r[6], 0), n = f.rows.length;
  const unit = metric ? 'm' : lang === 'tr' ? 'fit' : 'ft';
  await expect(page.locator('#sc-avg'), `${what}: average distance`).toHaveText(`${dec(metric ? half(3048 * sum, 100000 * n) : half(sum, 10 * n), lang)} ${unit}`);
  await go(page, '#team/BOS', () => document.querySelector('#tm-style [data-k="size"] .v'));
  const size = metric ? `${dec(half(254 * f.hin, 100 * f.hsec), lang)} cm` : (() => { const q = half(f.hin, f.hsec); return `${Math.floor(q / 120)}'${dec(q % 120, lang)}"`; })();
  await expect(page.locator('#tm-style [data-k="size"] .v'), `${what}: height on the floor`).toHaveText(size);
  await go(page, '#glossary/dist', () => document.querySelector('#gl-dist dd'));
  await expect(page.locator('#gl-dist dd span'), `${what}: glossary`).toContainText(metric ? 'metre' : lang === 'tr' ? 'fit' : 'feet');
}

for (const [name, use, lang, theme] of [['desktop', DESKTOP, 'en', 'light'], ['phone', PHONE, 'tr', 'dark']]) {
  test.describe(`units (${name}, ${lang})`, () => {
    test.use(use);
    test('the language picks the units until the reader does, and the pick is kept', async ({page}, info) => {
      const problems = await prepare(page, {lang, theme});
      await page.goto('./?l#BOS');
      await settled(page);
      const metric = lang === 'tr';
      await check(page, lang, metric, 'by language');
      await go(page, '#BOS', () => document.querySelector('#hero [data-k="height"]'));
      await page.evaluate(() => scrollTo(0, 0));
      await page.screenshot({path: info.outputPath(`hero-${name}-${lang}-${metric ? 'metric' : 'imperial'}.png`)});
      await noSidewaysScroll(page, 'the header with the units button');

      await page.click('#units');
      await page.waitForFunction(m => document.querySelector('#units').getAttribute('aria-pressed') === String(m), !metric);
      expect(await page.evaluate(() => localStorage.getItem('pl-units'))).toBe(metric ? 'imperial' : 'metric');
      await check(page, lang, !metric, 'picked');
      await go(page, '#BOS', () => document.querySelectorAll('#sc-dist tr[data-band]').length === 7);
      await page.click('#sc > summary');
      await page.locator('#sc-dist').scrollIntoViewIfNeeded();
      await page.screenshot({path: info.outputPath(`distance-${name}-${lang}-${metric ? 'imperial' : 'metric'}.png`)});

      // the pick outlasts a reload and a change of language
      await page.reload();
      await settled(page);
      await check(page, lang, !metric, 'after a reload');
      const other = lang === 'tr' ? 'en' : 'tr';
      await page.click(`[data-lang="${other}"]`);
      await check(page, other, !metric, 'in the other language');

      if (lang === 'tr') expect(await page.evaluate(() => [...MISSING]), 'Turkish strings missing from lang/tr.json').toEqual([]);
      expect(problems, 'the page reported errors').toEqual([]);
    });
  });
}
