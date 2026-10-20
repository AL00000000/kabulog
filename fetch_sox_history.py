"""SOX daily history, global record highs and event-window lookup.

Explicit decade requests avoid Yahoo range=max silently becoming monthly.
The source currently begins 1994-05-04; do not claim complete 1993 inception data.
"""
import argparse
import bisect
import json
import math
import os
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path(__file__).resolve().parent
OUT = BASE / 'docs/data_sox'
JST = timezone(timedelta(hours=9))
NY = ZoneInfo('America/New_York')
UA = 'Mozilla/5.0'


def get_daily(start, end, ticker='%5ESOX'):
    ts = lambda d: int(datetime.combine(d, datetime.min.time(), timezone.utc).timestamp())
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?period1={ts(start)}&period2={ts(end)}&interval=1d'
    request = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=45) as response:
        payload = json.load(response)
    result = payload['chart']['result'][0]
    if result['meta'].get('dataGranularity') != '1d':
        raise ValueError('Source changed daily data granularity')
    quote = result['indicators']['quote'][0]
    rows = []
    now = datetime.now(NY)
    for i, stamp in enumerate(result.get('timestamp', [])):
        d = datetime.fromtimestamp(stamp, NY).date()
        # Do not publish today's in-progress regular session as a closing price.
        if d == now.date() and now.hour < 17:
            continue
        close = quote['close'][i]
        if close is None:
            continue
        if not math.isfinite(close) or close <= 0:
            raise ValueError('Invalid source closing value')
        values = [quote.get(field, [None] * len(result['timestamp']))[i] for field in ['close', 'high', 'low', 'open']]
        rows.append([d.isoformat()] + [round(v, 6) if v is not None and math.isfinite(v) and v > 0 else None for v in values])
    if not rows:
        raise ValueError('Source returned no daily prices')
    return rows


def records(rows, column=1):
    high = None
    previous_date = None
    out = []
    for i, row in enumerate(rows):
        value = row[column]
        if value is None:
            continue
        if high is None:
            high, previous_date = value, row[0]
            continue  # start of coverage is not an established record breakout
        if value > high + 0.000001:
            out.append({'date': row[0], 'value': value, 'index': i,
                        'previous_record_date': previous_date, 'previous_record': high,
                        'gap_days': (date.fromisoformat(row[0]) - date.fromisoformat(previous_date)).days})
            high, previous_date = value, row[0]
    return out


def preceding_events(day, events, days=30):
    # Only earlier dates. Same-day and future news cannot explain an earlier breakout.
    end = date.fromisoformat(day)
    return [e['id'] for e in events if e.get('evidence') != '価格データから算出' and 1 <= (end - date.fromisoformat(e['date'])).days <= days]


def analyse(rows, events):
    dates = [r[0] for r in rows]
    analysed = []
    for event in events:
        item = dict(event)
        # Weekend announcements and explicitly after-close releases map to the
        # following session. Keep the original announcement date visible.
        requested = event.get('market_date', event['date'])
        i = bisect.bisect_left(dates, requested)
        if i < len(rows):
            item['plot_date'] = rows[i][0]
            item['plot_value'] = rows[i][1]
            item['sox_change_pct'] = round((rows[i][1] / rows[i - 1][1] - 1) * 100, 4) if i else None
            item['sox_5session_pct'] = round((rows[i + 4][1] / rows[i - 1][1] - 1) * 100, 4) if i and i + 4 < len(rows) else None
        else:
            item['plot_date'] = None
            item['plot_value'] = None
            item['sox_change_pct'] = None
            item['sox_5session_pct'] = None
        analysed.append(item)
    result = {'events': analysed, 'records': {}, 'breakouts': {}}
    for name, column in [('close', 1), ('high', 2)]:
        result['records'][name] = records(rows, column)
        result['breakouts'][name] = [{**r, 'event_ids': preceding_events(r['date'], events)}
                                     for r in result['records'][name] if r['gap_days'] >= 30]
    return result


def validate(rows):
    if len(rows) < 7500 or rows[0][0] > '1994-06-01':
        raise ValueError('History incomplete or unexpectedly shortened')
    if [r[0] for r in rows] != sorted(set(r[0] for r in rows)):
        raise ValueError('Duplicate or unordered dates')
    for year in range(1995, datetime.now(NY).year):
        if sum(r[0].startswith(str(year)) for r in rows) < 240:
            raise ValueError(f'Incomplete daily coverage: {year}')


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    os.replace(temporary, path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--full', action='store_true')
    parser.add_argument('--offline', action='store_true', help='Rebuild event analysis from saved actual prices')
    args = parser.parse_args()
    path = OUT / 'prices.json'
    old = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    rows = old.get('rows', [])
    if not args.offline:
        merged = {r[0]: r for r in rows}
        today = datetime.now(NY).date()
        spans = [(date(y, 1, 1), min(date(y + 10, 1, 1), today + timedelta(days=1)))
                 for y in [1990, 2000, 2010, 2020]] if args.full or not rows else [(today - timedelta(days=60), today + timedelta(days=1))]
        for start, end in spans:
            fetched = get_daily(start, end)
            merged.update({r[0]: r for r in fetched})
            print(f'{start}..{end}: {len(fetched)} daily rows')
            time.sleep(.2)
        rows = sorted(merged.values(), key=lambda r: r[0])
    validate(rows)
    events = json.loads((OUT / 'events.json').read_text(encoding='utf-8'))
    analysis = analyse(rows, events['events'])
    previous_analysis = json.loads((OUT / 'analysis.json').read_text(encoding='utf-8')) if (OUT / 'analysis.json').exists() else None
    changed = rows != old.get('rows') or analysis != previous_analysis
    if changed:
        meta = {'schema_version': 1, 'symbol': '^SOX', 'source': 'Yahoo Finance daily chart API',
                'source_url': 'https://finance.yahoo.com/quote/%5ESOX/history/',
                'index_url': 'https://beta.indexes.nasdaq.com/Index/Overview/SOX',
                'index_base_date': '1993-12-01', 'columns': ['date', 'close', 'high', 'low', 'open'],
                'start': rows[0][0], 'end': rows[-1][0], 'coverage': '1993-12-01〜1994-05-03は未取得。赤点は取得期間内の最高値更新。',
                'updated': datetime.now(JST).isoformat(timespec='seconds'), 'rows': rows}
        save(path, meta)
        save(OUT / 'analysis.json', analysis)
    print(f'{rows[0][0]}..{rows[-1][0]}: {len(rows)} days; {len(analysis["records"]["close"])} closing records; {len(analysis["breakouts"]["close"])} resumption dates; changed={changed}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
