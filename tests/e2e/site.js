// Shared helpers for the browser tests: open the site in a chosen language and theme, wait for a page to finish
// drawing, and collect anything the page complains about.
import {expect} from '@playwright/test';

export const PHONE = {viewport: {width: 390, height: 844}, isMobile: true, hasTouch: true, deviceScaleFactor: 1};
export const DESKTOP = {viewport: {width: 1280, height: 900}, deviceScaleFactor: 1};

export async function prepare(page, {lang = 'en', theme = 'light'} = {}) {
  await page.addInitScript(([l, th]) => {
    try { localStorage.setItem('pl-lang', l); localStorage.setItem('pl-theme', th); } catch (e) {}
  }, [lang, theme]);
  // headshots come from NBA's CDN; the made-up players have none, so every request gets a stand-in picture
  await page.route('https://cdn.nba.com/headshots/**', r => r.fulfill({contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 4 3"><rect width="4" height="3" fill="#888"/></svg>'}));
  const problems = [];
  page.on('pageerror', e => problems.push(`uncaught: ${e.message}`));
  page.on('console', m => { if (m.type() === 'error' || m.type() === 'warning') problems.push(`console.${m.type()}: ${m.text()}`); });
  page.on('requestfailed', r => { if (/\.(html|js|json)(\?|$)/.test(r.url())) problems.push(`failed request: ${r.url()} (${r.failure()?.errorText})`); });
  page.on('response', r => { if (r.status() >= 400 && /\.(html|js|json)(\?|$)/.test(r.url())) problems.push(`HTTP ${r.status()}: ${r.url()}`); });
  return problems;
}

// the route has finished: the season index is in, no loading bar, no error panel, one page showing
export const settled = page => page.waitForFunction(() => typeof IDX !== 'undefined' && IDX && !document.querySelector('#wipe.on') && document.querySelector('#fail').hidden && !!document.body.dataset.page);

export async function go(page, hash, probe, arg) {
  await page.evaluate(h => { location.hash = h; }, hash);
  await page.waitForFunction(h => location.hash.startsWith(h), hash);   // #compare settles on #compare/a/b
  await settled(page);
  if (probe) await page.waitForFunction(probe, arg);
}

export async function noSidewaysScroll(page, where) {
  const wide = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(wide, `${where} scrolls sideways by ${wide}px`).toBeLessThanOrEqual(2);
}
