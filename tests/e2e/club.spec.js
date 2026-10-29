// The club page (#team/<CODE>): its record is the Standings row, its next games are the schedule's with the rest the
// preview shows, its roster's averages are each Player page's tiles, and its ratings and Four Factors, values and
// ranks, are the Standings ones. Standings, the game page and the preview link to it.
import {test, expect} from '@playwright/test';
/* global get, tname */
import {DESKTOP, prepare, settled, go} from './site.js';

test.use(DESKTOP);
const CODE = 'BOS';
const club = c => document.body.dataset.page === 'team' && document.title === `${tname(c)} · NBA Player Lab`;

test('its record is the one Standings shows, and the Standings row opens it', async ({page}) => {
  const problems = await prepare(page);
  await page.goto('./?l#standings/league');
  await settled(page);
  await page.waitForFunction(() => document.querySelectorAll('#st-body tbody tr').length === 30);
  const row = await page.evaluate(c => [...document.querySelector(`#st-body tr[data-team="${c}"]`).cells].map(td => td.firstChild ? td.firstChild.textContent : ''), CODE);
  await page.click(`#st-body tr[data-team="${CODE}"] a`);
  await page.waitForFunction(club, CODE);
  const shown = await page.evaluate(() => ({
    tiles: Object.fromEntries([...document.querySelectorAll('#tm-tiles .tile')].map(x => [x.dataset.k, x.querySelector('b').textContent])),
    facts: [...document.querySelectorAll('#tm-hero .facts > span > b')].map(b => b.textContent),
    tab: document.querySelector('#tb-team').getAttribute('aria-current'),
  }));
  const [, , w, l, pctv, , home, away, l10, strk, ppg, opp, diff] = row;
  expect(shown.tiles).toEqual({W: w, L: l, PCT: pctv, PPG: ppg, 'OPP PPG': opp, DIFF: diff});
  expect(shown.facts).toEqual([home, away, l10, strk]);
  expect(shown.tab).toBe('page');
  expect(problems).toEqual([]);
});

test('its next five games come from the schedule, with the rest before each, and open their previews', async ({page}) => {
  const problems = await prepare(page);
  await page.goto(`./?l#team/${CODE}`);
  await settled(page);
  await page.waitForFunction(club, CODE);
  const G = await page.evaluate(() => get('games.json').then(d => d.games));
  const next = G.filter(g => g.hs == null && (g.home === CODE || g.away === CODE)).slice(0, 5);
  expect(next.length).toBeGreaterThan(0);
  const shown = await page.evaluate(() => [...document.querySelectorAll('#tm-next .up')].map(d => ({gid: d.querySelector('a.card').dataset.gid, rest: d.querySelector('.rest').dataset.rest})));
  expect(shown.map(x => x.gid)).toEqual(next.map(g => g.gid));
  for (const [i, g] of next.entries()) {
    const last = G.slice(0, G.indexOf(g)).filter(x => x.home === CODE || x.away === CODE).pop();
    expect(shown[i].rest, `rest before ${g.gid}`).toBe(String((Date.parse(g.date) - Date.parse(last.date)) / 864e5 - 1));
  }
  await page.click('#tm-next a.card');
  await page.waitForFunction(() => document.body.dataset.page === 'game' && !document.querySelector('#gm-pre').hidden);
  const rest = await page.evaluate(c => document.querySelector(`#pv-form [data-team="${c}"] .rest`).dataset.rest, CODE);
  expect(rest, 'the preview counts the same rest').toBe(shown[0].rest);
  await page.click(`#pv-form [data-team="${CODE}"] a.nm`);
  await page.waitForFunction(club, CODE);
  expect(problems).toEqual([]);
});

test('each roster line is the Player page\'s season averages, and opens that page', async ({page}) => {
  const problems = await prepare(page);
  await page.goto(`./?l#team/${CODE}`);
  await settled(page);
  await page.waitForFunction(club, CODE);
  const rows = await page.evaluate(() => {
    const head = [...document.querySelectorAll('#tm-roster thead th')].map(th => th.textContent);
    return [...document.querySelectorAll('#tm-roster tbody tr[data-pid]')].map(tr => ({pid: tr.dataset.pid, v: Object.fromEntries([...tr.cells].map((td, i) => [head[i], td.textContent]))}));
  });
  const data = await page.evaluate(c => get(`${c}.json`), CODE);
  expect(rows.map(r => r.pid).sort()).toEqual(data.players.map(p => p.pid).sort());
  for (const r of rows.filter(x => x.v.GP !== '0').slice(0, 4)) {
    await go(page, `#${CODE}/${r.pid}`, pid => document.querySelector('#player').value === pid && !!document.querySelector('#tiles .tile'), r.pid);
    const tiles = await page.evaluate(() => Object.fromEntries([...document.querySelectorAll('#tiles .tile')].map(x => [x.dataset.k, x.querySelector('b').textContent])));
    const games = await page.evaluate(() => [...document.querySelectorAll('#hero .facts span')].find(s => s.textContent.startsWith('Games')).querySelector('b').textContent);
    expect({GP: r.v.GP, MIN: r.v.MIN, PTS: r.v.PTS, REB: r.v.REB, AST: r.v.AST, STL: r.v.STL, BLK: r.v.BLK, TOV: r.v.TOV, 'FG%': r.v['FG%'], '3P%': r.v['3P%'], 'FT%': r.v['FT%'], '+/-': r.v['+/-']}, r.pid)
      .toEqual({GP: games, MIN: tiles.MIN, PTS: tiles.PTS, REB: tiles.REB, AST: tiles.AST, STL: tiles.STL, BLK: tiles.BLK, TOV: tiles.TOV, 'FG%': tiles['FG%'], '3P%': tiles['3P%'], 'FT%': tiles['FT%'], '+/-': tiles['+/-']});
  }
  await go(page, `#team/${CODE}`, club, CODE);
  const pid = rows[0].pid;
  await page.click(`#tm-roster tr[data-pid="${pid}"] a`);
  await page.waitForFunction(p => document.body.dataset.page === 'player' && document.querySelector('#player').value === p, pid);
  await page.click('#hero .tag a');
  await page.waitForFunction(club, CODE);
  expect(problems).toEqual([]);
});

test('its ratings and Four Factors, values and ranks, are the ones Standings shows', async ({page}) => {
  const problems = await prepare(page);
  await page.goto(`./?l#team/${CODE}`);
  await settled(page);
  await page.waitForFunction(club, CODE);
  const mine = await page.evaluate(() => Object.fromEntries([...document.querySelectorAll('#tm-rt td[data-k], #tm-ff td[data-k]')].map(td => [td.dataset.k, {v: td.querySelector('.v').textContent, r: td.dataset.r || null}])));
  expect(Object.keys(mine).length).toBe(12);
  const st = {};
  for (const view of ['ratings', 'factors']) {
    await go(page, `#standings/${view}`, v => document.querySelectorAll(`#st-${v} tbody tr`).length === 30, view);
    Object.assign(st, await page.evaluate(([v, c]) => Object.fromEntries([...document.querySelectorAll(`#st-${v} tr[data-team="${c}"] td[data-k]`)].map(td =>
      [td.dataset.k, {v: td.querySelector('.v').textContent, r: td.dataset.r || null}])), [view, CODE]));
  }
  expect(mine).toEqual(st);
  expect(problems).toEqual([]);
});

test('the game page\'s crests and score-by-period names open each club', async ({page}) => {
  const problems = await prepare(page);
  await page.goto('./?l#game/0022600001');
  await settled(page);
  await page.waitForFunction(() => document.body.dataset.page === 'game' && document.querySelectorAll('#gm-box table').length === 2);
  const g = await page.evaluate(() => get('games/0022600001.json'));
  expect(await page.evaluate(() => [...document.querySelectorAll('#gm-board a.side')].map(a => a.getAttribute('href')))).toEqual([`#team/${g.away}`, `#team/${g.home}`]);
  expect(await page.evaluate(() => [...document.querySelectorAll('#gm-periods tbody a')].map(a => a.getAttribute('href')))).toEqual([`#team/${g.away}`, `#team/${g.home}`]);
  await page.click('#gm-board a.side.h');
  await page.waitForFunction(club, g.home);
  expect(problems).toEqual([]);
});

test('its calendar link subscribes to the club\'s whole schedule: Google Calendar here, webcal on Apple devices', async ({page, browser}) => {
  const problems = await prepare(page);
  await page.goto(`./?l#team/${CODE}`);
  await settled(page);
  await page.waitForFunction(club, CODE);
  const href = await page.getAttribute('#tm-cal', 'href');
  expect(href).toMatch(/^https:\/\/calendar\.google\.com\/calendar\/r\?cid=/);
  const ics = decodeURIComponent(href.split('cid=')[1]);
  expect(ics).toMatch(new RegExp(`^webcal://.+/teams/[0-9-]+/cal/${CODE}\\.ics$`));
  const text = await (await page.request.get(ics.replace(/^webcal:/, 'http:'))).text();
  const G = await page.evaluate(() => get('games.json').then(d => d.games));
  expect([...text.matchAll(/^UID:(\d+)@/gm)].map(m => m[1])).toEqual(G.filter(g => g.home === CODE || g.away === CODE).map(g => g.gid));
  expect(problems).toEqual([]);

  const apple = await browser.newPage({...DESKTOP, userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1'});
  await prepare(apple);
  await apple.goto(new URL(`./?l#team/${CODE}`, page.url()).href);
  await settled(apple);
  await apple.waitForFunction(club, CODE);
  expect(await apple.getAttribute('#tm-cal', 'href')).toBe(ics);
  await apple.close();
});
