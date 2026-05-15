import os
import re
import json
import base64
import time
import argparse
import requests
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
    from cryptography.hazmat.primitives.asymmetric.padding import PSS, MGF1
    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False

EASTERN = ZoneInfo('America/New_York')

try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False

CACHE_FILE = 'odds_cache.json'
KALSHI_CACHE_FILE = 'kalshi_odds_cache.json'
CACHE_TTL_MINUTES = 10
SHARP_BOOK = 'pinnacle'
SOFT_BOOKS = ['fanduel', 'draftkings', 'betmgm', 'betrivers', 'bovada', 'betonlineag', 'lowvig', 'mybookieag']
DEFAULT_MIN_EDGE = 0.03
MARKETS = ['h2h', 'spreads', 'totals']

KALSHI_API_URL = 'https://external-api.kalshi.com/trade-api/v2'

KALSHI_GAME_SERIES = {
    'KXNBAGAME': {
        'sport': 'basketball_nba',
        'teams': {
            'ATL': 'Atlanta Hawks', 'BOS': 'Boston Celtics', 'BKN': 'Brooklyn Nets',
            'CHA': 'Charlotte Hornets', 'CHI': 'Chicago Bulls', 'CLE': 'Cleveland Cavaliers',
            'DAL': 'Dallas Mavericks', 'DEN': 'Denver Nuggets', 'DET': 'Detroit Pistons',
            'GSW': 'Golden State Warriors', 'HOU': 'Houston Rockets', 'IND': 'Indiana Pacers',
            'LAC': 'LA Clippers', 'LAL': 'Los Angeles Lakers', 'MEM': 'Memphis Grizzlies',
            'MIA': 'Miami Heat', 'MIL': 'Milwaukee Bucks', 'MIN': 'Minnesota Timberwolves',
            'NOP': 'New Orleans Pelicans', 'NYK': 'New York Knicks', 'OKC': 'Oklahoma City Thunder',
            'ORL': 'Orlando Magic', 'PHI': 'Philadelphia 76ers', 'PHX': 'Phoenix Suns',
            'POR': 'Portland Trail Blazers', 'SAC': 'Sacramento Kings', 'SAS': 'San Antonio Spurs',
            'TOR': 'Toronto Raptors', 'UTA': 'Utah Jazz', 'WAS': 'Washington Wizards',
        },
    },
    'KXMLBGAME': {
        'sport': 'baseball_mlb',
        'teams': {
            'ARI': 'Arizona Diamondbacks', 'ATL': 'Atlanta Braves', 'BAL': 'Baltimore Orioles',
            'BOS': 'Boston Red Sox', 'CHC': 'Chicago Cubs', 'CWS': 'Chicago White Sox',
            'CIN': 'Cincinnati Reds', 'CLE': 'Cleveland Guardians', 'COL': 'Colorado Rockies',
            'DET': 'Detroit Tigers', 'HOU': 'Houston Astros', 'KC': 'Kansas City Royals',
            'LAA': 'Los Angeles Angels', 'LAD': 'Los Angeles Dodgers', 'MIA': 'Miami Marlins',
            'MIL': 'Milwaukee Brewers', 'MIN': 'Minnesota Twins', 'NYM': 'New York Mets',
            'NYY': 'New York Yankees', 'OAK': 'Oakland Athletics', 'PHI': 'Philadelphia Phillies',
            'PIT': 'Pittsburgh Pirates', 'SDP': 'San Diego Padres', 'SFG': 'San Francisco Giants',
            'SEA': 'Seattle Mariners', 'STL': 'St. Louis Cardinals', 'TBR': 'Tampa Bay Rays',
            'TEX': 'Texas Rangers', 'TOR': 'Toronto Blue Jays', 'WSN': 'Washington Nationals',
        },
    },
    'KXNHLGAME': {
        'sport': 'icehockey_nhl',
        'teams': {
            'ANA': 'Anaheim Ducks', 'BOS': 'Boston Bruins', 'BUF': 'Buffalo Sabres',
            'CGY': 'Calgary Flames', 'CAR': 'Carolina Hurricanes', 'CHI': 'Chicago Blackhawks',
            'COL': 'Colorado Avalanche', 'CBJ': 'Columbus Blue Jackets', 'DAL': 'Dallas Stars',
            'DET': 'Detroit Red Wings', 'EDM': 'Edmonton Oilers', 'FLA': 'Florida Panthers',
            'LAK': 'Los Angeles Kings', 'MIN': 'Minnesota Wild', 'MTL': 'Montreal Canadiens',
            'NSH': 'Nashville Predators', 'NJD': 'New Jersey Devils', 'NYI': 'New York Islanders',
            'NYR': 'New York Rangers', 'OTT': 'Ottawa Senators', 'PHI': 'Philadelphia Flyers',
            'PIT': 'Pittsburgh Penguins', 'SJS': 'San Jose Sharks', 'SEA': 'Seattle Kraken',
            'STL': 'St. Louis Blues', 'TBL': 'Tampa Bay Lightning', 'TOR': 'Toronto Maple Leafs',
            'UTA': 'Utah Hockey Club', 'VAN': 'Vancouver Canucks', 'VGK': 'Vegas Golden Knights',
            'WSH': 'Washington Capitals', 'WPG': 'Winnipeg Jets',
        },
    },
    # NFL: re-enable in September when the season starts
    # 'KXNFLGAME': { 'sport': 'americanfootball_nfl', 'teams': { ... } },

    # Soccer: 3-way markets (home/draw/away). TIE leg is filtered out during fetching.
    # Arb detection is skipped for soccer since 2-leg arb doesn't cover the draw.
    'KXEPLGAME': {
        'sport': 'soccer_epl',
        'draws': True,
        'teams': {
            'ARS': 'Arsenal', 'AVL': 'Aston Villa', 'BOU': 'Bournemouth',
            'BRE': 'Brentford', 'BRI': 'Brighton and Hove Albion', 'BUR': 'Burnley',
            'CFC': 'Chelsea', 'CRY': 'Crystal Palace', 'EVE': 'Everton',
            'FUL': 'Fulham', 'LEE': 'Leeds United', 'LFC': 'Liverpool',
            'MCI': 'Manchester City', 'MUN': 'Manchester United', 'NEW': 'Newcastle United',
            'NFO': 'Nottingham Forest', 'SUN': 'Sunderland', 'TOT': 'Tottenham Hotspur',
            'WHU': 'West Ham United', 'WOL': 'Wolverhampton Wanderers',
        },
    },
    'KXUCLGAME': {
        'sport': 'soccer_uefa_champs_league',
        'draws': True,
        'teams': {
            'ARS': 'Arsenal', 'ATM': 'Atletico Madrid', 'BAR': 'Barcelona',
            'BAY': 'Bayern Munich', 'BVB': 'Borussia Dortmund', 'CHE': 'Chelsea',
            'INT': 'Inter Milan', 'JUV': 'Juventus', 'LFC': 'Liverpool',
            'MCI': 'Manchester City', 'PSG': 'Paris Saint-Germain', 'RMA': 'Real Madrid',
        },
    },
    'KXBUNDESLIGAGAME': {
        'sport': 'soccer_germany_bundesliga',
        'draws': True,
        'teams': {
            'BMG': 'Borussia Monchengladbach', 'BMU': 'Bayern Munich', 'BVB': 'Borussia Dortmund',
            'FCA': 'FC Augsburg', 'FCH': 'FC Heidenheim', 'HSV': 'Hamburger SV',
            'KOE': 'FC Koln', 'LEV': 'Bayer Leverkusen', 'M05': 'Mainz 05',
            'RBL': 'RB Leipzig', 'SCF': 'SC Freiburg', 'SGE': 'Eintracht Frankfurt',
            'STP': 'FC St. Pauli', 'SVW': 'Werder Bremen', 'TSG': 'Hoffenheim',
            'UNI': 'Union Berlin', 'VFB': 'VfB Stuttgart', 'WOB': 'Wolfsburg',
        },
    },
    'KXLIGUE1GAME': {
        'sport': 'soccer_france_ligue_one',
        'draws': True,
        'teams': {
            'ANG': 'Angers SCO', 'ASM': 'AS Monaco', 'AUX': 'AJ Auxerre',
            'FCL': 'FC Lorient', 'FCM': 'FC Metz', 'FCN': 'FC Nantes',
            'HAC': 'Le Havre AC', 'LIL': 'Lille OSC', 'NIC': 'OGC Nice',
            'OL': 'Olympique Lyonnais', 'OM': 'Olympique de Marseille', 'PAR': 'Paris FC',
            'PSG': 'Paris Saint-Germain', 'RCL': 'RC Lens', 'RCS': 'RC Strasbourg',
            'REN': 'Stade Rennais', 'STB': 'Stade Brestois 29', 'TFC': 'Toulouse FC',
        },
    },
}

ESPN_SPORT_MAP = {
    'americanfootball_nfl':      ('football',    'nfl'),
    'americanfootball_ncaaf':    ('football',    'college-football'),
    'basketball_nba':            ('basketball',  'nba'),
    'basketball_ncaab':          ('basketball',  'mens-college-basketball'),
    'baseball_mlb':              ('baseball',    'mlb'),
    'icehockey_nhl':             ('hockey',      'nhl'),
    'baseball_npb':              ('baseball',    'npb'),
    'soccer_usa_mls':            ('soccer',      'usa.1'),
    'soccer_epl':                ('soccer',      'eng.1'),
    'soccer_uefa_champs_league': ('soccer',      'uefa.champions'),
}


def to_eastern(iso_str):
    dt = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
    return dt.astimezone(EASTERN).strftime('%Y-%m-%d %I:%M %p ET')


def is_cache_valid():
    if not os.path.exists(CACHE_FILE):
        return False
    with open(CACHE_FILE) as f:
        cache = json.load(f)
    cached_at = datetime.fromisoformat(cache['cached_at'])
    return datetime.now() - cached_at < timedelta(minutes=CACHE_TTL_MINUTES)


def load_cache():
    with open(CACHE_FILE) as f:
        return json.load(f)['data']


def save_cache(data):
    with open(CACHE_FILE, 'w') as f:
        json.dump({'cached_at': datetime.now().isoformat(), 'data': data}, f, indent=2)


def fetch_odds(key, sport):
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds/"
    params = {
        'apiKey': key,
        'regions': 'us',
        'markets': 'h2h,spreads,totals',
        'oddsFormat': 'american',
        'bookmakers': ','.join([SHARP_BOOK] + SOFT_BOOKS),
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json()


def fetch_odds_for_kalshi(api_key, force_refresh=False):
    """Fetch odds for all Kalshi-covered sports, cached separately from normal EV scans."""
    if not force_refresh and os.path.exists(KALSHI_CACHE_FILE):
        with open(KALSHI_CACHE_FILE) as f:
            cache = json.load(f)
        if datetime.now() - datetime.fromisoformat(cache['cached_at']) < timedelta(minutes=CACHE_TTL_MINUTES):
            print("Using cached Kalshi odds (--refresh to update).")
            return cache['data']

    sports = list({info['sport'] for info in KALSHI_GAME_SERIES.values()})
    all_games = []
    for sport in sorted(sports):
        try:
            games = fetch_odds(api_key, sport)
            all_games.extend(games)
            print(f"  Fetched {len(games)} {sport} games.")
        except Exception as e:
            print(f"  Warning: could not fetch {sport}: {e}")

    with open(KALSHI_CACHE_FILE, 'w') as f:
        json.dump({'cached_at': datetime.now().isoformat(), 'data': all_games}, f, indent=2)

    return all_games


def fetch_odds_api_scores(api_key, sport):
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/scores/"
    response = requests.get(url, params={'apiKey': api_key, 'daysFrom': 3})
    response.raise_for_status()
    results = []
    for game in response.json():
        if not game.get('completed'):
            continue
        score_dict = {}
        for s in (game.get('scores') or []):
            try:
                score_dict[s['name']] = float(s['score'])
            except (KeyError, ValueError):
                pass
        results.append({
            'home_team': game['home_team'],
            'away_team': game['away_team'],
            'home_score': score_dict.get(game['home_team'], 0.0),
            'away_score': score_dict.get(game['away_team'], 0.0),
        })
    return results


def fetch_espn_scores(sport_key, date_str):
    mapping = ESPN_SPORT_MAP.get(sport_key)
    if not mapping:
        return []
    sport, league = mapping
    url = f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard"
    response = requests.get(url, params={'dates': date_str})
    response.raise_for_status()
    results = []
    for event in response.json().get('events', []):
        comp = event.get('competitions', [{}])[0]
        if not comp.get('status', {}).get('type', {}).get('completed'):
            continue
        competitors = comp.get('competitors', [])
        home = next((c for c in competitors if c['homeAway'] == 'home'), None)
        away = next((c for c in competitors if c['homeAway'] == 'away'), None)
        if not home or not away:
            continue
        try:
            results.append({
                'home_team': home['team']['displayName'],
                'away_team': away['team']['displayName'],
                'home_score': float(home['score']),
                'away_score': float(away['score']),
            })
        except (KeyError, ValueError):
            continue
    return results


def fetch_bookmakers(key, sport):
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds/"
    params = {
        'apiKey': key,
        'regions': 'us,uk,eu,au',
        'markets': 'h2h',
        'oddsFormat': 'american',
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()

    seen = {}
    for game in data:
        for book in game.get('bookmakers', []):
            seen[book['key']] = book['title']

    return seen


def american_to_decimal(price):
    if price > 0:
        return (price / 100) + 1
    return (100 / abs(price)) + 1


def implied_prob(price):
    if price > 0:
        return 100 / (price + 100)
    return abs(price) / (abs(price) + 100)


def outcome_id(outcome, market_key):
    if market_key == 'h2h':
        return outcome['name']
    return (outcome['name'], outcome.get('point'))


def format_pick(outcome, market_key):
    if market_key == 'h2h':
        return outcome['name']
    point = outcome.get('point', '')
    if market_key == 'spreads':
        sign = '+' if point > 0 else ''
        return f"{outcome['name']} {sign}{point}"
    return f"{outcome['name']} {point}"  # totals: Over/Under 8.5


def find_ev_opportunities(data, min_edge):
    opportunities = []
    now = datetime.now(timezone.utc)

    for game in data:
        if datetime.fromisoformat(game['commence_time'].replace('Z', '+00:00')) <= now:
            continue

        books = {b['key']: b for b in game['bookmakers']}

        if SHARP_BOOK not in books:
            continue

        for market_key in MARKETS:
            sharp_market = next((m for m in books[SHARP_BOOK]['markets'] if m['key'] == market_key), None)
            if not sharp_market:
                continue

            raw_probs = {outcome_id(o, market_key): implied_prob(o['price']) for o in sharp_market['outcomes']}
            total = sum(raw_probs.values())
            true_probs = {k: v / total for k, v in raw_probs.items()}
            pin_odds = {outcome_id(o, market_key): o['price'] for o in sharp_market['outcomes']}

            for book_key in SOFT_BOOKS:
                if book_key not in books:
                    continue

                soft_market = next((m for m in books[book_key]['markets'] if m['key'] == market_key), None)
                if not soft_market:
                    continue

                for outcome in soft_market['outcomes']:
                    oid = outcome_id(outcome, market_key)
                    if oid not in true_probs:
                        continue

                    ev = (true_probs[oid] * american_to_decimal(outcome['price'])) - 1

                    if ev >= min_edge:
                        opportunities.append({
                            'game': f"{game['away_team']} @ {game['home_team']}",
                            'sport': game['sport_key'],
                            'market': market_key,
                            'commence_time': game['commence_time'],
                            'pick': format_pick(outcome, market_key),
                            'book': books[book_key]['title'],
                            'soft_odds': outcome['price'],
                            'soft_prob': round(implied_prob(outcome['price']) * 100, 2),
                            'pinnacle_odds': pin_odds[oid],
                            'true_prob': round(true_probs[oid] * 100, 2),
                            'ev': round(ev * 100, 2),
                        })

    # Keep only best-edge book per (game, market, pick)
    best = {}
    for o in opportunities:
        key = (o['game'], o['market'], o['pick'])
        if key not in best or o['ev'] > best[key]['ev']:
            best[key] = o

    return sorted(best.values(), key=lambda x: x['ev'], reverse=True)


def kelly_fraction(true_prob_pct, soft_odds_american):
    p = true_prob_pct / 100
    decimal = american_to_decimal(soft_odds_american)
    b = decimal - 1
    if b <= 0:
        return 0.0
    return max(0.0, (p * decimal - 1) / b * 0.5)  # half Kelly


def determine_result(market, pick, home_name, home_score, away_name, away_score):
    if market == 'h2h':
        if home_score == away_score:
            return 'push'
        winner = home_name if home_score > away_score else away_name
        return 'win' if pick == winner else 'loss'

    elif market == 'spreads':
        parts = pick.rsplit(' ', 1)
        if len(parts) != 2:
            return None
        team, point_str = parts
        try:
            point = float(point_str)
        except ValueError:
            return None
        margin = (home_score - away_score) if team == home_name else (away_score - home_score)
        net = margin + point
        if net > 0: return 'win'
        if net < 0: return 'loss'
        return 'push'

    elif market == 'totals':
        parts = pick.split(' ', 1)
        if len(parts) != 2:
            return None
        direction, line_str = parts
        try:
            line = float(line_str)
        except ValueError:
            return None
        total = home_score + away_score
        if direction == 'Over':
            return 'win' if total > line else ('push' if total == line else 'loss')
        return 'win' if total < line else ('push' if total == line else 'loss')

    return None


SHEET_HEADERS = [
    'Date', 'Game', 'League', 'Type', 'Gametime', 'Pick', 'Book',
    'Pinnacle', 'Vigless Prob', 'Soft Odds', 'Soft Prob',
    'Edge %', 'Kelly %', 'Result', 'Profit/Loss',
]


def setup_sheet(creds_path, sheet_name):
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
    client = gspread.authorize(creds)

    try:
        sheet = client.open(sheet_name).sheet1
    except gspread.SpreadsheetNotFound:
        print(f"Error: Sheet '{sheet_name}' not found.")
        print("Create it manually in Google Drive, then share it with the service account email in your credentials JSON.")
        return None

    existing = sheet.get_all_values()
    if not existing:
        sheet.append_row(SHEET_HEADERS)
    else:
        headers = existing[0]

        if 'Kelly %' not in headers and 'Edge %' in headers:
            insert_at = headers.index('Edge %') + 2
            sheet.insert_cols([['Kelly %']], col=insert_at)
            headers.insert(insert_at - 1, 'Kelly %')
            print("Migrated sheet: added 'Kelly %' column.")

        if 'result' in headers:
            sheet.update_cell(1, headers.index('result') + 1, 'Result')
            headers[headers.index('result')] = 'Result'
            print("Migrated sheet: capitalized 'Result' header.")

        if 'Profit/Loss' not in headers and 'Result' in headers:
            insert_at = headers.index('Result') + 2
            sheet.insert_cols([['Profit/Loss']], col=insert_at)
            print("Migrated sheet: added 'Profit/Loss' column.")

    return sheet


def log_to_sheet(sheet, opps):
    existing = sheet.get_all_values()
    # Build a set of already-logged keys: game + type + pick
    logged = {(r[1], r[3], r[5]) for r in existing[1:]} if len(existing) > 1 else set()

    new_rows = []
    for o in opps:
        key = (o['game'], o['market'], o['pick'])
        if key in logged:
            continue
        kelly = round(kelly_fraction(o['true_prob'], o['soft_odds']) * 100, 2)
        new_rows.append([
            datetime.now(EASTERN).strftime('%Y-%m-%d %I:%M %p ET'),
            o['game'],
            o['sport'],
            o['market'],
            to_eastern(o['commence_time']),
            o['pick'],
            o['book'],
            f"+{o['pinnacle_odds']}" if o['pinnacle_odds'] > 0 else str(o['pinnacle_odds']),
            o['true_prob'],
            f"+{o['soft_odds']}" if o['soft_odds'] > 0 else str(o['soft_odds']),
            o['soft_prob'],
            o['ev'],
            kelly,
            'pending',
            '',
        ])

    if new_rows:
        sheet.append_rows(new_rows)
        print(f"Logged {len(new_rows)} new opportunity/opportunities to sheet.")
    else:
        print("No new opportunities to log (all already in sheet).")


def _american(decimal_odds):
    if decimal_odds >= 2:
        return f"+{round((decimal_odds - 1) * 100)}"
    return str(-round(100 / (decimal_odds - 1)))


def log_kalshi_to_sheet(sheet, ev_opps):
    existing = sheet.get_all_values()
    logged = {(r[1], r[3], r[5]) for r in existing[1:]} if len(existing) > 1 else set()

    new_rows = []
    for o in ev_opps:
        key = (o['game'], 'h2h', o['pick'])
        if key in logged:
            continue
        kalshi_american = _american(100 / o['kalshi_price_pct'])
        pin_american    = _american(100 / o['true_prob'])
        new_rows.append([
            datetime.now(EASTERN).strftime('%Y-%m-%d %I:%M %p ET'),
            o['game'],
            o['sport'],
            'h2h',
            to_eastern(o['commence_time']),
            o['pick'],
            'Kalshi',
            pin_american,
            o['true_prob'],
            kalshi_american,
            o['kalshi_price_pct'],
            o['ev'],
            o['kelly'],
            'pending',
            '',
        ])

    if new_rows:
        sheet.append_rows(new_rows)
        print(f"Logged {len(new_rows)} Kalshi opportunity/opportunities to sheet.")
    else:
        print("No new Kalshi opportunities to log (all already in sheet).")


def update_results(sheet, api_key=None):
    all_rows = sheet.get_all_values()
    if len(all_rows) < 2:
        print("No data rows in sheet.")
        return

    headers = all_rows[0]
    col = {h: i for i, h in enumerate(headers)}

    for required in ('Game', 'League', 'Type', 'Gametime', 'Pick', 'Soft Odds', 'Kelly %', 'Result', 'Profit/Loss'):
        if required not in col:
            print(f"Error: '{required}' column not found. Run --log-sheet first to set up headers.")
            return

    pending = [
        (i + 2, row)  # +2: skip header row + convert to 1-indexed
        for i, row in enumerate(all_rows[1:])
        if len(row) > col['Result'] and row[col['Result']] == 'pending'
    ]

    if not pending:
        print("No pending bets to update.")
        return

    print(f"Found {len(pending)} pending bet(s).")

    # Group by (sport, date) so we make one ESPN request per sport-day combo
    by_sport_date = {}
    for row_num, row in pending:
        sport = row[col['League']] if len(row) > col['League'] else ''
        game_time = row[col['Gametime']] if len(row) > col['Gametime'] else ''
        try:
            dt = datetime.strptime(game_time.replace(' ET', ''), '%Y-%m-%d %I:%M %p')
            date_str = dt.strftime('%Y%m%d')
        except ValueError:
            date_str = datetime.now(EASTERN).strftime('%Y%m%d')
        by_sport_date.setdefault((sport, date_str), []).append((row_num, row))

    scores_lookup = {}
    for (sport, date_str) in by_sport_date:
        games = []
        if sport in ESPN_SPORT_MAP:
            print(f"  Fetching ESPN scores for {sport} on {date_str}...")
            try:
                games = fetch_espn_scores(sport, date_str)
            except Exception:
                pass

        if not games and api_key:
            print(f"  ESPN unavailable for {sport}, falling back to Odds API...")
            try:
                games = fetch_odds_api_scores(api_key, sport)
            except Exception as e:
                print(f"  Warning: Odds API fallback failed for {sport}: {e}")
                continue

        if not games:
            print(f"  Warning: no scores found for '{sport}', skipping.")
            continue
        for game in games:
            game_key = f"{game['away_team']} @ {game['home_team']}"
            scores_lookup[game_key] = game

    result_col_num = col['Result'] + 1
    pl_col_num = col['Profit/Loss'] + 1

    updates = []
    updated = 0
    still_pending = 0

    for row_num, row in pending:
        game      = row[col['Game']]      if len(row) > col['Game']      else ''
        market    = row[col['Type']]      if len(row) > col['Type']      else ''
        pick      = row[col['Pick']]      if len(row) > col['Pick']      else ''
        odds_str  = row[col['Soft Odds']] if len(row) > col['Soft Odds'] else '0'
        kelly_str = row[col['Kelly %']]   if len(row) > col['Kelly %']   else '0'

        if game not in scores_lookup:
            still_pending += 1
            continue

        gs = scores_lookup[game]
        result = determine_result(market, pick, gs['home_team'], gs['home_score'], gs['away_team'], gs['away_score'])
        if result is None:
            print(f"  Could not parse result for: {game} | {market} | {pick}")
            still_pending += 1
            continue

        try:
            kelly_pct = float(kelly_str)
        except ValueError:
            kelly_pct = 0.0

        try:
            soft_odds = int(odds_str.lstrip('+'))
        except ValueError:
            soft_odds = 0

        if result == 'win' and soft_odds:
            net = american_to_decimal(soft_odds) - 1
            pl_str = f"+{kelly_pct * net:.2f}%"
        elif result == 'loss':
            pl_str = f"-{kelly_pct:.2f}%"
        else:
            pl_str = "0.00%"

        result_ref = gspread.utils.rowcol_to_a1(row_num, result_col_num)
        pl_ref     = gspread.utils.rowcol_to_a1(row_num, pl_col_num)
        updates += [
            {'range': result_ref, 'values': [[result]]},
            {'range': pl_ref,     'values': [[pl_str]]},
        ]
        updated += 1

    if updates:
        sheet.batch_update(updates)
        print(f"Updated {updated} bet(s). {still_pending} game(s) not yet complete.")
    else:
        print(f"No completed games matched. {still_pending} still pending.")


def print_validate(data):
    all_books = [SHARP_BOOK] + SOFT_BOOKS
    print(f"\n{'='*70}")
    print(f"  ODDS VALIDATION — compare these against the actual sites")
    print(f"{'='*70}")

    for game in data:
        books = {b['key']: b for b in game['bookmakers']}
        available = [b for b in all_books if b in books]
        if not available:
            continue

        print(f"\n  {game['away_team']} @ {game['home_team']}  ({game['sport_key']})")
        print(f"  Game time: {to_eastern(game['commence_time'])}")

        col_w = 22
        header = f"  {'Outcome':<24}" + ''.join(f"{books[b]['title']:<{col_w}}" for b in available)

        for market_key in MARKETS:
            market_outcomes = []
            for bk in available:
                m = next((mk for mk in books[bk]['markets'] if mk['key'] == market_key), None)
                if m:
                    for o in m['outcomes']:
                        label = format_pick(o, market_key)
                        if label not in market_outcomes:
                            market_outcomes.append(label)

            if not market_outcomes:
                continue

            print(f"\n  [{market_key}]")
            print(header)
            print(f"  {'-'*22}" + ('-' * col_w * len(available)))

            for label in market_outcomes:
                row = f"  {label:<24}"
                for bk in available:
                    m = next((mk for mk in books[bk]['markets'] if mk['key'] == market_key), None)
                    price = None
                    if m:
                        price = next((o['price'] for o in m['outcomes'] if format_pick(o, market_key) == label), None)
                    if price is not None:
                        sign = '+' if price > 0 else ''
                        cell = f"{sign}{price}  ({round(implied_prob(price) * 100, 1)}%)"
                    else:
                        cell = 'n/a'
                    row += f"{cell:<{col_w}}"
                print(row)

    print(f"\n{'='*70}\n")


def print_opportunities(opps):
    if not opps:
        print("No +EV opportunities found above threshold.")
        return

    print(f"\n{'='*60}")
    print(f"  +EV OPPORTUNITIES  ({len(opps)} found)")
    print(f"{'='*60}")

    for o in opps:
        pin_sign = '+' if o['pinnacle_odds'] > 0 else ''
        soft_sign = '+' if o['soft_odds'] > 0 else ''
        print(f"\n  {o['game']}  ({o['sport']})")
        print(f"  Game time:         {to_eastern(o['commence_time'])}")
        print(f"  Market:            {o['market']}")
        print(f"  Pick:              {o['pick']}")
        print(f"  Pinnacle:          {pin_sign}{o['pinnacle_odds']}  (no-vig prob: {o['true_prob']}%)")
        print(f"  {o['book']:<18} {soft_sign}{o['soft_odds']}  (implied prob: {o['soft_prob']}%)")
        print(f"  Edge:              +{o['ev']}%")
        kelly = kelly_fraction(o['true_prob'], o['soft_odds'])
        print(f"  Kelly (half):      {kelly*100:.2f}% of bankroll")

    print(f"\n{'='*60}\n")


def _kalshi_headers(key_id, private_key_path, method, path):
    timestamp_ms = str(int(time.time() * 1000))
    msg = (timestamp_ms + method.upper() + path).encode()
    with open(private_key_path, 'rb') as f:
        private_key = serialization.load_pem_private_key(f.read(), password=None)
    signature = private_key.sign(msg, PSS(mgf=MGF1(hashes.SHA256()), salt_length=PSS.MAX_LENGTH), hashes.SHA256())
    return {
        'KALSHI-ACCESS-KEY': key_id,
        'KALSHI-ACCESS-TIMESTAMP': timestamp_ms,
        'KALSHI-ACCESS-SIGNATURE': base64.b64encode(signature).decode(),
    }


def _kalshi_get(key_id, private_key_path, path, params=None):
    headers = _kalshi_headers(key_id, private_key_path, 'GET', '/trade-api/v2' + path)
    response = requests.get(f'{KALSHI_API_URL}{path}', headers=headers, params=params)
    response.raise_for_status()
    return response.json()


def fetch_kalshi_game_markets(key_id, private_key_path):
    """Fetch individual game winner markets from Kalshi, grouped by matchup."""
    all_games = []

    for series_ticker, series_info in KALSHI_GAME_SERIES.items():
        markets = []
        cursor = None
        while True:
            params = {'series_ticker': series_ticker, 'status': 'open', 'limit': 1000}
            if cursor:
                params['cursor'] = cursor
            resp = _kalshi_get(key_id, private_key_path, '/markets', params)
            batch = resp.get('markets', [])
            markets.extend(batch)
            cursor = resp.get('cursor')
            if not cursor or not batch:
                break

        # Group by event_ticker (one event = one game matchup)
        events = {}
        for market in markets:
            et = market.get('event_ticker', '')
            events.setdefault(et, []).append(market)

        for event_ticker, event_markets in events.items():
            # Parse game date from ticker: KXMLBGAME-26MAY152138LADLAA → 2026-05-15
            date_match = re.search(r'-(\d{2})([A-Z]{3})(\d{2})', event_ticker)
            if not date_match:
                continue
            _months = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
            try:
                game_date = datetime(
                    2000 + int(date_match.group(1)),
                    _months[date_match.group(2)],
                    int(date_match.group(3)),
                ).date()
            except (KeyError, ValueError):
                continue

            # Each market ticker ends in '-TEAMCODE' — extract both teams
            legs = {}
            for m in event_markets:
                parts = m.get('ticker', '').rsplit('-', 1)
                if len(parts) == 2:
                    legs[parts[1]] = m

            tie_market = legs.pop('TIE', None)  # soccer draw leg — save price, exclude from team matching

            if len(legs) != 2:
                continue

            codes = list(legs.keys())
            team_a_code, team_b_code = codes[0], codes[1]
            team_a = series_info['teams'].get(team_a_code)
            team_b = series_info['teams'].get(team_b_code)
            if not team_a or not team_b:
                continue

            try:
                team_a_yes_ask = float(legs[team_a_code].get('yes_ask_dollars', 0))
                team_b_yes_ask = float(legs[team_b_code].get('yes_ask_dollars', 0))
                tie_yes_ask = float(tie_market.get('yes_ask_dollars', 0)) if tie_market else 0.0
            except (TypeError, ValueError):
                continue

            if team_a_yes_ask <= 0 or team_b_yes_ask <= 0:
                continue

            all_games.append({
                'series': series_ticker,
                'sport': series_info['sport'],
                'event_ticker': event_ticker,
                'game_date': game_date,
                'team_a': team_a,
                'team_b': team_b,
                'team_a_yes_ask': team_a_yes_ask,  # dollars (0.0–1.0 = implied prob)
                'team_b_yes_ask': team_b_yes_ask,
                'tie_yes_ask': tie_yes_ask,
                'draws': series_info.get('draws', False),
            })

    return all_games


def _normalize(name):
    return re.sub(r'[^a-z ]', '', name.lower()).strip()


_AMBIGUOUS_WORDS = {'united', 'city', 'fc', 'sc', 'ac', 'athletic', 'rovers', 'wanderers', 'county', 'town', 'rangers'}

def _teams_match(a, b):
    na, nb = _normalize(a), _normalize(b)
    if na == nb or na in nb or nb in na:
        return True
    a_last = na.split()[-1] if na.split() else ''
    b_last = nb.split()[-1] if nb.split() else ''
    return bool(a_last and b_last and a_last == b_last and len(a_last) > 3 and a_last not in _AMBIGUOUS_WORDS)


def find_kalshi_opportunities(kalshi_games, odds_data, min_edge, debug=False):
    now = datetime.now(timezone.utc)

    # Build lookup: sport -> list of game info with Pinnacle true probs
    games_by_sport = {}
    for game in odds_data:
        if datetime.fromisoformat(game['commence_time'].replace('Z', '+00:00')) <= now:
            continue
        books = {b['key']: b for b in game['bookmakers']}
        if SHARP_BOOK not in books:
            continue
        sharp_h2h = next((m for m in books[SHARP_BOOK]['markets'] if m['key'] == 'h2h'), None)
        if not sharp_h2h:
            continue
        raw = {o['name']: implied_prob(o['price']) for o in sharp_h2h['outcomes']}
        total = sum(raw.values())
        games_by_sport.setdefault(game['sport_key'], []).append({
            'game': game,
            'books': books,
            'true_probs': {k: v / total for k, v in raw.items()},
            'game_str': f"{game['away_team']} @ {game['home_team']}",
        })

    if debug:
        matched_sports = set(games_by_sport.keys()) & {kg['sport'] for kg in kalshi_games}
        print(f"\n  Pinnacle has {sum(len(v) for v in games_by_sport.values())} upcoming games across: {list(games_by_sport.keys())}")
        print(f"  Kalshi sports with Pinnacle overlap: {matched_sports or 'none'}\n")

    arbs, ev_opps = [], []

    for kg in kalshi_games:
        sport = kg['sport']
        if sport not in games_by_sport:
            continue

        kg_date = kg['game_date']
        gi = next((
            g for g in games_by_sport[sport]
            if (
                datetime.fromisoformat(g['game']['commence_time'].replace('Z', '+00:00')).astimezone(EASTERN).date() == kg_date and
                (_teams_match(kg['team_a'], g['game']['home_team']) or _teams_match(kg['team_a'], g['game']['away_team'])) and
                (_teams_match(kg['team_b'], g['game']['home_team']) or _teams_match(kg['team_b'], g['game']['away_team']))
            )
        ), None)

        if debug:
            status = f"→ matched: {gi['game_str']}" if gi else "→ no Pinnacle match"
            print(f"  {kg['team_a']} vs {kg['team_b']} ({kg_date})  {status}")

        if not gi:
            continue

        game = gi['game']

        for team_name, yes_ask, opp_name in [
            (kg['team_a'], kg['team_a_yes_ask'], kg['team_b']),
            (kg['team_b'], kg['team_b_yes_ask'], kg['team_a']),
        ]:
            # yes_ask is 0.0–1.0: cost in dollars to win $1 → implied prob
            pinnacle_team = next((t for t in gi['true_probs'] if _teams_match(team_name, t)), None)
            if not pinnacle_team:
                continue
            true_prob = gi['true_probs'][pinnacle_team]
            decimal_k = 1.0 / yes_ask
            ev = true_prob * decimal_k - 1

            if debug:
                print(f"    {team_name}: Kalshi {round(yes_ask*100,1)}%  Pinnacle {round(true_prob*100,2)}%  EV {round(ev*100,2):+.2f}%")

            if ev >= min_edge:
                b = decimal_k - 1
                kelly = max(0.0, (true_prob * decimal_k - 1) / b * 0.5) * 100 if b > 0 else 0.0
                ev_opps.append({
                    'game': gi['game_str'],
                    'sport': sport,
                    'commence_time': game['commence_time'],
                    'pick': team_name,
                    'kalshi_price_pct': round(yes_ask * 100, 1),
                    'true_prob': round(true_prob * 100, 2),
                    'ev': round(ev * 100, 2),
                    'kelly': round(kelly, 2),
                })

            if not kg.get('draws'):
                # 2-leg arb: Kalshi YES one team + sportsbook on the other
                for book_key in SOFT_BOOKS:
                    if book_key not in gi['books']:
                        continue
                    soft_h2h = next((m for m in gi['books'][book_key]['markets'] if m['key'] == 'h2h'), None)
                    if not soft_h2h:
                        continue
                    opp_outcome = next((o for o in soft_h2h['outcomes'] if _teams_match(opp_name, o['name'])), None)
                    if not opp_outcome:
                        continue
                    sb_implied = 1 / american_to_decimal(opp_outcome['price'])
                    total_cost = yes_ask + sb_implied
                    profit = 1 - total_cost
                    if profit >= min_edge:
                        arbs.append({
                            'game': gi['game_str'], 'sport': sport,
                            'commence_time': game['commence_time'],
                            'profit_pct': round(profit * 100, 2),
                            'legs': [
                                {'source': 'Kalshi', 'desc': f'{team_name} YES @ {round(yes_ask*100,1)}¢', 'stake_pct': round(yes_ask/total_cost*100, 1)},
                                {'source': gi['books'][book_key]['title'], 'desc': f'{opp_name} {opp_outcome["price"]:+d}', 'stake_pct': round(sb_implied/total_cost*100, 1)},
                            ],
                        })

        # 3-leg soccer arb: requires covering home win, draw, and away win
        if kg.get('draws'):
            # Collect best odds per outcome across all soft books
            best_sb = {}  # outcome_name -> (book_title, price, implied)
            for book_key in SOFT_BOOKS:
                if book_key not in gi['books']:
                    continue
                soft_h2h = next((m for m in gi['books'][book_key]['markets'] if m['key'] == 'h2h'), None)
                if not soft_h2h:
                    continue
                book_title = gi['books'][book_key]['title']
                for o in soft_h2h['outcomes']:
                    existing = best_sb.get(o['name'])
                    if existing is None or o['price'] > existing[1]:
                        best_sb[o['name']] = (book_title, o['price'], 1 / american_to_decimal(o['price']))

            draw_entry = best_sb.get('Draw')
            best_a_entry = next((v for k, v in best_sb.items() if _teams_match(kg['team_a'], k)), None)
            best_b_entry = next((v for k, v in best_sb.items() if _teams_match(kg['team_b'], k)), None)

            # Combination 1: Kalshi YES Team A + best SB Draw + best SB Team B
            # Combination 2: Kalshi YES Team B + best SB Draw + best SB Team A
            for kalshi_team, kalshi_ask, sb_entry in [
                (kg['team_a'], kg['team_a_yes_ask'], best_b_entry),
                (kg['team_b'], kg['team_b_yes_ask'], best_a_entry),
            ]:
                if not draw_entry or not sb_entry:
                    continue
                total_cost = kalshi_ask + draw_entry[2] + sb_entry[2]
                profit = 1 - total_cost
                if profit >= min_edge:
                    arbs.append({
                        'game': gi['game_str'], 'sport': sport,
                        'commence_time': game['commence_time'],
                        'profit_pct': round(profit * 100, 2),
                        'legs': [
                            {'source': 'Kalshi', 'desc': f'{kalshi_team} YES @ {round(kalshi_ask*100,1)}¢', 'stake_pct': round(kalshi_ask/total_cost*100, 1)},
                            {'source': draw_entry[0], 'desc': f'Draw {draw_entry[1]:+d}', 'stake_pct': round(draw_entry[2]/total_cost*100, 1)},
                            {'source': sb_entry[0], 'desc': f'opp {sb_entry[1]:+d}', 'stake_pct': round(sb_entry[2]/total_cost*100, 1)},
                        ],
                    })

            # Combination 3: Kalshi YES TIE + best SB Team A + best SB Team B
            tie_ask = kg.get('tie_yes_ask', 0)
            if tie_ask > 0 and best_a_entry and best_b_entry:
                total_cost = tie_ask + best_a_entry[2] + best_b_entry[2]
                profit = 1 - total_cost
                if profit >= min_edge:
                    arbs.append({
                        'game': gi['game_str'], 'sport': sport,
                        'commence_time': game['commence_time'],
                        'profit_pct': round(profit * 100, 2),
                        'legs': [
                            {'source': 'Kalshi', 'desc': f'Draw YES @ {round(tie_ask*100,1)}¢', 'stake_pct': round(tie_ask/total_cost*100, 1)},
                            {'source': best_a_entry[0], 'desc': f'{kg["team_a"]} {best_a_entry[1]:+d}', 'stake_pct': round(best_a_entry[2]/total_cost*100, 1)},
                            {'source': best_b_entry[0], 'desc': f'{kg["team_b"]} {best_b_entry[1]:+d}', 'stake_pct': round(best_b_entry[2]/total_cost*100, 1)},
                        ],
                    })

    arbs.sort(key=lambda x: x['profit_pct'], reverse=True)
    ev_opps.sort(key=lambda x: x['ev'], reverse=True)
    return arbs, ev_opps


def print_kalshi_opportunities(arbs, ev_opps):
    if arbs:
        print(f"\n{'='*60}")
        print(f"  KALSHI ARB OPPORTUNITIES  ({len(arbs)} found)")
        print(f"{'='*60}")
        for a in arbs:
            print(f"\n  {a['game']}  ({a['sport']})")
            print(f"  Game time:    {to_eastern(a['commence_time'])}")
            for leg in a['legs']:
                print(f"  {leg['source']:<18} {leg['desc']}  ({leg['stake_pct']}% of stake)")
            print(f"  Profit:       +{a['profit_pct']}% of total staked")
        print(f"\n{'='*60}\n")

    if ev_opps:
        print(f"\n{'='*60}")
        print(f"  KALSHI +EV vs PINNACLE  ({len(ev_opps)} found)")
        print(f"{'='*60}")
        for o in ev_opps:
            print(f"\n  {o['game']}  ({o['sport']})")
            print(f"  Game time:    {to_eastern(o['commence_time'])}")
            print(f"  Pick:         {o['pick']} YES on Kalshi")
            print(f"  Kalshi price: {o['kalshi_price_pct']}¢  (implied: {o['kalshi_price_pct']}%)")
            print(f"  Pinnacle:     true prob {o['true_prob']}%")
            print(f"  Edge:         +{o['ev']}%")
            print(f"  Kelly (half): {o['kelly']}% of bankroll")
        print(f"\n{'='*60}\n")

    if not arbs and not ev_opps:
        print("No Kalshi opportunities found above threshold.")


def main():
    parser = argparse.ArgumentParser(description='Find +EV bets using Pinnacle as the sharp line.')
    parser.add_argument('--refresh', action='store_true', help='Force a fresh fetch from the API')
    parser.add_argument('--sport', default='upcoming', help='Sport key (default: upcoming)')
    parser.add_argument('--min-edge', type=float, default=3.0, help='Minimum edge %% to display (default: 3)')
    parser.add_argument('--list-books', action='store_true', help='List all available bookmakers for a sport and exit')
    parser.add_argument('--log-sheet', action='store_true', help='Log opportunities to Google Sheet')
    parser.add_argument('--validate', action='store_true', help='Show side-by-side odds table for manual verification')
    parser.add_argument('--update-results', action='store_true', help='Fetch scores and update Result/P&L for pending bets in Google Sheet')
    parser.add_argument('--kalshi', action='store_true', help='Scan Kalshi markets for arb and +EV opportunities')
    parser.add_argument('--kalshi-debug', action='store_true', help='Show every Kalshi game match and EV breakdown')
    args = parser.parse_args()

    load_dotenv()
    key = os.getenv('apiKey')
    if not key:
        print("Error: apiKey not found in .env")
        return

    if args.update_results:
        if not GSPREAD_AVAILABLE:
            print("Error: gspread not installed. Run: pip install gspread google-auth")
            return
        creds_path = os.getenv('GOOGLE_CREDENTIALS_PATH')
        sheet_name = os.getenv('SHEET_NAME', 'Sharp Bot Picks')
        if not creds_path:
            print("Error: GOOGLE_CREDENTIALS_PATH not set in .env")
            return
        sheet = setup_sheet(creds_path, sheet_name)
        if sheet:
            update_results(sheet, api_key=key)
        return

    if args.kalshi:
        if not CRYPTOGRAPHY_AVAILABLE:
            print("Error: cryptography not installed. Run: pip install cryptography")
            return
        kalshi_key_id = os.getenv('KALSHI_KEY_ID')
        kalshi_key_path = os.getenv('KALSHI_PRIVATE_KEY_PATH')
        if not kalshi_key_id or not kalshi_key_path:
            print("Error: KALSHI_KEY_ID and KALSHI_PRIVATE_KEY_PATH must be set in .env")
            return
        print("Fetching odds for all Kalshi-covered sports...")
        data = fetch_odds_for_kalshi(key, force_refresh=args.refresh)
        print("Fetching Kalshi game markets...")
        kalshi_games = fetch_kalshi_game_markets(kalshi_key_id, kalshi_key_path)
        print(f"Found {len(kalshi_games)} open Kalshi game matchups.")
        arbs, ev_opps = find_kalshi_opportunities(kalshi_games, data, min_edge=args.min_edge / 100, debug=args.kalshi_debug)
        print_kalshi_opportunities(arbs, ev_opps)
        if args.log_sheet:
            if not GSPREAD_AVAILABLE:
                print("Error: gspread not installed. Run: pip install gspread google-auth")
                return
            creds_path = os.getenv('GOOGLE_CREDENTIALS_PATH')
            sheet_name = os.getenv('SHEET_NAME', 'Sharp Bot Picks')
            if not creds_path:
                print("Error: GOOGLE_CREDENTIALS_PATH not set in .env")
                return
            sheet = setup_sheet(creds_path, sheet_name)
            if sheet:
                log_kalshi_to_sheet(sheet, ev_opps)
        return

    if args.list_books:
        print(f"Fetching available bookmakers for sport: {args.sport}...")
        books = fetch_bookmakers(key, args.sport)
        if not books:
            print("No bookmakers found.")
        else:
            print(f"\n{'='*40}")
            print(f"  AVAILABLE BOOKMAKERS ({len(books)} found)")
            print(f"{'='*40}")
            for key_name, title in sorted(books.items(), key=lambda x: x[1]):
                print(f"  {title:<25} ({key_name})")
            print()
        return

    if args.refresh or not is_cache_valid():
        print(f"Fetching fresh odds from API (sport: {args.sport})...")
        data = fetch_odds(key, args.sport)
        save_cache(data)
        print(f"Fetched and cached {len(data)} games.")
    else:
        print(f"Using cached odds from {json.load(open(CACHE_FILE))['cached_at']} (--refresh to update).")
        data = load_cache()

    if args.validate:
        print_validate(data)
        return

    opps = find_ev_opportunities(data, min_edge=args.min_edge / 100)
    print_opportunities(opps)

    if args.log_sheet:
        if not GSPREAD_AVAILABLE:
            print("Error: gspread not installed. Run: pip install gspread google-auth")
            return
        creds_path = os.getenv('GOOGLE_CREDENTIALS_PATH')
        sheet_name = os.getenv('SHEET_NAME', 'Sharp Bot Picks')
        if not creds_path:
            print("Error: GOOGLE_CREDENTIALS_PATH not set in .env")
            return
        sheet = setup_sheet(creds_path, sheet_name)
        if sheet:
            log_to_sheet(sheet, opps)


if __name__ == "__main__":
    main()
