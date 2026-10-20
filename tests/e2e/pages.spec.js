// Every page at 390 and 1280 px, in English and Turkish, light and dark: it draws without an error or a sideways scroll,
// the Turkish page uses no string the dictionary lacks, and a screenshot of each lands in the run's artifacts.
import {test, expect} from '@playwright/test';
import {PHONE, DESKTOP, prepare, settled, go, noSidewaysScroll} from './site.js';

const ROUTES = [
  ['player', '#BOS', () => document.body.dataset.page === 'player' && !!document.querySelector('#tiles .tile')],
  ['compare', '#compare', () => document.body.dataset.page === 'compare' && document.querySelectorAll('#cmp tr').length > 5],
  ['standings', '#standings', () => document.body.dataset.page === 'standings' && document.querySelectorAll('#st-body tbody tr').length === 30],
  ['games', '#games', () => document.body.dataset.page === 'games' && !!document.querySelector('#gm-list .card')],
  ['game', '#game/0022600001', () => document.body.dataset.page === 'game' && document.querySelectorAll('#gm-box table').length === 2],
  ['leaders', '#leaders', () => document.body.dataset.page === 'leaders' && document.querySelectorAll('#ld tbody tr').length > 0],
  ['leaders-rapm', '#leaders/rapm', () => document.body.dataset.page === 'leaders' && document.querySelector('#ld-tabs [aria-current="true"]')?.getAttribute('href') === '#leaders/rapm' && document.querySelectorAll('#ld tbody tr').length > 0],
  ['home', '#home', () => document.body.dataset.page === 'home' && document.querySelectorAll('#hm-leaders .panel').length === 3],
];

for (const [device, size] of [['phone', PHONE], ['desktop', DESKTOP]]) {
  for (const lang of ['en', 'tr']) {
    for (const theme of ['light', 'dark']) {
      test.describe(`${device} · ${lang} · ${theme}`, () => {
        test.use(size);
        test('every page draws', async ({page}, info) => {
          const problems = await prepare(page, {lang, theme});
          await page.goto('./');
          await settled(page);
          for (const [name, hash, probe] of ROUTES) {
            await go(page, hash, probe);
            await noSidewaysScroll(page, `${name} (${device}, ${lang}, ${theme})`);
            await page.screenshot({path: info.outputPath(`${name}.png`), fullPage: true});
          }
          if (lang === 'tr') expect(await page.evaluate(() => [...MISSING]), 'Turkish strings missing from lang/tr.json').toEqual([]);
          expect(problems, 'the page reported errors').toEqual([]);
        });
      });
    }
  }
}

test.describe('player pictures', () => {
  test.use(DESKTOP);
  test('the hero, Compare and box scores show the NBA headshot for the player id, over his initials', async ({page}) => {
    const problems = await prepare(page);
    await page.goto('./');
    await settled(page);
    await go(page, '#BOS', ROUTES[0][2]);
    const hero = await page.evaluate(() => ({img: document.querySelector('#hero .face img')?.getAttribute('src'), ini: document.querySelector('#hero .face span')?.textContent, pid: document.querySelector('#player').value}));
    expect(hero.img).toBe(`https://cdn.nba.com/headshots/nba/latest/1040x760/${hero.pid}.png`);
    expect(hero.ini).toMatch(/^[A-Z]{1,2}$/);
    await go(page, '#compare', ROUTES[1][2]);
    expect(await page.locator('#cmp-vs .face img').count()).toBe(2);
    await go(page, '#game/0022600001', ROUTES[4][2]);
    const rows = await page.evaluate(() => [...document.querySelectorAll('#gm-box tr[data-pid]')].map(tr => [tr.dataset.pid, tr.querySelector('.face img')?.getAttribute('src')]));
    expect(rows.length).toBeGreaterThan(0);
    for (const [pid, src] of rows) expect(src).toBe(`https://cdn.nba.com/headshots/nba/latest/260x190/${pid}.png`);
    expect(problems, 'the page reported errors').toEqual([]);
  });
  test('a picture that fails to load leaves the initials', async ({page}) => {
    const problems = await prepare(page);
    await page.route('https://cdn.nba.com/headshots/**', r => r.abort());
    await page.goto('./');
    await settled(page);
    await go(page, '#BOS', ROUTES[0][2]);
    await page.waitForFunction(() => !document.querySelector('#hero .face img'));
    expect(await page.locator('#hero .face span').isVisible()).toBe(true);
    expect(problems.filter(p => !p.includes('Failed to load resource')), 'the page reported errors').toEqual([]);
  });
  test('club logos come from NBA\'s CDN by team id on Standings, Games, the scoreboard and the hero', async ({page}) => {
    const problems = await prepare(page);
    await page.goto('./');
    await settled(page);
    const ids = await page.evaluate(() => Object.fromEntries(IDX.teams.map(T => [T.code, T.id])));
    for (const id of Object.values(ids)) expect(String(id), 'index.json carries each club\'s NBA team id').toMatch(/^\d{10}$/);
    const url = code => `https://cdn.nba.com/logos/nba/${ids[code]}/primary/L/logo.svg`;
    await go(page, '#standings', ROUTES[2][2]);
    const rows = await page.evaluate(() => [...document.querySelectorAll('#st-body tr[data-team]')].map(tr => [tr.dataset.team, tr.querySelector('.chip img')?.getAttribute('src')]));
    expect(rows.length).toBe(30);
    for (const [code, src] of rows) expect(src).toBe(url(code));
    await go(page, '#games', ROUTES[3][2]);
    expect(await page.locator('#gm-list .card .row .chip img').count()).toBeGreaterThan(0);
    await go(page, '#game/0022600001', ROUTES[4][2]);
    expect(await page.locator('#gm-board .crest img').count()).toBe(2);
    await go(page, '#BOS', ROUTES[0][2]);
    expect(await page.locator('#hero .tag .mark img').getAttribute('src')).toBe(url('BOS'));
    expect(problems, 'the page reported errors').toEqual([]);
  });
});

test.describe('opening page', () => {
  test.use(DESKTOP);
  test('no hash opens it; its cards and leaders match the Games and Leaders pages', async ({page}) => {
    const problems = await prepare(page);
    await page.goto('./');
    await settled(page);
    expect(await page.evaluate(() => document.body.dataset.page)).toBe('home');
    expect(await page.getAttribute('#rl-player', 'href')).toBe('#player');
    const home = await page.evaluate(() => ({
      gids: [...document.querySelectorAll('#hm-games a.card')].map(a => a.dataset.gid),
      day: document.querySelector('#hm-games-h a.more').getAttribute('href'),
      pts: [...document.querySelectorAll('#hm-leaders [data-stat="pts"] a')].map(a => [a.dataset.pid, a.querySelector('.v').textContent]),
    }));
    expect(home.gids.length).toBeGreaterThan(0);
    expect(home.pts.length).toBe(5);
    await go(page, home.day, () => !!document.querySelector('#gm-list .card'));
    expect(await page.evaluate(() => [...document.querySelectorAll('#gm-list a.card')].map(a => a.dataset.gid))).toEqual(home.gids);
    await go(page, '#leaders/pts', () => document.querySelectorAll('#ld tbody tr').length > 0);
    expect(await page.evaluate(() => [...document.querySelectorAll('#ld tbody tr')].slice(0, 5).map(tr => [tr.dataset.pid, tr.querySelector('.k').textContent]))).toEqual(home.pts);
    await page.click('.top .id');
    await page.waitForFunction(() => document.body.dataset.page === 'home');
    expect(problems, 'the page reported errors').toEqual([]);
  });
  for (const lang of ['en', 'tr']) {
    test(`before the first final it shows the first night to come and empty boards (${lang})`, async ({page}) => {
      const problems = await prepare(page, {lang});
      await page.route(/\/games\.json/, async r => {
        const d = await (await r.fetch()).json();
        await r.fulfill({json: {games: d.games.map(g => ({gid: g.gid, date: g.date, time: g.time, home: g.home, away: g.away, hs: null, as: null}))}});
      });
      await page.route(/\/leaders\.json/, r => r.fulfill({json: {players: []}}));
      await page.goto('./');
      await settled(page);
      const got = await page.evaluate(() => ({
        cards: document.querySelectorAll('#hm-games .card').length, links: document.querySelectorAll('#hm-games a.card').length,
        empty: document.querySelectorAll('#hm-leaders .empty').length,
      }));
      expect(got).toEqual({cards: 15, links: 0, empty: 3});
      await noSidewaysScroll(page, `empty opening page (${lang})`);
      if (lang === 'tr') expect(await page.evaluate(() => [...MISSING])).toEqual([]);
      expect(problems, 'the page reported errors').toEqual([]);
    });
  }
});

test.describe('roster', () => {
  test.use(DESKTOP);
  test('the player picker lists the club by jersey number and the arrows step through it, wrapping at the ends', async ({page}) => {
    const problems = await prepare(page);
    await page.goto('./');
    await settled(page);
    await go(page, '#BOS', () => !!document.querySelector('#player option'));
    const roster = await page.evaluate(() => [...document.querySelectorAll('#player option')].map(o => [o.dataset.j, o.value]));
    const nums = roster.map(([j]) => Number(j));
    expect(nums).toEqual([...nums].sort((a, b) => a - b));
    expect(roster.length).toBeGreaterThan(2);
    const first = roster[0][1], second = roster[1][1], last = roster[roster.length - 1][1];
    await go(page, `#BOS/${first}`, p => document.querySelector('#player').value === p, first);
    expect(await page.getAttribute('#next', 'href')).toBe(`#BOS/${second}`);
    expect(await page.getAttribute('#prev', 'href')).toBe(`#BOS/${last}`);
    await page.keyboard.press('ArrowRight');
    await page.waitForFunction(p => document.querySelector('#player').value === p, second);
    await page.click('#prev');
    await page.waitForFunction(p => document.querySelector('#player').value === p, first);
    expect(problems, 'the page reported errors').toEqual([]);
  });
});

test.describe('game log', () => {
  test.use(DESKTOP);
  test('its heading closes and opens the log, and the choice is kept across visits', async ({page}) => {
    const problems = await prepare(page);
    await page.goto('./#BOS');
    await settled(page);
    const isOpen = () => page.evaluate(() => document.querySelector('#log-sec').open);
    expect(await isOpen()).toBe(true);
    await page.click('#log-sec summary');
    expect(await isOpen()).toBe(false);
    expect(await page.locator('#log').isVisible()).toBe(false);
    await page.reload();
    await settled(page);
    expect(await isOpen()).toBe(false);
    await page.focus('#log-sec summary');
    await page.keyboard.press('Enter');
    expect(await isOpen()).toBe(true);
    expect(await page.locator('#log').isVisible()).toBe(true);
    expect(problems, 'the page reported errors').toEqual([]);
  });
});
