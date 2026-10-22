// The share button on the Player hero and the Game scoreboard: the picture it draws carries the page's own numbers, it is
// 1080 × 1350, it goes to the share sheet where the browser can share files, and it downloads where it can't.
// The pictures land in the run's artifacts.
import {test, expect} from '@playwright/test';
import {readFileSync, writeFileSync} from 'node:fs';
import {DESKTOP, PHONE, prepare, settled, go} from './site.js';

const PICK = (page, gid) => page.evaluate(g => { const s = document.querySelector('#sc-game'); s.value = g; s.dispatchEvent(new Event('change')); }, gid);
const size = path => { const b = readFileSync(path); return [b.readUInt32BE(16), b.readUInt32BE(20)]; };   // a PNG's IHDR

test.describe('share a player', () => {
  test.use(PHONE);
  for (const lang of ['en', 'tr']) {
    test(`the picture shows his log row or his season tiles, and goes to the share sheet (${lang})`, async ({page}, info) => {
      const problems = await prepare(page, {lang});
      await page.addInitScript(() => {
        navigator.canShare = d => !!(d.files && d.files.length);
        navigator.share = async d => {
          const f = d.files[0], bmp = await createImageBitmap(f), bytes = new Uint8Array(await f.arrayBuffer());
          window.shared = {name: f.name, type: f.type, title: d.title, w: bmp.width, h: bmp.height, png: Array.from(bytes)};
        };
      });
      await page.goto('./#BOS');
      await settled(page);
      await page.waitForFunction(() => document.querySelectorAll('#sc-game option').length > 1);
      const gid = await page.evaluate(() => document.querySelectorAll('#sc-game option')[1].value);
      await PICK(page, gid);
      const card = await page.evaluate(() => SHARE.player());
      const row = await page.evaluate(g => [...document.querySelector(`#log tr[data-gid="${g}"]`).cells].map(td => td.textContent), gid);
      const [, , , min, pts, reb, ast, stl, blk, tov, fg, fg3, ft, pm] = row;
      const v = Object.fromEntries(card.tiles.map(([k, x], i) => [i, x]));
      expect([v[0], v[1], v[2], v[3], v[4], v[5], v[6], v[7], v[8], v[9], v[11]], 'game tiles vs the log row').toEqual([pts, reb, ast, stl, blk, tov, min, fg, fg3, ft, pm]);
      expect(card.line).toContain(row[2].replace(/^\S+ /, ''));   // the score, as the log's result shows it
      expect(card.courts.length).toBe(1);
      const tag = await page.evaluate(() => document.querySelector('#hero .tag').textContent);
      expect(tag.toLocaleUpperCase('en-US')).toContain(card.tag);   // the hero's line, after the logo's code
      await page.click('#hero .share');
      await page.waitForFunction(() => window.shared);
      const got = await page.evaluate(() => window.shared);
      expect([got.w, got.h, got.type]).toEqual([1080, 1350, 'image/png']);
      expect(got.name).toMatch(/^[a-z0-9-]+-\d{4}-\d\d-\d\d\.png$/);
      expect(got.title).toBe(await page.title());
      writeFileSync(info.outputPath(`player-game-${lang}.png`), Buffer.from(got.png));
      await PICK(page, '');
      const season = await page.evaluate(() => SHARE.player().tiles.map(([, x]) => x));
      const tiles = await page.evaluate(() => [...document.querySelectorAll('#tiles .tile b')].map(b => b.textContent));
      expect(season, 'season tiles vs the page').toEqual(tiles);
      await page.evaluate(() => { window.shared = null; });
      await page.click('#hero .share');
      await page.waitForFunction(() => window.shared);
      writeFileSync(info.outputPath(`player-season-${lang}.png`), Buffer.from(await page.evaluate(() => window.shared.png)));
      if (lang === 'tr') expect(await page.evaluate(() => [...MISSING]), 'Turkish strings missing from lang/tr.json').toEqual([]);
      expect(problems, 'the page reported errors').toEqual([]);
    });
  }
});

test.describe('share a game', () => {
  test.use(DESKTOP);
  test('without file sharing the picture downloads, with each club\'s top scorers as the box score has them', async ({page}, info) => {
    const problems = await prepare(page);
    await page.addInitScript(() => { delete Navigator.prototype.canShare; delete Navigator.prototype.share; });
    await page.goto('./');
    await settled(page);
    await go(page, '#game/0022600001', () => document.querySelectorAll('#gm-shots svg').length === 2);
    const card = await page.evaluate(() => SHARE.game());
    const box = await page.evaluate(() => [...document.querySelectorAll('#gm-box table')].map(tb => [...tb.querySelectorAll('tbody tr[data-pid]')]
      .map(tr => [tr.cells[0].querySelector('a').lastChild.textContent, ...[...tr.cells].slice(1).map(td => td.textContent)]).filter(c => c.length > 2)));
    box.forEach((rows, i) => {
      const best = [...rows].sort((a, b) => (+b[2] - +a[2]) || (+b[3] - +a[3]))[0];
      expect(card.tops[i][0], 'top scorer vs the box score').toEqual([best[0], `${best[2]} PTS · ${best[3]} REB · ${best[6]} AST`]);
    });
    const score = await page.evaluate(() => [...document.querySelectorAll('#gm-board .score span')].map(s => +s.textContent));
    expect([card.as, card.hs]).toEqual(score);
    expect(card.courts.length).toBe(2);
    const [download] = await Promise.all([page.waitForEvent('download'), page.click('#gm-board .share')]);
    expect(download.suggestedFilename()).toBe(card.file);
    const path = info.outputPath(card.file);
    await download.saveAs(path);
    expect(size(path)).toEqual([1080, 1350]);
    expect(problems, 'the page reported errors').toEqual([]);
  });
});
