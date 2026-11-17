// Passing network: the club page's ring of the ten players with the most assists given plus received, ordered by assists
// given, an arrow from passer to scorer for each pair between them carrying that pair's season sum from assists/<CODE>.json
// (pairs of one assist hidden until one of the two is picked), and the club's top eight pairs ranked like duoSort. The top
// pair's count is the one the passer's "Assists to" and the scorer's "Assisted by" show. Picking a player keeps only his
// arrows, each with its count; picking him again clears it.
import {test, expect} from '@playwright/test';
import {DESKTOP, PHONE, prepare, settled, go, noSidewaysScroll} from './site.js';

const CODE = 'BOS';
const json = (page, path) => page.evaluate(p => fetch(`${META.base}${p}`).then(r => r.json()), path);

// the season pairs as the page sums them, and the names it shows them by
async function season(page) {
  const [f, club, L] = await Promise.all([json(page, `assists/${CODE}.json`), json(page, `${CODE}.json`), json(page, 'leaders.json')]);
  const by = {}, names = {};
  for (const x of L.players) names[x.pid] = x.name;
  for (const x of club.players) names[x.pid] = x.name;
  for (const [, a, b, ast, pts] of f.pairs) {
    const d = by[`${a}>${b}`] || (by[`${a}>${b}`] = {a, b, ast: 0, pts: 0});
    d.ast += ast;
    d.pts += pts;
  }
  return {pairs: Object.values(by), name: p => names[p] || p};
}

const visibleEdges = page => page.evaluate(() => [...document.querySelectorAll('#tm-net .e')].filter(e => getComputedStyle(e).display !== 'none').map(e => {
  const n = [...e.querySelectorAll('.n')].find(x => getComputedStyle(x).display !== 'none');
  return {k: `${e.dataset.a}>${e.dataset.b}`, label: n ? n.textContent : null};
}));

async function open(page, lang) {
  const problems = await prepare(page, {lang, theme: lang === 'tr' ? 'dark' : 'light'});
  await page.goto('./?l');
  await settled(page);
  await go(page, `#team/${CODE}`, () => !document.querySelector('#tm-net-sec').hidden && !!document.querySelector('#tm-net .pn'));
  await page.click('#tm-net-sec > summary');
  await page.waitForFunction(() => document.querySelector('#tm-net-sec').open);
  return problems;
}

for (const [name, use, lang] of [['desktop', DESKTOP, 'en'], ['phone', PHONE, 'tr']]) {
  test.describe(`passing network (${name}, ${lang})`, () => {
    test.use(use);
    test('the ring, its arrows and the top pairs are the season sums of the assist pairs', async ({page}, info) => {
      const problems = await open(page, lang);
      const {pairs, name: nm} = await season(page);
      const given = {}, got = {};
      for (const d of pairs) { given[d.a] = (given[d.a] || 0) + d.ast; got[d.b] = (got[d.b] || 0) + d.ast; }
      const gv = p => given[p] || 0, gt = p => got[p] || 0, all = Object.keys({...given, ...got});
      const ring = all.sort((x, y) => (gv(y) + gt(y)) - (gv(x) + gt(x)) || gv(y) - gv(x) || nm(x).localeCompare(nm(y))).slice(0, 10)
        .sort((x, y) => gv(y) - gv(x) || gt(y) - gt(x) || nm(x).localeCompare(nm(y)));
      expect(ring.length).toBe(Math.min(10, all.length));
      expect(await page.evaluate(() => [...document.querySelectorAll('#tm-net .nd')].map(n => n.dataset.pid))).toEqual(ring);
      // every pair between two ring players is one arrow carrying its season sum; pairs of one assist wait for a pick
      const on = new Set(ring), between = pairs.filter(d => on.has(d.a) && on.has(d.b));
      const drawn = await page.evaluate(() => [...document.querySelectorAll('#tm-net .e')].map(e => ({k: `${e.dataset.a}>${e.dataset.b}`, n: +e.dataset.n, title: e.querySelector('title').textContent})));
      expect(drawn.map(e => e.k).sort()).toEqual(between.map(d => `${d.a}>${d.b}`).sort());
      const sum = Object.fromEntries(pairs.map(d => [`${d.a}>${d.b}`, d.ast]));
      for (const e of drawn) {
        expect(e.n, e.k).toBe(sum[e.k]);
        expect(e.title).toMatch(new RegExp(` → .+: ${sum[e.k]}$`));
      }
      expect((await visibleEdges(page)).map(e => e.k).sort()).toEqual(between.filter(d => d.ast > 1).map(d => `${d.a}>${d.b}`).sort());
      // the table: the top eight pairs by assists then points, equal pairs sharing a rank
      const top = [...pairs].sort((x, y) => (y.ast - x.ast) || (y.pts - x.pts) || nm(x.a).localeCompare(nm(y.a)) || nm(x.b).localeCompare(nm(y.b))).slice(0, 8);
      const rows = await page.evaluate(() => [...document.querySelectorAll('#tm-net .pnt tbody tr')].map(tr => [tr.dataset.pair, ...[...tr.cells].map(c => c.textContent)]));
      let rank = 0;
      expect(rows).toEqual(top.map((d, i) => { if (!i || top[i - 1].ast !== d.ast || top[i - 1].pts !== d.pts) rank = i + 1; return [`${d.a}>${d.b}`, String(rank), expect.stringContaining(' → '), String(d.ast), String(d.pts)]; }));
      const links = await page.evaluate(() => [...document.querySelectorAll('#tm-net .pnt tbody tr:first-child a')].map(a => a.getAttribute('href')));
      expect(links).toEqual([`#${CODE}/${top[0].a}`, `#${CODE}/${top[0].b}`]);
      await page.locator('#tm-net-sec').scrollIntoViewIfNeeded();
      await page.screenshot({path: info.outputPath(`network-${name}-${lang}.png`)});
      await noSidewaysScroll(page, 'club passing network');
      // nothing on the ring is cut off: every name and count inside the drawing
      const cut = await page.evaluate(() => {
        const svg = document.querySelector('#tm-net svg'), vb = svg.viewBox.baseVal, r = svg.getBoundingClientRect();
        const out = r.left < 0 || r.right > document.documentElement.clientWidth ? ['the ring itself'] : [];
        for (const t of svg.querySelectorAll('.lb')) { const b = t.getBBox(); if (b.x < vb.x || b.y < vb.y || b.x + b.width > vb.x + vb.width || b.y + b.height > vb.y + vb.height) out.push(t.textContent); }
        return out;
      });
      expect(cut, 'labels cut off').toEqual([]);
      // the top pair's count is the passer's first "Assists to" row and the scorer's first "Assisted by" row
      for (const [who, side, other] of [[top[0].a, 'out', top[0].b], [top[0].b, 'in', top[0].a]]) {
        await go(page, `#${CODE}/${who}`, s => !document.querySelector('#duo').hidden && document.querySelectorAll(`#duo-cols [data-side="${s}"] a`).length > 0, side);
        const list = await page.evaluate(s => [...document.querySelectorAll(`#duo-cols [data-side="${s}"] a`)].map(a => [a.dataset.pid, a.querySelector('.v').firstChild.textContent]), side);
        expect(list[0][1], `${who} ${side}`).toBe(String(top[0].ast));
        expect(list.find(r => r[0] === other), `${who} ${side} lists ${other}`).toEqual([other, String(top[0].ast)]);
      }
      if (lang === 'tr') expect(await page.evaluate(() => [...MISSING]), 'Turkish strings missing from lang/tr.json').toEqual([]);
      expect(problems, 'the page reported errors').toEqual([]);
    });

    test('a player who has left the club keeps his pairs and his name, and the ring holds ten', async ({page}) => {
      // two players of another club added to this club's file, as after a trade: one in the club's top pair, one with a
      // single assist who is the eleventh player and stays off the ring
      const problems = await prepare(page, {lang, theme: lang === 'tr' ? 'dark' : 'light'});
      await page.goto('./?l');
      await settled(page);
      const [L, club] = await Promise.all([json(page, 'leaders.json'), json(page, `${CODE}.json`)]);
      const gone = L.players.filter(x => x.team !== CODE).slice(0, 2), star = club.players[0].pid;
      await page.route(new RegExp(`/assists/${CODE}\\.json`), async r => {
        const f = await (await r.fetch()).json();
        f.pairs.push([0, gone[0].pid, star, 99, 230], [1, gone[1].pid, star, 1, 2]);
        await r.fulfill({contentType: 'application/json', body: JSON.stringify(f)});
      });
      await go(page, `#team/${CODE}`, () => !!document.querySelector('#tm-net .pn'));
      const ring = await page.evaluate(() => [...document.querySelectorAll('#tm-net .nd')].map(n => [n.dataset.pid, n.getAttribute('aria-label')]));
      expect(ring.length).toBe(10);
      expect(ring[0]).toEqual([gone[0].pid, gone[0].name]);
      expect(ring.map(n => n[0])).not.toContain(gone[1].pid);
      const first = await page.evaluate(() => { const tr = document.querySelector('#tm-net .pnt tbody tr'); return [tr.dataset.pair, tr.cells[1].textContent, tr.cells[2].textContent, tr.querySelector('a').getAttribute('href')]; });
      expect(first[0]).toBe(`${gone[0].pid}>${star}`);
      expect(first[1].startsWith(gone[0].name.split(' ').slice(1).join(' '))).toBe(true);
      expect(first[2]).toBe('99');
      expect(first[3]).toBe(`#${CODE}/${gone[0].pid}`);
      expect(problems, 'the page reported errors').toEqual([]);
    });

    test('picking a player keeps exactly his arrows with their counts, and picking him again clears it', async ({page}, info) => {
      const problems = await open(page, lang);
      const {pairs} = await season(page);
      const ring = await page.evaluate(() => [...document.querySelectorAll('#tm-net .nd')].map(n => n.dataset.pid)), on = new Set(ring);
      const tap = sel => use === PHONE ? page.tap(sel) : page.click(sel);
      const p = ring[0], node = `#tm-net .nd[data-pid="${p}"]`;
      const box = `${node} .bx`;
      const mine = q => pairs.filter(d => on.has(d.a) && on.has(d.b) && (d.a === q || d.b === q)).map(d => ({k: `${d.a}>${d.b}`, label: String(d.ast)})).sort((x, y) => x.k.localeCompare(y.k));
      const shown = async () => (await visibleEdges(page)).sort((x, y) => x.k.localeCompare(y.k));
      const rest = pairs.filter(d => on.has(d.a) && on.has(d.b) && d.ast > 1).map(d => `${d.a}>${d.b}`).sort();
      await tap(box);
      expect(await page.getAttribute(node, 'aria-pressed')).toBe('true');
      expect(await shown()).toEqual(mine(p));
      expect(await page.evaluate(q => [...document.querySelectorAll('#tm-net .e.out')].every(e => e.dataset.a === q) && [...document.querySelectorAll('#tm-net .e.in')].every(e => e.dataset.b === q), p)).toBe(true);
      await page.locator('#tm-net-sec').scrollIntoViewIfNeeded();
      await page.screenshot({path: info.outputPath(`network-focus-${name}-${lang}.png`)});
      await tap(box);
      expect(await page.getAttribute(node, 'aria-pressed')).toBe('false');
      expect((await shown()).map(e => e.k)).toEqual(rest);
      expect((await shown()).every(e => e.label === null)).toBe(true);
      // the keyboard picks too, and a tap on the empty ring clears it
      const q = ring[1];
      await page.focus(`#tm-net .nd[data-pid="${q}"]`);
      await page.keyboard.press('Enter');
      expect(await shown()).toEqual(mine(q));
      await page.locator('#tm-net svg').click({position: {x: 4, y: 4}});
      expect(await page.evaluate(() => document.querySelectorAll('#tm-net .nd[aria-pressed="true"]').length)).toBe(0);
      expect((await shown()).map(e => e.k)).toEqual(rest);
      await noSidewaysScroll(page, 'club passing network, picked');
      expect(problems, 'the page reported errors').toEqual([]);
    });
  });
}
