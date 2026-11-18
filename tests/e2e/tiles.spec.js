// The stat tiles on the Player page and the club page: every tile is as tall as its number and label, the first (lead) tile's
// row included, on a phone and a desktop. The front page's lead story once shared the tile's class name and stretched it.
import {test, expect} from '@playwright/test';
import {DESKTOP, PHONE, prepare, settled} from './site.js';

for (const [name, use, lang] of [['desktop', DESKTOP, 'en'], ['phone', PHONE, 'tr']]) {
  test.describe(`stat tiles (${name})`, () => {
    test.use(use);
    for (const [hash, box] of [['#LAL', '#tiles'], ['#team/BOS', '#tm-tiles']]) {
      test(`${hash} tiles are as tall as their numbers (${lang})`, async ({page}) => {
        const problems = await prepare(page, {lang});
        await page.goto(`./?l${hash}`);
        await settled(page);
        await page.waitForFunction(sel => document.querySelectorAll(`${sel} .tile`).length > 5, box);
        await page.waitForTimeout(600);   // the tiles' entry rise
        // each tile's empty space: its height less its number, its label and their gap and padding
        const spare = await page.evaluate(sel => [...document.querySelectorAll(`${sel} .tile`)].map(x => {
          const h = e => e.getBoundingClientRect().height;
          return [x.dataset.k, Math.round(h(x) - h(x.querySelector('b')) - h(x.querySelector('span')))];
        }), box);
        expect(spare.filter(([, v]) => v > 60), JSON.stringify(spare)).toEqual([]);
        expect(problems).toEqual([]);
      });
    }
  });
}
