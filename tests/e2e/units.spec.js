// Best lineups: the Lineups tab on Leaders ranks the league's fives (and, toggled, pairs) at or above the minutes floor
// by net rating as shown, from lineups/league.json; each value is worked out here from the file's integer totals with the
// site's one rounding rule, each row stays on one line on a phone, and a row opens the unit's busiest player.
import {test, expect} from '@playwright/test';
import {DESKTOP, PHONE, prepare, settled, go, noSidewaysScroll} from './site.js';

const rq = (num, den) => Math.floor((2 * num * 10 + den) / (2 * den));
const rtg = (pts, fga, oreb, tov, fta) => { const p = 100 * (fga - oreb + tov) + 44 * fta; return p >= 100 ? rq(10000 * pts, p) : null; };
const show = (q, sign) => (q > 0 && sign ? '+' : q < 0 ? '-' : '') + (Math.abs(q) / 10).toFixed(1);
// the ten best of a list by net rating, then minutes; places shared on an equal rating
const best = units => {
  const rows = units.map(([code, pids, , ds, pts, opp, ...c]) => {
    const o = rtg(pts, ...c.slice(0, 4)), d = rtg(opp, ...c.slice(4));
    return {code, pids, ds, o, d, n: o != null && d != null ? o - d : null};
  }).filter(r => r.n != null).sort((a, b) => b.n - a.n || b.ds - a.ds || a.code.localeCompare(b.code) || a.pids.join().localeCompare(b.pids.join())).slice(0, 10);
  let rank = 0;
  return rows.map((r, i) => { if (!i || r.n !== rows[i - 1].n) rank = i + 1; return {...r, rank}; });
};

for (const [name, use, lang] of [['desktop', DESKTOP, 'en'], ['phone', PHONE, 'tr']]) {
  test.describe(`best lineups (${name})`, () => {
    test.use(use);
    test(`the Lineups tab ranks fives and pairs over the floor by net rating (${lang})`, async ({page}, info) => {
      const problems = await prepare(page, {lang});
      await page.goto('./?l#leaders/lineups');
      await settled(page);
      await page.waitForFunction(() => document.querySelectorAll('#ld-units tbody tr[data-unit]').length > 0);
      expect(await page.isHidden('#ld-sec')).toBe(true);
      expect(await page.isHidden('#ld-rook')).toBe(true);
      const lg = await page.evaluate(() => fetch(`${META.base}lineups/league.json`).then(r => r.json()));
      const L = (await page.evaluate(() => fetch(`${META.base}leaders.json`).then(r => r.json()))).players;
      const sec = Object.fromEntries(L.map(p => [p.pid, p.sec]));
      for (const [n, key] of [[5, 'fives'], [2, 'pairs']]) {
        if (n === 2) await go(page, '#leaders/lineups/2', () => document.querySelector('#ld-size [aria-current="true"]').dataset.n === '2');
        const want = best(lg[key]);
        expect(want.length, key).toBeGreaterThan(0);
        const shown = await page.$$eval('#ld-units tbody tr', trs => trs.map(tr => ({unit: tr.dataset.unit, href: tr.querySelector('a').getAttribute('href'),
          faces: tr.querySelectorAll('.face').length, cells: [...tr.cells].map(td => td.textContent.replace(',', '.').replace('−', '-')), h: tr.getBoundingClientRect().height})));
        expect(shown.map(r => r.unit), key).toEqual(want.map(r => `${r.code}:${r.pids.join(',')}`));
        shown.forEach((r, i) => {
          const w = want[i], top = w.pids.reduce((a, b) => (sec[b] || 0) > (sec[a] || 0) ? b : a);
          expect(r.faces).toBe(n);
          expect(r.href).toBe(`#${w.code}/${top}`);
          expect([r.cells[0], r.cells[3], r.cells[7]], r.unit).toEqual([String(w.rank), String(Math.floor((2 * w.ds + 600) / 1200)), show(w.n, 1)]);
          expect(w.ds, 'over the floor').toBeGreaterThanOrEqual(600 * lg.floor[n]);
          if (name === 'desktop') expect([r.cells[5], r.cells[6]]).toEqual([show(w.o), show(w.d)]);
          else expect(r.h, `${r.unit} on one line`).toBeLessThan(48);
        });
        await noSidewaysScroll(page, `#leaders/lineups (${key})`);
        if (name === 'phone') {
          const wide = await page.$eval('#ld-lu .scroll', el => el.scrollWidth - el.clientWidth);
          expect(wide, 'the board fits the phone').toBeLessThanOrEqual(1);
        }
        await page.screenshot({path: info.outputPath(`units-${key}-${name}-${lang}.png`), fullPage: true});
      }
      await go(page, '#leaders/lineups', () => document.querySelector('#ld-size [aria-current="true"]').dataset.n === '5');
      const first = page.locator('#ld-units tbody tr a').first();
      const [, code, pid] = (await first.getAttribute('href')).split(/[#/]/);
      await first.click();
      await page.waitForFunction(([c, p]) => document.body.dataset.page === 'player' && document.querySelector('#player').value === p
        && location.hash.startsWith(`#${c}/`) && !document.querySelector('#lu').hidden, [code, pid]);
      expect(problems, 'the page reported errors').toEqual([]);
    });
  });
}
