// My players: the star on the Player hero keeps the player on this device, Home lists every starred player with the last
// game he played, as his game log shows it, and the list goes away when the last star does.
import {test, expect} from '@playwright/test';
import {DESKTOP, PHONE, prepare, settled, go} from './site.js';

const PLAYER = () => document.body.dataset.page === 'player' && !!document.querySelector('#hero .star');
const HOME = () => document.body.dataset.page === 'home' && !!document.querySelector('#hm-leaders .panel');

for (const [name, use, lang] of [['desktop', DESKTOP, 'en'], ['phone', PHONE, 'tr']]) {
  test.describe(`my players (${name})`, () => {
    test.use(use);
    test(`a star puts the player on Home with his last game, and taking it off removes him (${lang})`, async ({page}, info) => {
      const problems = await prepare(page, {lang});
      await page.goto('./#BOS');
      await settled(page);
      await page.waitForFunction(PLAYER);
      const pid = await page.evaluate(() => document.querySelector('#player').value);
      const last = await page.evaluate(() => {   // the log runs newest first; the first row with minutes is his last game
        const tr = [...document.querySelectorAll('#log tbody tr[data-gid]')].find(r => r.cells.length > 4);
        return tr && {gid: tr.dataset.gid, pts: tr.cells[4].textContent, reb: tr.cells[5].textContent, ast: tr.cells[6].textContent, opp: tr.cells[1].textContent};
      });
      expect(last, 'the fixture player has played').toBeTruthy();
      await expect(page.locator('#hero .star')).toHaveAttribute('aria-pressed', 'false');
      await page.click('#hero .star');
      await expect(page.locator('#hero .star')).toHaveAttribute('aria-pressed', 'true');
      expect(await page.evaluate(() => JSON.parse(localStorage.getItem('pl-stars')))).toEqual([pid]);

      await go(page, '#home', HOME);
      await expect(page.locator('#hm-mine-sec')).toBeVisible();
      const row = page.locator(`#hm-mine a[data-pid="${pid}"]`);
      await expect(row).toHaveAttribute('href', `#BOS/${pid}/${last.gid}`);
      const small = await row.locator('small').textContent();
      for (const v of [last.opp, `${last.pts} `, `${last.reb} `, `${last.ast} `]) expect(small).toContain(v);
      await page.screenshot({path: info.outputPath(`home-${name}-${lang}.png`), fullPage: true});

      await page.reload();   // the star is still there on the next visit
      await settled(page);
      await page.waitForFunction(HOME);
      await expect(row).toBeVisible();
      await row.click();
      await page.waitForFunction(g => location.hash.endsWith(g) && !!document.querySelector('#hero .star'), last.gid);
      expect(await page.evaluate(() => document.querySelector('#sc-game').value)).toBe(last.gid);
      await page.click('#hero .star');
      await expect(page.locator('#hero .star')).toHaveAttribute('aria-pressed', 'false');
      expect(await page.evaluate(() => localStorage.getItem('pl-stars'))).toBeNull();
      await go(page, '#home', HOME);
      await expect(page.locator('#hm-mine-sec')).toBeHidden();
      expect(problems, 'the page reported errors').toEqual([]);
    });
  });
}
