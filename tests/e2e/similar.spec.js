// Similar role: the Player page shows the three players of similar.json for him, nearest first, each a face, surname and
// club opening Compare with the two of them; a player without comps has no section, and the row fits a phone.
import {test, expect} from '@playwright/test';
import {DESKTOP, PHONE, prepare, settled, go, noSidewaysScroll} from './site.js';

for (const [name, use, lang] of [['desktop', DESKTOP, 'en'], ['phone', PHONE, 'tr']]) {
  test.describe(`similar role (${name}, ${lang})`, () => {
    test.use(use);
    test('the Player page shows his three comps from similar.json, and each opens Compare', async ({page}, info) => {
      const problems = await prepare(page, {lang, theme: lang === 'tr' ? 'dark' : 'light'});
      await page.goto('./');
      await settled(page);
      await go(page, '#BOS', () => !document.querySelector('#sim').hidden && document.querySelectorAll('#sims a').length > 0);
      const pid = await page.evaluate(() => document.querySelector('#player').value);
      const [S, L] = await page.evaluate(() => Promise.all([fetch(`${META.base}similar.json`).then(r => r.json()), fetch(`${META.base}leaders.json`).then(r => r.json())]));
      const want = S.players[pid], by = Object.fromEntries(L.players.map(p => [p.pid, p]));
      expect(want).toHaveLength(3);
      const shown = await page.evaluate(() => [...document.querySelectorAll('#sims a')].map(a => [a.dataset.pid, a.getAttribute('href'), a.querySelector('small .cd').textContent]));
      expect(shown).toEqual(want.map(q => [q, `#compare/${pid}/${q}`, by[q].team]));
      expect(await page.locator('#sim h2').textContent()).toBe(lang === 'tr' ? 'Benzer rol' : 'Similar role');
      await page.locator('#sim').scrollIntoViewIfNeeded();
      await page.screenshot({path: info.outputPath(`player-${name}-${lang}.png`)});
      await noSidewaysScroll(page, 'similar role');
      await page.click(`#sims a[data-pid="${want[0]}"]`);
      await page.waitForFunction(() => document.body.dataset.page === 'compare');
      expect(await page.evaluate(() => [document.querySelector('#cmp-a').value, document.querySelector('#cmp-b').value])).toEqual([pid, want[0]]);
      expect(problems, 'the page reported errors').toEqual([]);
    });

    test('a player without comps has no Similar role section', async ({page}) => {
      const problems = await prepare(page, {lang});
      await page.goto('./');
      await settled(page);
      const [S, L] = await page.evaluate(() => Promise.all([fetch(`${META.base}similar.json`).then(r => r.json()), fetch(`${META.base}leaders.json`).then(r => r.json())]));
      const none = L.players.find(p => !S.players[p.pid]);
      test.skip(!none, 'every fixture player has comps');
      await go(page, `#${none.team}/${none.pid}`, () => document.querySelector('#player').value && !document.querySelector('#log tbody').classList.contains('x'));
      await page.waitForTimeout(300);
      expect(await page.locator('#sim').isHidden()).toBe(true);
      expect(problems, 'the page reported errors').toEqual([]);
    });
  });
}
