// Streaks and doubles: the Streaks tab on Leaders lists each run's active streaks and the season's double-doubles and
// triple-doubles as the game box scores give them, counted over games played in tip-off order; the Player hero shows
// his DD and TD and flags an active run of three or more.
import {test, expect} from '@playwright/test';
import {DESKTOP, PHONE, prepare, settled, go, noSidewaysScroll} from './site.js';

const tens = x => ['pts', 'reb', 'ast', 'stl', 'blk'].filter(k => x[k] >= 10).length;
const TESTS = {p20: x => x.pts >= 20, p10: x => x.pts >= 10, dd: x => tens(x) >= 2, t3: x => x.fg3m >= 1};
// every player's lines with seconds, in tip-off order, from games/<gid>.json, and his runs and doubles from them
const fromBoxes = page => page.evaluate(async () => {
  const G = (await fetch(`${META.base}games.json`).then(r => r.json())).games.filter(g => g.hs != null);
  const B = await Promise.all(G.map(g => fetch(`${META.base}games/${g.gid}.json`).then(r => r.json())));
  const by = {};
  for (const b of B) for (const side of Object.values(b.box)) for (const x of side) if (x.sec > 0) (by[x.pid] = by[x.pid] || []).push(x);
  return by;
});
const tally = lines => {
  const run = {};
  for (const [k, ok] of Object.entries(TESTS)) {
    let cur = 0, best = 0;
    for (const x of lines) { cur = ok(x) ? cur + 1 : 0; best = Math.max(best, cur); }
    run[k] = [cur, best];
  }
  return {dd: lines.filter(x => tens(x) >= 2).length, td: lines.filter(x => tens(x) >= 3).length, run};
};

for (const [name, use, lang] of [['desktop', DESKTOP, 'en'], ['phone', PHONE, 'tr']]) {
  test.describe(`streaks (${name})`, () => {
    test.use(use);
    test(`the Streaks tab is the box scores' runs and doubles (${lang})`, async ({page}, info) => {
      const problems = await prepare(page, {lang});
      await page.goto('./?l#leaders/streaks');
      await settled(page);
      await page.waitForFunction(() => document.querySelectorAll('#ld-runs .panel a[data-pid]').length > 0);
      expect(await page.isHidden('#ld-sec')).toBe(true);
      const L = (await page.evaluate(() => fetch(`${META.base}leaders.json`).then(r => r.json()))).players;
      const by = await fromBoxes(page), T = Object.fromEntries(L.map(p => [p.pid, tally(by[p.pid] || [])]));
      const boards = [
        ...Object.keys(TESTS).map(k => [`run-${k}`, p => T[p.pid].run[k][0], p => T[p.pid].run[k][0] >= 2, (x, y) => T[y.pid].run[k][1] - T[x.pid].run[k][1]]),
        ...['dd', 'td'].map(k => [k, p => T[p.pid][k], p => T[p.pid][k] > 0, (x, y) => x.gp - y.gp])];
      for (const [k, v, keep, tie] of boards) {
        const want = L.filter(keep).sort((x, y) => v(y) - v(x) || tie(x, y) || x.name.localeCompare(y.name)).slice(0, 10);
        expect(want.length, `${k} has rows in the fixture`).toBeGreaterThan(0);
        let rank = 0;
        const ranks = want.map((p, i) => { if (!i || v(p) !== v(want[i - 1])) rank = i + 1; return String(rank); });
        const shown = await page.evaluate(s => [...document.querySelectorAll(`#ld-runs .panel[data-stat="${s}"] a`)].map(a =>
          [a.getAttribute('href'), a.querySelector('.rk').textContent, a.querySelector('.v').firstChild.textContent]), k);
        expect(shown, k).toEqual(want.map((p, i) => [`#${p.team}/${p.pid}`, ranks[i], String(v(p))]));
      }
      await noSidewaysScroll(page, 'streaks');
      await page.screenshot({path: info.outputPath(`streaks-${name}-${lang}.png`), fullPage: true});
      expect(problems, 'the page reported errors').toEqual([]);
    });

    test(`the Player hero shows DD, TD and an active run (${lang})`, async ({page}, info) => {
      const problems = await prepare(page, {lang});
      await page.goto('./?l#home');
      await settled(page);
      const L = (await page.evaluate(() => fetch(`${META.base}leaders.json`).then(r => r.json()))).players;
      const by = await fromBoxes(page);
      const hot = L.filter(p => Object.values(tally(by[p.pid] || []).run).some(r => r[0] >= 3)).sort((x, y) => tally(by[y.pid] || []).dd - tally(by[x.pid] || []).dd)[0];
      const cold = L.find(p => p.gp > 0 && Object.values(tally(by[p.pid] || []).run).every(r => r[0] < 3));
      for (const p of [hot, cold]) {
        const me = tally(by[p.pid] || []);
        await go(page, `#${p.team}/${p.pid}`, x => document.querySelector('#player').value === x && !!document.querySelector('#hero [data-k="dd"]'), p.pid);
        expect(await page.textContent('#hero [data-k="dd"] b')).toBe(String(me.dd));
        expect(await page.textContent('#hero [data-k="td"] b')).toBe(String(me.td));
        const want = ['dd', 'p20', 't3', 'p10'].filter(k => me.run[k][0] >= 3).slice(0, 2);
        const chips = await page.evaluate(() => [...document.querySelectorAll('#hero .run')].map(c => [c.dataset.run, c.dataset.n]));
        expect(chips, p.name).toEqual(want.map(k => [k, String(me.run[k][0])]));
        if (p === hot) {
          await noSidewaysScroll(page, 'player hero');
          await page.locator('#hero').screenshot({path: info.outputPath(`streaks-hero-${name}-${lang}.png`)});
        }
      }
      expect(problems, 'the page reported errors').toEqual([]);
    });
  });
}
