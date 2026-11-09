// Shot distance: the Player page's shot chart panel carries, under the shot types, his attempts by distance band (the
// seventh field of a shot row in shots/<CODE>.json, tenths of a foot, banded as shots.py band() does) with his share of
// attempts against the league's, FG and FG% and the league's FG% there (shots/league.json bands), and his average
// distance against the league's (league.json dist); the bands add up to the zone table's FG, the three-point bands to its
// threes. Leaders has a Range tab: the most deep threes made (27 feet out, from 10 attempts) and the longest average
// distance (from 100 attempts), from league.json players.
import {test, expect} from '@playwright/test';
import {DESKTOP, PHONE, prepare, settled, go, noSidewaysScroll} from './site.js';

const ev = (page, expr) => page.evaluate(e => /** @type {any} */ (window).eval(e), expr);
const band = (d, z) => z >= 3 ? (d < 270 ? 4 : d < 300 ? 5 : 6) : d < 30 ? 0 : d < 100 ? 1 : d < 160 ? 2 : 3;

for (const [name, use, lang] of [['desktop', DESKTOP, 'en'], ['phone', PHONE, 'tr']]) {
  test.describe(`shot distance (${name}, ${lang})`, () => {
    test.use(use);
    test('the distance table splits his attempts by band against the league, with his average distance', async ({page}, info) => {
      const problems = await prepare(page, {lang, theme: lang === 'tr' ? 'dark' : 'light'});
      await page.goto('./');
      await settled(page);
      await go(page, '#BOS', () => !document.querySelector('#sc-dist').hidden && document.querySelectorAll('#sc-dist tr[data-band]').length === 7);
      await page.click('#sc > summary');
      const pid = await page.evaluate(() => document.querySelector('#player').value);
      const [f, lg] = await page.evaluate(() => Promise.all(['shots/BOS.json', 'shots/league.json'].map(p => fetch(`${META.base}${p}`).then(r => r.json()))));
      const lgN = lg.bands.reduce((a, c) => a + c[1], 0);
      expect(lgN, 'league bands add up to its zones').toBe(lg.zones.reduce((a, c) => a + c[1], 0));
      expect(await page.textContent('#sc-lavg')).toBe(await ev(page, `feet(${lg.dist}, ${lgN})`));
      const check = async (gid, what) => {
        const rows = f.players[pid].filter(r => !gid || f.games[r[0]] === gid);
        const want = lg.bands.map((_, b) => rows.filter(r => band(r[6], r[4]) === b)).map(rs => [rs.reduce((a, r) => a + r[3], 0), rs.length]);
        const shown = await page.$$eval('#sc-dist tr[data-band]', trs => trs.map(tr => [...tr.cells].slice(2).map(td => td.textContent)));
        for (const [b, [m, n]] of want.entries()) {
          expect(shown[b], `${what}: band ${b}`).toEqual([`${m}-${n}`, n ? await ev(page, `pct(${m}, ${n})`) : '–', await ev(page, `pct(${lg.bands[b][0]}, ${lg.bands[b][1]})`)]);
        }
        const bars = await page.$$eval('#sc-dist td.bars', tds => tds.map(td => [...td.querySelectorAll('i')].map(i => parseFloat(i.style.width))));
        bars.forEach(([mine, all], b) => {
          expect(mine, `${what}: band ${b} his share`).toBeCloseTo(100 * want[b][1] / rows.length, 3);
          expect(all, `${what}: band ${b} league share`).toBeCloseTo(100 * lg.bands[b][1] / lgN, 3);
        });
        expect(await page.textContent('#sc-avg'), `${what}: average distance`).toBe(await ev(page, `feet(${rows.reduce((a, r) => a + r[6], 0)}, ${rows.length})`));
        const zones = await page.$$eval('#sc-zones tr[data-z]', trs => trs.map(tr => tr.cells[1].textContent.split('-').map(Number)));
        const sum = rs => rs.reduce((a, [m, n]) => [a[0] + m, a[1] + n], [0, 0]);
        expect(sum(want), `${what}: bands add up to the zones`).toEqual(sum(zones));
        expect(sum(want.slice(4)), `${what}: three-point bands add up to the three-point zones`).toEqual(sum(zones.slice(3)));
      };
      await check('', 'season');
      const gid = await page.evaluate(() => [...document.querySelectorAll('#sc-game option')].map(o => o.value).find(Boolean));
      await page.selectOption('#sc-game', gid, {force: true});
      await check(gid, `game ${gid}`);
      await page.selectOption('#sc-game', '', {force: true});
      await page.locator('#sc-dist').scrollIntoViewIfNeeded();
      await page.screenshot({path: info.outputPath(`player-${name}-${lang}.png`)});
      await noSidewaysScroll(page, 'distance table');
      if (lang === 'tr') expect(await page.evaluate(() => [...MISSING]), 'Turkish strings missing from lang/tr.json').toEqual([]);
      expect(problems, 'the page reported errors').toEqual([]);
    });

    test('the Range tab lists the most deep threes and the longest average distance', async ({page}, info) => {
      const problems = await prepare(page, {lang, theme: lang === 'tr' ? 'dark' : 'light'});
      await page.goto('./');
      await settled(page);
      await go(page, '#leaders/range', () => !document.querySelector('#ld-range').hidden && document.querySelectorAll('#ld-deep tbody tr').length > 0);
      expect(await page.isHidden('#ld-sec')).toBe(true);
      expect(await page.getAttribute('#ld-tabs a[href="#leaders/range"]', 'aria-current')).toBe('true');
      const [L, P] = await page.evaluate(() => Promise.all(['leaders.json', 'shots/league.json'].map(p => fetch(`${META.base}${p}`).then(r => r.json())))).then(([l, s]) => [l.players, s.players]);
      const nm = pid => L.find(p => p.pid === pid).name;
      const deep = L.filter(p => P[p.pid] && P[p.pid][3] >= 10).map(p => p.pid)
        .sort((x, y) => P[y][2] - P[x][2] || P[x][3] - P[y][3] || nm(x).localeCompare(nm(y))).slice(0, 10);
      expect(deep.length, 'the fixture has deep shooters').toBeGreaterThan(0);
      const shown = await page.$$eval('#ld-deep tbody tr', trs => trs.map(tr => [tr.dataset.pid, tr.cells[0].textContent, tr.cells[2].textContent, tr.cells[3].textContent]));
      expect(shown.map(s => s[0])).toEqual(deep);
      for (const [i, pid] of deep.entries()) {
        expect(shown[i].slice(2)).toEqual([`${P[pid][2]}-${P[pid][3]}`, await ev(page, `pct(${P[pid][2]}, ${P[pid][3]})`)]);
        const ties = deep.findIndex(q => P[q][2] === P[pid][2]);
        expect(shown[i][1], `place of ${pid}`).toBe(String(ties + 1));
      }
      const far = L.filter(p => P[p.pid] && P[p.pid][0] >= 100).map(p => p.pid)
        .sort((x, y) => P[y][1] * P[x][0] - P[x][1] * P[y][0] || nm(x).localeCompare(nm(y))).slice(0, 10);
      const farShown = await page.$$eval('#ld-far tbody tr[data-pid]', trs => trs.map(tr => [tr.dataset.pid, tr.cells[2].textContent, tr.cells[3].textContent]));
      expect(farShown.map(s => s[0])).toEqual(far);
      for (const [i, pid] of far.entries()) expect(farShown[i].slice(1)).toEqual([String(P[pid][0]), await ev(page, `feet(${P[pid][1]}, ${P[pid][0]})`)]);
      // the Rookies switch keeps both lists to rookies
      await page.click('#ld-rook');
      await page.waitForFunction(() => location.hash === '#leaders/range/rookies' && document.querySelector('#ld-rook').getAttribute('aria-pressed') === 'true');
      const rook = new Set(L.filter(p => p.rookie).map(p => p.pid));
      expect((await page.$$eval('#ld-deep tbody tr[data-pid], #ld-far tbody tr[data-pid]', trs => trs.map(tr => tr.dataset.pid))).every(p => rook.has(p))).toBe(true);
      await page.click('#ld-rook');
      await page.waitForFunction(() => location.hash === '#leaders/range');
      await page.screenshot({path: info.outputPath(`range-${name}-${lang}.png`), fullPage: true});
      await noSidewaysScroll(page, 'range boards');
      if (lang === 'tr') expect(await page.evaluate(() => [...MISSING]), 'Turkish strings missing from lang/tr.json').toEqual([]);
      expect(problems, 'the page reported errors').toEqual([]);
    });
  });
}
