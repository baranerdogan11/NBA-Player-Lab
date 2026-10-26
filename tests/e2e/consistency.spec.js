// Every number agrees across pages to the decimal: for every player in the first night's games, his line on the game page
// is the row of his game log, his season averages on his page equal his Compare and Leaders values, and each box score
// adds up to the final.
import {test, expect} from '@playwright/test';
import {DESKTOP, prepare, settled, go} from './site.js';

test.use(DESKTOP);

test('a game, the players in it, their pages, compare and leaders agree', async ({page}) => {
  test.setTimeout(240_000);
  const problems = await prepare(page);
  await page.goto('./?l#games/2026-10-21');
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
  await page.goto('./?l#games/2026-10-21');
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

// The zones split the FG column along the 3P column: for the season and for each game picked, the five rows add up to the
// game log's FG and the two three-point rows to its 3P; each FG% is its row's makes over attempts by the one rounding
// rule, the league column is shots/league.json, and a zone is tinted only past five attempts and only off the league's
test('shot zones add up to the game log and compare with the league', async ({page}) => {
  test.setTimeout(120_000);
  const problems = await prepare(page);
  await page.goto('./?l#games/2026-10-21');
  await settled(page);
  const gid = await page.evaluate(() => document.querySelector('#gm-list a.card').dataset.gid);
  await go(page, `#game/${gid}`, () => document.querySelectorAll('#gm-box table').length === 2);
  const pid = await page.$$eval('#gm-box tr[data-pid]', trs => trs.find(tr => tr.cells.length > 2).dataset.pid);
  await page.click(`#gm-box tr[data-pid="${pid}"] a`);
  await page.waitForFunction(p => document.querySelector('#player').value === p && document.querySelectorAll('#sc-zones tr[data-z]').length === 5, pid);
  const league = await page.evaluate(() => fetch(`${META.base}shots/league.json`).then(r => r.json()).then(d => d.zones));
  const read = () => page.evaluate(() => ({
    rows: [...document.querySelectorAll('#sc-zones tr[data-z]')].map(tr => ({fg: tr.cells[1].textContent, pct: tr.cells[2].textContent, lg: tr.cells[3].textContent, heat: tr.querySelector('i').className})),
    tint: Object.fromEntries([...document.querySelectorAll('#sc-court path[data-z]')].map(p => [p.dataset.z, p.getAttribute('class').slice(2)])),
  }));
  const check = async (logFg, log3p, what) => {
    const {rows, tint} = await read();
    const n = rows.map(r => r.fg.split('-').map(Number));
    const sum = ns => ns.reduce((a, [m, k]) => [a[0] + m, a[1] + k], [0, 0]).join('-');
    expect(sum(n), `${what}: zones vs FG`).toBe(sum(logFg.map(c => c.split('-').map(Number))));
    expect(sum(n.slice(3)), `${what}: three-point zones vs 3P`).toBe(sum(log3p.map(c => c.split('-').map(Number))));
    const rd = (a, b) => page.evaluate(([x, y]) => /** @type {any} */ (window).eval(`rq(100 * ${x}, ${y})`), [a, b]);
    for (const [z, r] of rows.entries()) {
      expect(r.pct, `${what}: zone ${z} FG%`).toBe(n[z][1] ? await page.evaluate(([m, k]) => /** @type {any} */ (window).eval(`pct(${m}, ${k})`), n[z]) : '–');
      expect(r.lg, `${what}: zone ${z} league`).toBe(await page.evaluate(([m, k]) => /** @type {any} */ (window).eval(`pct(${m}, ${k})`), league[z]));
      const d = n[z][1] >= 5 ? (await rd(...n[z])) - (await rd(...league[z])) : 0;
      const want = d > 0 ? 'hi' : d < 0 ? 'lo' : '';
      expect(r.heat, `${what}: zone ${z} swatch`).toBe(want);
      expect(tint[z] || '', `${what}: zone ${z} tint`).toBe(want);
    }
  };
  const log = await page.$$eval('#log tr[data-gid]', trs => trs.filter(tr => tr.cells.length > 4).map(tr => [tr.dataset.gid, tr.cells[10].textContent, tr.cells[11].textContent]));
  await check(log.map(x => x[1]), log.map(x => x[2]), 'season');
  expect(Object.keys((await read()).tint).length, 'a season has tinted zones').toBeGreaterThan(0);
  for (const [g, f, t3] of log.slice(0, 3)) {
    await page.selectOption('#sc-game', g, {force: true});
    await check([f], [t3], g);
  }
  expect(problems, 'the page reported errors').toEqual([]);
});

// Lineups hold the box score's plus-minus: a player's points for and against on the floor add up to his game log's +/-,
// on − off is the difference of the two shown rows, and each net is its ORtg minus its DRtg as shown
const num = s => s === '–' ? null : Number(s.replace('−', '-'));
test('lineups and on/off agree with the game log', async ({page}) => {
  const problems = await prepare(page);
  await page.goto('./?l#games/2026-10-21');
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

// A game's lineups: at most five units a club, most minutes first, each row's +/- its points for minus against; the
// fixture plays four or fewer fives a game, so every unit is shown and their points add up to the final
test('a game\'s lineups add up to its score', async ({page}) => {
  const problems = await prepare(page);
  await page.goto('./?l#games/2026-10-21');
  await settled(page);
  const gid = await page.evaluate(() => document.querySelector('#gm-list a.card').dataset.gid);
  await go(page, `#game/${gid}`, () => !document.querySelector('#gm-lu').hidden);
  const score = await page.$$eval('#gm-board .score span', s => s.map(x => +x.textContent));
  const sides = await page.$$eval('#gm-fives > div', ds => ds.map(d => [...d.querySelectorAll('tbody tr')].map(tr => ({
    n: tr.dataset.five.split(',').length, faces: tr.querySelectorAll('.face').length, min: tr.cells[1].textContent, pts: tr.cells[2].textContent, pm: tr.cells[3].textContent}))));
  expect(sides.length).toBe(2);
  sides.forEach((rows, i) => {
    expect(rows.length).toBeGreaterThan(0);
    expect(rows.length).toBeLessThanOrEqual(5);
    const sec = rows.map(r => r.min.split(':').reduce((m, s) => 60 * +m + +s));
    expect(sec, 'most minutes first').toEqual([...sec].sort((a, b) => b - a));
    for (const r of rows) {
      const [f, a] = r.pts.split('-').map(Number);
      expect([r.n, r.faces]).toEqual([5, 5]);
      expect(Number(r.pm.replace('−', '-'))).toBe(f - a);
    }
    expect(rows.reduce((s, r) => s + Number(r.pts.split('-')[0]), 0), 'points add up to the final').toBe(score[i]);
  });
  expect(problems, 'the page reported errors').toEqual([]);
});

// A game's flow ends on the scoreboard's final and passes each period's score at the period's end; its last scoring
// play reads the final, and the lead changes, ties and biggest leads are the ones its margins give
test('a game\'s flow ends on the final', async ({page}) => {
  const problems = await prepare(page);
  await page.goto('./?l#games/2026-10-21');
  await settled(page);
  const gid = await page.evaluate(() => document.querySelector('#gm-list a.card').dataset.gid);
  await go(page, `#game/${gid}`, () => !document.querySelector('#gm-flow-sec').hidden);
  const [as, hs] = await page.$$eval('#gm-board .score span', s => s.map(x => +x.textContent));
  const g = await page.evaluate(id => fetch(`${META.base}games/${id}.json`).then(r => r.json()), gid);
  expect(g.flow.at(-1).slice(1), 'flow ends on the final').toEqual([hs, as]);
  let h = 0, a = 0;
  g.periods.forEach(([qh, qa], i) => {
    h += qh; a += qa;
    const end = i < 4 ? 7200 * (i + 1) : 28800 + 3000 * (i - 3);
    expect(g.flow.filter(p => p[0] <= end).at(-1).slice(1), `score after period ${i + 1}`).toEqual([h, a]);
  });
  await page.focus('#gm-flow');
  await page.keyboard.press('End');
  expect(await page.textContent('#gm-flow .fl-tip')).toContain(`${g.away} ${as} – ${hs} ${g.home}`);
  const m = [0, ...g.flow.map(p => p[1] - p[2])];
  let lc = 0, lead = 0, tied = 0;
  m.forEach((x, i) => { const s = Math.sign(x); if (s && lead && s !== lead) lc++; if (s) lead = s; if (i && !x && m[i - 1]) tied++; });
  const tiles = await page.$$eval('#gm-flow-sum .tile b', bs => bs.map(b => +b.textContent));
  expect(tiles).toEqual([lc, tied, Math.max(0, ...m.map(x => -x)), Math.max(0, ...m)]);
  expect(problems, 'the page reported errors').toEqual([]);
});

// Team ratings and the Four Factors: every value is the club's box scores (summed here from the game pages' JSON), the
// ratings are also what its lineup rows add up to, each rank is the value's place among the 30, and a heading sorts
// the clubs best first
test('team ratings and the Four Factors are the box scores\' and the lineups\'', async ({page}) => {
  test.setTimeout(120_000);
  const problems = await prepare(page);
  await page.goto('./?l#standings/ratings');
  await settled(page);
  await page.waitForFunction(() => document.querySelectorAll('#st-ratings tbody tr').length === 30);
  const read = id => page.$$eval(`#${id} tbody tr`, trs => Object.fromEntries(trs.map(tr => [tr.dataset.team,
    Object.fromEntries([...tr.querySelectorAll('td[data-k]')].map(td => [td.dataset.k, [td.querySelector('.v').textContent, td.dataset.r ? +td.dataset.r : null]]))])));
  const shown = await read('st-ratings');
  await go(page, '#standings/factors', () => document.querySelectorAll('#st-factors tbody tr').length === 30);
  Object.entries(await read('st-factors')).forEach(([c, v]) => Object.assign(shown[c], v));
  const want = await page.evaluate(async () => {
    const at = p => fetch(`${META.base}${p}`).then(r => r.json());
    const finals = (await at('games.json')).games.filter(g => g.hs != null);
    const K = ['pts', 'fgm', 'fga', 'fg3m', 'ftm', 'fta', 'oreb', 'dreb', 'tov'], zero = () => Object.fromEntries(K.map(k => [k, 0]));
    const T = Object.fromEntries(IDX.teams.map(x => [x.code, {f: zero(), a: zero(), games: 0}]));
    for (const g of finals) {
      const b = await at(`games/${g.gid}.json`), tot = c => { const s = zero(); for (const x of b.box[c]) for (const k of K) s[k] += x[k]; return s; };
      for (const [c, o] of [[g.home, g.away], [g.away, g.home]]) { const us = tot(c), them = tot(o); T[c].games++; for (const k of K) { T[c].f[k] += us[k]; T[c].a[k] += them[k]; } }
    }
    const lu = {};
    for (const c of Object.keys(T)) {
      const s = Array(10).fill(0);
      for (const r of (await at(`lineups/${c}.json`)).rows) r.slice(3).forEach((v, i) => { s[i] += v; });
      lu[c] = s;
    }
    return {T, lu};
  });
  const q = (n, d, dig = 1) => { const v = Math.floor((2 * n * 10 ** dig + d) / (2 * d)); return [v, dig]; };
  const str = ([v, dig]) => { const s = String(Math.abs(v)).padStart(dig + 1, '0'); return (v < 0 ? '-' : '') + `${s.slice(0, -dig)}.${s.slice(-dig)}`; };
  const P = x => 100 * (x.fga - x.oreb + x.tov) + 44 * x.fta;
  const ffs = (x, o) => ({efg: q(100 * (2 * x.fgm + x.fg3m), 2 * x.fga), tov: q(10000 * x.tov, 100 * (x.fga + x.tov) + 44 * x.fta), orb: q(100 * x.oreb, x.oreb + o.dreb), ftr: q(x.ftm, x.fga, 3)});
  const exp = {};
  for (const [c, {f, a, games}] of Object.entries(want.T)) {
    const ortg = q(10000 * f.pts, P(f)), drtg = q(10000 * a.pts, P(a)), net = [ortg[0] - drtg[0], 1];
    const d = ffs(a, f);
    exp[c] = {ortg, drtg, net, pace: q(72 * (P(f) + P(a)), 14400 * games), ...ffs(f, a), ...Object.fromEntries(Object.entries(d).map(([k, v]) => ['o' + k, v]))};
    const l = want.lu[c], lf = {pts: l[0], fga: l[2], oreb: l[3], tov: l[4], fta: l[5]}, la = {pts: l[1], fga: l[6], oreb: l[7], tov: l[8], fta: l[9]};
    expect([q(10000 * lf.pts, P(lf)), q(10000 * la.pts, P(la))], `${c}: lineups give the same ratings`).toEqual([ortg, drtg]);
  }
  const fmt = (k, v) => k === 'net' ? (v[0] > 0 ? '+' : '') + str(v).replace('-', '−') : /ftr$/.test(k) ? str(v).replace(/^0/, '') : str(v);
  const better = {drtg: -1, tov: -1, oefg: -1, oorb: -1, oftr: -1, otov: 1};
  for (const [c, cols] of Object.entries(shown)) {
    for (const [k, [text, rank]] of Object.entries(cols)) {
      expect(text, `${c} ${k}`).toBe(fmt(k, exp[c][k]));
      const dir = better[k] || 1;
      expect(rank, `${c} ${k} rank`).toBe(1 + Object.values(exp).filter(x => dir * (x[k][0] - exp[c][k][0]) > 0).length);
    }
  }
  await go(page, '#standings/ratings', () => document.querySelectorAll('#st-ratings tbody tr').length === 30);
  const order = () => page.$$eval('#st-ratings tbody tr', trs => trs.map(tr => tr.dataset.team));
  const first = await order();
  await page.click('#st-ratings th[data-sort="drtg"] button');
  const by = await order();
  expect(by.map(c => shown[c].drtg[1]), 'DRtg sorts best first').toEqual([...by.map(c => shown[c].drtg[1])].sort((x, y) => x - y));
  await page.click('#st-ratings th[data-sort="drtg"] button');
  expect(await order(), 'the same heading again restores the net rating order').toEqual(first);
  expect(first.map(c => exp[c].net[0]), 'net rating order').toEqual(first.map(c => exp[c].net[0]).sort((x, y) => y - x));
  expect(problems, 'the page reported errors').toEqual([]);
});
