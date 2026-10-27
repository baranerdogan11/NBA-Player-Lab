// Season highs: the Highs tab on Leaders is each stat's ten best lines of the season as the game box scores give them,
// ranks tied on the value (a Turkish decimal comma read as a point), each opening his page at that game; his game log
// marks the games where a stat is at his most.
import {test, expect} from '@playwright/test';
import {DESKTOP, PHONE, prepare, settled, go} from './site.js';

const gs = x => 10 * x.pts + 4 * x.fgm - 7 * x.fga - 4 * (x.fta - x.ftm) + 7 * x.oreb + 3 * x.dreb + 10 * x.stl + 7 * x.ast + 7 * x.blk - 4 * x.pf - 10 * x.tov;
const show = q => (q < 0 ? '-' : '') + (Math.abs(q) / 10).toFixed(1);
const STATS = ['pts', 'reb', 'ast', 'stl', 'blk', 'fg3m', 'gs'];
// every line of the season's finals, in tip-off order, from games/<gid>.json
const boxes = page => page.evaluate(async () => {
  const G = (await fetch(`${META.base}games.json`).then(r => r.json())).games.filter(g => g.hs != null);
  return Promise.all(G.map(g => fetch(`${META.base}games/${g.gid}.json`).then(r => r.json())));
});

for (const [name, use, lang] of [['desktop', DESKTOP, 'en'], ['phone', PHONE, 'tr']]) {
  test.describe(`season highs (${name})`, () => {
    test.use(use);
    test(`the Highs tab is each stat's ten best box-score lines and opens the game (${lang})`, async ({page}, info) => {
      const problems = await prepare(page, {lang});
      await page.goto('./?l#leaders/highs');
      await settled(page);
      await page.waitForFunction(() => document.querySelectorAll('#ld-highs .panel a[data-pid]').length > 0);
      expect(await page.isHidden('#ld-sec')).toBe(true);
      const club = Object.fromEntries((await page.evaluate(() => fetch(`${META.base}leaders.json`).then(r => r.json()))).players.map(p => [p.pid, p.team]));
      const lines = (await boxes(page)).flatMap((b, i) => Object.entries(b.box).flatMap(([c, side]) => side.filter(x => x.sec > 0)
        .map(x => ({...x, gs: gs(x), gid: b.gid, i, team: c, opp: c === b.home ? b.away : b.home}))));
      for (const k of STATS) {
        const want = lines.filter(x => x[k] > 0).sort((x, y) => y[k] - x[k] || x.i - y.i || x.gid.localeCompare(y.gid) || x.name.localeCompare(y.name) || x.pid.localeCompare(y.pid)).slice(0, 10);
        let rank = 0;
        const ranks = want.map((x, i) => { if (!i || x[k] !== want[i - 1][k]) rank = i + 1; return String(rank); });
        const shown = await page.evaluate(s => [...document.querySelectorAll(`#ld-highs .panel[data-stat="${s}"] a`)].map(a =>
          [a.getAttribute('href'), a.querySelector('.rk').textContent, a.querySelector('.v').firstChild.textContent.replace(',', '.'), a.querySelector('small').textContent]), k);
        expect(shown.map(r => r.slice(0, 3)), k).toEqual(want.map((x, i) => [`#${club[x.pid]}/${x.pid}/${x.gid}`, ranks[i], k === 'gs' ? show(x.gs) : String(x[k])]));
        shown.forEach((r, i) => expect(r[3]).toContain(want[i].opp));
      }
      await page.screenshot({path: info.outputPath(`highs-${name}-${lang}.png`), fullPage: true});
      const first = page.locator('#ld-highs .panel[data-stat="pts"] a').first();
      const [, code, pid, gid] = (await first.getAttribute('href')).split(/[#/]/);
      await first.click();
      await page.waitForFunction(([c, p, g]) => document.body.dataset.page === 'player' && document.querySelector('#player').value === p
        && document.querySelector('#sc-game').value === g && location.hash.startsWith(`#${c}/`), [code, pid, gid]);
      expect(problems, 'the page reported errors').toEqual([]);
    });
  });
}

test.describe('season highs in the game log', () => {
  test.use(DESKTOP);
  test('his game log marks the games where a stat is at its most, from the box scores', async ({page}) => {
    const problems = await prepare(page);
    await page.goto('./?l#BOS');
    await settled(page);
    const all = await boxes(page);
    const pids = await page.evaluate(() => [...document.querySelectorAll('#player option')].map(o => o.value));
    let marked = 0;
    for (const pid of pids) {
      await go(page, `#BOS/${pid}`, p => document.querySelector('#player').value === p && !!document.querySelector('#log tbody tr'), pid);
      const mine = all.flatMap(b => Object.values(b.box).flat().filter(x => x.pid === pid && x.sec > 0).map(x => ({...x, gid: b.gid})));
      const want = [];
      if (mine.length > 1) {
        for (const k of STATS.slice(0, 6)) {
          const m = Math.max(...mine.map(x => x[k]));
          if (m > 0) want.push(...mine.filter(x => x[k] === m).map(x => `${x.gid} ${k}`));
        }
      }
      const shown = await page.evaluate(() => [...document.querySelectorAll('#log td.best')].map(td => `${td.closest('tr').dataset.gid} ${td.dataset.high}`));
      expect(shown.sort(), pid).toEqual(want.sort());
      marked += shown.length;
    }
    expect(marked, 'some season highs are marked').toBeGreaterThan(0);
    expect(problems, 'the page reported errors').toEqual([]);
  });
});
