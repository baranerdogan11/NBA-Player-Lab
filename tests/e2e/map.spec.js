// The league map: every club's logo sits at its ORtg (across) and DRtg (down, the lowest at the top) as Ratings shows
// them, on one scale for both axes; a logo picked shows the club's ORtg, DRtg and net rating with the ranks Ratings
// gives, the best net rating picked on arrival; it fits a phone without a sideways scroll and reads in Turkish.
import {test, expect} from '@playwright/test';
import {PHONE, prepare, settled, go, noSidewaysScroll} from './site.js';

const ready = () => document.querySelectorAll('#st-map .lm-d').length === 30 && !!document.querySelector('#st-map-card a');
const ratings = page => page.$$eval('#st-ratings tbody tr', trs => Object.fromEntries(trs.map(tr => [tr.dataset.team,
  Object.fromEntries([...tr.querySelectorAll('td[data-k]')].map(td => [td.dataset.k, [td.querySelector('.v').textContent, td.dataset.r]]))])));

test('each logo stands at the club\'s ratings, and a pick shows the Ratings values and ranks', async ({page}) => {
  const problems = await prepare(page);
  await page.goto('./?l#standings/ratings');
  await settled(page);
  await page.waitForFunction(() => document.querySelectorAll('#st-ratings tbody tr').length === 30);
  const R = await ratings(page), best = await page.$eval('#st-ratings tbody tr', tr => tr.dataset.team);
  await go(page, '#standings/map', ready);
  expect(await page.getAttribute('#st-tabs [aria-current="true"]', 'href')).toBe('#standings/map');
  const dots = await page.$$eval('#st-map .lm-d', bs => {
    const box = document.querySelector('#st-map .lm').getBoundingClientRect();
    return bs.map(b => { const r = b.getBoundingClientRect(); return {c: b.dataset.team, o: b.dataset.ortg, d: b.dataset.drtg, x: (r.left + r.width / 2 - box.left) / box.width, y: (r.top + r.height / 2 - box.top) / box.height}; });
  });
  for (const d of dots) {
    expect([d.o, d.d], `${d.c} on the map`).toEqual([R[d.c].ortg[0], R[d.c].drtg[0]]);
    expect(d.x > 0 && d.x < 1 && d.y > 0 && d.y < 1, `${d.c} inside the sheet`).toBe(true);
  }
  // one linear scale for both axes: position = (value - lo) / (hi - lo), the same lo and hi across and down
  const a = dots.reduce((m, d) => (+d.o < +m.o ? d : m)), b = dots.reduce((m, d) => (+d.o > +m.o ? d : m));
  const k = (b.x - a.x) / (b.o - a.o), lo = +a.o - a.x / k;
  for (const d of dots) {
    expect(Math.abs(d.x - (d.o - lo) * k), `${d.c} across`).toBeLessThan(0.004);
    expect(Math.abs(d.y - (d.d - lo) * k), `${d.c} down`).toBeLessThan(0.004);
  }
  const card = () => page.$eval('#st-map-card', el => ({c: el.dataset.team, v: Object.fromEntries([...el.querySelectorAll('[data-k]')].map(s => [s.dataset.k, [s.querySelector('.v').textContent, s.querySelector('.rk').textContent]]))}));
  const want = c => Object.fromEntries(['ortg', 'drtg', 'net'].map(x => [x, R[c][x]]));
  expect(await card()).toEqual({c: best, v: want(best)});
  for (const c of ['BOS', 'SAC']) {
    await page.click(`#st-map .lm-d[data-team="${c}"]`, {force: true});
    expect(await card()).toEqual({c, v: want(c)});
    expect(await page.$$eval('#st-map .lm-d.on', bs => bs.map(x => x.dataset.team))).toEqual([c]);
    expect(await page.getAttribute('#st-map-card a', 'href')).toBe(`#team/${c}`);
  }
  expect(problems, 'the page reported errors').toEqual([]);
});

test.describe('phone', () => {
  test.use(PHONE);
  test('the map fits a phone in Turkish and a tap picks a club', async ({page}) => {
    const problems = await prepare(page, {lang: 'tr', theme: 'dark'});
    await page.goto('./?l#standings/map');
    await settled(page);
    await page.waitForFunction(ready);
    await noSidewaysScroll(page, 'league map');
    expect(await page.textContent('#st-tabs [aria-current="true"]')).toBe('Lig haritası');
    const box = await page.$eval('#st-map .lm', el => { const r = el.getBoundingClientRect(); return [r.width, r.height]; });
    expect(Math.abs(box[0] - box[1]), 'the sheet is square').toBeLessThan(2);
    await page.tap('#st-map .lm-d[data-team="BOS"]', {force: true});
    expect(await page.getAttribute('#st-map-card', 'data-team')).toBe('BOS');
    expect(await page.evaluate(() => [...MISSING])).toEqual([]);
    expect(problems, 'the page reported errors').toEqual([]);
  });
});
