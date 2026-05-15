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
python main.py --kalshi               # scan Kalshi markets for arb + +EV opportunities
python main.py --kalshi --kalshi-debug  # show every matched game and EV breakdown
python main.py --list-books           # show all bookmakers available for a sport
```

## Environment variables (`.env`)

```
apiKey=                        # The Odds API key
GOOGLE_CREDENTIALS_PATH=       # Path to Google service account JSON (for --log-sheet)
SHEET_NAME=Sharp Bot Picks     # Google Sheet name (optional, this is the default)
KALSHI_KEY_ID=                 # Kalshi API key ID (for --kalshi)
KALSHI_PRIVATE_KEY_PATH=       # Path to Kalshi RSA private key .pem file (for --kalshi)
```

## Dependencies

```bash
pip install -r requirements.txt
```

## Core logic

**Markets** — scans `h2h` (moneyline), `spreads`, and `totals` for every game. Controlled by the `MARKETS` constant at the top of `main.py`.

**EV calculation** — strips Pinnacle's vig by normalizing raw implied probabilities so they sum to 1. That gives the true probability of each outcome. EV is then `(true_prob × soft_book_decimal_odds) - 1`. Only the best-edge book per `(game, market, pick)` is shown.

**Caching** — odds are cached to `odds_cache.json` for 10 minutes to conserve the API's 500 req/month limit. `--refresh` bypasses the cache. `--kalshi` uses a separate `kalshi_odds_cache.json` so the two flows don't overwrite each other. Both cache files are gitignored.

**Kelly sizing** — `kelly_fraction()` computes half-Kelly stake as a % of bankroll. Stored in the `Kelly %` sheet column when logging. Shown in terminal output too. Formula: `(p × decimal_odds − 1) / (decimal_odds − 1) × 0.5`.

**Google Sheets** — `--log-sheet` requires `gspread` + a service account JSON. The sheet must be created manually in Google Drive and shared with the service account email from your credentials JSON. Deduplication is based on `(game, market, pick)` — the same opportunity won't be logged twice. Running `--log-sheet` or `--update-results` on an existing sheet that lacks `Kelly %` will auto-insert the column.

**Result tracking** — `--update-results` fetches scores from ESPN's unofficial public API (no key, no quota: `site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard?dates=YYYYMMDD`). Groups pending bets by `(sport, date)` to minimise requests, matches completed games to pending bets by `away @ home` string, determines win/loss/push for h2h/spreads/totals, and writes `Result` + `Profit/Loss` (as % of bankroll using the stored Kelly %). Sport→ESPN path mapping is in `ESPN_SPORT_MAP`.

**Books** — `SHARP_BOOK` and `SOFT_BOOKS` at the top of `main.py` are the only place to add/change which books are tracked.

**Kalshi** — `--kalshi` automatically fetches odds for all Kalshi-covered sports (no `--sport` flag needed) and queries Kalshi by `series_ticker` for each league:

| Series | Sport | Notes |
|---|---|---|
| KXNBAGAME | basketball_nba | 2-outcome |
| KXMLBGAME | baseball_mlb | 2-outcome |
| KXNHLGAME | icehockey_nhl | 2-outcome |
| KXNFLGAME | americanfootball_nfl | 2-outcome |
| KXEPLGAME | soccer_epl | 3-outcome (draws) |
| KXUCLGAME | soccer_uefa_champs_league | 3-outcome (draws) |
| KXBUNDESLIGAGAME | soccer_germany_bundesliga | 3-outcome (draws) |
| KXLIGUE1GAME | soccer_france_ligue_one | 3-outcome (draws) |

Team names are decoded from the ticker suffix (e.g. `KXNBAGAME-26MAY15DETCLE-DET` → Detroit Pistons) using `KALSHI_GAME_SERIES`. Prices come from `yes_ask_dollars` (0.0–1.0 = implied prob). Outputs: (1) arb opportunities and (2) +EV vs Pinnacle true probability.

**Arb logic:** For 2-outcome sports: Kalshi YES one team + sportsbook on the other — if total < 100%, locked profit. For soccer (3-outcome): checks three combinations — Kalshi YES [home] + best SB draw + best SB away, Kalshi YES [away] + best SB draw + best SB home, Kalshi YES Draw + best SB home + best SB away. SB legs pick the best available odds across all 8 soft books independently.

Auth uses RSA-PSS signing via `KALSHI_KEY_ID` + `KALSHI_PRIVATE_KEY_PATH`. Use `--kalshi-debug` to see every matched game and its EV breakdown.
