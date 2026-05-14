# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A personal +EV sports betting tool. It treats Pinnacle as the "sharp" (efficient) book and compares its no-vig implied probabilities against soft books (FanDuel, DraftKings, BetMGM, BetRivers, Bovada, BetOnline, LowVig, MyBookie) to surface positive expected value opportunities. All logic lives in `main.py`.

## Running the bot

```bash
python main.py                        # use cache if fresh (<10 min), else fetch
python main.py --refresh              # force a new API call
python main.py --sport americanfootball_nfl
python main.py --min-edge 5           # only show edges ≥5%
python main.py --validate             # side-by-side odds table for manual verification
python main.py --log-sheet            # append opportunities to Google Sheet (with Kelly %)
python main.py --update-results       # fetch scores, fill in Result + P&L for pending bets
python main.py --list-books           # show all bookmakers available for a sport
```

## Environment variables (`.env`)

```
apiKey=                        # The Odds API key
GOOGLE_CREDENTIALS_PATH=       # Path to Google service account JSON (for --log-sheet)
SHEET_NAME=Sharp Bot Picks     # Google Sheet name (optional, this is the default)
```

## Dependencies

```bash
pip install -r requirements.txt
```

## Core logic

**Markets** — scans `h2h` (moneyline), `spreads`, and `totals` for every game. Controlled by the `MARKETS` constant at the top of `main.py`.

**EV calculation** — strips Pinnacle's vig by normalizing raw implied probabilities so they sum to 1. That gives the true probability of each outcome. EV is then `(true_prob × soft_book_decimal_odds) - 1`. Only the best-edge book per `(game, market, pick)` is shown.

**Caching** — odds are cached to `odds_cache.json` for 10 minutes to conserve the API's 500 req/month limit. `--refresh` bypasses the cache. The cache file is gitignored.

**Kelly sizing** — `kelly_fraction()` computes half-Kelly stake as a % of bankroll. Stored in the `Kelly %` sheet column when logging. Shown in terminal output too. Formula: `(p × decimal_odds − 1) / (decimal_odds − 1) × 0.5`.

**Google Sheets** — `--log-sheet` requires `gspread` + a service account JSON. The sheet must be created manually in Google Drive and shared with the service account email from your credentials JSON. Deduplication is based on `(game, market, pick)` — the same opportunity won't be logged twice. Running `--log-sheet` or `--update-results` on an existing sheet that lacks `Kelly %` will auto-insert the column.

**Result tracking** — `--update-results` fetches scores from ESPN's unofficial public API (no key, no quota: `site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard?dates=YYYYMMDD`). Groups pending bets by `(sport, date)` to minimise requests, matches completed games to pending bets by `away @ home` string, determines win/loss/push for h2h/spreads/totals, and writes `Result` + `Profit/Loss` (as % of bankroll using the stored Kelly %). Sport→ESPN path mapping is in `ESPN_SPORT_MAP`.

**Books** — `SHARP_BOOK` and `SOFT_BOOKS` at the top of `main.py` are the only place to add/change which books are tracked.

## Planned features (tracked as tasks)

- Kalshi API integration as a second odds source (their public REST API, matching events to Pinnacle lines by team/date is the fiddly part)
