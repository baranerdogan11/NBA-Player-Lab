// A made-up Yahoo fantasy league for the browser tests, drawn from the fixture league that site_fixture.py wrote: twelve
// teams of thirteen players picked in a snake draft, a 9-category head-to-head week, the slot each player sat in on each
// day (one bench swap mid-week, so a week's totals span two slot runs), and Yahoo's week totals as the pipeline would
// keep them for its gate (the box lines of players in active slots). The league is encrypted the way the pipeline
// publishes it: AES-256-GCM, the league id as additional data, iv and ciphertext (tag appended) in base64url. The key
// is a test key, committed on purpose; a real league's key never is.
// usage: node tests/fixtures/league_fixture.mjs OUT_DIR   (reads OUT_DIR/teams/<season>/, writes OUT_DIR/fantasy/<id>.enc)
import {readFileSync, writeFileSync, mkdirSync} from 'node:fs';
import {join} from 'node:path';
import {webcrypto as crypto} from 'node:crypto';

export const LEAGUE = '12345';
export const KEY = Buffer.from(Array.from({length: 32}, (_, i) => i)).toString('base64url');   // AAECAwQF…Hh8
const SEASON = '2026-27', BUILT = '2026-10-26T06:00:00Z', WEEK = ['2026-10-20', '2026-10-26'];
const NAMES = ['Bosphorus Bigs', 'Euro Steppers', 'Pick and Roll Call', 'Kadıköy Fast Break', 'Glass Cleaners', 'Corner Three Club',
  'Midrange Merchants', 'Hack-a-Friend', 'Two-Way Contracts', 'Tank Commanders', 'Bench Mob', 'Late Scratch'];
const MGRS = ['Baran', 'Deniz', 'Ece', 'Can', 'Selin', 'Mert', 'Ada', 'Emre', 'Zeynep', 'Kaan', 'İpek', 'Onur'];
const SLOTS = ['PG', 'SG', 'G', 'SF', 'PF', 'F', 'C', 'C', 'UTIL', 'UTIL', 'BN', 'BN', 'BN', 'IL'];
const ELIG = {G: ['PG', 'SG', 'G', 'UTIL'], F: ['SF', 'PF', 'F', 'UTIL'], C: ['C', 'UTIL'], 'G-F': ['SG', 'G', 'SF', 'F', 'UTIL'], 'F-C': ['PF', 'F', 'C', 'UTIL']};
const ACTIVE = s => s !== 'BN' && s !== 'IL';
const STATS = ['pts', 'reb', 'ast', 'stl', 'blk', 'tov', 'fgm', 'fga', 'fg3m', 'ftm', 'fta'];

export function league(dir) {
  const read = f => JSON.parse(readFileSync(join(dir, 'teams', SEASON, f), 'utf8'));
  const lead = read('leaders.json').players.filter(p => p.gp > 0).sort((a, b) => b.pts - a.pts || a.pid.localeCompare(b.pid));
  const logs = {};
  for (const T of read('index.json').teams) for (const p of read(`${T.code}.json`).players) logs[p.pid] = p.log;
  const picks = NAMES.map(() => []);
  lead.slice(0, 13 * NAMES.length).forEach((p, i) => { const r = Math.floor(i / NAMES.length), k = i % NAMES.length; picks[r % 2 ? NAMES.length - 1 - k : k].push(p); });
  const teams = picks.map((ps, i) => {
    // fill the starting slots in order with the first eligible player, the rest on the bench; team 2's last pick is out (IL)
    const open = [...SLOTS], roster = [];
    for (const p of ps) {
      const out = i === 1 && p === ps[ps.length - 1];
      const elig = ELIG[p.pos] || ['UTIL'];
      const fit = open.findIndex(s => ACTIVE(s) && elig.includes(s)), at = out ? open.indexOf('IL') : fit >= 0 ? fit : open.indexOf('BN');
      const slot = at >= 0 ? open.splice(at, 1)[0] : 'BN';   // more guards than guard slots: the extra one sits on the bench too
      roster.push([p.pid, slot, elig, out ? 'O' : i === 0 && roster.length === 4 ? 'GTD' : null]);
    }
    // the bench swap: the first bench player started in the second UTIL slot until Thursday, its owner the other way round
    const runs = roster.map(([pid, slot]) => [pid, slot, WEEK[0], WEEK[1]]);
    const util = runs.filter(r => r[1] === 'UTIL').pop(), bench = runs.find(r => r[1] === 'BN');
    if (util && bench) {
      runs.push([bench[0], 'UTIL', WEEK[0], '2026-10-22'], [util[0], 'BN', WEEK[0], '2026-10-22']);
      bench[2] = util[2] = '2026-10-23';
    }
    return {t: i + 1, name: NAMES[i], mgr: MGRS[i], w: 0, l: 0, tie: 0, rank: i + 1, roster, runs};
  });
  // Yahoo's week totals: every box line of a player on a day he sat in an active slot
  const yahoo = {1: {}};
  for (const T of teams) {
    const s = Object.fromEntries(STATS.map(k => [k, 0]));
    for (const [pid, slot, from, to] of T.runs) if (ACTIVE(slot)) for (const x of logs[pid] || []) if (x.sec > 0 && x.date >= from && x.date <= to) for (const k of STATS) s[k] += x[k];
    yahoo[1][T.t] = s;
  }
  return {
    league: {id: LEAGUE, name: 'Friends of the Lab', season: SEASON, built: BUILT, format: 'h2h-cats', week: 1,
      cats: ['fg%', 'ft%', 'fg3m', 'pts', 'reb', 'ast', 'stl', 'blk', 'tov'], slots: SLOTS, weeks: [WEEK, ['2026-10-27', '2026-11-02']]},
    teams, matchups: [0, 2, 4, 6, 8, 10].map(i => [1, i + 1, i + 2]), yahoo, moves: [],
  };
}

export async function encrypt(obj, id = LEAGUE, key = KEY) {
  const k = await crypto.subtle.importKey('raw', Buffer.from(key, 'base64url'), 'AES-GCM', false, ['encrypt']);
  const iv = new Uint8Array(12).fill(7);   // a fixed iv keeps the fixture file stable; the pipeline draws a fresh one every build
  const ct = await crypto.subtle.encrypt({name: 'AES-GCM', iv, additionalData: new TextEncoder().encode(id)}, k, new TextEncoder().encode(JSON.stringify(obj)));
  return {v: 1, alg: 'A256GCM', iv: Buffer.from(iv).toString('base64url'), ct: Buffer.from(ct).toString('base64url'), built: obj.league.built};
}

if (process.argv[1] && process.argv[1].endsWith('league_fixture.mjs')) {
  const dir = process.argv[2] || '_site';
  mkdirSync(join(dir, 'fantasy'), {recursive: true});
  writeFileSync(join(dir, 'fantasy', `${LEAGUE}.enc`), JSON.stringify(await encrypt(league(dir))));
  console.log(`fixture fantasy league written to ${join(dir, 'fantasy', `${LEAGUE}.enc`)}`);
}
