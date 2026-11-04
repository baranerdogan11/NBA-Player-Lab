// Season chart: inside the Game log, every final of his club since his first game as a bar of the stat picked, as his game
// log gives it, with the average of his last five games played and his season average as the hero shows it; a game he
// missed is an empty slot and each bar opens its game. The fixture's four nights are under the five-game floor, so the test
// adds eight more finals for his club and gives him seven of them: one he misses, and one he sits out with no minutes.
import {test, expect} from '@playwright/test';
import {DESKTOP, PHONE, prepare, settled, go, noSidewaysScroll} from './site.js';

const CODE = 'BOS', MORE = 8;
const show = (k, v) => k === 'gs' ? (v < 0 ? '-' : '') + (Math.abs(v) / 10).toFixed(1) : k === 'sec' ? `${Math.floor(v / 60)}:${String(v % 60).padStart(2, '0')}` : String(v);
const tenths = (num, den) => Math.floor((2 * num * 10 + den) / (2 * den));
const pick = (page, k) => page.selectOption('#sea-stat', k, {force: true});
const mean = (k, sum, n) => k === 'gs' ? show('gs', tenths(sum, 10 * n)) : (tenths(sum, (k === 'sec' ? 60 : 1) * n) / 10).toFixed(1);

async function longer(page) {
  let pid = null;
  await page.route(/\/games\.json/, async r => {
    const d = await (await r.fetch()).json();
    const mine = d.games.filter(g => g.hs != null && (g.home === CODE || g.away === CODE));
    for (let i = 0; i < MORE; i++) d.games.push({...mine[i % mine.length], gid: `00229${String(i).padStart(5, '0')}`, date: `2026-11-${String(i + 1).padStart(2, '0')}`});
    await r.fulfill({json: d});
  });
  await page.route(new RegExp(`/\\d{4}-\\d{2}/${CODE}\\.json`), async r => {
    const d = await (await r.fetch()).json();
    const p = d.players.find(x => x.log.filter(y => y.sec > 0).length === x.log.length);
    pid = p.pid;
    const src = p.log;
    for (let i = 0; i < MORE; i++) {
      if (i === 2) continue;   // not in the box score at all
      const x = src[i % src.length], k = i + 1;
      p.log.push(i === 5 ? {...x, gid: `00229${String(i).padStart(5, '0')}`, date: `2026-11-0${k}`, sec: 0, pts: 0, reb: 0, ast: 0, fg3m: 0, gs: 0}
        : {...x, gid: `00229${String(i).padStart(5, '0')}`, date: `2026-11-0${k}`, pts: x.pts + k, reb: x.reb + (k % 3), ast: x.ast + (k % 2), fg3m: x.fg3m, gs: x.gs + 7 * k - 30, sec: x.sec + 13 * k});
    }
    await r.fulfill({json: d});
  });
  return () => pid;
}

test('the season chart is his log, game by game, with the five-game and season averages, and opens each game', async ({page}) => {
  const problems = await prepare(page);
  const who = await longer(page);
  await page.goto('./');
  await settled(page);
  await go(page, `#${CODE}`, () => !!document.querySelector('#player').value);
  await go(page, `#${CODE}/${who()}`, () => !document.querySelector('#season').hidden && !!document.querySelector('#sea-in a'));
  expect(await page.isVisible('#sea-in')).toBe(false);   // closed with the Game log when the page opens
  await page.click('#log-sec summary');
  const log = await page.evaluate(code => fetch(`${META.base}${code}.json`).then(r => r.json()), CODE).then(d => d.players.find(p => p.pid === who()).log);
  const played = log.filter(x => x.sec > 0);
  for (const [k, label] of [['pts', 'PTS'], ['reb', 'REB'], ['ast', 'AST'], ['fg3m', '3PM'], ['gs', 'GmSc'], ['sec', 'MIN']]) {
    await pick(page, k);
    await expect(page.locator('#sea-stat + .sel')).toHaveText(label);
    const slots = await page.evaluate(() => [...document.querySelectorAll('#sea-in .sea-plot > [data-i]')].map(s => [s.dataset.gid, s.tagName === 'A' ? s.dataset.v : null]));
    // every game in order: the four fixture nights, the eight new finals, the missed one and the one without minutes empty
    expect(slots.map(s => s[0])).toEqual([...log.slice(0, 4).map(x => x.gid), ...Array.from({length: MORE}, (_, i) => `00229${String(i).padStart(5, '0')}`)]);
    expect(slots.filter(s => s[1] == null).map(s => s[0])).toEqual(['0022900002', '0022900005']);
    expect(slots.filter(s => s[1] != null).map(s => s[1])).toEqual(played.map(x => show(k, x[k])));
    const sum = played.reduce((n, x) => n + x[k], 0), five = played.slice(-5).reduce((n, x) => n + x[k], 0);
    expect(await page.textContent('#sea-avg')).toBe(mean(k, sum, played.length));
    expect(await page.textContent('#sea-roll')).toBe(mean(k, five, 5));
  }
  // the season averages are the hero's and the form strip's
  await pick(page, 'pts');
  expect(await page.textContent('#sea-avg')).toBe(await page.textContent('#tiles [data-k="PTS"] b'));
  await pick(page, 'gs');
  expect(await page.textContent('#sea-avg')).toBe(await page.textContent('#form-avg'));
  const gid = log[0].gid;
  await page.click(`#sea-in a[data-gid="${gid}"]`);
  await page.waitForFunction(g => document.body.dataset.page === 'game' && location.hash === `#game/${g}`, gid);
  expect(problems, 'the page reported errors').toEqual([]);
});

test('the season chart waits for five games', async ({page}) => {
  const problems = await prepare(page);
  await page.goto('./');
  await settled(page);
  await go(page, `#${CODE}`, () => !!document.querySelector('#log tbody tr'));
  await page.waitForTimeout(300);
  expect(await page.isHidden('#season')).toBe(true);
  expect(problems, 'the page reported errors').toEqual([]);
});

test.describe('phone', () => {
  test.use(PHONE);
  test('the season chart fits a phone in Turkish', async ({page}) => {
    const problems = await prepare(page, {lang: 'tr', theme: 'dark'});
    const who = await longer(page);
    await page.goto('./');
    await settled(page);
    await go(page, `#${CODE}`, () => !!document.querySelector('#player').value);
    await go(page, `#${CODE}/${who()}`, () => !!document.querySelector('#sea-in a'));
    await page.click('#log-sec summary');
    const [inner, outer] = await page.evaluate(() => [document.querySelector('#sea-in').scrollWidth, document.querySelector('#sea-in').parentElement.clientWidth]);
    expect(inner).toBeLessThanOrEqual(outer);   // twelve games fit without sideways scrolling
    await noSidewaysScroll(page, 'the season chart');
    await page.evaluate(() => scrollTo(0, document.querySelector('#log-sec').getBoundingClientRect().top + scrollY - 70));
    await page.screenshot({path: 'test-results/season-phone-dark-tr.png'});
    expect(await page.evaluate(() => [...MISSING]), 'Turkish strings missing from lang/tr.json').toEqual([]);
    expect(problems, 'the page reported errors').toEqual([]);
  });
});

test.describe('desktop', () => {
  test.use(DESKTOP);
  test('screenshot', async ({page}) => {
    await prepare(page);
    const who = await longer(page);
    await page.goto('./');
    await settled(page);
    await go(page, `#${CODE}`, () => !!document.querySelector('#player').value);
    await go(page, `#${CODE}/${who()}`, () => !!document.querySelector('#sea-in a'));
    await page.click('#log-sec summary');
    await page.evaluate(() => scrollTo(0, document.querySelector('#log-sec').getBoundingClientRect().top + scrollY - 80));
    await page.screenshot({path: 'test-results/season-desktop-light.png'});
  });
});
