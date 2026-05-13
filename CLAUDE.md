# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A personal +EV sports betting tool. It treats Pinnacle as the "sharp" (efficient) book and compares its no-vig implied probabilities against soft books (FanDuel, DraftKings) to surface positive expected value opportunities. All logic lives in `main.py`.

## Running the bot

```bash
python main.py                        # use cache if fresh (<10 min), else fetch
python main.py --refresh              # force a new API call
python main.py --sport americanfootball_nfl
python main.py --min-edge 5           # only show edges ≥5%
python main.py --validate             # side-by-side odds table for manual verification
python main.py --log-sheet            # append opportunities to Google Sheet
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

**EV calculation** — `no_vig_probs()` strips Pinnacle's vig by normalizing raw implied probabilities so they sum to 1. That gives the true probability of each outcome. EV is then `(true_prob × soft_book_decimal_odds) - 1`.

**Caching** — odds are cached to `odds_cache.json` for 10 minutes to conserve the API's 500 req/month limit. `--refresh` bypasses the cache. The cache file is gitignored.

**Google Sheets** — `--log-sheet` requires `gspread` + a service account JSON. On first run it creates the sheet and prints its URL. Deduplication is based on `(game, pick, book)` — the same opportunity won't be logged twice.

**Books** — `SHARP_BOOK` and `SOFT_BOOKS` at the top of `main.py` are the only place to add/change which books are tracked.

## Planned features (tracked as tasks)

- Kalshi API integration as a second odds source (their public REST API, matching events to Pinnacle lines by team/date is the fiddly part)
