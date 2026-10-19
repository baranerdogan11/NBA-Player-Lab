// Shared helpers for the browser tests: open the site in a chosen language and theme, and collect anything the page
// complains about.
import {expect} from '@playwright/test';

export const PHONE = {viewport: {width: 390, height: 844}, isMobile: true, hasTouch: true, deviceScaleFactor: 1};
export const DESKTOP = {viewport: {width: 1280, height: 900}, deviceScaleFactor: 1};

// language and theme are what a returning reader has chosen
export async function prepare(page, {lang = 'en', theme = 'light'} = {}) {
  await page.addInitScript(([l, th]) => {
    try { localStorage.setItem('pl-lang', l); localStorage.setItem('pl-theme', th); } catch (e) {}
  }, [lang, theme]);
  const problems = [];
  page.on('pageerror', e => problems.push(`uncaught: ${e.message}`));
  page.on('console', m => { if (m.type() === 'error') problems.push(`console.error: ${m.text()}`); });
  page.on('requestfailed', r => { if (/\.(html|js|json)(\?|$)/.test(r.url())) problems.push(`failed request: ${r.url()} (${r.failure()?.errorText})`); });
  page.on('response', r => { if (r.status() >= 400 && /\.(html|js|json)(\?|$)/.test(r.url())) problems.push(`HTTP ${r.status()}: ${r.url()}`); });
  return problems;
}

export const settled = page => page.waitForFunction(() => typeof META !== 'undefined' && !!document.querySelector('#page-title')?.textContent);

export async function noSidewaysScroll(page, where) {
  const wide = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(wide, `${where} scrolls sideways by ${wide}px`).toBeLessThanOrEqual(2);
}
