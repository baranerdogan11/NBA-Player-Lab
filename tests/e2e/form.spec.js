// Form: the strip on the Player page is his last ten games' Game Scores as his game page box scores give them, over his
// season average, and each bar opens its game; Trending ranks the change from the season average to the last five's,
// both as shown. The fixture's four nights are under the ten-game floor, so that test stretches every season to triple
// and moves each last five away from it.
import {test, expect} from '@playwright/test';
import {DESKTOP, prepare, settled, go} from './site.js';

test.use(DESKTOP);
const gs = x => 10 * x.pts + 4 * x.fgm - 7 * x.fga - 4 * (x.fta - x.ftm) + 7 * x.oreb + 3 * x.dreb + 10 * x.stl + 7 * x.ast + 7 * x.blk - 4 * x.pf - 10 * x.tov;
const tenths = (num, den) => Math.floor((2 * num * 10 + den) / (2 * den));
const show = q => (q < 0 ? '-' : '') + (Math.abs(q) / 10).toFixed(1);

test('the form strip is his last ten Game Scores from the box scores, over his season average, and opens each game', async ({page}) => {
  const problems = await prepare(page);
  await page.goto('./');
  await settled(page);
  await go(page, '#BOS', () => !!document.querySelector('#form .fm-plot a'));
  const pid = await page.evaluate(() => document.querySelector('#player').value);
  const bars = await page.evaluate(() => [...document.querySelectorAll('#form .fm-plot a')].map(a => [a.dataset.gid, a.querySelector('b').textContent]));
  const box = await page.evaluate(async ([p, gids]) => Promise.all(gids.map(g => fetch(`${META.base}games/${g}.json`).then(r => r.json())
    .then(d => Object.values(d.box).flat().find(x => x.pid === p)))), [pid, bars.map(b => b[0])]);
  expect(bars.map(b => b[1])).toEqual(box.map(x => show(gs(x))));
  const log = await page.evaluate(() => [...document.querySelectorAll('#log tbody tr[data-gid]')].filter(tr => tr.querySelectorAll('td').length > 4).map(tr => tr.dataset.gid));
  expect(bars.map(b => b[0])).toEqual(log.slice(0, 10).reverse());
  const all = await page.evaluate(async p => (await fetch(`${META.base}leaders.json`).then(r => r.json())).players.find(x => x.pid === p), pid);
  expect(await page.textContent('#form-avg')).toBe(show(tenths(all.gs, 10 * all.gp)));
  await page.click('#form .fm-plot a:last-child');
  await page.waitForFunction(g => document.body.dataset.page === 'game' && location.hash === `#game/${g}`, bars.at(-1)[0]);
  expect(problems, 'the page reported errors').toEqual([]);
});

test('Trending ranks the change from season to last five, both as shown, over the floor', async ({page}) => {
  const problems = await prepare(page);
  await page.route(/\/leaders\.json/, async r => {
    const d = await (await r.fetch()).json();
    for (const p of d.players) {
      const n = Math.min(p.gp, 5);   // the last five as five games, some better and some worse, then the season as three of his
      if (n) { p.gs5 = Math.round(5 * p.gs5 / n) + 10 * (Number(p.pid) % 41 - 20); p.sec5 = Math.round(5 * p.sec5 / n); }
      for (const k of ['gp', 'sec', 'gs', 'tm_sec']) p[k] *= 3;
    }
    await r.fulfill({json: d});
  });
  await page.goto('./');
  await settled(page);
  const lead = await page.evaluate(() => fetch(`${META.base}leaders.json`).then(r => r.json()).then(d => d.players));
  const tg = Object.fromEntries((await page.evaluate(() => IDX.teams)).map(x => [x.code, x.gp]));
  await go(page, '#leaders/form', () => document.querySelectorAll('#ld-up tbody tr[data-pid]').length > 0);
  const rows = rs => rs.filter(p => p.gp >= 10 && 10 * p.gp >= 7 * tg[p.team] && p.sec >= 900 * p.gp && p.sec5 >= 4500)
    .map(p => ({pid: p.pid, name: p.name, sa: tenths(p.gs, 10 * p.gp), l5: tenths(p.gs5, 50)})).map(r => ({...r, d: r.l5 - r.sa}));
  const want = rows(lead), sign = q => (q > 0 ? '+' : q < 0 ? '−' : '') + show(Math.abs(q));
  const up = want.filter(r => r.d > 0).sort((x, y) => y.d - x.d || x.name.localeCompare(y.name)).slice(0, 10);
  const down = want.filter(r => r.d < 0).sort((x, y) => x.d - y.d || x.name.localeCompare(y.name)).slice(0, 10);
  for (const [id, list] of [['#ld-up', up], ['#ld-down', down]]) {
    const shown = await page.evaluate(sel => [...document.querySelectorAll(`${sel} tbody tr[data-pid]`)].map(tr => [tr.dataset.pid, ...[...tr.cells].slice(3).map(c => c.textContent)]), id);
    expect(shown).toEqual(list.map(r => [r.pid, show(r.sa), show(r.l5), sign(r.d)]));
  }
  expect(await page.isHidden('#ld-sec')).toBe(true);
  await go(page, '#leaders/pts', () => document.querySelectorAll('#ld tbody tr[data-pid]').length > 0);
  expect(await page.isHidden('#ld-form')).toBe(true);
  expect(problems, 'the page reported errors').toEqual([]);
});
