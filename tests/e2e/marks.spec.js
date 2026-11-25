// Readable by everyone: marks that once differed only by colour carry a second cue. A form run's loss is an empty square and
// the run is read out as W and L; a shot zone worse than the league prints in stripes, one better in solid pink.
import {test, expect} from '@playwright/test';
import {DESKTOP, prepare, settled} from './site.js';

test.use(DESKTOP);

test('form runs: losses are empty squares and the run is read out', async ({page}) => {
  const problems = await prepare(page);
  await page.goto('./?l#standings');
  await settled(page);
  await page.waitForFunction(() => document.querySelectorAll('#st-body .form b').length > 0);
  const runs = await page.evaluate(() => [...document.querySelectorAll('#st-body .form')].map(f => {
    const b = [...f.querySelectorAll('b')];
    return {label: f.getAttribute('aria-label'), seq: b.map(x => x.classList.contains('lo') ? 'L' : 'W').join(' '),
      lossFilled: b.filter(x => x.classList.contains('lo')).some(x => getComputedStyle(x).backgroundColor !== 'rgba(0, 0, 0, 0)')};
  }));
  expect(runs.length).toBeGreaterThan(0);
  for (const r of runs) { expect(r.label).toBe(r.seq); expect(r.lossFilled).toBe(false); }
  expect(problems).toEqual([]);
});

test('shot zones: worse than the league is striped, better is solid pink', async ({page}) => {
  const problems = await prepare(page);
  await page.goto('./?l#team/BOS');
  await settled(page);
  await page.evaluate(() => { document.querySelector('#tm-zones-sec').open = true; });
  await page.waitForFunction(() => document.querySelectorAll('#tm-zones .zg').length > 0);
  const fills = await page.evaluate(() => [...document.querySelectorAll('#tm-zones .zg')].map(z => [Math.sign(+z.dataset.g), z.getAttribute('fill')]));
  expect(fills.filter(([g]) => g < 0).every(([, f]) => f === 'url(#zh)')).toBe(true);
  expect(fills.filter(([g]) => g > 0).every(([, f]) => f === '#ff4fa5')).toBe(true);
  expect(await page.locator('pattern#zh').count()).toBe(1);
  expect(problems).toEqual([]);
});
