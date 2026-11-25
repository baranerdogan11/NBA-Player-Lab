// Readable by everyone: the page's type follows the reader's browser text size (Settings > Font size), so at 150% and 200%
// the text grows with it, a desktop window switches to the phone layout once the masthead no longer fits, and no page
// scrolls sideways.
import {test, expect} from '@playwright/test';
import {DESKTOP, PHONE, prepare, settled, go, noSidewaysScroll} from './site.js';

const PAGES = ['#home', '#LAL', '#compare', '#standings', '#standings/ratings', '#games', '#game/0022600001', '#leaders', '#leaders/lineups', '#team/BOS', '#glossary'];

for (const [name, use] of [['desktop', DESKTOP], ['phone', PHONE]]) {
  test.describe(`text size (${name})`, () => {
    test.use(use);
    for (const size of [24, 32]) {
      test(`at ${size}px browser text every page grows with it and stays on screen`, async ({page, context}) => {
        const problems = await prepare(page);
        const cdp = await context.newCDPSession(page);
        await cdp.send('Page.enable');
        await cdp.send('Page.setFontSizes', {fontSizes: {standard: size, fixed: size}});
        await page.goto('./?l#home');
        await settled(page);
        expect(await page.evaluate(() => parseFloat(getComputedStyle(document.body).fontSize))).toBeCloseTo(15 * size / 16, 1);
        for (const hash of PAGES) {
          await go(page, hash);
          await page.evaluate(() => document.querySelectorAll('details').forEach(d => { d.open = true; }));
          await page.waitForTimeout(300);
          await noSidewaysScroll(page, `${hash} at ${size}px`);
        }
        expect(problems).toEqual([]);
      });
    }
  });
}
