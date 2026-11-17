// League-wide search: the header's magnifier finds any player who has played by name, whatever the accents or the page's
// language (the feed spells Şengün "Sengun"; a Turkish lower case would turn JOKIC into jokıc), and opens his page.
import {test, expect} from '@playwright/test';
import {DESKTOP, PHONE, prepare, settled, noSidewaysScroll} from './site.js';

const rows = page => page.locator('#menu [role="option"]');
const names = page => page.$$eval('#menu [role="option"] > span:last-of-type', xs => xs.map(x => x.textContent));

for (const [name, use, lang] of [['desktop', DESKTOP, 'en'], ['phone', PHONE, 'tr']]) {
  test.describe(`player search (${name})`, () => {
    test.use(use);
    test(`folds accents and Turkish letters and opens the player's page (${lang})`, async ({page}, info) => {
      const problems = await prepare(page, {lang});
      await page.goto('./?l#standings');
      await settled(page);
      await page.click('#find-btn');
      await expect(page.locator('#menu')).toBeVisible();
      await expect(page.locator('#menu input')).toBeFocused();   // a phone gets its keyboard straight away
      const all = await page.evaluate(() => fetch(`${META.base}leaders.json`).then(r => r.json()).then(d => d.players.length));
      await expect(rows(page)).toHaveCount(all);

      for (const q of ['Şengün', 'ŞENGÜN', 'sengun', 'alperen seng']) {
        await page.fill('#menu input', q);
        expect(await names(page), q).toEqual(['Alperen Sengun']);
      }
      for (const q of ['JOKIC', 'jokić', 'Nİkola']) {
        await page.fill('#menu input', q);
        expect(await names(page), q).toContain('Nikola Jokić');
      }
      await page.fill('#menu input', 'Nikola');
      expect((await names(page))[0], 'names that start with the query come first').toBe('Nikola Jokić');
      await page.fill('#menu input', 'zzz');
      await expect(page.locator('#menu .empty')).toBeVisible();

      await page.fill('#menu input', 'sengun');
      await expect(rows(page).first().locator('.chip')).toHaveCount(1);   // his club beside him
      await noSidewaysScroll(page, `search ${name}`);
      await page.screenshot({path: info.outputPath(`search-${name}-${lang}.png`)});
      const pid = await rows(page).first().getAttribute('data-v');
      await page.keyboard.press('Enter');
      await page.waitForFunction(p => location.hash === `#HOU/${p}` && document.body.dataset.page === 'player' && document.querySelector('#player').value === p, pid);
      await expect(page.locator('#menu')).toBeHidden();
      await settled(page);
      expect(problems).toEqual([]);
      expect(await page.evaluate(() => [...MISSING])).toEqual([]);
    });
  });
}

test.describe('player search keys', () => {
  test.use(DESKTOP);
  test('slash opens the search, Escape closes it, a club name lists its players', async ({page}) => {
    await prepare(page);
    await page.goto('./?l#games');
    await settled(page);
    await page.keyboard.press('/');
    await expect(page.locator('#menu input')).toBeFocused();
    await page.fill('#menu input', 'rockets');
    const n = await page.evaluate(() => fetch(`${META.base}leaders.json`).then(r => r.json()).then(d => d.players.filter(p => p.team === 'HOU').length));
    await expect(rows(page)).toHaveCount(n);
    await page.keyboard.press('Escape');
    await expect(page.locator('#menu')).toBeHidden();
    await expect(page.locator('#find-btn')).toBeFocused();
  });
});

// A picker long enough to have a search box (Compare's player pickers, the team picker) must survive the phone's keyboard:
// tapping the box pops the keyboard up, which resizes or scrolls the window, and the menu used to close right then.
test.describe('picker search on a phone', () => {
  test.use(PHONE);
  test('tapping the search box and typing keeps the menu open and filters it', async ({page}) => {
    const problems = await prepare(page);
    await page.goto('./?l#compare');
    await settled(page);
    await page.locator('#cmp-a + .sel').tap();
    await expect(page.locator('#menu input')).toBeVisible();
    const box = await page.locator('#menu').boundingBox();
    expect(box && box.y, 'the sheet sits at the top, out of the keyboard\'s way').toBeLessThan(100);
    await page.locator('#menu input').tap();
    await page.setViewportSize({width: 390, height: 500});   // the keyboard comes up
    await page.evaluate(() => { scrollBy(0, 40); dispatchEvent(new Event('scroll')); });
    await expect(page.locator('#menu')).toBeVisible();
    await page.keyboard.type('seng');
    expect(await names(page)).toEqual(['Alperen Sengun']);
    const pid = await rows(page).first().getAttribute('data-v');
    await rows(page).first().tap();
    await expect(page.locator('#menu')).toBeHidden();
    await expect(page.locator('#cmp-a')).toHaveValue(/** @type {string} */ (pid));
    expect(problems).toEqual([]);
  });
});
