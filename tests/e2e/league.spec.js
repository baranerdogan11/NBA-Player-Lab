// My league, against the made-up fantasy league in tests/fixtures/league_fixture.mjs: the invite link unlocks the league
// and leaves the address, the team pick is remembered, This week's categories equal the league's own week totals (Yahoo's
// numbers, which the pipeline's gate holds our box lines to) and each line of the last night equals the player's game
// log, the roster counts the games left, and a wrong key or a missing league file shows its message instead of failing.
// Every league view draws at 390 and 1280 px, in English and Turkish, light and dark.
import {test, expect} from '@playwright/test';
import {PHONE, DESKTOP, prepare, settled, noSidewaysScroll} from './site.js';
import {dirname, join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {LEAGUE, KEY, league} from '../fixtures/league_fixture.mjs';

// the fixture league as the page decrypts it, read from the built site once the web server has made it
let LG = null;
test.beforeAll(() => { LG = league(join(dirname(fileURLToPath(import.meta.url)), '..', '..', '_site')); });
const unlocked = (page, team = 1) => page.addInitScript(([id, key, t]) => {
  try { localStorage.setItem('pl-league', JSON.stringify({id, key})); localStorage.setItem('pl-league-team', String(t)); } catch (e) {}
}, [LEAGUE, KEY, team]);
const open = async (page, hash, probe) => {
  await page.evaluate(h => { location.hash = h; }, hash);
  await settled(page);
  await page.waitForFunction(probe);
};
const WEEK = () => document.body.dataset.page === 'league' && !!document.querySelector('#lg-cats .cat');
const ROSTER = () => document.body.dataset.page === 'league' && !!document.querySelector('#lg-roster tbody tr');
const PICK = () => document.body.dataset.page === 'league' && document.querySelectorAll('#lg-body [data-lt]').length === 12;

for (const [device, size] of [['phone', PHONE], ['desktop', DESKTOP]]) {
  for (const lang of ['en', 'tr']) {
    for (const theme of ['light', 'dark']) {
      test.describe(`league · ${device} · ${lang} · ${theme}`, () => {
        test.use(size);
        test('every league view draws', async ({page}, info) => {
          const problems = await prepare(page, {lang, theme});
          await unlocked(page);
          await page.goto('./');
          await settled(page);
          for (const [name, hash, probe] of [['league-week', '#league', WEEK], ['league-roster', '#league/roster', ROSTER], ['league-pick', '#league/pick', PICK]]) {
            await open(page, hash, probe);
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

test.describe('league', () => {
  test.use(DESKTOP);

  test('the invite link unlocks the league, leaves the address, and the team pick is remembered', async ({page}) => {
    const problems = await prepare(page);
    await page.goto('./');
    await settled(page);
    expect(await page.locator('#lg-btn').isHidden(), 'no league button before the invite link').toBe(true);
    await open(page, '#league', () => !!document.querySelector('#lg-link'));
    await page.evaluate(([id, key]) => { location.hash = `league/${id}/${key}`; }, [LEAGUE, KEY]);
    await settled(page);
    await page.waitForFunction(PICK);
    expect(await page.evaluate(() => location.hash)).toBe('#league');
    expect(await page.evaluate(() => JSON.parse(localStorage.getItem('pl-league')))).toEqual({id: LEAGUE, key: KEY});
    expect(await page.locator('#lg-btn').isVisible()).toBe(true);
    await page.click('#lg-body [data-lt="3"]');
    await page.waitForFunction(WEEK);
    expect(await page.textContent('#lg-board .side.a b')).toBe(LG.teams[2].name);
    await page.reload();
    await settled(page);
    await page.waitForFunction(WEEK);
    expect(await page.textContent('#lg-board .side.a b'), 'the team pick survives a reload').toBe(LG.teams[2].name);
    expect(problems, 'the page reported errors').toEqual([]);
  });

  test('pasting the invite link opens the league; other text is refused', async ({page}) => {
    const problems = await prepare(page);
    await page.goto('./#league');
    await settled(page);
    await page.fill('#lg-link', 'hello');
    await page.click('#lg-form button');
    expect(await page.evaluate(() => document.querySelector('#lg-link').validity.valid)).toBe(false);
    await page.fill('#lg-link', `https://example.org/NBA-Player-Lab/#league/${LEAGUE}/${KEY}`);
    await page.click('#lg-form button');
    await page.waitForFunction(PICK);
    expect(problems, 'the page reported errors').toEqual([]);
  });

  test('This week equals the league\'s own week totals, and last night\'s lines equal the game logs', async ({page}) => {
    const problems = await prepare(page);
    await unlocked(page, 1);
    await page.goto('./#league');
    await settled(page);
    await page.waitForFunction(WEEK);
    const [, a, b] = LG.matchups.find(m => m[1] === 1 || m[2] === 1);
    const ya = LG.yahoo[1][a], yb = LG.yahoo[1][b];
    const want = await page.evaluate(([x, y, cats]) => cats.map(k => {
      // the same rule as the page, from the league's numbers: a percentage through rdiv, a count as it is
      const f = s => k === 'fg%' ? rdiv(100 * s.fgm, s.fga) : k === 'ft%' ? rdiv(100 * s.ftm, s.fta) : String(s[k]);
      return [k, f(x), f(y)];
    }), [ya, yb, LG.league.cats]);
    const shown = await page.evaluate(() => [...document.querySelectorAll('#lg-cats .cat')].map(c => [c.dataset.cat, c.querySelector('.v').textContent, c.querySelector('small').textContent]));
    expect(shown).toEqual(want);
    // the score: categories won and lost, a tie on equal totals (the fixture's week has one: turnovers)
    const won = LG.league.cats.filter(k => { const better = k === 'tov' ? -1 : 1; const d = k === 'fg%' ? ya.fgm * yb.fga - yb.fgm * ya.fga : k === 'ft%' ? ya.ftm * yb.fta - yb.ftm * ya.fta : ya[k] - yb[k]; return better * d > 0; }).length;
    const lost = LG.league.cats.filter(k => { const better = k === 'tov' ? -1 : 1; const d = k === 'fg%' ? ya.fgm * yb.fga - yb.fgm * ya.fga : k === 'ft%' ? ya.ftm * yb.fta - yb.ftm * ya.fta : ya[k] - yb[k]; return better * d < 0; }).length;
    expect(await page.evaluate(() => [...document.querySelectorAll('#lg-board .score span')].map(s => +s.textContent))).toEqual([won, lost]);
    expect(await page.locator('#lg-cats .cat:not(.w):not(.lo)').count()).toBe(LG.league.cats.length - won - lost);
    // last night: every line is the player's game-log row for that night
    const night = await page.evaluate(() => [...document.querySelectorAll('#lg-body table[data-t] tbody tr[data-pid]')].map(tr => ({
      pid: tr.dataset.pid, href: tr.querySelector('a').getAttribute('href'), cells: [...tr.cells].slice(1).map(td => td.textContent)})));
    expect(night.length).toBeGreaterThan(0);
    for (const row of night.slice(0, 4)) {
      await open(page, row.href, () => document.body.dataset.page === 'player' && !!document.querySelector('#log tr[data-gid]'));
      const log = await page.evaluate(() => { const tr = document.querySelector('#log tbody tr[data-gid]'); return [...tr.cells].map(td => td.textContent); });
      // game log: date, opp, result, MIN, PTS, REB, AST, STL, BLK, TOV, FG, 3P, FT, +/-
      expect(row.cells, `${row.pid} last night`).toEqual(log.slice(3, 13));
    }
    expect(problems, 'the page reported errors').toEqual([]);
  });

  test('the roster lists every player in slot order with the games his club has left this week', async ({page}) => {
    const problems = await prepare(page);
    await unlocked(page, 2);
    await page.goto('./#league/roster');
    await settled(page);
    await page.waitForFunction(ROSTER);
    const rows = await page.evaluate(() => [...document.querySelectorAll('#lg-roster tbody tr')].map(tr => ({pid: tr.dataset.pid, slot: tr.querySelector('.slot').textContent, left: +tr.querySelector('[data-left]').dataset.left, dots: tr.querySelectorAll('.left i').length, bench: tr.classList.contains('bn'), inj: tr.querySelector('.inj')?.textContent || null})));
    const T = LG.teams[1];
    expect(rows.map(r => r.pid).sort()).toEqual(T.roster.map(r => r[0]).sort());
    const order = rows.map(r => LG.league.slots.indexOf(r.slot));
    expect(order, 'slot order').toEqual([...order].sort((x, y) => x - y));
    const games = await page.evaluate(() => fetch(`${META.base}games.json`).then(r => r.json()).then(d => d.games));
    const board = await page.evaluate(() => fetch(`${META.base}leaders.json`).then(r => r.json()).then(d => d.players));
    const club = Object.fromEntries(board.map(p => [p.pid, p.team]));
    const [from, to] = LG.league.weeks[0];
    for (const r of rows) {
      const n = games.filter(g => g.hs == null && g.date >= from && g.date <= to && (g.home === club[r.pid] || g.away === club[r.pid])).length;
      expect([r.left, r.dots], `${r.pid} games left`).toEqual([n, n]);
      expect(r.bench).toBe(r.slot === 'BN' || r.slot === 'IL');
    }
    expect(rows.find(r => r.slot === 'IL').inj).toBe('O');
    expect(problems, 'the page reported errors').toEqual([]);
  });

  test('a wrong key and a missing league file show their messages', async ({page}) => {
    const problems = await prepare(page);
    await page.goto('./');
    await settled(page);
    await page.evaluate(id => { location.hash = `league/${id}/${'A'.repeat(43)}`; }, LEAGUE);
    await settled(page);
    await page.waitForFunction(() => !!document.querySelector('#lg-link') && /does not open/.test(document.querySelector('#lg-body p').textContent));
    expect(await page.evaluate(() => localStorage.getItem('pl-league')), 'a key that fails is forgotten').toBeNull();
    await page.evaluate(() => { location.hash = `league/99999/${'A'.repeat(43)}`; });
    await settled(page);
    await page.waitForFunction(() => document.querySelector('#lg-body .gate') && !document.querySelector('#lg-link'));
    expect(await page.textContent('#lg-body p')).toContain('unavailable');
    expect(problems.filter(p => !p.includes('Failed to load resource')), 'the page reported errors').toEqual([]);
  });
});
