// A game to come (#game/<gid> before its final): the tip-off in the reader's time, each club's record, last ten and rest,
// both clubs' ratings and Four Factors as Standings shows them, and the season's earlier meetings; once final, the same
// address is the game page. The fixture's first night to come is 2026-10-25 (games 0022600061 on).
import {test, expect} from '@playwright/test';
/* global get */
import {DESKTOP, prepare, settled, go} from './site.js';

test.use({...DESKTOP, timezoneId: 'Asia/Tokyo'});
const PRE = '#game/0022600061';
const preview = () => document.body.dataset.page === 'game' && !document.querySelector('#gm-pre').hidden && document.querySelectorAll('#pv-ff [data-k]').length === 8;
const games = page => page.evaluate(() => get('games.json').then(d => d.games));

test('a card for a game to come opens its preview, with the tip-off in the reader\'s time', async ({page}) => {
  const problems = await prepare(page);
  await page.goto('./#games/2026-10-25');
  await settled(page);
  const card = page.locator('#gm-list a.card.next').first();
  const gid = await card.getAttribute('data-gid');
  await card.click();
  await page.waitForFunction(preview);
  expect(page.url()).toContain(`#game/${gid}`);
  const g = (await games(page)).find(x => x.gid === gid);
  const shown = await page.evaluate(() => ({
    time: document.querySelector('#gm-board .score.tip').textContent, status: document.querySelector('#gm-board .mid small').textContent,
    final: document.querySelector('#gm-final').hidden, share: !!document.querySelector('#gm-board .share'),
  }));
  const want = new Intl.DateTimeFormat('en-US', {hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Tokyo'}).format(new Date(g.time));
  const day = new Intl.DateTimeFormat('en-US', {weekday: 'short', month: 'short', day: 'numeric', timeZone: 'Asia/Tokyo'}).format(new Date(g.time));
  expect(shown).toEqual({time: want, status: `Tip-off · ${day}`, final: true, share: false});
  expect(problems).toEqual([]);
});

test('each club\'s record and last ten agree with Standings, and its rest counts the days since its last game', async ({page}) => {
  const problems = await prepare(page);
  await page.goto(`./${PRE}`);
  await settled(page);
  await page.waitForFunction(preview);
  const G = await games(page), i = G.findIndex(g => g.gid === PRE.slice(6)), g = G[i];
  const form = await page.evaluate(() => Object.fromEntries([...document.querySelectorAll('#pv-form [data-team]')].map(d => [d.dataset.team, {
    rec: d.querySelector('.rec').textContent, dots: [...d.querySelectorAll('.form b')].map(b => b.className).join(''), rest: d.querySelector('.rest').dataset.rest}])));
  await go(page, '#standings/league', () => document.querySelectorAll('#st-body tbody tr').length === 30);
  for (const c of [g.away, g.home]) {
    const row = await page.evaluate(c => { const td = document.querySelector(`#st-body tr[data-team="${c}"]`).cells; return {w: td[2].textContent, l: td[3].textContent, dots: [...td[8].querySelectorAll('.form b')].map(b => b.className).join('')}; }, c);
    expect(form[c].rec).toBe(`${row.w}-${row.l}`);
    expect(form[c].dots).toBe(row.dots);
    const last = G.slice(0, i).filter(x => x.home === c || x.away === c).pop();
    expect(form[c].rest).toBe(String((Date.parse(g.date) - Date.parse(last.date)) / 864e5 - 1));
  }
  expect(problems).toEqual([]);
});

test('both clubs\' ratings and Four Factors, values and ranks, are the ones Standings shows', async ({page}) => {
  const problems = await prepare(page);
  await page.goto(`./${PRE}`);
  await settled(page);
  await page.waitForFunction(preview);
  const pv = await page.evaluate(() => [...document.querySelectorAll('#pv-rt [data-k], #pv-ff [data-k]')].flatMap(row =>
    [...row.querySelectorAll('.v')].map(v => ({k: row.dataset.k, team: v.dataset.team, v: v.childNodes[v.querySelector('.rk') === v.firstChild ? 1 : 0].textContent, r: v.dataset.r || null}))));
  expect(pv.length).toBe(24);
  const st = {};
  for (const view of ['ratings', 'factors']) {
    await go(page, `#standings/${view}`, v => document.querySelectorAll(`#st-${v} tbody tr`).length === 30, view);
    Object.assign(st, await page.evaluate(v => Object.fromEntries([...document.querySelectorAll(`#st-${v} td[data-k]`)].map(td =>
      [`${td.closest('tr').dataset.team}/${td.dataset.k}`, {v: td.querySelector('.v').textContent, r: td.dataset.r || null}])), view));
  }
  for (const x of pv) expect({k: x.k, team: x.team, v: x.v, r: x.r}).toEqual({k: x.k, team: x.team, ...st[`${x.team}/${x.k}`]});
  expect(problems).toEqual([]);
});

test('the season series lists the earlier finals between the two clubs, each opening its game page', async ({page}) => {
  const problems = await prepare(page);
  let pair = null;
  await page.route(/\/games\.json/, async r => {
    const d = await (await r.fetch()).json();
    const f = d.games.find(g => g.hs != null);
    pair = [f.home, f.away];
    await r.fulfill({json: {games: d.games.map(g => g.gid === PRE.slice(6) ? {...g, home: f.away, away: f.home} : g)}});
  });
  await page.goto(`./${PRE}`);
  await settled(page);
  await page.waitForFunction(preview);
  const G = await games(page);
  const want = G.filter(g => g.hs != null && g.time < G.find(x => x.gid === PRE.slice(6)).time && pair.includes(g.home) && pair.includes(g.away)).map(g => g.gid);
  expect(want.length).toBeGreaterThan(0);
  expect(await page.evaluate(() => [...document.querySelectorAll('#pv-meet a.card')].map(a => a.dataset.gid))).toEqual(want);
  await page.click('#pv-meet a.card');
  await page.waitForFunction(() => document.body.dataset.page === 'game' && document.querySelectorAll('#gm-box table').length === 2);
  expect(await page.evaluate(() => [document.querySelector('#gm-pre').hidden, document.querySelector('#gm-final').hidden])).toEqual([true, false]);
  expect(problems).toEqual([]);
});

test('clubs yet to meet say so; a final and a game to come swap the page between its two states', async ({page}) => {
  const problems = await prepare(page);
  await page.goto(`./${PRE}`);
  await settled(page);
  await page.waitForFunction(preview);
  const G = await games(page), g = G.find(x => x.gid === PRE.slice(6));
  const met = G.some(x => x.hs != null && [x.home, x.away].includes(g.home) && [x.home, x.away].includes(g.away));
  if (!met) expect(await page.locator('#pv-meet .empty').textContent()).toBe('First meeting this season.');
  await go(page, '#game/0022600001', () => document.querySelectorAll('#gm-box table').length === 2);
  expect(await page.evaluate(() => [document.querySelector('#gm-pre').hidden, document.querySelector('#gm-final').hidden, !!document.querySelector('#gm-board .score:not(.tip)')])).toEqual([true, false, true]);
  await go(page, PRE, preview);
  expect(await page.evaluate(() => [document.querySelector('#gm-pre').hidden, document.querySelector('#gm-final').hidden])).toEqual([false, true]);
  expect(problems).toEqual([]);
});
