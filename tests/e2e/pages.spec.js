// Every page at 390 and 1280 px, in English and Turkish, light and dark: it draws without an error or a sideways scroll,
// the Turkish page uses no string the dictionary lacks, and a screenshot of each lands in the run's artifacts.
import {test, expect} from '@playwright/test';
import {PHONE, DESKTOP, prepare, settled, go, noSidewaysScroll} from './site.js';

const ROUTES = [
  ['player', '#BOS', () => document.body.dataset.page === 'player' && !!document.querySelector('#tiles .tile')],
  ['compare', '#compare', () => document.body.dataset.page === 'compare' && document.querySelectorAll('#cmp tr').length > 5],
  ['standings', '#standings', () => document.body.dataset.page === 'standings' && document.querySelectorAll('#st-body tbody tr').length === 30],
  ['games', '#games', () => document.body.dataset.page === 'games' && !!document.querySelector('#gm-list .card')],
  ['game', '#game/0022600001', () => document.body.dataset.page === 'game' && document.querySelectorAll('#gm-box table').length === 2],
  ['leaders', '#leaders', () => document.body.dataset.page === 'leaders' && document.querySelectorAll('#ld tbody tr').length > 0],
];

for (const [device, size] of [['phone', PHONE], ['desktop', DESKTOP]]) {
  for (const lang of ['en', 'tr']) {
    for (const theme of ['light', 'dark']) {
      test.describe(`${device} · ${lang} · ${theme}`, () => {
        test.use(size);
        test('every page draws', async ({page}, info) => {
          const problems = await prepare(page, {lang, theme});
          await page.goto('./');
          await settled(page);
          for (const [name, hash, probe] of ROUTES) {
            await go(page, hash, probe);
            await noSidewaysScroll(page, `${name} (${device}, ${lang}, ${theme})`);
            await page.screenshot({path: info.outputPath(`${name}.png`), fullPage: true});
          }
          if (lang === 'tr') expect(await page.evaluate(() => [...MISSING]), 'Turkish strings missing from lang/tr.json').toEqual([]);
          expect(problems, 'the page reported errors').toEqual([]);
        });
      });
    }
  }
}
