// Shot types: the Player page's shot chart panel carries, under the zone table, his attempts by type (the sixth field of a
// shot row in shots/<CODE>.json) with FG and FG% and the league's FG% on that type (shots/league.json types), most attempts
// first, for the season and for a game picked; the types add up to the zone table's FG.
import {test, expect} from '@playwright/test';
import {DESKTOP, PHONE, prepare, settled, go, noSidewaysScroll} from './site.js';

const pct = (page, m, n) => page.evaluate(([a, b]) => /** @type {any} */ (window).eval(`pct(${a}, ${b})`), [m, n]);

for (const [name, use, lang] of [['desktop', DESKTOP, 'en'], ['phone', PHONE, 'tr']]) {
  test.describe(`shot types (${name}, ${lang})`, () => {
    test.use(use);
    test('the shot type table splits his attempts by type against the league, most attempts first', async ({page}, info) => {
      const problems = await prepare(page, {lang, theme: lang === 'tr' ? 'dark' : 'light'});
      await page.goto('./');
      await settled(page);
      await go(page, '#BOS', () => !document.querySelector('#sc-types').hidden && document.querySelectorAll('#sc-types tr[data-type]').length > 0);
      await page.click('#sc > summary');
      const pid = await page.evaluate(() => document.querySelector('#player').value);
      const [f, lg] = await page.evaluate(() => Promise.all(['shots/BOS.json', 'shots/league.json'].map(p => fetch(`${META.base}${p}`).then(r => r.json()))));
      const check = async (gid, what) => {
        const rows = f.players[pid].filter(r => !gid || f.games[r[0]] === gid);
        const want = lg.types.map((_, k) => [k, rows.filter(r => r[5] === k).reduce((a, r) => a + r[3], 0), rows.filter(r => r[5] === k).length])
          .filter(r => r[2]).sort((a, b) => b[2] - a[2] || a[0] - b[0]);
        const shown = await page.$$eval('#sc-types tr[data-type]', trs => trs.map(tr => [Number(tr.dataset.type), ...[...tr.cells].slice(1).map(td => td.textContent)]));
        expect(shown.map(s => s[0]), `${what}: types, most attempts first`).toEqual(want.map(w => w[0]));
        for (const [i, [k, m, n]] of want.entries()) {
          expect(shown[i].slice(1), `${what}: type ${k}`).toEqual([`${m}-${n}`, await pct(page, m, n), await pct(page, ...lg.types[k])]);
        }
        const zoneFg = await page.$$eval('#sc-zones tr[data-z]', trs => trs.map(tr => tr.cells[1].textContent.split('-').map(Number)).reduce((a, [m, n]) => [a[0] + m, a[1] + n], [0, 0]));
        expect(want.reduce((a, [, m, n]) => [a[0] + m, a[1] + n], [0, 0]), `${what}: types add up to the zones`).toEqual(zoneFg);
        expect(await page.$$eval('#sc-types th', ths => ths.length), `${what}: four columns`).toBe(4);
      };
      await check('', 'season');
      const gid = await page.evaluate(() => [...document.querySelectorAll('#sc-game option')].map(o => o.value).find(Boolean));
      await page.selectOption('#sc-game', gid, {force: true});
      await check(gid, `game ${gid}`);
      await page.selectOption('#sc-game', '', {force: true});
      await page.locator('#sc-types').scrollIntoViewIfNeeded();
      await page.screenshot({path: info.outputPath(`player-${name}-${lang}.png`)});
      await noSidewaysScroll(page, 'shot type table');
      expect(problems, 'the page reported errors').toEqual([]);
    });
  });
}
