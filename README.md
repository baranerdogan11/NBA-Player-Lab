# NBA Player Lab

Player, team and lineup analytics for the 2026-27 NBA season, rebuilt from the official game feeds after every final.
A port of [Euroleague Player Lab](https://github.com/baranerdogan11/Euroleague-Player-Lab) with the same stack: Python
3.11, DuckDB and Parquet for the data, one HTML page generated from `template.html`, GitHub Actions and GitHub Pages.

## Layout

- `config.json`: the season every script works on (`2026-27`); any script also takes the season as its first argument
- `build.py`: renders `index.html` from `template.html` with the build's metadata and the Turkish strings in `lang/tr.json`
- `template.html`: the whole site, one page in the hardwood look (a maple court floor under frosted rounded panels, the
  player's hero painted in the club's colours with court lines, a centre-court scoreboard, club-colour table headers;
  the dark theme dims the arena lights). Five pages, on the header rail and on the phone's bottom bar: Player
  (`#BOS/<pid>`), Compare (`#compare/<a>/<b>`), Standings (`#standings`), Games (`#games/<date>`, a final at `#game/<gid>`)
  and Leaders (`#leaders/<stat>`). Turkish strings are in `lang/tr.json`; club logos from NBA's CDN by `teams.json`'s team id (its two colours show when a logo is
  missing). Player pictures are NBA's headshots
  (`cdn.nba.com/headshots/...<person id>.png`), loaded by the reader's browser over the player's initials, which stay when
  there is no picture
- My league (`#league`): a Yahoo fantasy league's own room, kept off the public pages. Its invite link
  (`#league/<id>/<key>`) unlocks it on the reader's device; the page decrypts `fantasy/<id>.enc` (AES-256-GCM, the league
  id as additional data) and shows This week (the 9-category matchup and the last game night) and Roster. The league file
  says only who sat in which slot on which day; every number is summed from the same box-score lines as the rest of the
  site. `tests/fixtures/league_fixture.mjs` writes a made-up, encrypted twelve-team league for the browser tests
- `site_data.py`: writes the JSON the page reads under `teams/<season>/`: `index.json` (clubs), `games.json` (schedule
  and finals), `<CODE>.json` (each player's log of box-score lines), `games/<gid>.json` (both box scores) and
  `leaders.json` (season totals), all from the same box-score lines. The page turns integer totals into averages and
  percentages through one rule, `rdiv` (half away from zero, exact integer arithmetic), with the same formula in Python
- `shots.py`: writes `teams/<season>/shots/<CODE>.json`, every field-goal attempt of the club's finals by shooter, for
  the shot charts on the Player and Game pages (a half court in the club's two colours, drawn as SVG by the page); it
  stops if a player's shots in a game differ from his box-score FGM-FGA
- `tests/fixtures/site_fixture.py`: a made-up, self-consistent league the browser tests run against
- `tests/`: Python self-tests (`tests/run_all.py` runs every `tests/test_*.py`), the Playwright browser tests
  (`tests/e2e/`) and the lint and type-check setup for the page's script (`tests/lint/`)

## Checks

`.github/workflows/test.yml` runs on every pull request and every push to main:

- Python: Ruff (`ruff check .`, rules in `ruff.toml`) and the self-tests (`python tests/run_all.py`)
- Node (tooling only, the site and the pipeline do not need it): ESLint and TypeScript's checker over the page's script,
  copied out of `template.html` with the same line numbers, then Playwright: every page at 390 and 1280 px, in English
  and Turkish, light and dark, must draw without an error or a sideways scroll, the five phone tabs must fit, and every
  player's line on a game page must match his game log, his season row, Compare and Leaders

```bash
pip install -r requirements.txt -r requirements-dev.txt
ruff check . && python tests/run_all.py
npm ci
npm run lint && npm run typecheck
CHROME=/path/to/chrome npm run test:e2e   # or: npx playwright install chromium
```

## Publishing

Nothing needs a human on game nights:

- `.github/workflows/update.yml` checks every 5 minutes from 17:00 to 09:59 UTC whether a game has gone final since the
  last build (`due.py`, reading the NBA schedule from the S3 origin behind cdn.nba.com, which refuses scripted
  clients), and runs once a night after 10:00 UTC for late corrections. A run fetches, passes every gate (self-tests, the warehouse gates including play-by-play against the box score, the Playwright smoke test on the built
  site), commits and deploys. A failed gate stops the run before anything is committed, so the last good build stays
  live, and GitHub emails the failure.
- `.github/workflows/pages.yml` deploys one tested commit to GitHub Pages (Settings, Pages, Source: GitHub Actions) and
  then checks the public site serves it (`live.py`). Code changes deploy through `test.yml` after their checks pass.
