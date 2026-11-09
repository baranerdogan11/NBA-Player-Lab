// Free throws attempt by attempt: the Player page's Free throws section lists his made-attempted and FT% by kind (ft.json),
// the kinds he shot only, each beside the league's, and his trips add up to the FT column of his game log; Leaders ranks
// the first of two and pressure free throws above their floors, best and worst; the club page adds the club's FT% and
// its opponents' beside the Four Factors (ratings.json). Every value is computed here with the site's rounding rule.
import {test, expect} from '@playwright/test';
import {DESKTOP, PHONE, prepare, settled, go, noSidewaysScroll} from './site.js';

const rq = (num, den, d) => Math.floor((2 * num * 10 ** d + den) / (2 * den));
const fix = (q, d) => { const s = String(Math.abs(q)).padStart(d + 1, '0'); return `${q < 0 ? '-' : ''}${s.slice(0, -d)}.${s.slice(-d)}`; };
const pct = (m, a, lang) => a ? (lang === 'tr' ? fix(rq(100 * m, a, 1), 1).replace('.', ',') : fix(rq(100 * m, a, 1), 1)) : '–';
const ORDER = [0, 1, 2, 5, 3, 4, 6];

for (const [name, use, lang] of [['desktop', DESKTOP, 'en'], ['phone', PHONE, 'tr']]) {
  test.describe(`free throws (${name}, ${lang})`, () => {
    test.use(use);
    test('the Player page lists his free throws by kind beside the league, adding up to his FT column', async ({page}, info) => {
      const problems = await prepare(page, {lang, theme: lang === 'tr' ? 'dark' : 'light'});
      await page.goto('./');
      await settled(page);
      const F = await page.evaluate(() => fetch(`${META.base}ft.json`).then(r => r.json()));
      await go(page, '#BOS', () => document.querySelectorAll('#player option').length > 0);
      const pids = await page.evaluate(() => [...document.querySelectorAll('#player option')].map(o => o.value).filter(Boolean));
      let seen = 0;
      for (const pid of pids.slice(0, 5)) {
        await go(page, `#BOS/${pid}`, p => document.querySelector('#player').value === p && document.querySelector('#log tbody tr') !== null, pid);
        const c = F.players[pid];
        if (!c) {
          await expect(page.locator('#ft')).toBeHidden();
          continue;
        }
        await expect(page.locator('#ft')).toBeVisible();
        // closed when the page opens; moving from player to player keeps it as the reader left it
        if (!seen) expect(await page.evaluate(() => document.querySelector('#ft').open), 'closed on arrival').toBe(false);
        if (!await page.evaluate(() => document.querySelector('#ft').open)) await page.locator('#ft summary').click();
        const rows = await page.evaluate(() => [...document.querySelectorAll('#ft-tbl tbody tr')].map(tr => [tr.dataset.k, ...[...tr.cells].slice(1).map(td => td.textContent)]));
        const want = ORDER.filter(i => c[i][1]).map(i => [F.kinds[i], `${c[i][0]}-${c[i][1]}`, pct(c[i][0], c[i][1], lang), pct(F.league[i][0], F.league[i][1], lang)]);
        expect(rows, pid).toEqual(want);
        // the trips (the first five kinds) are his free throws, the FT column of his game log
        const log = await page.evaluate(() => [...document.querySelectorAll('#log tbody tr')].map(tr => tr.cells[12]?.textContent).filter(s => s && /^\d+-\d+$/.test(s)));
        const sum = log.reduce((a, s) => { const [m, n] = s.split('-').map(Number); return [a[0] + m, a[1] + n]; }, [0, 0]);
        expect([0, 1, 2, 3, 4].reduce((a, i) => [a[0] + c[i][0], a[1] + c[i][1]], [0, 0]), `${pid} trips add up to his FT`).toEqual(sum);
        seen++;
      }
      expect(seen, 'players with free throws in the fixture').toBeGreaterThan(0);
      await page.locator('#ft').scrollIntoViewIfNeeded();
      await page.locator('#ft').screenshot({path: info.outputPath(`player-${name}-${lang}.png`)});
      await noSidewaysScroll(page, 'player free throws');
      expect(problems, 'the page reported errors').toEqual([]);
    });

    test('Leaders ranks the first of two and pressure free throws, best and worst, above the floors', async ({page}, info) => {
      const problems = await prepare(page, {lang, theme: lang === 'tr' ? 'dark' : 'light'});
      await page.goto('./');
      await settled(page);
      const [L, F] = await page.evaluate(() => Promise.all(['leaders.json', 'ft.json'].map(p => fetch(`${META.base}${p}`).then(r => r.json()))));
      const gp = await page.evaluate(() => Object.fromEntries(IDX.teams.map(t => [t.code, t.gp])));
      await go(page, '#leaders/ftsplit', () => !document.querySelector('#ld-ft').hidden && document.querySelectorAll('#ld-ft1-up tr').length > 1);
      const pool = L.players.filter(p => F.players[p.pid] && gp[p.team] && p.fta >= 3 * gp[p.team]);
      const board = (k, dir, extra) => pool.filter(p => F.players[p.pid][k][1] > 0 && extra(p)).map(p => { const [m, a] = F.players[p.pid][k]; return {p, m, a, v: rq(100 * m, a, 1)}; })
        .sort((x, y) => dir * (y.v - x.v) || y.a - x.a || x.p.name.localeCompare(y.p.name)).slice(0, 10).map(r => [r.p.pid, `${r.m}-${r.a}`, pct(r.m, r.a, lang)]);
      const shown = id => page.evaluate(i => [...document.querySelectorAll(`#${i} tr[data-pid]`)].map(tr => [tr.dataset.pid, tr.cells[2].textContent, tr.cells[3].textContent]), id);
      const any = () => true, press = p => 3 * F.players[p.pid][6][1] >= gp[p.team];
      const first = board(0, 1, any);
      expect(first.length, 'the fixture has players on the first-of-two board').toBeGreaterThan(0);
      expect(await shown('ld-ft1-up')).toEqual(first);
      expect(await shown('ld-ft1-dn')).toEqual(board(0, -1, any));
      expect(await shown('ld-press-up')).toEqual(board(6, 1, press));
      expect(await shown('ld-press-dn')).toEqual(board(6, -1, press));
      await expect(page.locator('#ld-sec')).toBeHidden();
      await page.screenshot({path: info.outputPath(`leaders-${name}-${lang}.png`), fullPage: true});
      await noSidewaysScroll(page, 'free-throw boards');
      expect(problems, 'the page reported errors').toEqual([]);
    });

    test('the club page shows its FT% and its opponents’ beside the Four Factors', async ({page}, info) => {
      const problems = await prepare(page, {lang, theme: lang === 'tr' ? 'dark' : 'light'});
      await page.goto('./');
      await settled(page);
      const R = await page.evaluate(() => fetch(`${META.base}ratings.json`).then(r => r.json()));
      await go(page, '#team/BOS', () => document.querySelector('#tm-ff td[data-k="ftp"]') !== null);
      const c = R.teams.find(x => x.code === 'BOS');
      const got = await page.evaluate(() => ['ftp', 'oftp'].map(k => document.querySelector(`#tm-ff td[data-k="${k}"] .v`).textContent));
      expect(got).toEqual([pct(c.for.ftm, c.for.fta, lang), pct(c.against.ftm, c.against.fta, lang)]);
      await page.locator('#tm-ff-sec summary').click();
      await page.locator('#tm-ff-sec').screenshot({path: info.outputPath(`club-${name}-${lang}.png`)});
      await noSidewaysScroll(page, 'club four factors');
      expect(problems, 'the page reported errors').toEqual([]);
    });
  });
}
