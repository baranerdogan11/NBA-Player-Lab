// Clutch splits (clutch.json): Leaders' Clutch board lists every player above the floor (a minute of clutch time per club
// game) by clutch points, a heading re-ranks it; the Player page's clutch line under the season tiles shows once he has
// played clutch time, within his game log's totals; the club page's Closing five opens on its clutch record, its results
// in the games clutch.json lists as games.json has them. Every value is computed here with the site's rounding rule.
import {test, expect} from '@playwright/test';
import {DESKTOP, PHONE, prepare, settled, go, noSidewaysScroll} from './site.js';

const rq = (num, den, d) => Math.floor((2 * num * 10 ** d + den) / (2 * den));
const fix = (q, d) => { const s = String(Math.abs(q)).padStart(d + 1, '0'); return `${q < 0 ? '-' : ''}${s.slice(0, -d)}.${s.slice(-d)}`; };
const loc = (s, lang) => lang === 'tr' ? s.replace('.', ',') : s;
const pct = (m, a, lang) => a ? loc(fix(rq(100 * m, a, 1), 1), lang) : '–';
const min = ds => { const s = rq(ds, 10, 0); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`; };
const signed = n => n < 0 ? `−${-n}` : n === 0 ? '0' : `+${n}`;
const KEY = {pts: c => c[2], min: c => c[1], fgp: c => c[4] ? rq(100 * c[3], c[4], 1) : -1, pm: c => c[11]};

for (const [name, use, lang] of [['desktop', DESKTOP, 'en'], ['phone', PHONE, 'tr']]) {
  test.describe(`clutch (${name}, ${lang})`, () => {
    test.use(use);

    test('Leaders ranks clutch points above the floor, and a heading re-ranks the board', async ({page}, info) => {
      const problems = await prepare(page, {lang, theme: lang === 'tr' ? 'dark' : 'light'});
      await page.goto('./');
      await settled(page);
      const [L, C] = await page.evaluate(() => Promise.all(['leaders.json', 'clutch.json'].map(p => fetch(`${META.base}${p}`).then(r => r.json()))));
      const gp = await page.evaluate(() => Object.fromEntries(IDX.teams.map(t => [t.code, t.gp])));
      await go(page, '#leaders/clutch', () => !document.querySelector('#ld-clutch').hidden && document.querySelectorAll('#ld-cl tbody tr').length > 0);
      expect(await page.getAttribute('#ld-tabs a[aria-current="true"]', 'href')).toBe('#leaders/clutch');
      const want = by => L.players.filter(p => C.players[p.pid] && gp[p.team] && C.players[p.pid][1] >= 600 * gp[p.team])
        .sort((x, y) => KEY[by](C.players[y.pid]) - KEY[by](C.players[x.pid]) || x.name.localeCompare(y.name)).slice(0, 25)
        .map(p => { const c = C.players[p.pid]; return [p.pid, String(c[0]), min(c[1]), String(c[2]), `${c[3]}-${c[4]}`, pct(c[3], c[4], lang), `${c[5]}-${c[6]}`, `${c[7]}-${c[8]}`, signed(c[11])]; });
      const rows = () => page.evaluate(() => [...document.querySelectorAll('#ld-cl tbody tr[data-pid]')].map(tr => [tr.dataset.pid, ...[...tr.cells].slice(3).map(td => td.textContent)]));
      const pts = want('pts');
      expect(pts.length, 'players above the floor in the fixture').toBeGreaterThan(3);
      expect(await rows()).toEqual(pts);
      // places are shared on equal points
      const places = await page.evaluate(() => [...document.querySelectorAll('#ld-cl tbody tr')].map(tr => +tr.cells[0].textContent));
      places.forEach((r, i) => expect(r, `row ${i}`).toBe(i && pts[i][3] === pts[i - 1][3] ? places[i - 1] : i + 1));
      for (const k of ['fgp', 'pm', 'min']) {
        await page.click(`#ld-cl th[data-sort="${k}"] button`);
        await page.waitForFunction(s => document.querySelector('#ld-cl th[aria-sort]')?.dataset.sort === s, k);
        expect(await rows(), `ranked by ${k}`).toEqual(want(k));
      }
      // the same heading again goes back to points
      await page.click('#ld-cl th[data-sort="min"] button');
      await page.waitForFunction(() => document.querySelector('#ld-cl th[aria-sort]')?.dataset.sort === 'pts');
      expect(await rows()).toEqual(pts);
      await page.locator('#ld-clutch').screenshot({path: info.outputPath(`leaders-${name}-${lang}.png`)});
      await noSidewaysScroll(page, 'clutch board');
      expect(problems, 'the page reported errors').toEqual([]);
    });

    test('the Player page shows his clutch line once he has clutch time, within his game log', async ({page}, info) => {
      const problems = await prepare(page, {lang, theme: lang === 'tr' ? 'dark' : 'light'});
      await page.goto('./');
      await settled(page);
      const [L, C] = await page.evaluate(() => Promise.all(['leaders.json', 'clutch.json'].map(p => fetch(`${META.base}${p}`).then(r => r.json()))));
      const withC = L.players.find(p => C.players[p.pid] && C.players[p.pid][1] > 0);
      const without = L.players.find(p => p.team === withC.team && !C.players[p.pid] && p.gp > 0);
      await go(page, `#${withC.team}/${withC.pid}`, p => document.querySelector('#player').value === p && !document.querySelector('#clutch').hidden, withC.pid);
      const c = C.players[withC.pid];
      const got = await page.evaluate(() => Object.fromEntries([...document.querySelectorAll('#clutch span[data-k]')].map(s => [s.dataset.k, s.querySelector('b').textContent])));
      expect(got).toEqual({g: String(c[0]), min: min(c[1]), pts: String(c[2]), fg: `${c[3]}-${c[4]}`, fg3: `${c[5]}-${c[6]}`, ft: `${c[7]}-${c[8]}`, pm: signed(c[11])});
      // within his game log: clutch games, points, field goals and free throws never above the season's
      const log = await page.evaluate(() => [...document.querySelectorAll('#log tbody tr')].filter(tr => tr.cells.length > 5).map(tr => [+tr.cells[4].textContent, ...tr.cells[10].textContent.split('-').map(Number), ...tr.cells[12].textContent.split('-').map(Number)]));
      const tot = log.reduce((a, r) => a.map((x, i) => x + r[i]), [0, 0, 0, 0, 0]);
      expect(c[0]).toBeLessThanOrEqual(log.length);
      expect([c[2], c[3], c[4], c[7], c[8]].every((x, i) => x <= tot[i]), `${withC.pid} clutch within ${tot}`).toBe(true);
      await page.locator('#tiles').screenshot({path: info.outputPath(`player-${name}-${lang}.png`)});
      await page.locator('#clutch').screenshot({path: info.outputPath(`player-line-${name}-${lang}.png`)});
      await noSidewaysScroll(page, 'player clutch line');
      if (without) {
        await go(page, `#${without.team}/${without.pid}`, p => document.querySelector('#player').value === p && document.querySelector('#log tbody tr') !== null, without.pid);
        await expect(page.locator('#clutch')).toBeHidden();
      }
      expect(problems, 'the page reported errors').toEqual([]);
    });

    test('the club page opens Closing five on its clutch record, its results in those games', async ({page}, info) => {
      const problems = await prepare(page, {lang, theme: lang === 'tr' ? 'dark' : 'light'});
      await page.goto('./');
      await settled(page);
      const [C, G] = await page.evaluate(() => Promise.all(['clutch.json', 'games.json'].map(p => fetch(`${META.base}${p}`).then(r => r.json()))));
      const code = Object.keys(C.teams).sort().find(k => C.teams[k][0] > 1);
      const mine = G.games.filter(g => C.games[g.gid] && (g.home === code || g.away === code));
      const w = mine.filter(g => (g.home === code) === (g.hs > g.as)).length;
      const ds = mine.reduce((s, g) => s + C.games[g.gid].ds, 0);
      const pf = mine.reduce((s, g) => s + C.games[g.gid][code][0], 0), pa = mine.reduce((s, g) => s + C.games[g.gid][g.home === code ? g.away : g.home][0], 0);
      await go(page, `#team/${code}`, c => document.body.dataset.page === 'team' && document.querySelector('#tm-close-sec').dataset.code === c && document.querySelector('#tm-clutch b'), code);
      await page.click('#tm-close-sec > summary');
      await expect(page.locator('#tm-clutch')).toBeVisible();
      const got = await page.evaluate(() => Object.fromEntries([...document.querySelectorAll('#tm-clutch span[data-k]')].map(s => [s.dataset.k, s.querySelector('b').textContent])));
      expect(got).toEqual({g: String(mine.length), rec: `${w}-${mine.length - w}`, min: min(ds), pts: `${pf}-${pa}`, pm: signed(pf - pa)});
      await page.locator('#tm-close-sec').screenshot({path: info.outputPath(`club-${name}-${lang}.png`)});
      await noSidewaysScroll(page, 'club clutch record');
      expect(problems, 'the page reported errors').toEqual([]);
    });
  });
}
