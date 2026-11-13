// Closing five on the club page: its record counts the club's finals decided by 10 points or fewer, as games.json scores
// them; in each one the five closers are the club's players with the most time on the court in the game's last five
// minutes by the game's rotation (more minutes in the game breaking a tie), and the groups and players listed are those
// games counted. A group opens its busiest player's page. On a phone the section fits the screen.
import {test, expect} from '@playwright/test';
/* global get */
import {DESKTOP, PHONE, prepare, settled, noSidewaysScroll} from './site.js';

const CODE = 'SAS';

// the same rule as the page, written apart from it
function expected(G, games, code) {
  const close = G.filter(g => g.hs != null && (g.home === code || g.away === code) && Math.abs(g.hs - g.as) <= 10);
  const w = close.filter(g => (g.home === code) === (g.hs > g.as)).length;
  const units = {}, men = {};
  for (const g of games) {
    if (!g.rotation) continue;
    let n = g.periods.length;
    while (n > 4 && !g.periods[n - 1][0] && !g.periods[n - 1][1]) n--;
    const end = 28800 + 3000 * Math.max(0, n - 4), mine = new Set(g.box[code].map(x => x.pid));
    const five = Object.entries(g.rotation).filter(([p]) => mine.has(p)).map(([p, r]) => {
      let late = 0, all = 0;
      for (const [a, b] of r) { late += Math.max(0, Math.min(b, end) - Math.max(a, end - 3000)); all += b - a; }
      return {p, late, all};
    }).sort((x, y) => y.late - x.late || y.all - x.all || (x.p < y.p ? -1 : 1)).slice(0, 5).map(x => x.p).sort();
    const won = (g.home === code) === (g.hs > g.as) ? 1 : 0;
    const u = units[five.join()] || (units[five.join()] = [0, 0]);
    u[0]++; u[1] += won;
    for (const p of five) { const m = men[p] || (men[p] = [0, 0]); m[0]++; m[1] += won; }
  }
  return {rec: `${w}-${close.length - w}`, close, units, men};
}

async function open(page) {
  await page.goto(`./?l#team/${CODE}`);
  await settled(page);
  await page.waitForFunction(c => document.body.dataset.page === 'team' && document.querySelector('#tm-close-sec').dataset.code === c, CODE);
  await page.click('#tm-close-sec > summary');
  await page.waitForFunction(() => document.querySelector('#tm-close tbody tr'));
}

test.describe('desktop', () => {
  test.use(DESKTOP);
  test('the record, the groups and the players follow the close games\' rotations', async ({page}) => {
    const problems = await prepare(page);
    await open(page);
    const G = await page.evaluate(() => get('games.json').then(d => d.games));
    const gids = G.filter(g => g.hs != null && (g.home === CODE || g.away === CODE) && Math.abs(g.hs - g.as) <= 10).map(g => g.gid);
    const games = await page.evaluate(ids => Promise.all(ids.map(id => get(`games/${id}.json`))), gids);
    const want = expected(G, games, CODE);
    expect(want.close.length, 'the fixture has close games').toBeGreaterThan(1);
    expect(await page.locator('#tm-close-rec b').textContent()).toBe(want.rec);
    const units = await page.locator('#tm-close tbody tr[data-unit]').evaluateAll(rs => rs.map(r => [r.dataset.unit, r.cells[1].textContent, r.cells[2].textContent]));
    const top = Object.entries(want.units).sort((a, b) => b[1][0] - a[1][0] || b[1][1] - a[1][1] || (a[0] < b[0] ? -1 : 1)).slice(0, 3);
    expect(units).toEqual(top.map(([k, [g, w]]) => [k, String(g), `${w}-${g - w}`]));
    const men = await page.locator('#tm-closers tbody tr[data-pid]').evaluateAll(rs => Object.fromEntries(rs.map(r => [r.dataset.pid, [r.cells[1].textContent, r.cells[2].textContent]])));
    expect(men).toEqual(Object.fromEntries(Object.entries(want.men).map(([p, [g, w]]) => [p, [String(g), `${w}-${g - w}`]])));
    // five closers a game: the players' games add up to five times the games with a rotation
    expect(Object.values(want.men).reduce((s, [g]) => s + g, 0)).toBe(5 * games.filter(g => g.rotation).length);
    await page.click('#tm-close tbody tr[data-unit] a');
    await page.waitForFunction(() => document.body.dataset.page === 'player');
    expect(units[0][0].split(',')).toContain(await page.evaluate(() => document.querySelector('#player').value));
    expect(problems).toEqual([]);
  });
});

test.describe('phone', () => {
  test.use(PHONE);
  test('the section fits the screen, in Turkish too', async ({page}) => {
    const problems = await prepare(page, {lang: 'tr', theme: 'dark'});
    await open(page);
    expect(await page.locator('#tm-close-sec summary [data-t="Closing five"]').textContent()).toBe('Son beşlik');
    await noSidewaysScroll(page, 'closing five');
    expect(problems).toEqual([]);
  });
});
