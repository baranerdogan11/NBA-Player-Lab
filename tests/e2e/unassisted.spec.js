// Unassisted makes: the Player page's zone table carries each zone's assisted share of his makes and a line above it his
// unassisted makes, for the season and for a game picked, all from the made rows of assists/<CODE>.json; the makes there are
// the table's FG makes. The Leaders board ranks the unassisted share of makes from assists/league.json above its floor.
import {test, expect} from '@playwright/test';
import {DESKTOP, PHONE, prepare, settled, go, noSidewaysScroll} from './site.js';

const pct = (page, m, n) => page.evaluate(([a, b]) => /** @type {any} */ (window).eval(`pct(${a}, ${b})`), [m, n]);

for (const [name, use, lang] of [['desktop', DESKTOP, 'en'], ['phone', PHONE, 'tr']]) {
  test.describe(`unassisted (${name}, ${lang})`, () => {
    test.use(use);
    test('the zone table shows the assisted share by zone and the line his unassisted makes', async ({page}, info) => {
      const problems = await prepare(page, {lang, theme: lang === 'tr' ? 'dark' : 'light'});
      await page.goto('./');
      await settled(page);
      await go(page, '#BOS', () => !document.querySelector('#sc-unast').hidden && document.querySelectorAll('#sc-zones td.astd').length === 5);
      const pid = await page.evaluate(() => document.querySelector('#player').value);
      const f = await page.evaluate(() => fetch(`${META.base}assists/BOS.json`).then(r => r.json()));
      const check = async (gid, what) => {
        const rows = f.made.filter(r => r[1] === pid && (!gid || f.games[r[0]] === gid));
        const za = [0, 1, 2, 3, 4].map(z => rows.filter(r => r[2] === z).reduce((a, r) => [a[0] + r[3], a[1] + r[4]], [0, 0]));
        const shown = await page.evaluate(() => ({
          fg: [...document.querySelectorAll('#sc-zones tr[data-z]')].map(tr => Number(tr.cells[1].textContent.split('-')[0])),
          astd: [...document.querySelectorAll('#sc-zones td.astd')].map(td => td.textContent),
          line: document.querySelector('#sc-unast').hidden ? null : [...document.querySelectorAll('#sc-unast b')].map(b => b.textContent),
        }));
        expect(shown.fg, `${what}: made rows vs the table's makes`).toEqual(za.map(z => z[1]));
        for (const [z, [a, m]] of za.entries()) expect(shown.astd[z], `${what}: zone ${z}`).toBe(m ? await pct(page, a, m) : '–');
        const [a, m] = za.reduce((s, [x, y]) => [s[0] + x, s[1] + y], [0, 0]);
        expect(shown.line, `${what}: line`).toEqual(m ? [`${m - a}/${m}`, `${await pct(page, m - a, m)}%`] : null);
      };
      await check('', 'season');
      const gid = await page.evaluate(() => [...document.querySelectorAll('#sc-game option')].map(o => o.value).find(Boolean));
      await page.selectOption('#sc-game', gid, {force: true});
      await check(gid, `game ${gid}`);
      await page.selectOption('#sc-game', '', {force: true});
      await page.locator('#sc-zones').scrollIntoViewIfNeeded();
      await page.screenshot({path: info.outputPath(`player-${name}-${lang}.png`)});
      await noSidewaysScroll(page, 'zone table');
      expect(problems, 'the page reported errors').toEqual([]);
    });

    test('the Leaders board ranks the unassisted share of makes above its floor', async ({page}, info) => {
      const problems = await prepare(page, {lang, theme: lang === 'tr' ? 'dark' : 'light'});
      await page.goto('./');
      await settled(page);
      await go(page, '#leaders/uast', () => document.querySelector('#ld-tabs a[aria-current="true"]')?.getAttribute('href') === '#leaders/uast' && document.querySelectorAll('#ld tr[data-pid]').length > 0);
      const [A, L] = await page.evaluate(() => Promise.all(['assists/league.json', 'leaders.json'].map(p => fetch(`${META.base}${p}`).then(r => r.json()))));
      const gp = await page.evaluate(codes => Object.fromEntries(codes.map(c => [c, /** @type {any} */ (window).eval(`team(${JSON.stringify(c)})`)?.gp || 0])), [...new Set(L.players.map(p => p.team))]);
      const want = L.players.filter(p => A.players[p.pid] && p.gp > 0 && 10 * p.gp >= 7 * (gp[p.team] || 0) && 82 * A.players[p.pid][1] >= 300 * (gp[p.team] || 0))
        .map(p => ({pid: p.pid, name: p.name, a: A.players[p.pid][0], m: A.players[p.pid][1]}))
        .sort((x, y) => (y.m - y.a) / y.m - (x.m - x.a) / x.m || x.name.localeCompare(y.name)).slice(0, 25);
      const shown = await page.$$eval('#ld tr[data-pid]', trs => trs.map(tr => [tr.dataset.pid, tr.cells[4].textContent]));
      expect(shown.map(s => s[0])).toEqual(want.map(w => w.pid));
      for (const [i, w] of want.entries()) expect(shown[i][1]).toBe(await pct(page, w.m - w.a, w.m));
      await page.screenshot({path: info.outputPath(`leaders-${name}-${lang}.png`)});
      await noSidewaysScroll(page, 'unassisted board');
      expect(problems, 'the page reported errors').toEqual([]);
    });
  });
}
