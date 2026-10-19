# NBA Player Lab

Player, team and lineup analytics for the 2026-27 NBA season, rebuilt from the official game feeds after every final.
A port of [Euroleague Player Lab](https://github.com/baranerdogan11/Euroleague-Player-Lab) with the same stack: Python
3.11, DuckDB and Parquet for the data, one HTML page generated from `template.html`, GitHub Actions and GitHub Pages.

## Layout

- `config.json`: the season every script works on (`2026-27`); any script also takes the season as its first argument
- `build.py`: renders `index.html` from `template.html` with the build's metadata and the Turkish strings in `lang/tr.json`
- `tests/`: Python self-tests (`tests/run_all.py` runs every `tests/test_*.py`), the Playwright browser tests
  (`tests/e2e/`) and the lint and type-check setup for the page's script (`tests/lint/`)

## Checks

`.github/workflows/test.yml` runs on every pull request and every push to main:

- Python: Ruff (`ruff check .`, rules in `ruff.toml`) and the self-tests (`python tests/run_all.py`)
- Node (tooling only, the site and the pipeline do not need it): ESLint and TypeScript's checker over the page's script,
  copied out of `template.html` with the same line numbers, then Playwright: every page at 390 and 1280 px, in English
  and Turkish, light and dark, must draw without an error or a sideways scroll, and the five phone tabs must fit

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
  last build (`due.py`, reading the NBA CDN schedule), and runs once a night after 10:00 UTC for late corrections.
  cdn.nba.com refuses GitHub's runners, so the check and the fetch run on a self-hosted runner (Settings, Actions,
  Runners); while it is offline those jobs wait and the site keeps its last good build. A run fetches, passes every gate (self-tests, the warehouse gates including play-by-play against the box score, the Playwright smoke test on the built
  site), commits and deploys. A failed gate stops the run before anything is committed, so the last good build stays
  live, and GitHub emails the failure.
- `.github/workflows/pages.yml` deploys one tested commit to GitHub Pages (Settings, Pages, Source: GitHub Actions) and
  then checks the public site serves it (`live.py`). Code changes deploy through `test.yml` after their checks pass.
