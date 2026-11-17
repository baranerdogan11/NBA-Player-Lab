// A shot's moment: on the Player page's chart and the Game page's two charts, a tap on a mark (or a mouse over it) rings it
// and shows a card under the court with the game (Player page) or the shooter (Game page), the period and clock, the score
// as he let it go (the row's score after the shot, a make's points taken off; his club first) and how it went; a second
// tap on the same mark puts the card away. Rows: shots/<CODE>.json [g, x, y, made, zone, type, dist, period, clock, own, opp].
import {test, expect} from '@playwright/test';
import {DESKTOP, PHONE, prepare, settled, go, noSidewaysScroll} from './site.js';

const ev = (page, expr) => page.evaluate(e => /** @type {any} */ (window).eval(e), expr);
// the page position of a court point, from the chart's own transform
const spot = (page, sel, x, y) => page.$eval(sel, (svg, [x, y]) => {
  const p = new DOMPoint(x, -y).matrixTransform(/** @type {any} */ (svg).getScreenCTM());
  return [p.x, p.y];
}, [x, y]);
// a row whose spot no other row in the list shares, so a tap on it can only pick it
const lone = rows => rows.find(r => r[1] != null && rows.filter(q => q[1] === r[1] && q[2] === r[2]).length === 1);
const expected = async (page, r, club, opp) => {
  const pts = r[4] >= 3 ? 3 : 2;
  return {when: `${await ev(page, `perShort(${r[7]})`)} ${await ev(page, `shotClock(${r[8]})`)}`, score: `${club} ${r[9] - (r[3] ? pts : 0)}-${r[10]} ${opp}`,
    made: await ev(page, `t(${JSON.stringify(`${r[3] ? 'Made' : 'Missed'} ${pts}-pointer`)})`)};
};
const card = (page, sel) => page.$eval(sel, el => ({hidden: /** @type {HTMLElement} */ (el).hidden,
  ...Object.fromEntries([...el.querySelectorAll('[data-k]')].map(x => [/** @type {HTMLElement} */ (x).dataset.k, x.textContent]))}));

for (const [name, use, lang] of [['desktop', DESKTOP, 'en'], ['phone', PHONE, 'tr']]) {
  test.describe(`shot context (${name}, ${lang})`, () => {
    test.use(use);
    test('a tap on a mark shows its game, period and clock, the score as he shot and how it went', async ({page}, info) => {
      const problems = await prepare(page, {lang, theme: lang === 'tr' ? 'dark' : 'light'});
      await page.goto('./');
      await settled(page);
      expect([await ev(page, 'shotClock(243)'), await ev(page, 'shotClock(7200)'), await ev(page, 'shotClock(605)'), await ev(page, 'shotClock(5)')])
        .toEqual(['0:24.3', '12:00', '1:00', '0:00.5']);
      expect([await ev(page, 'perShort(1)'), await ev(page, 'perShort(4)')]).toEqual([lang === 'tr' ? 'Ç1' : 'Q1', lang === 'tr' ? 'Ç4' : 'Q4']);
      expect([await ev(page, 'perShort(5)'), await ev(page, 'perShort(6)')]).toEqual(lang === 'tr' ? ['UZ', '2UZ'] : ['OT', '2OT']);
      await go(page, '#BOS', () => document.querySelector('#sc-court svg[data-tap]') && document.querySelector('#sc-game').options.length > 1);
      await page.click('#sc > summary');
      const pid = await page.evaluate(() => document.querySelector('#player').value);
      const f = await page.evaluate(() => fetch(`${META.base}shots/BOS.json`).then(r => r.json()));
      const rows = f.players[pid].map(r => [f.games[r[0]], ...r.slice(1)]);
      expect(rows.every(r => r.length === 11), 'every row has its period, clock and score').toBe(true);
      const log = await page.evaluate(() => Object.fromEntries([...document.querySelectorAll('#log tr[data-gid]')].map(tr => [tr.dataset.gid, [tr.cells[0].textContent, tr.cells[1].textContent]])));
      const r = lone(rows);
      expect(await card(page, '#sc-court .shot-card')).toEqual({hidden: true});
      await page.locator('#sc-court svg').scrollIntoViewIfNeeded();
      const [x, y] = await spot(page, '#sc-court svg', r[1], r[2]);
      await page.mouse.click(x, y);
      const opp = log[r[0]][1].replace(/^(vs|@)\s*/, '').trim();
      expect(await card(page, '#sc-court .shot-card'), 'season chart card').toEqual({hidden: false, game: `${log[r[0]][0]} ${log[r[0]][1]}`, ...await expected(page, r, 'BOS', opp)});
      expect(await page.getAttribute('#sc-court .shot-card a', 'href')).toBe(`#game/${r[0]}`);
      expect(await page.$eval('#sc-court .sel', c => [Number(c.getAttribute('cx')), Number(c.getAttribute('cy'))])).toEqual([r[1], -r[2]]);
      expect(await page.$eval('#sc-court .shot-card', el => el.getBoundingClientRect().bottom <= innerHeight - 80), 'the card is in view above the tab bar').toBe(true);
      await page.screenshot({path: info.outputPath(`player-${name}-${lang}.png`)});
      await noSidewaysScroll(page, 'shot card');
      await page.mouse.click(...await spot(page, '#sc-court svg', r[1], r[2]));   // the page has scrolled since
      expect(await card(page, '#sc-court .shot-card'), 'a second tap puts it away').toEqual({hidden: true});
      expect(await page.$$('#sc-court .sel')).toHaveLength(0);
      // one game picked: the same card from that game's marks
      await page.selectOption('#sc-game', r[0], {force: true});
      await page.waitForFunction(() => document.querySelector('#sc-court svg[data-tap]'));
      const g = lone(rows.filter(q => q[0] === r[0]));
      await page.mouse.click(...await spot(page, '#sc-court svg', g[1], g[2]));
      expect(await card(page, '#sc-court .shot-card'), 'game chart card').toEqual({hidden: false, game: `${log[r[0]][0]} ${log[r[0]][1]}`, ...await expected(page, g, 'BOS', opp)});

      // the Game page: both clubs' charts, the card naming the shooter and linking to his night
      await go(page, `#game/${r[0]}`, () => document.querySelectorAll('#gm-shots svg[data-tap]').length === 2);
      const [away, home] = await page.$$eval('#gm-shots [data-team]', ds => ds.map(d => /** @type {HTMLElement} */ (d).dataset.team));
      const hf = await page.evaluate(c => fetch(`${META.base}shots/${c}.json`).then(r => r.json()), home);
      const k = hf.games.indexOf(r[0]);
      const hrows = Object.entries(hf.players).flatMap(([p, rs]) => rs.filter(q => q[0] === k).map(q => [...q, p]));
      const h = lone(hrows), sel = `#gm-shots [data-team="${home}"]`;
      await page.locator(`${sel} svg`).scrollIntoViewIfNeeded();
      await page.mouse.click(...await spot(page, `${sel} svg`, h[1], h[2]));
      const nm = await page.$eval(`#gm-box tr[data-pid="${h[11]}"] a`, a => a.lastChild.textContent);
      expect(await card(page, `${sel} .shot-card`), 'game page card').toEqual({hidden: false, who: nm, ...await expected(page, h, home, away)});
      expect(await page.getAttribute(`${sel} .shot-card a`, 'href')).toBe(`#${home}/${h[11]}/${r[0]}`);
      expect(await card(page, `#gm-shots [data-team="${away}"] .shot-card`), 'the other chart keeps its card away').toEqual({hidden: true});
      await page.screenshot({path: info.outputPath(`game-${name}-${lang}.png`)});
      if (lang === 'tr') expect(await page.evaluate(() => [...MISSING]), 'Turkish strings missing from lang/tr.json').toEqual([]);
      expect(problems, 'the page reported errors').toEqual([]);
    });
  });
}
