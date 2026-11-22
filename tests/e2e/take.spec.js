// Take the table: the button on Leaders and Standings copies the tables in view, downloads them as CSV, or shares them
// as a picture. Every value it hands over is the string the table shows; a rank under a value gets its own column.
// The pictures land in the run's artifacts.
import {test, expect} from '@playwright/test';
import {readFileSync, writeFileSync} from 'node:fs';
import {DESKTOP, PHONE, prepare, settled, go} from './site.js';

// what a table shows, row by row, the way a reader sees it (logos, faces, dots and the small ranks left out)
const shown = (page, sel) => page.evaluate(s => [...document.querySelectorAll(`${s} tbody tr`)].filter(r => !r.querySelector('td.empty')).map(r => [...r.cells].map(td => {
  const k = document.createElement('template');
  k.innerHTML = td.innerHTML;
  k.content.querySelectorAll('.chip,.mark,.face,.form,.rk,.abbr,[aria-hidden="true"],img').forEach(e => e.remove());
  return k.content.textContent.replace(/\s+/g, ' ').trim().replace(/\u2212/g, '-');
})), sel);
const csv = text => text.replace(/^\ufeff/, '').trimEnd().split('\n\n').map(block => block.split('\n').map(line => {
  const out = []; let cur = '', q = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (q) { if (ch === '"' && line[i + 1] === '"') { cur += '"'; i++; } else if (ch === '"') q = false; else cur += ch; }
    else if (ch === '"') q = true; else if (ch === ',') { out.push(cur); cur = ''; } else cur += ch;
  }
  out.push(cur);
  return out;
}));
const pick = async (page, btn, item) => {
  await page.click(btn);
  await expect(page.locator('#tk-menu')).toBeVisible();
  await page.click(`#tk-menu [data-tk="${item}"]`);
};

test.describe('take the table, desktop', () => {
  test.use(DESKTOP);
  test('Standings downloads as CSV, both conferences, and ranks get their own column', async ({page}) => {
    const problems = await prepare(page);
    await page.goto('./?l#standings');
    await settled(page);
    const [dl] = await Promise.all([page.waitForEvent('download'), pick(page, '#st-take', 'csv')]);
    expect(dl.suggestedFilename()).toMatch(/^standings-conferences-\d{4}-\d\d-\d\d\.csv$/);
    const blocks = csv(readFileSync(await dl.path(), 'utf8'));
    expect(blocks.map(b => b[0][0])).toEqual(['Eastern Conference', 'Western Conference']);
    expect(blocks[0][1].slice(0, 3)).toEqual(['#', 'Team', 'W']);
    const tables = page.locator('#st-body table');
    for (const i of [0, 1]) {
      const id = `st-t${i}`;
      await tables.nth(i).evaluate((el, x) => { el.id = x; }, id);
      expect(blocks[i].slice(2), `conference ${i} vs the page`).toEqual(await shown(page, `#${id}`));
    }
    await expect(page.locator('#tk-menu')).toBeHidden();
    await page.click('#st-take');
    await page.waitForTimeout(400);
    await page.screenshot({path: test.info().outputPath('standings-menu-en.png')});
    await page.keyboard.press('Escape');
    await expect(page.locator('#tk-menu')).toBeHidden();
    await go(page, '#standings/ratings');
    const [dl2] = await Promise.all([page.waitForEvent('download'), pick(page, '#st-take', 'csv')]);
    const [rt] = csv(readFileSync(await dl2.path(), 'utf8'));
    expect(rt[0]).toEqual(['Team', 'ORtg', '#', 'DRtg', '#', 'Net', '#', 'Pace', '#']);
    const want = await page.evaluate(() => [...document.querySelectorAll('#st-ratings tbody tr')].map(r => [r.querySelector('.full').textContent.trim(), ...[...r.querySelectorAll('td[data-k]')].flatMap(td => [td.querySelector('.v').textContent.replace(/\u2212/g, '-'), td.querySelector('.rk').textContent])]));
    expect(rt.slice(1)).toEqual(want);
    expect(problems, 'the page reported errors').toEqual([]);
  });

  test('Leaders copies the board as tab-separated text; boards without a table hide the button', async ({page}) => {
    const problems = await prepare(page);
    await page.addInitScript(() => { navigator.clipboard.writeText = async s => { window.copied = s; }; });
    await page.goto('./?l#leaders/pts');
    await settled(page);
    await pick(page, '#ld-take', 'copy');
    await page.waitForFunction(() => window.copied);
    const rows = (await page.evaluate(() => window.copied)).trimEnd().split('\n').map(l => l.split('\t'));
    expect(rows[0]).toEqual(['#', 'Player', 'Team', 'GP', 'Points']);
    expect(rows.slice(1)).toEqual(await shown(page, '#ld'));
    await expect(page.locator('#tk-menu [data-tk="copy"]')).toHaveText('Copied');
    await go(page, '#leaders/map');
    await expect(page.locator('#ld-take')).toBeHidden();
    await go(page, '#leaders/reb');
    await expect(page.locator('#ld-take')).toBeVisible();
    // every board and table hands over rows as wide as its header
    for (const h of await page.evaluate(() => [...document.querySelectorAll('#ld-tabs a, #st-tabs a')].map(a => a.getAttribute('href')))) {
      await go(page, h.startsWith('#leaders') ? '#leaders/pts' : '#standings');   // the tab rails differ by page
      await go(page, h);
      const T = await page.evaluate(p => tkTake(p), h.startsWith('#leaders') ? 'leaders' : 'standings');
      for (const tb of T.tables) expect(new Set(tb.rows.map(r => r.length)).size, `${h} ${tb.head}`).toBe(1);
    }
    expect(problems, 'the page reported errors').toEqual([]);
  });
});

test.describe('take the table, phone', () => {
  test.use(PHONE);
  for (const lang of ['en', 'tr']) {
    test(`the picture goes to the share sheet (${lang})`, async ({page}, info) => {
      const problems = await prepare(page, {lang, theme: 'dark'});
      await page.addInitScript(() => {
        navigator.canShare = d => !!(d.files && d.files.length);
        navigator.share = async d => {
          const f = d.files[0], bmp = await createImageBitmap(f);
          window.shared = {name: f.name, type: f.type, title: d.title, w: bmp.width, h: bmp.height, png: Array.from(new Uint8Array(await f.arrayBuffer()))};
        };
      });
      for (const [hash, btn, name] of [['#leaders/pts', '#ld-take', 'leaders'], ['#standings/factors', '#st-take', 'factors']]) {
        await page.goto(`./?l${hash}`);
        await settled(page);
        await page.click(btn);
        await expect(page.locator('#tk-menu')).toBeVisible();
        await page.waitForTimeout(400);   // the menu's rise
        await page.screenshot({path: info.outputPath(`${name}-menu-${lang}.png`)});
        await page.click('#tk-menu [data-tk="png"]');
        await page.waitForFunction(() => window.shared);
        const got = await page.evaluate(() => window.shared);
        expect([got.w, got.type]).toEqual([1080, 'image/png']);
        expect(got.name).toMatch(/^[a-z0-9-]+-\d{4}-\d\d-\d\d\.png$/);
        writeFileSync(info.outputPath(`${name}-${lang}.png`), Buffer.from(got.png));
        await page.evaluate(() => { window.shared = null; });
      }
      if (lang === 'tr') expect(await page.evaluate(() => [...MISSING]), 'Turkish strings missing from lang/tr.json').toEqual([]);
      expect(problems, 'the page reported errors').toEqual([]);
    });
  }
});
