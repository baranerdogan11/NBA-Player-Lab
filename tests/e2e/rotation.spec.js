// Who played when: under each club's box score, a row per player who played and a bar per stretch on the court. A
// player's bars add up to his box-score minutes (within the second the box score drops) and his +/-, every bar sits on
// the game flow's clock, and a bar opens its clock times, minutes and +/-. On a phone the rows fit the screen.
import {test, expect} from '@playwright/test';
import {DESKTOP, PHONE, prepare, settled, go, noSidewaysScroll} from './site.js';

const clock = s => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
const rq = (num, den) => Math.floor((2 * num + den) / (2 * den));

async function open(page) {
  await page.goto('./?l#games/2026-10-21');
  await settled(page);
  const gid = await page.evaluate(() => document.querySelector('#gm-list a.card').dataset.gid);
  await go(page, `#game/${gid}`, () => document.querySelectorAll('#gm-box .rot').length === 2);
  return page.evaluate(id => fetch(`${META.base}games/${id}.json`).then(r => r.json()), gid);
}

test.describe('desktop', () => {
  test.use(DESKTOP);
  test('each club\'s rows add up to its box score and a bar reads its stretch', async ({page}) => {
    const problems = await prepare(page);
    const g = await open(page);
    for (const [i, code] of [g.away, g.home].entries()) {
      const rot = page.locator('#gm-box .rot').nth(i);
      expect(await rot.getAttribute('data-team')).toBe(code);
      const played = g.box[code].filter(x => x.sec > 0);
      expect(await rot.locator('.rot-r[data-pid]').evaluateAll(rs => rs.map(r => r.dataset.pid))).toEqual(played.map(x => x.pid));
      for (const x of played) {
        const r = g.rotation[x.pid];
        expect(Math.abs(r.reduce((s, [a, b]) => s + b - a, 0) - 10 * x.sec), `${x.pid} minutes`).toBeLessThanOrEqual(10);
        expect(r.reduce((s, [, , m]) => s + m, 0), `${x.pid} +/-`).toBe(x.pm);
        const left = await rot.locator(`.rot-r[data-pid="${x.pid}"] .rot-b`).evaluateAll(bs => bs.map(b => parseFloat(b.style.left)));
        expect(left.map(v => v.toFixed(2))).toEqual(r.map(([a]) => (100 * a / 28800).toFixed(2)));
      }
      // the club's minutes: five on the court for the whole game
      expect(Object.entries(g.rotation).filter(([p]) => played.some(x => x.pid === p)).reduce((s, [, r]) => s + r.reduce((t, [a, b]) => t + b - a, 0), 0)).toBe(5 * 28800);
    }
    const x = g.box[g.home].find(y => g.rotation[y.pid] && g.rotation[y.pid].length > 1) || g.box[g.home][0];
    const [a, b, m] = g.rotation[x.pid][0];
    await page.click(`#gm-box .rot[data-team="${g.home}"] .rot-r[data-pid="${x.pid}"] .rot-b >> nth=0`);
    const tip = await page.textContent(`#gm-box .rot[data-team="${g.home}"] .rot-tip`);
    expect(tip).toContain(x.name);
    expect(tip).toContain(`${clock(rq(b - a, 10))} MIN`);
    expect(tip).toContain(`${m > 0 ? '+' : m < 0 ? '−' : ''}${Math.abs(m)} +/-`);
    expect(tip).toContain('Q1 12:00');
    expect(problems, 'the page reported errors').toEqual([]);
  });

  test('a game without a rotation shows none', async ({page}) => {
    const problems = await prepare(page);
    await page.route(/\/games\/\d+\.json/, async r => { const d = await (await r.fetch()).json(); delete d.rotation; await r.fulfill({json: d}); });
    await page.goto('./?l#games/2026-10-21');
    await settled(page);
    const gid = await page.evaluate(() => document.querySelector('#gm-list a.card').dataset.gid);
    await go(page, `#game/${gid}`, () => document.querySelectorAll('#gm-box table').length === 2);
    expect(await page.locator('#gm-box .rot').count()).toBe(0);
    expect(problems, 'the page reported errors').toEqual([]);
  });
});

test.describe('phone', () => {
  test.use(PHONE);
  test('the rows fit a 390px screen in Turkish and a tap reads a stretch', async ({page}) => {
    const problems = await prepare(page, {lang: 'tr', theme: 'dark'});
    const g = await open(page);
    await noSidewaysScroll(page, 'game page with the rotation');
    const w = await page.locator('#gm-box .rot').first().evaluate(el => [el.scrollWidth, el.clientWidth]);
    expect(w[0]).toBeLessThanOrEqual(w[1]);
    const pid = g.box[g.away].find(x => x.sec > 0).pid;
    await page.locator(`#gm-box .rot[data-team="${g.away}"] .rot-r[data-pid="${pid}"] .rot-b`).first().tap();
    expect(await page.textContent(`#gm-box .rot[data-team="${g.away}"] .rot-tip`)).toContain('Ç1 12:00');
    await page.locator('#gm-box .rot').first().screenshot({path: test.info().outputPath('rotation-phone-dark-tr.png')});
    expect(problems, 'the page reported errors').toEqual([]);
  });
});
