import os
import json
import argparse
import requests
from dotenv import load_dotenv
from datetime import datetime, timedelta

CACHE_FILE = 'odds_cache.json'
CACHE_TTL_MINUTES = 10
SHARP_BOOK = 'pinnacle'
SOFT_BOOKS = ['fanduel', 'draftkings']
DEFAULT_MIN_EDGE = 0.03


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
        'markets': 'h2h',
        'oddsFormat': 'american',
        'bookmakers': ','.join([SHARP_BOOK] + SOFT_BOOKS),
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json()


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


def no_vig_probs(outcomes):
    raw = {o['name']: implied_prob(o['price']) for o in outcomes}
    total = sum(raw.values())
    return {name: prob / total for name, prob in raw.items()}


def find_ev_opportunities(data, min_edge):
    opportunities = []

    for game in data:
        books = {b['key']: b for b in game['bookmakers']}

        if SHARP_BOOK not in books:
            continue

        sharp_h2h = next((m for m in books[SHARP_BOOK]['markets'] if m['key'] == 'h2h'), None)
        if not sharp_h2h:
            continue

        true_probs = no_vig_probs(sharp_h2h['outcomes'])
        pinnacle_odds = {o['name']: o['price'] for o in sharp_h2h['outcomes']}

        for book_key in SOFT_BOOKS:
            if book_key not in books:
                continue

            soft_h2h = next((m for m in books[book_key]['markets'] if m['key'] == 'h2h'), None)
            if not soft_h2h:
                continue

            for outcome in soft_h2h['outcomes']:
                name = outcome['name']
                if name not in true_probs:
                    continue

                ev = (true_probs[name] * american_to_decimal(outcome['price'])) - 1

                if ev >= min_edge:
                    opportunities.append({
                        'game': f"{game['away_team']} @ {game['home_team']}",
                        'sport': game['sport_key'],
                        'commence_time': game['commence_time'],
                        'pick': name,
                        'book': books[book_key]['title'],
                        'soft_odds': outcome['price'],
                        'soft_prob': round(implied_prob(outcome['price']) * 100, 2),
                        'pinnacle_odds': pinnacle_odds.get(name),
                        'true_prob': round(true_probs[name] * 100, 2),
                        'ev': round(ev * 100, 2),
                    })

    return sorted(opportunities, key=lambda x: x['ev'], reverse=True)


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
        print(f"  Pick:              {o['pick']}")
        print(f"  Pinnacle:          {pin_sign}{o['pinnacle_odds']}  (no-vig prob: {o['true_prob']}%)")
        print(f"  {o['book']:<18} {soft_sign}{o['soft_odds']}  (implied prob: {o['soft_prob']}%)")
        print(f"  Edge:              +{o['ev']}%")

    print(f"\n{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description='Find +EV bets using Pinnacle as the sharp line.')
    parser.add_argument('--refresh', action='store_true', help='Force a fresh fetch from the API')
    parser.add_argument('--sport', default='upcoming', help='Sport key (default: upcoming)')
    parser.add_argument('--min-edge', type=float, default=3.0, help='Minimum edge %% to display (default: 3)')
    parser.add_argument('--list-books', action='store_true', help='List all available bookmakers for a sport and exit')
    args = parser.parse_args()

    load_dotenv()
    key = os.getenv('apiKey')
    if not key:
        print("Error: apiKey not found in .env")
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

    opps = find_ev_opportunities(data, min_edge=args.min_edge / 100)
    print_opportunities(opps)


if __name__ == "__main__":
    main()
