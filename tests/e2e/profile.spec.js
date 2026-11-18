// Profile: the Player page shows where he ranks in his position group on each rate of profiles.json, every number the
// percentile rdiv(100 × ahead, group) rounded once and every bar that long; a player profiles.json leaves out has no
// section; Compare puts both players' marks on the same bars with the same numbers.
import {test, expect} from '@playwright/test';
import {DESKTOP, PHONE, prepare, settled, go, noSidewaysScroll} from './site.js';

// the site's rule, half up on the exact value, as whole numbers
const pctile = (a, n) => a == null ? null : Math.floor((2 * 100 * a + n) / (2 * n));
const want = (P, pid) => { const [g, xs] = P.players[pid]; return P.keys.map((k, i) => [k, pctile(xs[i], P.groups[g][i])]); };

for (const [name, use, lang] of [['desktop', DESKTOP, 'en'], ['phone', PHONE, 'tr']]) {
  test.describe(`profile (${name}, ${lang})`, () => {
    test.use(use);
    test('the Player page shows his percentiles in his group, closed on open', async ({page}, info) => {
      const problems = await prepare(page, {lang, theme: lang === 'tr' ? 'dark' : 'light'});
      await page.goto('./');
      await settled(page);
      await go(page, '#BOS', () => !document.querySelector('#prof').hidden && document.querySelectorAll('#prof-body .pr').length > 0);
      const pid = await page.evaluate(() => document.querySelector('#player').value);
      const P = await page.evaluate(() => fetch(`${META.base}profiles.json`).then(r => r.json()));
      expect(await page.evaluate(() => document.querySelector('#prof').open)).toBe(false);
      const shown = await page.evaluate(() => [...document.querySelectorAll('#prof-body .pr')].map(r => {
        const b = r.querySelector('.bar b'), v = r.querySelector('.v').textContent;
        return [r.dataset.k, v === '–' ? null : Number(v), b ? b.style.width : ''];
      }));
      expect(shown.map(r => r.slice(0, 2))).toEqual(want(P, pid));
      for (const [, v, w] of shown) expect(w).toBe(v == null ? '' : `${v}%`);
      const [g] = P.players[pid], n = Math.max(...P.groups[g]);
      const names = {en: {G: 'guards', F: 'forwards', C: 'centres'}, tr: {G: 'gard', F: 'forvet', C: 'pivot'}}[lang];
      expect(await page.locator('#prof-grp').textContent()).toContain(`${n} ${names[g]}`);
      expect(await page.locator('#prof h2').textContent()).toBe(lang === 'tr' ? 'Profil' : 'Profile');
      expect(await page.locator('#prof-body h3').allTextContents()).toEqual(lang === 'tr' ? ['Rol', 'Verimlilik'] : ['Role', 'Efficiency']);
      expect(await page.locator('#prof-body .pf').first().locator('.pr').count()).toBe(P.role);
      await page.click('#prof summary');
      await page.locator('#prof').scrollIntoViewIfNeeded();
      await page.locator('#prof').screenshot({path: info.outputPath(`player-${name}-${lang}.png`)});
      await noSidewaysScroll(page, 'profile');
      // the numbers never wrap: one line each
      expect(await page.evaluate(() => [...document.querySelectorAll('#prof-body .v')].every(v => v.getBoundingClientRect().height < 24))).toBe(true);
      expect(problems, 'the page reported errors').toEqual([]);
    });

    test('Compare shows both players on the same bars', async ({page}, info) => {
      const problems = await prepare(page, {lang, theme: lang === 'tr' ? 'dark' : 'light'});
      await page.goto('./');
      await settled(page);
      const P = await page.evaluate(() => fetch(`${META.base}profiles.json`).then(r => r.json()));
      const [a, b] = Object.keys(P.players);
      await go(page, `#compare/${a}/${b}`, () => !document.querySelector('#cmp-prof').hidden && document.querySelectorAll('#cmp-pbody .pr').length > 0);
      const shown = await page.evaluate(() => [...document.querySelectorAll('#cmp-pbody .pr')].map(r => {
        const v = [...r.querySelectorAll('.v')].map(x => x.textContent === '–' ? null : Number(x.textContent));
        return [r.dataset.k, v[0], v[1], r.querySelector('.bar i.a')?.style.left || '', r.querySelector('.bar i.b')?.style.left || ''];
      }));
      const wa = want(P, a), wb = want(P, b);
      expect(shown).toEqual(wa.map(([k, v], i) => [k, v, wb[i][1], v == null ? '' : `${v}%`, wb[i][1] == null ? '' : `${wb[i][1]}%`]));
      await page.locator('#cmp-prof').screenshot({path: info.outputPath(`compare-${name}-${lang}.png`)});
      await noSidewaysScroll(page, 'compare profile');
      expect(problems, 'the page reported errors').toEqual([]);
    });

    test('a player without a profile has no Profile section', async ({page}) => {
      const problems = await prepare(page, {lang});
      await page.goto('./');
      await settled(page);
      const [P, L] = await page.evaluate(() => Promise.all([fetch(`${META.base}profiles.json`).then(r => r.json()), fetch(`${META.base}leaders.json`).then(r => r.json())]));
      const none = L.players.find(p => !P.players[p.pid]);
      test.skip(!none, 'every fixture player has a profile');
      await go(page, `#${none.team}/${none.pid}`, () => document.querySelector('#player').value && !document.querySelector('#log tbody').classList.contains('x'));
      await page.waitForTimeout(300);
      expect(await page.locator('#prof').isHidden()).toBe(true);
      expect(problems, 'the page reported errors').toEqual([]);
    });
  });
}
