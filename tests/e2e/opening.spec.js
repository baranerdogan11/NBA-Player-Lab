// The site opens on Home: a fresh open lands there whatever address it carries (the home-screen icon keeps the one it was
// saved on), and so does a tab brought back after half an hour; a shared link (?l), the league invite link and a quick
// reload keep their page, and so does a link on the site opened in a new tab (right-click, long-press, middle or ctrl-click).
import {test, expect} from '@playwright/test';
import {DESKTOP, PHONE, prepare, settled} from './site.js';

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

test.describe('a link opened in a new tab', () => {
  test.use(DESKTOP);
  test('ctrl-click and middle-click open the linked page, not Home', async ({page, context}) => {
    const problems = await prepare(page);
    await page.goto('./?l#standings');
    await settled(page);
    const link = page.locator('#st-body a[href^="#"]').first();
    const hash = await link.getAttribute('href');
    for (const how of [{modifiers: ['ControlOrMeta']}, {button: 'middle'}]) {
      const [tab] = await Promise.all([context.waitForEvent('page'), link.click(/** @type {any} */ (how))]);
      await tab.waitForLoadState();
      await tab.waitForFunction(() => typeof IDX !== 'undefined' && IDX && !document.querySelector('#wipe.on') && !!document.body.dataset.page);
      expect(await tab.evaluate(() => [document.body.dataset.page, location.hash])).toEqual([hash.startsWith('#team/') ? 'team' : 'player', hash]);
      await tab.close();
    }
    expect(page.url()).toContain('#standings');
    expect(problems, 'the page reported errors').toEqual([]);
  });
  test('"open in new tab" from the menu keeps the page, and the same address opened later starts on Home', async ({page, context}) => {
    const problems = await prepare(page);
    await page.clock.install();
    await page.goto('./?l#standings');
    await settled(page);
    const link = page.locator('#st-body a[href^="#"]').first();
    const hash = await link.getAttribute('href');
    await link.click({button: 'right'});   // the browser's own menu then opens the address in a new tab
    const tab = await context.newPage();
    await tab.clock.install();
    await tab.goto(`./${hash}`);
    await settled(tab);
    expect(await tab.evaluate(() => location.hash)).toBe(hash);
    await tab.close();
    await page.clock.fastForward(3 * 60e3);
    const later = await context.newPage();
    await later.clock.install({time: await page.evaluate(() => Date.now())});
    await later.goto(`./${hash}`);
    await settled(later);
    await later.waitForFunction(HOME);
    expect(problems, 'the page reported errors').toEqual([]);
  });
});

test.describe('a link opened in a new tab on a phone', () => {
  test.use(PHONE);
  test('a long-press then "open in new tab" keeps the page', async ({page, context}) => {
    const problems = await prepare(page);
    await page.goto('./?l#standings');
    await settled(page);
    const link = page.locator('#st-body a[href^="#"]').first();
    const hash = await link.getAttribute('href');
    const box = await link.boundingBox();
    await page.touchscreen.tap(box.x + 4, box.y + box.height / 2);   // the press is what the page notes
    const tab = await context.newPage();
    await tab.goto(`./${hash}`);
    await settled(tab);
    expect(await tab.evaluate(() => location.hash)).toBe(hash);
    expect(problems, 'the page reported errors').toEqual([]);
  });
});
