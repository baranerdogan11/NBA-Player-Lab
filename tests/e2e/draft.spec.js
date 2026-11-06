// Draft: the Player hero and each Compare corner say when a player was drafted (year, round, overall pick), "Undrafted"
// for a player who was not, and nothing for a player without a roster row (the feed has no draft for him).
import {test, expect} from '@playwright/test';
import {DESKTOP, PHONE, prepare, settled, go, noSidewaysScroll} from './site.js';

const leaders = page => page.evaluate(() => fetch(`${META.base}leaders.json`).then(r => r.json()).then(d => d.players));
const say = (lang, d) => !d.length ? (lang === 'tr' ? 'Draft edilmedi' : 'Undrafted')
  : lang === 'tr' ? `Draft ${d[0]}, ${d[1]}. tur, ${d[2]}. sıra` : `Draft ${d[0]}, round ${d[1]}, pick ${d[2]}`;

for (const [name, use, lang, theme] of [['desktop', DESKTOP, 'en', 'light'], ['phone', PHONE, 'tr', 'dark']]) {
  test.describe(`draft (${name})`, () => {
    test.use(use);
    test(`the hero and the compare corners give the draft (${lang})`, async ({page}, info) => {
      const problems = await prepare(page, {lang, theme});
      await page.goto('./?l#BOS');
      await settled(page);
      const L = await leaders(page);
      const picked = L.find(p => p.draft && p.draft.length && p.draft[1] === 2), undrafted = L.find(p => p.draft && !p.draft.length), unknown = L.find(p => p.draft === null);
      expect(picked && undrafted && unknown, 'the fixture has drafted, undrafted and unknown players').toBeTruthy();

      for (const p of [picked, undrafted]) {
        await go(page, `#${p.team}/${p.pid}`, pid => document.querySelector('#player').value === pid && document.querySelector('#hero h1'), p.pid);
        await expect(page.locator('#hero [data-k="draft"]')).toHaveText(say(lang, p.draft));
      }
      // the club file agrees with leaders.json
      const club = await page.evaluate(c => fetch(`${META.base}${c}.json`).then(r => r.json()), picked.team);
      expect(club.players.find(x => x.pid === picked.pid).draft).toEqual(picked.draft);
      await go(page, `#${picked.team}/${picked.pid}`, pid => document.querySelector('#player').value === pid, picked.pid);
      await page.screenshot({path: info.outputPath(`player-draft-${name}-${lang}.png`), fullPage: false});
      await noSidewaysScroll(page, 'Player page with a draft');

      await go(page, `#${unknown.team}/${unknown.pid}`, pid => document.querySelector('#player').value === pid && document.querySelector('#hero h1'), unknown.pid);
      await expect(page.locator('#hero [data-k="draft"]')).toHaveCount(0);

      await go(page, `#compare/${picked.pid}/${undrafted.pid}`, () => document.body.dataset.page === 'compare' && document.querySelectorAll('#cmp-vs .dr').length === 2);
      expect(await page.$$eval('#cmp-vs .dr', ps => ps.map(p => p.textContent))).toEqual([picked, undrafted].map(p => say(lang, p.draft)));
      await page.screenshot({path: info.outputPath(`compare-draft-${name}-${lang}.png`), fullPage: false});
      await noSidewaysScroll(page, 'Compare with drafts');
      await go(page, `#compare/${picked.pid}/${unknown.pid}`, pid => document.body.dataset.page === 'compare' && location.hash.endsWith(pid), unknown.pid);
      await expect(page.locator('#cmp-vs .dr')).toHaveCount(1);
      expect(problems, 'the page reported errors').toEqual([]);
    });
  });
}
