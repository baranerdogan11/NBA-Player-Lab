// Every page at phone and desktop width, in English and Turkish, light and dark: it draws without an error or a sideways
// scroll, and a screenshot of each lands in the run's artifacts.
import {test, expect} from '@playwright/test';
import {PHONE, DESKTOP, prepare, settled, noSidewaysScroll} from './site.js';

const PAGES = ['player', 'compare', 'standings', 'games', 'leaders'];

for (const [size, device] of [['phone', PHONE], ['desktop', DESKTOP]]) {
  for (const lang of ['en', 'tr']) {
    for (const theme of ['light', 'dark']) {
      test.describe(`${size} · ${lang} · ${theme}`, () => {
        test.use(device);
        test('every page draws', async ({page}, info) => {
          const problems = await prepare(page, {lang, theme});
          await page.goto('./');
          await settled(page);
          for (const id of PAGES) {
            await page.evaluate(h => { location.hash = h; }, `#${id}`);
            await page.waitForFunction(h => document.querySelector(`[data-tab="${h}"]`)?.getAttribute('aria-current') === 'page', id);
            await noSidewaysScroll(page, `#${id}`);
            await page.screenshot({path: info.outputPath(`${id}.png`), fullPage: true});
          }
          expect(problems, 'the page reported errors').toEqual([]);
        });
      });
    }
  }
}
