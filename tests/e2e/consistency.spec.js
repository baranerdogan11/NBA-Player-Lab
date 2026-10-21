// Every number agrees across pages to the decimal: for every player in the first night's games, his line on the game page
// is the row of his game log, his season averages on his page equal his Compare and Leaders values, and each box score
// adds up to the final.
import {test, expect} from '@playwright/test';
import {DESKTOP, prepare, settled, go} from './site.js';

test.use(DESKTOP);

test('a game, the players in it, their pages, compare and leaders agree', async ({page}) => {
  test.setTimeout(240_000);
  const problems = await prepare(page);
  await page.goto('./#games/2026-10-21');
  await settled(page);
  const gids = await page.evaluate(() => [...document.querySelectorAll('#gm-list a.card')].map(a => a.dataset.gid));
  expect(gids.length).toBeGreaterThan(0);
  const board = await page.evaluate(() => fetch(`${META.base}leaders.json`).then(r => r.json()).then(d => d.players));
  const lead = Object.fromEntries(board.map(p => [p.pid, p]));
  for (const gid of gids.slice(0, 3)) {
    await go(page, `#game/${gid}`, () => document.querySelectorAll('#gm-box table').length === 2);
    const game = await page.evaluate(() => {
      const score = [...document.querySelectorAll('#gm-board .score span')].map(s => +s.textContent);
      return {score, sides: [...document.querySelectorAll('#gm-box table')].map(tb => ({
        code: tb.dataset.team, total: +tb.querySelector('tr.tot [data-k="pts"]').textContent,
        rows: [...tb.querySelectorAll('tbody tr[data-pid]')].map(tr => ({pid: tr.dataset.pid, cells: [...tr.cells].slice(1).map(td => td.textContent)})),
      }))};
    });
    expect(game.sides.map(s => s.total), `box totals of ${gid}`).toEqual(game.score);
    for (const side of game.sides) {
      for (const row of side.rows.filter(r => r.cells.length > 1).slice(0, 4)) {
        await go(page, `#${side.code}/${row.pid}`, p => document.querySelector('#player').value === p, row.pid);
        await page.waitForFunction(p => document.querySelector('#player').value === p, row.pid);
        const mine = await page.evaluate(g => {
          const tr = document.querySelector(`#log tr[data-gid="${g}"]`);
          const c = [...tr.cells].map(td => td.textContent);
          const tile = k => document.querySelector(`#tiles [data-k="${k}"] b`).textContent;
          return {min: c[3], pts: c[4], reb: c[5], ast: c[6], fg: c[10], pts_avg: tile('PTS'), fg_pct: tile('FG%')};
        }, gid);
        const [min, pts, reb, , , ast, , , , , fg] = row.cells;
        expect({min: mine.min, pts: mine.pts, reb: mine.reb, ast: mine.ast, fg: mine.fg}, `${row.pid} in ${gid}`).toEqual({min, pts, reb, ast, fg});
        const p = lead[row.pid];
        await go(page, `#compare/${row.pid}/${row.pid === board[0].pid ? board[1].pid : board[0].pid}`, () => document.querySelectorAll('#cmp tr').length > 5);
        const cmp = await page.evaluate(() => Object.fromEntries([...document.querySelectorAll('#cmp tr')].map(tr => [tr.cells[1].textContent, tr.cells[0].textContent])));
        expect(cmp.Points, `${p.name}: page vs compare`).toBe(mine.pts_avg);
        expect(cmp['FG%'], `${p.name}: page vs compare`).toBe(mine.fg_pct);
        await go(page, '#leaders/pts', () => document.querySelectorAll('#ld tbody tr').length > 0);
        const onBoard = await page.evaluate(pid => { const tr = document.querySelector(`#ld tr[data-pid="${pid}"]`); return tr ? tr.lastElementChild.textContent : null; }, row.pid);
        if (onBoard !== null) expect(onBoard, `${p.name}: page vs leaders`).toBe(mine.pts_avg);
      }
    }
  }
  expect(problems, 'the page reported errors').toEqual([]);
});

// Usage is the page's formula over the totals in leaders.json; RAPM, O-RAPM and D-RAPM are the values site_data.py wrote
// (already rounded by rounding.rnd), signed; every board runs from best to worst
test('usage and RAPM boards show the written values, best first', async ({page}) => {
  const problems = await prepare(page);
  await page.goto('./');
  await settled(page);
  const lead = await page.evaluate(() => fetch(`${META.base}leaders.json`).then(r => r.json()).then(d => Object.fromEntries(d.players.map(p => [p.pid, p]))));
  for (const stat of ['usg', 'rapm', 'orapm', 'drapm']) {
    await go(page, `#leaders/${stat}`, s => document.querySelector('#ld-tabs [aria-current="true"]')?.getAttribute('href') === `#leaders/${s}` && document.querySelectorAll('#ld tbody tr[data-pid]').length > 0, stat);
    const rows = await page.evaluate(() => [...document.querySelectorAll('#ld tbody tr[data-pid]')].map(tr => [tr.dataset.pid, tr.lastElementChild.textContent]));
    const vals = rows.map(([pid, v]) => {
      const p = lead[pid], shown = Number(v.replace('−', '-'));
      if (stat === 'usg') {
        const exact = 100 * (p.fga + 0.44 * p.fta + p.tov) * (p.tm_sec / 5) / (p.sec * (p.tm_fga + 0.44 * p.tm_fta + p.tm_tov));
        expect(Math.abs(shown - exact), `${p.name} USG%`).toBeLessThanOrEqual(0.05 + 1e-9);
      } else {
        expect(v, `${p.name} ${stat}`).toBe((p[stat] > 0 ? '+' : p[stat] < 0 ? '−' : '') + Math.abs(p[stat]).toFixed(1));
        expect(p.sec, `${p.name} plays 15 minutes a game`).toBeGreaterThanOrEqual(900 * p.gp);
      }
      return shown;
    });
    expect(vals, `${stat} best first`).toEqual([...vals].sort((x, y) => y - x));
  }
  expect(problems, 'the page reported errors').toEqual([]);
});

// The page rounds as rounding.avg does in Python (half up, exact): these answers are rounding.avg's, halves included.
test('the page rounds as rounding.py does', async ({page}) => {
  await prepare(page);
  await page.goto('./');
  await settled(page);
  const cases = [[1985, 100, 1, '19.9'], [1, 4, 1, '0.3'], [-1, 4, 1, '-0.2'], [5, 2, 0, '3'], [-5, 2, 0, '-2'], [-25, 100, 1, '-0.2'],
    [-1, 40, 1, '0.0'], [-3, 40, 1, '-0.1'], [5, 8, 2, '0.63'], [-5, 8, 2, '-0.62'], [2675, 1000, 2, '2.68'], [7, 0, 1, null]];
  const got = await page.evaluate(cs => cs.map(([n, d, k]) => /** @type {any} */ (window).eval(`rdiv(${n}, ${d}, ${k})`)), cases);
  expect(got).toEqual(cases.map(c => c[3]));
});

// The shot charts hold the FG column: each club's court on a game page has its box score's FGM dots and FGA - FGM
// crosses, and a player's court has his game log's for the game picked, and his season's for the season
const marks = el => ({made: el.querySelectorAll('.made circle').length, miss: (el.querySelector('path.miss').getAttribute('d').match(/M/g) || []).length});
const fg = cells => cells.reduce((a, c) => { const [m, n] = c.split('-').map(Number); return {made: a.made + m, miss: a.miss + n - m}; }, {made: 0, miss: 0});
test('shot charts match the box score and the game log', async ({page}) => {
  const problems = await prepare(page);
  await page.goto('./#games/2026-10-21');
  await settled(page);
  const gid = await page.evaluate(() => document.querySelector('#gm-list a.card').dataset.gid);
  await go(page, `#game/${gid}`, () => document.querySelectorAll('#gm-shots svg').length === 2);
  for (const code of await page.$$eval('#gm-box table', ts => ts.map(t => t.dataset.team))) {
    const box = await page.$eval(`#gm-box table[data-team="${code}"] tr.tot`, tr => tr.cells[11].textContent);
    expect(await page.$eval(`#gm-shots [data-team="${code}"]`, marks), `${code} in ${gid}`).toEqual(fg([box]));
  }
  const pid = await page.$$eval('#gm-box tr[data-pid]', trs => trs.find(tr => tr.cells.length > 2).dataset.pid);
  await page.click(`#gm-box tr[data-pid="${pid}"] a`);
  await page.waitForFunction(p => document.querySelector('#player').value === p && !document.querySelector('#sc').hidden, pid);
  const log = await page.$$eval('#log tr[data-gid]', trs => trs.filter(tr => tr.cells.length > 4).map(tr => tr.cells[10].textContent));
  expect(await page.$eval('#sc-court', marks), 'season chart vs game log').toEqual(fg(log));
  await page.selectOption('#sc-game', gid, {force: true});
  expect(await page.$eval('#sc-court', marks), 'game chart vs game log').toEqual(fg([await page.$eval(`#log tr[data-gid="${gid}"]`, tr => tr.cells[10].textContent)]));
  expect(problems, 'the page reported errors').toEqual([]);
});

// Lineups hold the box score's plus-minus: a player's points for and against on the floor add up to his game log's +/-,
// on − off is the difference of the two shown rows, and each net is its ORtg minus its DRtg as shown
const num = s => s === '–' ? null : Number(s.replace('−', '-'));
test('lineups and on/off agree with the game log', async ({page}) => {
  const problems = await prepare(page);
  await page.goto('./#games/2026-10-21');
  await settled(page);
  const gid = await page.evaluate(() => document.querySelector('#gm-list a.card').dataset.gid);
  await go(page, `#game/${gid}`, () => document.querySelectorAll('#gm-box table').length === 2);
  for (const pid of await page.$$eval('#gm-box tr[data-pid]', trs => trs.filter(tr => tr.cells.length > 2).slice(0, 12).map(tr => tr.dataset.pid))) {
    const code = await page.$eval(`#gm-box tr[data-pid="${pid}"]`, tr => tr.closest('table').dataset.team);
    await go(page, `#${code}/${pid}`, p => document.querySelector('#player').value === p && !document.querySelector('#lu').hidden, pid);
    const pm = await page.$$eval('#log tr[data-gid]', trs => trs.filter(tr => tr.cells.length > 4).reduce((a, tr) => a + Number(tr.cells[13].textContent.replace('−', '-')), 0));
    const oo = await page.$$eval('#onoff tbody tr', trs => trs.map(tr => [...tr.cells].slice(1).map(td => td.textContent)));
    expect(num(oo[0][0]), `${pid}: on-court +/- vs game log`).toBe(pm);
    for (const k of [1, 2, 3]) if (num(oo[0][k]) != null && num(oo[1][k]) != null) expect(num(oo[2][k]), `${pid}: on − off`).toBeCloseTo(num(oo[0][k]) - num(oo[1][k]), 6);
    const fives = await page.$$eval('#fives tbody tr', trs => trs.map(tr => ({n: tr.dataset.five.split(',').length, c: [...tr.cells].slice(1).map(td => td.textContent)})));
    expect(fives.length).toBeGreaterThan(0);
    for (const f of fives) {
      expect(f.n, 'four teammates').toBe(4);
      if (num(f.c[2]) != null && num(f.c[3]) != null) expect(num(f.c[4]), `${pid}: net`).toBeCloseTo(num(f.c[2]) - num(f.c[3]), 6);
    }
  }
  expect(problems, 'the page reported errors').toEqual([]);
});
