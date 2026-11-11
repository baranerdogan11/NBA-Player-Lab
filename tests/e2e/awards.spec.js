// Awards ladder: the Awards tab on Leaders shows each ladder of awards.json (MVP, Rookie, Defensive Player) in order,
// places shared on equal scores, with the numbers every other page shows (RAPM, Game Score and record; D-RAPM, steals and
// blocks and the club's defensive rating) and a bar of each count's rank points; the Player hero carries a chip with his
// best place.
import {test, expect} from '@playwright/test';
import {DESKTOP, PHONE, prepare, settled, go, noSidewaysScroll} from './site.js';

const rq = (num, den, d = 1) => Math.floor((2 * num * 10 ** d + den) / (2 * den));
const fq = q => { const s = String(Math.abs(q)).padStart(2, '0'); return `${q < 0 ? '-' : ''}${s.slice(0, -1)}.${s.slice(-1)}`; };
const sign = s => s[0] === '-' ? '−' + s.slice(1) : s === '0.0' ? s : '+' + s;
const places = rows => { let r = 0; return rows.map((x, i) => { if (!i || x.s !== rows[i - 1].s) r = i + 1; return String(r); }); };
const KEYS = ['mvp', 'roy', 'dpoy'];
const data = page => page.evaluate(async () => {
  const j = f => fetch(`${META.base}${f}`).then(r => r.json());
  return {A: await j('awards.json'), L: (await j('leaders.json')).players, G: (await j('games.json')).games, RT: (await j('ratings.json')).teams};
});

for (const [name, use, lang] of [['desktop', DESKTOP, 'en'], ['phone', PHONE, 'tr']]) {
  test.describe(`awards (${name})`, () => {
    test.use(use);
    test(`the Awards tab is awards.json, with the site's numbers (${lang})`, async ({page}, info) => {
      const problems = await prepare(page, {lang});
      await page.goto('./?l#leaders/awards');
      await settled(page);
      await page.waitForFunction(() => document.querySelectorAll('#ld-award tbody tr[data-pid]').length > 0);
      expect(await page.isHidden('#ld-sec')).toBe(true);
      expect(await page.isHidden('#ld-rook')).toBe(true);
      expect(await page.evaluate(() => [...document.querySelectorAll('#ld-aw a')].map(a => a.dataset.award))).toEqual(KEYS);
      const {A, L, G, RT} = await data(page), P = Object.fromEntries(L.map(p => [p.pid, p]));
      const rec = {};
      for (const g of G.filter(g => g.hs != null)) for (const [c, w] of [[g.home, g.hs > g.as], [g.away, g.as > g.hs]]) { rec[c] = rec[c] || [0, 0]; rec[c][w ? 0 : 1]++; }
      const drtg = Object.fromEntries(RT.map(c => { const a = c.against; return [c.code, fq(rq(10000 * a.pts, 100 * (a.fga - a.oreb + a.tov) + 44 * a.fta))]; }));
      const dec = s => lang === 'tr' ? s.replace('.', ',') : s;
      for (const k of KEYS) {
        await go(page, `#leaders/awards/${k}`, x => document.querySelector(`#ld-aw [data-award="${x}"]`)?.getAttribute('aria-current') === 'true', k);
        const rows = A[k];
        expect(rows.length, `${k} has rows in the fixture`).toBeGreaterThan(0);
        const shown = await page.evaluate(() => [...document.querySelectorAll('#ld-award tbody tr')].map(tr => [...tr.cells].map(c => c.textContent)));
        const bars = await page.evaluate(() => [...document.querySelectorAll('#ld-award tbody tr')].map(tr => [...tr.querySelectorAll('.pb')].map(b => b.style.getPropertyValue('--w'))));
        expect(shown.map(r => r[0]), `${k} places`).toEqual(places(rows));
        rows.forEach((x, i) => {
          const p = P[x.pid], r = shown[i], [w, l] = rec[p.team] || [0, 0];
          expect(r[1], k).toContain(p.name);
          expect(r[2]).toContain(p.team);
          expect(r[3]).toBe(String(p.gp));
          const want = k === 'dpoy' ? [dec(sign(p.drapm.toFixed(1))), dec(fq(rq(p.stl + p.blk, p.gp))), dec(drtg[p.team])]
            : [dec(sign(p.rapm.toFixed(1))), dec(fq(rq(p.gs, 10 * p.gp))), `${w}-${l}`];
          expect(r.slice(4), `${k} ${p.name}`).toEqual([...want, dec(fq(x.s))]);
          expect(bars[i]).toEqual(x.c.map(c => `${c}%`));
          expect(x.s).toBe(5 * x.c[0] + 3 * x.c[1] + 2 * x.c[2]);
        });
        await noSidewaysScroll(page, `awards ${k}`);
        if (k !== 'roy') await page.screenshot({path: info.outputPath(`awards-${k}-${name}-${lang}.png`), fullPage: true});
      }
      expect(problems, 'the page reported errors').toEqual([]);
    });

    test(`the Player hero shows his best place on the ladders (${lang})`, async ({page}, info) => {
      const problems = await prepare(page, {lang});
      await page.goto('./?l#home');
      await settled(page);
      const {A, L} = await data(page);
      const on = new Set(KEYS.flatMap(k => A[k].map(x => x.pid)));
      const top = L.find(p => p.pid === A.mvp[0].pid), off = L.find(p => p.gp > 0 && !on.has(p.pid));
      const stopper = A.dpoy.map(x => L.find(p => p.pid === x.pid)).find(p => !A.mvp.some(x => x.pid === p.pid) && !A.roy.some(x => x.pid === p.pid));
      const chips = () => page.evaluate(() => [...document.querySelectorAll('#hero .lad')].map(c => [c.dataset.award, c.dataset.n, c.getAttribute('href')]));
      await go(page, `#${top.team}/${top.pid}`, x => document.querySelector('#player').value === x && !!document.querySelector('#hero h1'), top.pid);
      expect(await chips()).toEqual([['mvp', '1', '#leaders/awards/mvp']]);
      expect(await page.textContent('#hero .lad')).toContain(lang === 'tr' ? '1.' : '1st');
      await page.screenshot({path: info.outputPath(`awards-hero-${name}-${lang}.png`)});
      if (stopper) {
        await go(page, `#${stopper.team}/${stopper.pid}`, x => document.querySelector('#player').value === x && !!document.querySelector('#hero h1'), stopper.pid);
        expect(await chips()).toEqual([['dpoy', places(A.dpoy)[A.dpoy.findIndex(x => x.pid === stopper.pid)], '#leaders/awards/dpoy']]);
      }
      await go(page, `#${off.team}/${off.pid}`, x => document.querySelector('#player').value === x && !!document.querySelector('#hero h1'), off.pid);
      expect(await page.locator('#hero .lad').count()).toBe(0);
      expect(problems, 'the page reported errors').toEqual([]);
    });
  });
}
