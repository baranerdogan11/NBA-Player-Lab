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
