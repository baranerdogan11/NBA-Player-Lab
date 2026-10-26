// The site opens on Home: after half an hour away, a reload, a reopened tab or a tab brought back from the background
// lands on Home wherever it was left, while a link to another page still opens that page, and a quick reload stays put.
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
  test('a quick reload stays on the page; reopening the site after half an hour opens Home', async ({page, context}) => {
    const problems = await prepare(page);
    await context.clock.install();
    await page.goto('./#BOS');
    await settled(page);
    await page.waitForFunction(PLAYER);
    await page.reload();
    await settled(page);
    expect(await page.evaluate(() => [document.body.dataset.page, location.hash])).toEqual(['player', '#BOS']);
    await page.close();
    await context.clock.fastForward(31 * 60e3);
    const again = await context.newPage();   // the home-screen icon, or a tab restored on the address it was left on
    const more = await prepare(again);
    await again.goto('./#BOS');
    await settled(again);
    await again.waitForFunction(HOME);
    expect([...problems, ...more], 'the page reported errors').toEqual([]);
  });
  test('a link to another page opens it, even after a long time away', async ({page, context}) => {
    const problems = await prepare(page);
    await context.clock.install();
    await page.goto('./#standings');
    await settled(page);
    await page.close();
    await context.clock.fastForward(120 * 60e3);
    const link = await context.newPage();
    const more = await prepare(link);
    await link.goto('./#BOS');
    await settled(link);
    await link.waitForFunction(PLAYER);
    expect(await link.evaluate(() => location.hash)).toBe('#BOS');
    expect([...problems, ...more], 'the page reported errors').toEqual([]);
  });
  test('a tab brought back after half an hour in the background shows Home', async ({page}) => {
    const problems = await prepare(page);
    await page.clock.install();
    await page.goto('./#BOS');
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
