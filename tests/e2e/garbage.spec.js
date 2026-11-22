// Garbage time: the Without garbage time switch on the Player page's Lineups section and on Standings' Ratings takes the
// gt rows of the lineup files (and ratings.json's gt totals) off the figures, off by default and remembered on the
// device; every value is worked out here from the files' integer totals with the site's one rounding rule. The Four
// Factors keep every minute and have no switch.
import {test, expect} from '@playwright/test';
import {DESKTOP, PHONE, prepare, settled, go, noSidewaysScroll} from './site.js';

const rq = (num, den) => Math.floor((2 * num * 10 + den) / (2 * den));
const P100 = x => 100 * (x.fga - x.oreb + x.tov) + 44 * x.fta;
const rtg = x => P100(x) >= 100 ? rq(10000 * x.pts, P100(x)) : null;
const show = (q, sign) => q == null ? '–' : (q > 0 && sign ? '+' : q < 0 ? '-' : '') + (Math.abs(q) / 10).toFixed(1);
const clean = s => s.replace(',', '.').replace('−', '-');
// a row's for and against sides, as {pts, fga, oreb, tov, fta}
const sides = s => [{pts: s[1], fga: s[3], oreb: s[4], tov: s[5], fta: s[6]}, {pts: s[2], fga: s[7], oreb: s[8], tov: s[9], fta: s[10]}];

for (const [name, use, lang] of [['desktop', DESKTOP, 'en'], ['phone', PHONE, 'tr']]) {
  test.describe(`garbage time (${name})`, () => {
    test.use(use);
    test(`the Lineups switch leaves garbage time out of on/off and the fives (${lang})`, async ({page}, info) => {
      const problems = await prepare(page, {lang});
      await page.goto('./?l#standings');
      await settled(page);
      // a player who played garbage time, and every club file's rows with and without it
      const {code, pid, files} = await page.evaluate(async () => {
        const files = {};
        for (const x of IDX.teams) files[x.code] = await fetch(`${META.base}lineups/${x.code}.json`).then(r => r.json());
        const [c, f] = Object.entries(files).find(([, f]) => f.gt.length);
        return {code: c, pid: f.fives[f.gt[0][1]][0], files};
      });
      const sums = gtOut => {
        const on = Array(11).fill(0), tot = Array(11).fill(0);
        for (const f of Object.values(files)) {
          const cut = Object.fromEntries(f.gt.map(r => [`${r[0]},${r[1]}`, r]));
          for (const r of f.rows) {
            const g = gtOut && cut[`${r[0]},${r[1]}`];
            const v = r.slice(2).map((x, k) => x - (g ? g[2 + k] : 0));
            if (!f.fives[r[1]].includes(pid)) { if (f.fives.some(five => five.includes(pid))) v.forEach((x, k) => { tot[k] += x; }); continue; }
            v.forEach((x, k) => { on[k] += x; tot[k] += x; });
          }
        }
        const off = tot.map((x, k) => x - on[k]);
        const rate = s => { const [f, a] = sides(s), o = rtg(f), d = rtg(a); return [o, d, o != null && d != null ? o - d : null]; };
        return {pm: on[1] - on[2], on: rate(on), off: rate(off)};
      };
      await go(page, `#${code}/${pid}`, p => document.querySelector('#player').value === p && !document.querySelector('#lu').hidden, pid);
      await page.click('#lu summary');
      const read = () => page.$$eval('#onoff tbody tr', trs => trs.map(tr => [...tr.cells].slice(1).map(td => td.textContent)));
      const expectShown = async gtOut => {
        const w = sums(gtOut), oo = (await read()).map(r => r.map(clean));
        expect(oo[0], `on court, garbage time ${gtOut ? 'out' : 'in'}`).toEqual([(w.pm > 0 ? '+' : '') + String(w.pm), show(w.on[0]), show(w.on[1]), show(w.on[2], 1)]);
        expect(oo[1].slice(1)).toEqual([show(w.off[0]), show(w.off[1]), show(w.off[2], 1)]);
        return oo;
      };
      expect(await page.getAttribute('#lu-gt', 'aria-pressed')).toBe('false');
      expect(await page.isHidden('#lu .gt-tag')).toBe(true);
      const before = await expectShown(false);
      await page.click('#lu-gt');
      await page.waitForFunction(() => document.querySelector('#lu-gt').getAttribute('aria-pressed') === 'true');
      expect(await page.isVisible('#lu .gt-tag')).toBe(true);
      const after = await expectShown(true);
      expect(after, 'the switch changes the figures').not.toEqual(before);
      await noSidewaysScroll(page, '#lu');
      await page.screenshot({path: info.outputPath(`garbage-lineups-${name}-${lang}.png`), fullPage: true});
      // remembered on the device, and off again with a second press
      await page.reload();
      await settled(page);
      await page.waitForFunction(() => !document.querySelector('#lu').hidden && document.querySelector('#lu-gt').getAttribute('aria-pressed') === 'true');
      await page.click('#lu summary');
      await page.click('#lu-gt');
      await page.waitForFunction(() => document.querySelector('#lu-gt').getAttribute('aria-pressed') === 'false');
      await expectShown(false);
      expect(problems, 'the page reported errors').toEqual([]);
    });

    test(`the Ratings switch leaves each club's garbage time out (${lang})`, async ({page}, info) => {
      const problems = await prepare(page, {lang});
      await page.goto('./?l#standings/ratings');
      await settled(page);
      await page.waitForFunction(() => document.querySelectorAll('#st-ratings tbody tr').length === 30);
      const rt = await page.evaluate(() => fetch(`${META.base}ratings.json`).then(r => r.json()));
      const read = () => page.$$eval('#st-ratings tbody tr', trs => Object.fromEntries(trs.map(tr => [tr.dataset.team,
        Object.fromEntries([...tr.querySelectorAll('td[data-k]')].map(td => [td.dataset.k, td.querySelector('.v').textContent]))])));
      const want = gtOut => Object.fromEntries(rt.teams.map(c => {
        const sub = (x, y) => Object.fromEntries(['pts', 'fga', 'oreb', 'tov', 'fta'].map(k => [k, x[k] - (gtOut ? y[k] : 0)]));
        const f = sub(c.for, c.gt.for), a = sub(c.against, c.gt.against), s2 = 2 * c.sec - (gtOut ? c.gt.ds : 0);
        const o = rtg(f), d = rtg(a);
        return [c.code, {ortg: show(o), drtg: show(d), net: show(o - d, 1), pace: show(rq(144 * (P100(f) + P100(a)), s2))}];
      }));
      const tidy = v => Object.fromEntries(Object.entries(v).map(([c, x]) => [c, Object.fromEntries(Object.entries(x).map(([k, s]) => [k, clean(s)]))]));
      expect(await page.getAttribute('#st-gt', 'aria-pressed')).toBe('false');
      expect(tidy(await read())).toEqual(want(false));
      expect(rt.teams.some(c => c.gt.ds), 'the fixture has garbage time').toBe(true);
      await page.click('#st-gt');
      await page.waitForFunction(() => document.querySelector('#st-gt').getAttribute('aria-pressed') === 'true');
      expect(tidy(await read())).toEqual(want(true));
      await noSidewaysScroll(page, '#standings/ratings');
      await page.screenshot({path: info.outputPath(`garbage-ratings-${name}-${lang}.png`), fullPage: true});
      await go(page, '#standings/factors', () => document.querySelectorAll('#st-factors tbody tr').length === 30);
      expect(await page.$('#st-gt'), 'the Four Factors have no switch').toBeNull();
      await go(page, '#standings/ratings', () => document.querySelectorAll('#st-ratings tbody tr').length === 30);
      expect(await page.getAttribute('#st-gt', 'aria-pressed')).toBe('true');
      expect(tidy(await read())).toEqual(want(true));
      expect(problems, 'the page reported errors').toEqual([]);
    });
  });
}
