// Who gets to the line: the Player page's tiles carry his fouls drawn (FD) and personal fouls (PF) per game and his
// free-throw rate (FTR, FTA ÷ FGA to three decimals, .380), summed from his box-score lines in the game files; Compare
// shows the same two rows; Leaders ranks fouls drawn per game, free-throw rate and personal fouls per 36 minutes above
// the per-game and 15-minute floors, from leaders.json. Every value is computed here with the site's rounding rule.
import {test, expect} from '@playwright/test';
import {DESKTOP, PHONE, prepare, settled, go, noSidewaysScroll} from './site.js';

// the site's rounding rule, half up on the exact value, in integers: num / den to d decimals
const rq = (num, den, d) => Math.floor((2 * num * 10 ** d + den) / (2 * den));
const fix = (q, d) => { const s = String(Math.abs(q)).padStart(d + 1, '0'); return `${q < 0 ? '-' : ''}${s.slice(0, -d)}.${s.slice(-d)}`; };
const loc = (s, lang) => lang === 'tr' ? s.replace('.', ',') : s;
const avg = (n, gp, lang) => gp ? loc(fix(rq(n, gp, 1), 1), lang) : '–';
const ftr = (fta, fga, lang) => fga ? loc(fix(rq(fta, fga, 3), 3).replace(/^0/, ''), lang) : '–';
const per36 = (n, sec, lang) => sec ? loc(fix(rq(2160 * n, sec, 1), 1), lang) : '–';
const fromBoxes = page => page.evaluate(async () => {
  const G = (await fetch(`${META.base}games.json`).then(r => r.json())).games.filter(g => g.hs != null);
  const B = await Promise.all(G.map(g => fetch(`${META.base}games/${g.gid}.json`).then(r => r.json())));
  const by = {};
  for (const b of B) for (const side of Object.values(b.box)) for (const x of side) if (x.sec > 0) (by[x.pid] = by[x.pid] || []).push(x);
  return by;
});
const total = (lines, k) => lines.reduce((a, x) => a + x[k], 0);

for (const [name, use, lang] of [['desktop', DESKTOP, 'en'], ['phone', PHONE, 'tr']]) {
  test.describe(`fouls (${name}, ${lang})`, () => {
    test.use(use);
    test('the Player tiles and Compare show fouls drawn, fouls and the free-throw rate from his box scores', async ({page}, info) => {
      const problems = await prepare(page, {lang, theme: lang === 'tr' ? 'dark' : 'light'});
      await page.goto('./');
      await settled(page);
      await go(page, '#BOS', () => document.querySelectorAll('#tiles .tile').length === 15);
      const by = await fromBoxes(page);
      const pids = await page.evaluate(() => [...document.querySelectorAll('#player option')].map(o => o.value).filter(Boolean));
      let seen = 0;
      for (const pid of pids.slice(0, 4)) {
        await go(page, `#BOS/${pid}`, p => document.querySelector('#player').value === p && document.querySelectorAll('#tiles .tile').length === 15, pid);
        const ls = by[pid] || [];
        const tile = await page.evaluate(() => Object.fromEntries([...document.querySelectorAll('#tiles .tile')].map(d => [d.dataset.k, d.querySelector('b').textContent])));
        expect(Object.keys(tile)).toEqual(['PTS', 'REB', 'AST', 'STL', 'BLK', 'FG%', '3P%', 'FT%', 'FTR', 'TS%', 'TOV', 'FD', 'PF', '+/-', 'MIN']);
        expect(tile.FD, `${pid} FD`).toBe(avg(total(ls, 'fd'), ls.length, lang));
        expect(tile.PF, `${pid} PF`).toBe(avg(total(ls, 'pf'), ls.length, lang));
        expect(tile.FTR, `${pid} FTR`).toBe(ftr(total(ls, 'fta'), total(ls, 'fga'), lang));
        if (ls.length && total(ls, 'fd')) seen++;
      }
      expect(seen, 'players with fouls drawn in the fixture').toBeGreaterThan(0);
      await page.evaluate(() => scrollTo(0, 0));
      await page.screenshot({path: info.outputPath(`player-${name}-${lang}.png`)});
      await noSidewaysScroll(page, 'player tiles');
      // the tiles sit five to a row (three on a phone), every row full (offsetTop: the entry rise moves them a while)
      const cols = await page.evaluate(() => new Set([...document.querySelectorAll('#tiles .tile')].map(d => /** @type {HTMLElement} */ (d).offsetTop)).size);
      expect(cols).toBe(use === PHONE ? 5 : 3);

      const [a, b] = pids;
      await go(page, `#compare/${a}/${b}`, () => document.querySelectorAll('#cmp tr').length > 5);
      const cmp = await page.evaluate(() => Object.fromEntries([...document.querySelectorAll('#cmp tr')].map(tr => [tr.cells[1].textContent, [tr.cells[0].textContent, tr.cells[2].textContent]])));
      const fdL = lang === 'tr' ? 'Alınan faul' : 'Fouls drawn', ftL = lang === 'tr' ? 'SA oranı' : 'FT rate';
      const A = by[a] || [], B = by[b] || [];
      expect(cmp[fdL]).toEqual([avg(total(A, 'fd'), A.length, lang), avg(total(B, 'fd'), B.length, lang)]);
      expect(cmp[ftL]).toEqual([ftr(total(A, 'fta'), total(A, 'fga'), lang), ftr(total(B, 'fta'), total(B, 'fga'), lang)]);
      await page.screenshot({path: info.outputPath(`compare-${name}-${lang}.png`), fullPage: true});
      await noSidewaysScroll(page, 'compare');
      expect(problems, 'the page reported errors').toEqual([]);
    });

    test('the Leaders boards rank fouls drawn, free-throw rate and foul trouble above their floors', async ({page}, info) => {
      const problems = await prepare(page, {lang, theme: lang === 'tr' ? 'dark' : 'light'});
      await page.goto('./');
      await settled(page);
      const L = (await page.evaluate(() => fetch(`${META.base}leaders.json`).then(r => r.json()))).players;
      const gp = await page.evaluate(() => Object.fromEntries(IDX.teams.map(t => [t.code, t.gp])));
      const busy = p => p.gp > 0 && 10 * p.gp >= 7 * (gp[p.team] || 0) && p.sec >= 900 * p.gp;
      const boards = {
        fd: [p => p.fd / p.gp, p => avg(p.fd, p.gp, lang), busy],
        ftar: [p => p.fta / p.fga, p => ftr(p.fta, p.fga, lang), p => p.fga > 0 && busy(p)],
        pf36: [p => p.pf / p.sec, p => per36(p.pf, p.sec, lang), busy],
      };
      for (const [k, [v, f, ok]] of Object.entries(boards)) {
        await go(page, `#leaders/${k}`, s => document.querySelector('#ld-tabs a[aria-current="true"]')?.getAttribute('href') === `#leaders/${s}` && document.querySelectorAll('#ld tr[data-pid]').length > 0, k);
        const want = L.filter(ok).sort((x, y) => v(y) - v(x) || x.name.localeCompare(y.name)).slice(0, 25);
        expect(want.length, `${k} has players in the fixture`).toBeGreaterThan(0);
        const shown = await page.$$eval('#ld tr[data-pid]', trs => trs.map(tr => [tr.dataset.pid, tr.lastElementChild.textContent]));
        expect(shown, k).toEqual(want.map(p => [p.pid, f(p)]));
        expect(await page.getAttribute('#ld-tabs a[aria-current="true"]', 'data-def')).toBe(`${k} floor-pg floor-busy`);
        await noSidewaysScroll(page, `${k} board`);
      }
      await page.screenshot({path: info.outputPath(`leaders-${name}-${lang}.png`), fullPage: true});
      expect(problems, 'the page reported errors').toEqual([]);
    });
  });
}
