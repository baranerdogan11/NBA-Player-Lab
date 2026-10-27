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
  ['leaders-form', '#leaders/form', () => document.body.dataset.page === 'leaders' && document.querySelectorAll('#ld-up tbody tr').length > 0],
  ['leaders-highs', '#leaders/highs', () => document.body.dataset.page === 'leaders' && document.querySelectorAll('#ld-highs .panel a').length > 0],
  ['home', '#home', () => document.body.dataset.page === 'home' && document.querySelectorAll('#hm-leaders .panel').length === 3],
  ['privacy', '#privacy', () => document.body.dataset.page === 'privacy' && document.querySelectorAll('#pg-privacy .panel').length === 3],
  ['standings-ratings', '#standings/ratings', () => document.body.dataset.page === 'standings' && document.querySelectorAll('#st-ratings tbody tr').length === 30],
  ['game-preview', '#game/0022600061', () => document.body.dataset.page === 'game' && !document.querySelector('#gm-pre').hidden && document.querySelectorAll('#pv-ff [data-k]').length === 8],
  ['standings-factors', '#standings/factors', () => document.body.dataset.page === 'standings' && document.querySelectorAll('#st-factors tbody tr').length === 30],  ['team', '#team/BOS', () => document.body.dataset.page === 'team' && document.querySelectorAll('#tm-roster tbody tr').length > 0 && document.querySelectorAll('#tm-ff td[data-k]').length === 8],
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
  test("the night's best are its box scores' top Game Scores, and open the player at that game", async ({page}) => {
    const problems = await prepare(page);
    await page.goto('./');
    await settled(page);
    const rows = await page.evaluate(() => [...document.querySelectorAll('#hm-best a')].map(a => ({pid: a.dataset.pid, gid: a.dataset.gid, href: a.getAttribute('href'),
      gs: a.querySelector('.v').firstChild.textContent, line: a.querySelector('.nm small').textContent})));
    expect(rows.length).toBe(5);
    // every line of the night's games, scored from its box score in tenths
    const all = await page.evaluate(async gids => {
      const out = [];
      for (const gid of gids) {
        const g = await fetch(`${META.base}games/${gid}.json`).then(r => r.json());
        for (const side of Object.values(g.box)) for (const x of side) if (x.sec > 0) out.push({pid: x.pid, gid, name: x.name, line: `${x.pts} PTS · ${x.reb} REB · ${x.ast} AST · ${x.fgm}-${x.fga} FG`,
          gs: 10 * x.pts + 4 * x.fgm - 7 * x.fga - 4 * (x.fta - x.ftm) + 7 * x.oreb + 3 * x.dreb + 10 * x.stl + 7 * x.ast + 7 * x.blk - 4 * x.pf - 10 * x.tov});
      }
      return out;
    }, await page.evaluate(() => [...document.querySelectorAll('#hm-games a.card')].map(a => a.dataset.gid)));
    const top = all.sort((x, y) => y.gs - x.gs || x.name.localeCompare(y.name) || x.pid.localeCompare(y.pid)).slice(0, 5);
    expect(rows.map(r => [r.pid, r.gid, r.gs, r.line])).toEqual(top.map(x => [x.pid, x.gid, (x.gs / 10).toFixed(1), x.line]));
    await page.click('#hm-best a:first-child');
    await page.waitForFunction(p => document.body.dataset.page === 'player' && document.querySelector('#player').value === p, rows[0].pid);
    expect(await page.evaluate(() => document.querySelector('#sc-game').value)).toBe(rows[0].gid);
    expect(await page.textContent('#sc .sel')).toContain(await page.evaluate(() => document.querySelector('#sc-game').selectedOptions[0].textContent));
    expect(problems, 'the page reported errors').toEqual([]);
  });
  for (const lang of ['en', 'tr']) {
    test(`before the first final it shows the first night to come, each card opening its preview, and empty boards (${lang})`, async ({page}) => {
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
      expect(got).toEqual({cards: 15, links: 15, empty: 3});
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

test.describe('profile sections', () => {
  test.use(DESKTOP);
  for (const [id, body, key] of [['sc', '#sc-court', 'pl-shots'], ['lu', '#onoff', 'pl-lineups'], ['log-sec', '#log', 'pl-log']]) {
    test(`the ${id} heading closes and opens its section, and the choice is kept across visits`, async ({page}) => {
      const problems = await prepare(page);
      await page.goto('./?l#BOS');
      await settled(page);
      await page.waitForFunction(i => !document.getElementById(i).hidden, id);
      const isOpen = () => page.evaluate(i => document.getElementById(i).open, id);
      expect(await isOpen()).toBe(true);
      await page.click(`#${id} summary`);
      expect(await isOpen()).toBe(false);
      expect(await page.locator(body).isVisible()).toBe(false);
      await page.waitForFunction(k => localStorage.getItem(k) === 'closed', key);   // the toggle event is queued, not synchronous
      await page.reload();
      await settled(page);
      expect(await isOpen()).toBe(false);
      await page.focus(`#${id} summary`);
      await page.keyboard.press('Enter');
      expect(await isOpen()).toBe(true);
      expect(await page.locator(body).isVisible()).toBe(true);
      expect(problems, 'the page reported errors').toEqual([]);
    });
  }
});

test.describe('game box scores', () => {
  test.use(DESKTOP);
  test('each club\'s heading folds its box score, and the choice is kept across games and visits', async ({page}) => {
    const problems = await prepare(page);
    await page.goto('./?l#game/0022600001');
    await settled(page);
    const open = () => page.$$eval('#gm-box details', ds => ds.map(d => d.open));
    expect(await open()).toEqual([true, true]);
    await page.click('#gm-box details[data-side="home"] summary');
    expect(await open()).toEqual([true, false]);
    expect(await page.locator('#gm-box details[data-side="home"] table').isVisible()).toBe(false);
    await page.waitForFunction(() => localStorage.getItem('pl-box-home') === 'closed');   // the toggle event is queued
    await page.reload();
    await settled(page);
    expect(await open()).toEqual([true, false]);
    await page.focus('#gm-box details[data-side="home"] summary');
    await page.keyboard.press('Enter');
    expect(await open()).toEqual([true, true]);
    expect(problems, 'the page reported errors').toEqual([]);
  });

  test('a stat heading orders that club\'s players by it, most first; again restores the box score order', async ({page}) => {
    const problems = await prepare(page);
    await page.goto('./?l#game/0022600001');
    await settled(page);
    const tb = '#gm-box table >> nth=0';
    const order = () => page.locator(tb).evaluate(t => [...t.querySelectorAll('tbody tr[data-pid]')].map(r => r.dataset.pid));
    const col = i => page.locator(tb).evaluate((t, i) => [...t.querySelectorAll('tbody tr[data-pid]')].filter(r => r.cells.length > 2).map(r => r.cells[i].textContent), i);
    const first = await order(), other = await page.locator('#gm-box table >> nth=1').evaluate(t => [...t.querySelectorAll('tbody tr[data-pid]')].map(r => r.dataset.pid));
    const num = s => Number(s.replace('−', '-').split('-')[0] || s);
    for (const [h, i] of [['REB', 3], ['AST', 6], ['FG', 11], ['+/-', 14]]) {
      await page.locator(tb).locator(`th[data-sort="${h}"] button`).click();
      const vals = (await col(i)).map(h === '+/-' ? s => Number(s.replace('−', '-').replace('+', '')) : num);
      expect(vals, h).toEqual([...vals].sort((a, b) => b - a));
      expect(await page.locator(tb).locator('th[aria-sort="descending"]').getAttribute('data-sort')).toBe(h);
      expect(await page.locator(tb).evaluate(t => t.tBodies[0].lastElementChild.classList.contains('tot'))).toBe(true);
      const dnp = await page.locator(tb).evaluate(t => [...t.querySelectorAll('tbody tr[data-pid]')].map(r => r.cells.length > 2));
      expect(dnp, 'who did not play stays below').toEqual([...dnp].sort((a, b) => +b - +a));
    }
    expect(await page.locator('#gm-box table >> nth=1').evaluate(t => [...t.querySelectorAll('tbody tr[data-pid]')].map(r => r.dataset.pid))).toEqual(other);
    await page.locator(tb).locator('th[data-sort="+/-"] button').click();
    expect(await order()).toEqual(first);
    expect(await page.locator(tb).locator('th[aria-sort]').count()).toBe(0);
    await page.locator(tb).locator('th[data-sort="PTS"] button').click();
    await page.locator(tb).locator('th[data-sort="Player"] button').click();
    expect(await order()).toEqual(first);
    expect(problems, 'the page reported errors').toEqual([]);
  });
});
