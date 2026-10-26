// The site opens on Home: a fresh open lands there whatever address it carries (the home-screen icon keeps the one it was
// saved on), and so does a tab brought back after half an hour; a shared link (?l), the league invite link and a quick
// reload keep their page.
import {test, expect} from '@playwright/test';
import {DESKTOP, prepare, settled} from './site.js';

const PLAYER = () => document.body.dataset.page === 'player' && !!document.querySelector('#tiles .tile');
const HOME = () => document.body.dataset.page === 'home' && location.hash === '';
const show = (page, hidden) => page.evaluate(h => {
  Object.defineProperty(document, 'hidden', {configurable: true, get: () => h});
  document.dispatchEvent(new Event('visibilitychange'));
}, hidden);

test.describe('opening page', () => {
  test.use(DESKTOP);
  test('a fresh open lands on Home whatever the address, even on a first visit', async ({page}) => {
    const problems = await prepare(page);
    for (const hash of ['#BOS', '#player', '#standings', '#game/0022600001']) {
      await page.goto(`./?x=${hash.length}${hash}`);   // a new document every time, as an icon or a new tab opens it
      await settled(page);
      await page.waitForFunction(HOME);
    }
    expect(problems, 'the page reported errors').toEqual([]);
  });
  test('a shared link opens its page and drops its mark; and a reload stays on it', async ({page}) => {
    const problems = await prepare(page);
    await page.goto('./?l#BOS');
    await settled(page);
    await page.waitForFunction(PLAYER);
    expect(await page.evaluate(() => location.search + location.hash)).toBe('#BOS');
    await page.reload();
    await settled(page);
    expect(await page.evaluate(() => [document.body.dataset.page, location.hash])).toEqual(['player', '#BOS']);
    expect(problems, 'the page reported errors').toEqual([]);
  });
  test('a tab brought back after half an hour in the background shows Home', async ({page}) => {
    const problems = await prepare(page);
    await page.clock.install();
    await page.goto('./?l#BOS');
    await settled(page);
    await page.waitForFunction(PLAYER);
    await show(page, true);
    await page.clock.fastForward(5 * 60e3);
    await show(page, false);
    expect(await page.evaluate(() => location.hash)).toBe('#BOS');
    await show(page, true);
    await page.clock.fastForward(31 * 60e3);
    await show(page, false);
    await settled(page);
    await page.waitForFunction(HOME);
    expect(problems, 'the page reported errors').toEqual([]);
  });
});
