// Duos: the Game page lists each club's five passer → scorer pairs with the most assists in that game, ranked by assists
// then points, and every passer's pairs in the file add up to his AST in the box score beside them; the Player page lists
// the three team-mates who assisted him most this season and the three he assisted most, summed over the season's games.
import {test, expect} from '@playwright/test';
import {DESKTOP, PHONE, prepare, settled, go, noSidewaysScroll} from './site.js';

const file = (page, code) => page.evaluate(c => fetch(`${META.base}assists/${c}.json`).then(r => r.json()), code);
const top = (rows, n) => [...rows].sort((a, b) => (b.ast - a.ast) || (b.pts - a.pts)).slice(0, n);

for (const [name, use, lang] of [['desktop', DESKTOP, 'en'], ['phone', PHONE, 'tr']]) {
  test.describe(`duos (${name}, ${lang})`, () => {
    test.use(use);
    test('the Game page shows each club\'s top pairs, and every passer\'s pairs add up to his box-score AST', async ({page}, info) => {
      const problems = await prepare(page, {lang, theme: lang === 'tr' ? 'dark' : 'light'});
      await page.goto('./');
      await settled(page);
      const gid = await page.evaluate(() => fetch(`${META.base}games.json`).then(r => r.json()).then(d => d.games.find(g => g.hs != null).gid));
      await go(page, `#game/${gid}`, () => !document.querySelector('#gm-duo').hidden && document.querySelectorAll('#gm-duos a[data-pair]').length > 0);
      const g = await page.evaluate(id => fetch(`${META.base}games/${id}.json`).then(r => r.json()), gid);
      for (const code of [g.away, g.home]) {
        const f = await file(page, code), k = f.games.indexOf(gid);
        const rows = f.pairs.filter(r => r[0] === k).map(([, a, b, ast, pts]) => ({a, b, ast, pts}));
        const given = {};
        for (const r of rows) given[r.a] = (given[r.a] || 0) + r.ast;
        expect(given).toEqual(Object.fromEntries(g.box[code].filter(x => x.ast).map(x => [x.pid, x.ast])));
        const shown = await page.evaluate(c => [...document.querySelectorAll(`#gm-duos [data-team="${c}"] a`)].map(a => [a.dataset.pair, a.querySelector('.v').firstChild.textContent, a.querySelector('.nm small').textContent]), code);
        const want = top(rows, 5);
        expect(shown.map(s => s[0])).toEqual(want.map(r => `${r.a}>${r.b}`));
        expect(shown.map(s => s[1])).toEqual(want.map(r => String(r.ast)));
        expect(shown.map(s => s[2].split(' ')[0])).toEqual(want.map(r => String(r.pts)));
      }
      await page.locator('#gm-duo').scrollIntoViewIfNeeded();
      await page.screenshot({path: info.outputPath(`game-${name}-${lang}.png`)});
      await noSidewaysScroll(page, 'game duos');
      await page.click('#gm-duos a[data-pair]');
      await page.waitForFunction(() => document.body.dataset.page === 'player');
      expect(problems, 'the page reported errors').toEqual([]);
    });

    test('the Player page lists who assisted him most and whom he assisted most this season', async ({page}, info) => {
      const problems = await prepare(page, {lang, theme: lang === 'tr' ? 'dark' : 'light'});
      await page.goto('./');
      await settled(page);
      await go(page, '#BOS', () => !document.querySelector('#duo').hidden && document.querySelectorAll('#duo-cols a').length > 0);
      const pid = await page.evaluate(() => document.querySelector('#player').value);
      const f = await file(page, 'BOS'), sum = {in: {}, out: {}};
      for (const [, a, b, ast, pts] of f.pairs) {
        const side = b === pid ? 'in' : a === pid ? 'out' : null;
        if (!side) continue;
        const o = side === 'in' ? a : b, d = sum[side][o] || (sum[side][o] = {pid: o, ast: 0, pts: 0});
        d.ast += ast;
        d.pts += pts;
      }
      for (const side of ['in', 'out']) {
        const shown = await page.evaluate(s => [...document.querySelectorAll(`#duo-cols [data-side="${s}"] a`)].map(a => [a.querySelector('.v').firstChild.textContent, a.querySelector('.nm small').textContent.split(' ')[0]]), side);
        const want = top(Object.values(sum[side]), 3);
        expect(shown).toEqual(want.map(d => [String(d.ast), String(d.pts)]));
      }
      await page.locator('#duo').scrollIntoViewIfNeeded();
      await page.screenshot({path: info.outputPath(`player-${name}-${lang}.png`)});
      await noSidewaysScroll(page, 'player duos');
      expect(problems, 'the page reported errors').toEqual([]);
    });
  });
}
