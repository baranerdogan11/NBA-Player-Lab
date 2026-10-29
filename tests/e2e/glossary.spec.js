// Stat definitions: the glossary page (#glossary, linked from the foot of every page) lists every entry of GLOSS, in
// English and Turkish; #glossary/<id> opens at one. A stat's label (a tile, a heading, the Leaders tab in use) opens its
// entry in a card above it, which a tap elsewhere, a scroll or Escape closes. Headings that sort keep sorting.
import {test, expect} from '@playwright/test';
import {DESKTOP, PHONE, prepare, settled, go} from './site.js';

const card = page => page.evaluate(() => { const d = document.querySelector('#def'); return d.hidden ? null : {text: d.textContent, def: DEF_AT && DEF_AT.dataset.def}; });

for (const [name, use, lang] of [['desktop', DESKTOP, 'en'], ['phone', PHONE, 'tr']]) {
  test.describe(`glossary (${name}, ${lang})`, () => {
    test.use(use);
    test('the foot opens the glossary with every entry, and an entry opens on its own address', async ({page}, info) => {
      const problems = await prepare(page, {lang});
      await page.goto('./?l#home');
      await settled(page);
      await page.click('.foot a[href="#glossary"]');
      await page.waitForFunction(() => document.body.dataset.page === 'glossary');
      const shown = await page.evaluate(() => [...document.querySelectorAll('#gl [data-id]')].map(x => x.dataset.id));
      expect(shown).toEqual(await page.evaluate(() => GLOSS.flatMap(([, rows]) => rows.map(r => r[0]))));
      expect(await page.locator('#gl .panel').count()).toBe(await page.evaluate(() => GLOSS.length));
      expect(await page.textContent('#gl-ts code')).toBe(lang === 'tr' ? 'Sayı ÷ (2 × (denenen FG + 0,44 × denenen SA))' : 'PTS ÷ (2 × (FGA + 0.44 × FTA))');
      await page.screenshot({path: info.outputPath(`glossary-${name}-${lang}.png`), fullPage: true});
      await go(page, '#glossary/poss', () => document.querySelector('#gl-poss.hit'));
      const top = await page.evaluate(() => document.querySelector('#gl-poss').getBoundingClientRect().top);
      expect(top).toBeGreaterThanOrEqual(0);
      expect(top).toBeLessThan(200);
      if (lang === 'tr') expect(await page.evaluate(() => [...MISSING]), 'Turkish strings missing from lang/tr.json').toEqual([]);
      expect(problems, 'the page reported errors').toEqual([]);
    });

    test('a stat label opens its definition; a tap elsewhere, a scroll and Escape close it', async ({page}, info) => {
      const problems = await prepare(page, {lang});
      const tap = sel => use === PHONE ? page.tap(sel) : page.click(sel);
      await page.goto('./?l#BOS');
      await settled(page);
      await page.waitForFunction(() => !!document.querySelector('#tiles .tile'));
      expect(await card(page)).toBeNull();
      await tap('#tiles .tile[data-k="TS%"]');
      let c = await card(page);
      expect(c.def).toBe('ts');
      expect(c.text).toContain(lang === 'tr' ? 'Gerçek şut yüzdesi' : 'True shooting percentage');
      expect(c.text).toContain(lang === 'tr' ? '0,44' : '0.44');
      const [box, tile] = await page.evaluate(() => [document.querySelector('#def').getBoundingClientRect(), document.querySelector('#tiles .tile[data-k="TS%"]').getBoundingClientRect()].map(r => ({top: r.top, bottom: r.bottom, left: r.left, right: r.right})));
      expect(box.bottom <= tile.top || box.top >= tile.bottom, 'the card sits above or below the tile, not over it').toBe(true);
      expect(box.left).toBeGreaterThanOrEqual(0);
      expect(box.right).toBeLessThanOrEqual(use.viewport.width);
      await page.screenshot({path: info.outputPath(`def-${name}-${lang}.png`)});
      await tap('#hero h1');
      expect(await card(page)).toBeNull();
      // the same label again closes it; a scroll closes it
      await tap('#tiles .tile[data-k="PTS"]');
      expect((await card(page)).def).toBe('pts');
      await tap('#tiles .tile[data-k="PTS"]');
      expect(await card(page)).toBeNull();
      await tap('#tiles .tile[data-k="PTS"]');
      await page.mouse.wheel(0, 300);
      await page.waitForFunction(() => document.querySelector('#def').hidden);
      // the card's link opens the glossary at the entry
      await page.evaluate(() => scrollTo(0, 0));
      await tap('#tiles .tile[data-k="+/-"]');
      await tap('#def a');
      await page.waitForFunction(() => document.body.dataset.page === 'glossary' && !!document.querySelector('#gl-pm.hit'));
      expect(await card(page)).toBeNull();
      // Standings headings define themselves; the ratings headings keep sorting
      await go(page, '#standings', () => document.querySelectorAll('#st-body tbody tr').length === 30);
      await tap('#st-body th[data-def="gb"]');
      expect((await card(page)).text).toContain(lang === 'tr' ? 'lider' : 'leader');
      await page.keyboard.press('Escape');
      expect(await card(page)).toBeNull();
      await go(page, '#standings/ratings', () => document.querySelectorAll('#st-ratings tbody tr').length === 30);
      await tap('#st-ratings th[data-sort="drtg"] .sort');
      expect(await page.getAttribute('#st-ratings th[data-sort="drtg"]', 'aria-sort')).toBe('ascending');
      expect(await card(page)).toBeNull();
      // a box-score heading sorts and opens nothing
      await go(page, '#game/0022600001', () => document.querySelectorAll('#gm-box table').length === 2);
      await tap('#gm-box th[data-sort="PTS"] .sort');
      expect(await page.locator('#gm-box th[aria-sort]').count()).toBe(1);
      expect(await card(page)).toBeNull();
      // Leaders: another tab opens its board; the tab in use opens its definition with the board's floor
      await go(page, '#leaders', () => document.querySelectorAll('#ld tbody tr').length > 0);
      await tap('#ld-tabs a[href="#leaders/fg"]');
      await page.waitForFunction(() => location.hash === '#leaders/fg' && document.querySelector('#ld-tabs a[aria-current="true"]')?.getAttribute('href') === '#leaders/fg');
      await settled(page);
      expect(await card(page)).toBeNull();
      await tap('#ld-tabs a[aria-current="true"]');
      c = await card(page);
      expect(c.def).toBe('fgp floor-pg floor-fg');
      expect(c.text).toContain('300');
      expect(await page.evaluate(() => location.hash)).toBe('#leaders/fg');
      expect(problems, 'the page reported errors').toEqual([]);
    });
  });
}

test.describe('definitions by keyboard', () => {
  test.use(DESKTOP);
  test('a label takes focus, Enter opens its card and Escape closes it and gives focus back', async ({page}) => {
    const problems = await prepare(page);
    await page.goto('./?l#team/BOS');
    await settled(page);
    await page.waitForFunction(() => document.querySelectorAll('#tm-ff td[data-k]').length === 8);
    await page.focus('#tm-rt th[data-def^="pace"]');
    await page.keyboard.press('Enter');
    expect((await card(page)).text).toContain('48');
    await page.keyboard.press('Escape');
    expect(await card(page)).toBeNull();
    expect(await page.evaluate(() => document.activeElement.dataset.def)).toBe('pace poss');
    expect(problems, 'the page reported errors').toEqual([]);
  });
});
