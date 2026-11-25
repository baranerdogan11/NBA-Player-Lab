// Readable by everyone: every ink the page sets as text stands 4.5:1 (WCAG AA) against the sheet it prints on, for all 30
// clubs and the house inks, on the paper and on the dark sheet.
import {test, expect} from '@playwright/test';
/* global TEAMS, inks, contrast, netInk */
import {DESKTOP, prepare, settled} from './site.js';

test.use(DESKTOP);

for (const theme of ['light', 'dark']) {
  test(`every club's text ink and the house inks read 4.5:1 on the ${theme} sheet`, async ({page}) => {
    const problems = await prepare(page, {theme});
    await page.goto('./?l#standings');
    await settled(page);
    const low = await page.evaluate(dark => {
      const sheet = getComputedStyle(document.documentElement).getPropertyValue('--paper').trim();
      const out = [];
      for (const code of Object.keys(TEAMS)) {
        const css = Object.fromEntries(inks(TEAMS[code].colors).split(';').map(d => d.split(':')));
        const ink = dark ? css['--an'] : css['--ap'];
        if (contrast(ink, sheet) < 4.5) out.push(`${code} ${ink} ${contrast(ink, sheet).toFixed(2)}`);
        const net = Object.fromEntries(netInk(code).split(';').map(d => d.split(':')))[dark ? '--nn' : '--np'];
        if (contrast(net, sheet) < 4.5) out.push(`${code} network ${net} ${contrast(net, sheet).toFixed(2)}`);
      }
      const root = getComputedStyle(document.documentElement);
      for (const k of ['--A', '--ink', '--ink2', '--muted', '--good', '--bad']) {
        const v = root.getPropertyValue(k).trim();
        if (contrast(v, sheet) < 4.5) out.push(`${k} ${v} ${contrast(v, sheet).toFixed(2)}`);
      }
      return out;
    }, theme === 'dark');
    expect(low).toEqual([]);
    expect(problems).toEqual([]);
  });
}
