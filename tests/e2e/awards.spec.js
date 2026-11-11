// Awards ladder: the Awards tab on Leaders shows each ladder of awards.json in order, places shared on equal scores, with
// the RAPM, Game Score and record every other page shows and a bar of each count's rank points; Most Improved shows
// Game Score per 36 then and now and their difference; the Player hero carries a chip with his best place.
import {test, expect} from '@playwright/test';
import {DESKTOP, PHONE, prepare, settled, go, noSidewaysScroll} from './site.js';

const rq = (num, den, d = 1) => Math.floor((2 * num * 10 ** d + den) / (2 * den));
const fq = q => { const s = String(Math.abs(q)).padStart(2, '0'); return `${q < 0 ? '-' : ''}${s.slice(0, -1)}.${s.slice(-1)}`; };
const sign = s => s[0] === '-' ? '−' + s.slice(1) : s === '0.0' ? s : '+' + s;
const places = (rows, v) => { let r = 0; return rows.map((x, i) => { if (!i || v(x) !== v(rows[i - 1])) r = i + 1; return String(r); }); };
const data = page => page.evaluate(async () => {
  const j = f => fetch(`${META.base}${f}`).then(r => r.json());
  return {A: await j('awards.json'), L: (await j('leaders.json')).players, G: (await j('games.json')).games};
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
      const {A, L, G} = await data(page), P = Object.fromEntries(L.map(p => [p.pid, p]));
      const rec = {};
      for (const g of G.filter(g => g.hs != null)) for (const [c, w] of [[g.home, g.hs > g.as], [g.away, g.as > g.hs]]) { rec[c] = rec[c] || [0, 0]; rec[c][w ? 0 : 1]++; }
      const dec = s => lang === 'tr' ? s.replace('.', ',') : s;
      for (const k of ['mvp', 'roy', 'smoy', 'mip']) {
        await go(page, `#leaders/awards/${k}`, x => document.querySelector(`#ld-aw [data-award="${x}"]`)?.getAttribute('aria-current') === 'true', k);
        const rows = A[k];
        expect(rows.length, `${k} has rows in the fixture`).toBeGreaterThan(0);
        const shown = await page.evaluate(() => [...document.querySelectorAll('#ld-award tbody tr')].map(tr => [...tr.cells].map(c => c.textContent)));
        const bars = await page.evaluate(() => [...document.querySelectorAll('#ld-award tbody tr')].map(tr => [...tr.querySelectorAll('.pb')].map(b => b.style.getPropertyValue('--w'))));
        const pl = places(rows, x => k === 'mip' ? x.d : x.s);
        expect(shown.map(r => r[0]), `${k} places`).toEqual(pl);
        rows.forEach((x, i) => {
          const p = P[x.pid], r = shown[i];
          expect(r[1], k).toContain(p.name);
          expect(r[2]).toContain(p.team);
          expect(r[3]).toBe(String(p.gp));
          if (k === 'mip') {
            expect(r.slice(4), `${k} ${p.name}`).toEqual([dec(fq(rq(x.last[2] * 216, x.last[1]))), dec(fq(rq(p.gs * 216, p.sec))), dec(sign(fq(x.d)))]);
            expect(x.d).toBe(rq(p.gs * 216, p.sec) - rq(x.last[2] * 216, x.last[1]));
          } else {
            const [w, l] = rec[p.team] || [0, 0];
            expect(r.slice(4), `${k} ${p.name}`).toEqual([dec(sign(p.rapm.toFixed(1))), dec(fq(rq(p.gs, 10 * p.gp))), `${w}-${l}`, dec(fq(x.s))]);
            expect(bars[i]).toEqual(x.c.map(c => `${c}%`));
            expect(x.s).toBe(5 * x.c[0] + 3 * x.c[1] + 2 * x.c[2]);
          }
        });
        await noSidewaysScroll(page, `awards ${k}`);
        if (k === 'mvp' || k === 'mip') await page.screenshot({path: info.outputPath(`awards-${k}-${name}-${lang}.png`), fullPage: true});
      }
      expect(problems, 'the page reported errors').toEqual([]);
    });

    test(`the Player hero shows his best place on the ladders (${lang})`, async ({page}, info) => {
      const problems = await prepare(page, {lang});
      await page.goto('./?l#home');
      await settled(page);
      const {A, L} = await data(page);
      const on = new Set(['mvp', 'roy', 'smoy', 'mip'].flatMap(k => A[k].map(x => x.pid)));
      const top = L.find(p => p.pid === A.mvp[0].pid), off = L.find(p => p.gp > 0 && !on.has(p.pid));
      const sixth = A.smoy.map(x => L.find(p => p.pid === x.pid)).find(p => !A.mvp.some(x => x.pid === p.pid) && !A.roy.some(x => x.pid === p.pid));
      await go(page, `#${top.team}/${top.pid}`, x => document.querySelector('#player').value === x && !!document.querySelector('#hero h1'), top.pid);
      expect(await page.evaluate(() => [...document.querySelectorAll('#hero .lad')].map(c => [c.dataset.award, c.dataset.n, c.getAttribute('href')]))).toEqual([['mvp', '1', '#leaders/awards/mvp']]);
      expect(await page.textContent('#hero .lad')).toContain(lang === 'tr' ? '1.' : '1st');
      if (sixth) {
        await go(page, `#${sixth.team}/${sixth.pid}`, x => document.querySelector('#player').value === x && !!document.querySelector('#hero h1'), sixth.pid);
        const i = A.smoy.findIndex(x => x.pid === sixth.pid);
        expect(await page.evaluate(() => [...document.querySelectorAll('#hero .lad')].map(c => [c.dataset.award, c.dataset.n]))).toEqual([['smoy', places(A.smoy, x => x.s)[i]]].map(([a, n]) => [a, n]));
      }
      await go(page, `#${off.team}/${off.pid}`, x => document.querySelector('#player').value === x && !!document.querySelector('#hero h1'), off.pid);
      expect(await page.locator('#hero .lad').count()).toBe(0);
      await page.screenshot({path: info.outputPath(`awards-hero-${name}-${lang}.png`)});
      expect(problems, 'the page reported errors').toEqual([]);
    });
  });
}
