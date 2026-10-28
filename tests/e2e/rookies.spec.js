// Rookies and countries: the Rookies switch on Leaders keeps every board to players in their first NBA season; the Player
// hero names the country a player is from, and the country picker lists everyone in the league from there, by club.
import {test, expect} from '@playwright/test';
import {DESKTOP, PHONE, prepare, settled, go, noSidewaysScroll} from './site.js';

const BOARD = () => document.body.dataset.page === 'leaders' && document.querySelectorAll('#ld tbody tr').length > 0;
const leaders = page => page.evaluate(() => fetch(`${META.base}leaders.json`).then(r => r.json()).then(d => d.players));

for (const [name, use, lang] of [['desktop', DESKTOP, 'en'], ['phone', PHONE, 'tr']]) {
  test.describe(`rookies and countries (${name})`, () => {
    test.use(use);
    test(`the Rookies switch keeps the boards to rookies (${lang})`, async ({page}, info) => {
      const problems = await prepare(page, {lang});
      await page.goto('./?l#leaders/pts');
      await settled(page);
      await page.waitForFunction(BOARD);
      const L = await leaders(page), rookie = new Set(L.filter(p => p.rookie).map(p => p.pid));
      expect(rookie.size, 'the fixture has rookies').toBeGreaterThan(0);
      const all = await page.$$eval('#ld tbody tr[data-pid]', rs => rs.map(r => r.dataset.pid));
      expect(all.some(pid => !rookie.has(pid)), 'the full board has veterans').toBe(true);

      await page.click('#ld-rook');
      await page.waitForFunction(() => location.hash === '#leaders/pts/rookies' && document.querySelector('#ld-rook').getAttribute('aria-pressed') === 'true');
      await settled(page);
      const rows = await page.$$eval('#ld tbody tr[data-pid]', rs => rs.map(r => r.dataset.pid));
      expect(rows.length).toBeGreaterThan(0);
      expect(rows.filter(pid => !rookie.has(pid)), 'only rookies on the board').toEqual([]);
      expect(await page.$eval('#ld-tabs a[href^="#leaders/reb"]', a => a.getAttribute('href'))).toBe('#leaders/reb/rookies');
      await page.screenshot({path: info.outputPath(`leaders-rookies-${name}-${lang}.png`), fullPage: true});

      await go(page, '#leaders/form/rookies', () => document.body.dataset.page === 'leaders' && !document.querySelector('#ld-form').hidden);
      const trend = await page.$$eval('#ld-form tbody tr[data-pid]', rs => rs.map(r => r.dataset.pid));
      expect(trend.filter(pid => !rookie.has(pid)), 'only rookies trending').toEqual([]);

      await go(page, '#leaders/highs', () => document.querySelectorAll('#ld-highs .panel').length > 0);
      await expect(page.locator('#ld-rook')).toBeHidden();

      await go(page, '#leaders/pts/rookies', BOARD);
      await page.click('#ld-rook');
      await page.waitForFunction(() => location.hash === '#leaders/pts' && document.querySelector('#ld-rook').getAttribute('aria-pressed') === 'false');
      await settled(page);
      expect(await page.$$eval('#ld tbody tr[data-pid]', rs => rs.map(r => r.dataset.pid))).toEqual(all);
      expect(problems, 'the page reported errors').toEqual([]);
    });

    test(`the hero says where he is from and the country picker lists the league by club (${lang})`, async ({page}, info) => {
      const problems = await prepare(page, {lang});
      await page.goto('./?l#BOS');
      await settled(page);
      const L = await leaders(page);
      const fr = L.filter(p => p.country === 'France');
      const p = fr.find(x => x.rookie) || fr[0];
      await go(page, `#${p.team}/${p.pid}`, pid => document.querySelector('#player').value === pid, p.pid);
      await expect(page.locator('#hero [data-k="from"] b')).toHaveText(lang === 'tr' ? 'Fransa' : 'France');
      if (p.rookie) await expect(page.locator('#hero .rook')).toHaveText(lang === 'tr' ? 'Çaylak' : 'Rookie');
      expect(await page.$eval('#from', s => s.value), 'no country picked yet').toBe('');

      await page.locator('#from + .sel').click();
      await page.locator(`#menu li[data-v="France"]`).click();
      await page.waitForFunction(n => document.querySelectorAll('#player option').length === n && document.querySelector('#from').value === 'France', fr.length);
      expect(await page.$eval('#player', s => s.value), 'the player shown stays').toBe(p.pid);
      const clubs = await page.$$eval('#player optgroup', gs => gs.length);
      expect(clubs).toBe(new Set(fr.map(x => x.team)).size);
      const opts = await page.$$eval('#player option', os => os.map(o => [o.value, o.dataset.c]));
      expect(opts.map(([pid]) => pid).sort()).toEqual(fr.map(x => x.pid).sort());
      await page.screenshot({path: info.outputPath(`player-from-${name}-${lang}.png`), fullPage: false});
      await noSidewaysScroll(page, 'Player page with a country picked');

      // the arrows step through the country's players, across clubs
      const i = opts.findIndex(([pid]) => pid === p.pid), [npid, nclub] = opts[(i + 1) % opts.length];
      await expect(page.locator('#next')).toHaveAttribute('href', `#${nclub}/${npid}`);
      await page.click('#next');
      await page.waitForFunction(([pid, c]) => document.querySelector('#player').value === pid && document.querySelector('#team').value === c && document.querySelector('#from').value === 'France', [npid, nclub]);
      await page.reload();   // the pick is kept on this device
      await settled(page);
      await page.waitForFunction(() => document.querySelector('#from').value === 'France');

      // picking a club lets go of the country
      const other = await page.evaluate(c => IDX.teams.find(x => x.code !== c).code, nclub);
      await page.locator('#team + .sel').click();
      await page.locator(`#menu li[data-v="${other}"]`).click();
      await page.waitForFunction(c => document.querySelector('#team').value === c && document.querySelector('#from').value === '' && !document.querySelector('#player optgroup'), other);
      expect(await page.evaluate(() => localStorage.getItem('pl-from'))).toBeNull();
      expect(problems, 'the page reported errors').toEqual([]);
    });
  });
}
