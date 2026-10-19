// The phone tab bar at 390px: five tabs in order, and every label in English and Turkish fits its tab without being cut off.
import {test, expect} from '@playwright/test';
import {PHONE, prepare, settled} from './site.js';

for (const lang of ['en', 'tr']) {
  test.describe(`phone · ${lang}`, () => {
    test.use(PHONE);
    test('five tabs whose labels fit', async ({page}) => {
      const problems = await prepare(page, {lang});
      await page.goto('./');
      await settled(page);
      const tabs = await page.evaluate(() => [...document.querySelectorAll('#tabbar > *')].map(el => {
        const s = el.querySelector('span'), r = el.getBoundingClientRect(), sr = s.getBoundingClientRect();
        return {id: el.id, text: s.textContent.trim(), cut: s.scrollWidth > s.clientWidth + 1 || sr.left < r.left - 1 || sr.right > r.right + 1};
      }));
      expect(tabs.map(x => x.id)).toEqual(['tb-player', 'tb-compare', 'tb-standings', 'tb-games', 'tb-leaders']);
      for (const x of tabs) {
        expect(x.text.length, `${x.id} has a label`).toBeGreaterThan(0);
        expect(x.cut, `${x.id} label "${x.text}" is cut off at 390px`).toBe(false);
      }
      expect(problems, 'the page reported errors').toEqual([]);
    });
  });
}
