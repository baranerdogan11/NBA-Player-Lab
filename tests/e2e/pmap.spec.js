// The player map: every player on the usage board's floor has his face at his USG% (across) and TS% (up) as the USG%
// and TS% boards show them; the scale is the whole pool's, so a position filter keeps each face where it was; a face
// picked shows those two values with their ranks among the faces shown, the highest usage picked on arrival; it fits
// a phone without a sideways scroll and reads in Turkish. A club picker narrows it to one club, with or without a position.
/* global get */
import {test, expect} from '@playwright/test';
import {PHONE, prepare, settled, go, noSidewaysScroll} from './site.js';

const ready = () => document.querySelectorAll('#ld-pmap .lm-d').length > 0 && !!document.querySelector('#ld-pmap-card a');
const faces = page => page.$$eval('#ld-pmap .lm-d', bs => {
  const box = document.querySelector('#ld-pmap .lm').getBoundingClientRect();
  return bs.map(b => { const r = b.getBoundingClientRect(); return {pid: b.dataset.pid, u: b.dataset.usg, ts: b.dataset.ts, x: (r.left + r.width / 2 - box.left) / box.width, y: (r.top + r.height / 2 - box.top) / box.height}; });
});
const card = page => page.$eval('#ld-pmap-card', el => ({pid: el.dataset.pid, v: Object.fromEntries([...el.querySelectorAll('[data-k]')].map(s => [s.dataset.k, [s.querySelector('.v').textContent, s.querySelector('.rk')?.textContent ?? null]]))}));

test('each face stands at the player\'s USG% and TS% from the boards, and a filter keeps it there', async ({page}) => {
  const problems = await prepare(page);
  const board = async stat => {
    await go(page, `#leaders/${stat}`, () => document.querySelectorAll('#ld tbody tr[data-pid]').length > 0);
    return page.$$eval('#ld tbody tr[data-pid]', trs => Object.fromEntries(trs.map(tr => [tr.dataset.pid, tr.querySelector('.k').textContent])));
  };
  await page.goto('./?l#leaders/usg');
  await settled(page);
  const U = await board('usg'), T = await board('ts');
  await go(page, '#leaders/map', ready);
  expect(await page.getAttribute('#ld-tabs [aria-current="true"]', 'href')).toBe('#leaders/map');
  expect(await page.isHidden('#ld-sec')).toBe(true);
  const all = await faces(page);
  // the pool is the usage board's (its top 25 all on the map), every value as the boards show it
  for (const pid of Object.keys(U)) expect(all.find(f => f.pid === pid)?.u, `${pid} usage`).toBe(U[pid]);
  for (const f of all) if (T[f.pid]) expect(f.ts, `${f.pid} TS%`).toBe(T[f.pid]);
  for (const f of all) expect(f.x > 0 && f.x < 1 && f.y > 0 && f.y < 1, `${f.pid} inside the sheet`).toBe(true);
  // linear: across by usage, up by TS%
  const lin = (k, pos) => {
    const a = all.reduce((m, f) => (+f[k] < +m[k] ? f : m)), b = all.reduce((m, f) => (+f[k] > +m[k] ? f : m)), s = (b[pos] - a[pos]) / (b[k] - a[k]);
    for (const f of all) expect(Math.abs(f[pos] - (a[pos] + (f[k] - a[k]) * s)), `${f.pid} ${k}`).toBeLessThan(0.004);
    return s;
  };
  expect(lin('u', 'x')).toBeGreaterThan(0);
  expect(lin('ts', 'y')).toBeLessThan(0);
  // the busiest picked, ranks among the faces shown
  const top = all.reduce((m, f) => (+f.u > +m.u ? f : m));
  const rank = (list, k, v) => 1 + list.filter(f => +f[k] > +v).length;
  const c0 = await card(page);
  expect(c0.pid).toBe(top.pid);
  expect(c0.v.usg).toEqual([top.u, '1']);
  expect(c0.v.ts).toEqual([top.ts, String(rank(all, 'ts', top.ts))]);
  const other = all[0];
  await page.click(`#ld-pmap .lm-d[data-pid="${other.pid}"]`, {force: true});
  const c1 = await card(page);
  expect(c1.pid).toBe(other.pid);
  expect(c1.v.usg).toEqual([other.u, String(rank(all, 'u', other.u))]);
  expect(await page.$$eval('#ld-pmap .lm-d.on', bs => bs.map(b => b.dataset.pid))).toEqual([other.pid]);
  expect(await page.getAttribute('#ld-pmap-card a', 'href')).toMatch(new RegExp(`^#[A-Z]{3}/${other.pid}$`));
  // guards only: a subset, each face where it was
  await go(page, '#leaders/map/G', () => document.querySelector('#ld-pos [aria-current="true"]')?.getAttribute('href') === '#leaders/map/G' && !!document.querySelector('#ld-pmap-card a'));
  const g = await faces(page);
  expect(g.length).toBeGreaterThan(0);
  expect(g.length).toBeLessThan(all.length);
  for (const f of g) {
    const was = all.find(x => x.pid === f.pid);
    expect(was, `${f.pid} was on the full map`).toBeTruthy();
    expect(Math.abs(f.x - was.x) + Math.abs(f.y - was.y), `${f.pid} stays put`).toBeLessThan(0.002);
  }
  const pos = await page.evaluate(async pids => { const L = (await get('leaders.json')).players; return pids.map(p => L.find(x => x.pid === p).pos); }, g.map(f => f.pid));
  for (const p of pos) expect(p[0]).toBe('G');
  expect(problems, 'the page reported errors').toEqual([]);
});

test('the club filter keeps the position filter, and both keep every face where it was', async ({page}) => {
  const problems = await prepare(page);
  await page.goto('./?l#leaders/map');
  await settled(page);
  await page.waitForFunction(ready);
  const all = await faces(page);
  const L = await page.evaluate(async () => (await get('leaders.json')).players.map(p => [p.pid, p.team, p.pos]));
  const by = Object.fromEntries(L.map(([pid, c, pos]) => [pid, {c, pos}]));
  const club = by[all[0].pid].c;
  // the club picker, then guards: the hash carries both, every face is a guard of that club, each where it was
  await page.click('#ld-map .pick .sel');
  await page.click(`#menu [role="option"][data-v="${club}"]`);
  await page.waitForFunction(c => location.hash === `#leaders/map/all/${c}` && !!document.querySelector('#ld-pmap-card a'), club);
  const c1 = await faces(page);
  expect(c1.length).toBeGreaterThan(0);
  for (const f of c1) expect(by[f.pid].c).toBe(club);
  expect(c1.length).toBe(all.filter(f => by[f.pid].c === club).length);
  expect(await page.getAttribute('#ld-pos a[href$="/G/' + club + '"]', 'aria-current')).toBe('false');
  await go(page, `#leaders/map/G/${club}`, () => document.querySelector('#ld-pos [aria-current="true"]')?.getAttribute('href') === `#leaders/map/G/${location.hash.split('/').pop()}`);
  const c2 = await faces(page);
  for (const f of c2) {
    expect([by[f.pid].c, (by[f.pid].pos || '')[0]]).toEqual([club, 'G']);
    const was = all.find(x => x.pid === f.pid);
    expect(Math.abs(f.x - was.x) + Math.abs(f.y - was.y), `${f.pid} stays put`).toBeLessThan(0.002);
  }
  expect(await page.$eval('#ld-mteam', s => s.value)).toBe(club);
  // back to every club, still guards
  await page.click('#ld-map .pick .sel');
  await page.click('#menu [role="option"][data-v=""]');
  await page.waitForFunction(() => location.hash === '#leaders/map/G');
  expect(problems, 'the page reported errors').toEqual([]);
});

test.describe('phone', () => {
  test.use(PHONE);
  test('the map fits a phone in Turkish and a tap picks a player', async ({page}) => {
    const problems = await prepare(page, {lang: 'tr', theme: 'dark'});
    await page.goto('./?l#leaders/map');
    await settled(page);
    await page.waitForFunction(ready);
    await noSidewaysScroll(page, 'player map');
    expect(await page.textContent('#ld-tabs [aria-current="true"]')).toBe('Oyuncu haritası');
    expect(await page.textContent('#ld-pos [aria-current="true"]')).toBe('Tümü');
    const box = await page.$eval('#ld-pmap .lm', el => { const r = el.getBoundingClientRect(); return [r.width, r.height]; });
    expect(Math.abs(box[0] - box[1]), 'the sheet is square').toBeLessThan(2);
    const pid = await page.$eval('#ld-pmap .lm-d:not(.on)', b => b.dataset.pid);
    await page.tap(`#ld-pmap .lm-d[data-pid="${pid}"]`, {force: true});
    expect(await page.getAttribute('#ld-pmap-card', 'data-pid')).toBe(pid);
    expect(await page.evaluate(() => [...MISSING])).toEqual([]);
    expect(problems, 'the page reported errors').toEqual([]);
  });
});
