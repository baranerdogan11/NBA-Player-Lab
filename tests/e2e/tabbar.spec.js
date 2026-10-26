// The phone tab bar at 390 px: five tabs in order, every label fits in English and Turkish, each tab opens its page and
// marks itself current, and the Player tab returns to the last player opened. On a wide screen the same five pages sit
// on the header rail and the bar is hidden.
import {test, expect} from '@playwright/test';
import {PHONE, DESKTOP, prepare, settled, go} from './site.js';

for (const lang of ['en', 'tr']) {
  test.describe(`phone · ${lang}`, () => {
    test.use(PHONE);
    test('five tabs whose labels fit and open their pages', async ({page}) => {
      const problems = await prepare(page, {lang});
      await page.goto('./');
      await settled(page);
      const tabs = await page.evaluate(() => [...document.querySelectorAll('#tabbar > a')].map(el => {
        const s = el.querySelector('span');
        return {id: el.id, text: s.textContent.trim(), cut: s.scrollWidth > s.clientWidth + 1, visible: el.getBoundingClientRect().height > 0};
      }));
      expect(tabs.map(x => x.id)).toEqual(['tb-player', 'tb-compare', 'tb-standings', 'tb-games', 'tb-leaders']);
      for (const x of tabs) {
        expect(x.visible, `${x.id} shows`).toBe(true);
        expect(x.text.length, `${x.id} has a label`).toBeGreaterThan(0);
        expect(x.cut, `${x.id} label "${x.text}" is cut off at 390px`).toBe(false);
      }
      await go(page, '#LAL', () => !!document.querySelector('#player option'));
      const pid = await page.evaluate(() => document.querySelectorAll('#player option')[2].value);
      await go(page, `#LAL/${pid}`, () => document.querySelector('#player').value === document.querySelectorAll('#player option')[2].value);
      for (const [id, page_] of [['tb-compare', 'compare'], ['tb-standings', 'standings'], ['tb-games', 'games'], ['tb-leaders', 'leaders'], ['tb-player', 'player']]) {
        await page.click(`#${id}`);
        await page.waitForFunction(p => document.body.dataset.page === p && !document.querySelector('#wipe.on'), page_);
        expect(await page.getAttribute(`#${id}`, 'aria-current')).toBe('page');
      }
      expect(await page.evaluate(() => location.hash)).toBe(`#LAL/${pid}`);
      expect(problems, 'the page reported errors').toEqual([]);
    });
  });
}

test.describe('desktop', () => {
  test.use(DESKTOP);
  test('the header rail carries the five pages and the bar is hidden', async ({page}) => {
    await prepare(page);
    await page.goto('./?l#standings');
    await settled(page);
    expect(await page.isVisible('#tabbar')).toBe(false);
    expect(await page.evaluate(() => [...document.querySelectorAll('#rail a')].map(a => a.textContent.trim()))).toEqual(['Players', 'Compare', 'Standings', 'Games', 'Leaders']);
    expect(await page.getAttribute('#rl-standings', 'aria-current')).toBe('page');
  });
});
