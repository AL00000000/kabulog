"""Official call-center guidance snapshots, twice daily. No live waiting-time feed.

Dependencies: beautifulsoup4 (see requirements_congestion.txt).
Only the selected guidance is fingerprinted, never the surrounding page.
"""
import argparse
import hashlib
import json
import os
import re
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

from bs4 import BeautifulSoup

BASE = Path(__file__).resolve().parent
OUT = BASE / 'docs/data_congestion'
JST = timezone(timedelta(hours=9))
SBI = 'https://www.sbisec.co.jp/ETGate/?_ControlID=WPLETmgR001Control&_DataStoreID=DSWPLETmgR001Control&burl=search_home&cat1=home&cat2=support&dir=support%2F&file=home_support.html&getFlg=on'
SOURCES = {
    'sbi': ('SBI証券', SBI),
    'rakuten': ('楽天証券', 'https://www.rakuten-sec.co.jp/web/support/contact/'),
    'monex': ('マネックス証券', 'https://mst.monex.co.jp/mst/servlet/ITS/ucu/CcPeakHoursGST'),
}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Cache-Control': 'no-cache'})
    # This PC has stale proxy environment settings; direct public HTTPS is intended.
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=40) as r:
        body = r.read()
        if not body:
            raise ValueError('empty response')
        return body, {'url': url, 'last_modified': r.headers.get('Last-Modified'),
                      'etag': r.headers.get('ETag'), 'cache_control': r.headers.get('Cache-Control')}


def parse_sbi(body):
    soup = BeautifulSoup(body.decode('cp932'), 'html.parser')
    table = soup.find(id='karte_home_support_call_busy')
    if table is None:
        raise ValueError('SBI telephone table missing')
    rows = [[c.get_text(' ', strip=True) for c in row.find_all(attrs={'role': ['cell', 'columnheader']})]
            for row in table.find_all(attrs={'role': 'row'})]
    if len(rows) != 3 or any(len(r) != 12 for r in rows):
        raise ValueError('SBI telephone table layout changed')
    allowed = {'◎', '〇', '○', '△', '▲', '-', '−'}
    if any(v not in allowed for r in rows[1:] for v in r[2:]):
        raise ValueError('SBI unknown waiting-time symbol')
    legend = table.find_next_sibling('div')
    note = table.find_next_sibling('ul')
    legend_text = legend.get_text(' ', strip=True) if legend else ''
    note_text = note.get_text(' ', strip=True) if note else ''
    if '約5分' not in legend_text or '約30分' not in legend_text:
        raise ValueError('SBI legend missing or changed; review required')
    period = re.search(r'.{0,25}(?:基準|年\d{1,2}月).{0,65}', note_text)
    return {'tables': [{'title': '電話', 'headers': rows[0], 'rows': rows[1:]}],
            'legend': legend_text,
            'basis': period.group() if period else '公式表に具体的な集計期間の記載を確認できず',
            'note': note_text}


def parse_rakuten(body):
    data = json.loads(body)
    keys = [str(h) for h in range(8, 18)] + ['18～23']
    labels = [f'{h:02}:00' for h in range(8, 18)] + ['18:00～23:00']
    labels[0] = '08:30'
    names = {'1': '約5分', '2': '約15分', '3': '約30分〜', None: '−'}
    tables = []
    for kind, title in [('tel', '電話'), ('chat', 'オペレーターチャット')]:
        rows = []
        for day in ['平日平均', '土日平均']:
            values = data[kind][day]
            if not all(k in values for k in keys[:10]):
                raise ValueError('Rakuten required hours missing')
            row = [day]
            for k in keys:
                v = values.get(k)
                if v is not None:
                    v = str(v)
                if v not in names:
                    raise ValueError('Rakuten unknown waiting-time code')
                row.append(names[v])
            rows.append(row)
        tables.append({'title': title, 'headers': ['区分'] + labels, 'rows': rows})
    return {'tables': tables, 'legend': '約5分: つながりやすい / 約15分: 混雑 / 約30分〜: 非常に混雑 / −: サポート時間外',
            'basis': '直近の混雑状況（具体的な集計期間は記載なし）',
            'note': '土日は投資信託・NISAのみ。平日チャット18時以降も投資信託・NISAのみ。祝日・年末年始を除く。'}


def parse_monex(body):
    soup = BeautifulSoup(body, 'html.parser', from_encoding='shift_jis')
    table = next((t for t in soup.find_all('table') if '8:00' in t.get_text() and '16:00' in t.get_text()), None)
    if table is None:
        raise ValueError('Monex congestion table missing')
    rows = [[c.get_text(' ', strip=True) for c in tr.find_all(['th', 'td'], recursive=False)] for tr in table.find_all('tr')]
    if len(rows) < 6 or any(len(r) != 10 for r in rows[1:6]):
        raise ValueError('Monex table layout changed')
    if any(v not in {'◎', '○', '〇', '△'} for r in rows[1:6] for v in r[1:]):
        raise ValueError('Monex unknown symbol')
    text = soup.get_text(' ', strip=True)
    basis = re.search(r'受付状況は.{0,150}?基準に表示', text)
    if not basis:
        raise ValueError('Monex reference period missing')
    return {'tables': [{'title': '電話', 'headers': rows[0], 'rows': rows[1:6]}],
            'basis': basis.group(), 'legend': '◎ つながりやすい / ○ 比較的つながりやすい / △ 混雑',
            'note': '休日明けなどは混雑する場合があります。'}


def collect(company):
    _, source = SOURCES[company]
    if company == 'rakuten':
        url = 'https://www.rakuten-sec.co.jp/web/support/json/cs-congestion.json'
        body, meta = get(url)
        content = parse_rakuten(body)
        page, _ = get(source)
        # The UTF-8 page contains legacy bytes in unrelated lower sections.
        # Validate the selected section itself rather than reject the whole page.
        soup = BeautifulSoup(page.decode('utf-8', errors='replace'), 'html.parser')
        target = soup.find(id='tel-cs-table')
        if target is None:
            raise ValueError('Rakuten guidance section missing')
        section = target.find_parent('section')
        if section is None or '\ufffd' in section.get_text():
            raise ValueError('Rakuten guidance section encoding invalid')
        notes = [li.get_text(' ', strip=True) for li in section.select('ul li')]
        basis = [n for n in notes if any(k in n for k in ['直近', '基準', '平均'])]
        if not basis:
            raise ValueError('Rakuten reference note missing')
        content.update(basis=' '.join(basis), note=' '.join(notes))
        return content, [meta]
    body, meta = get(source)
    return (parse_sbi(body) if company == 'sbi' else parse_monex(body)), [meta]


def observe(previous, content=None, resources=None, error=None, now=None):
    """Failures preserve the last good state. Headers are not content changes."""
    now = now or datetime.now(JST).isoformat(timespec='seconds')
    state = dict(previous or {})
    state['checked_at'] = now
    if error:
        state.update(status='error', error=error)
        return state, {'at': now, 'status': 'error', 'error': error}
    fingerprint = digest(content)
    changed = bool(state.get('fingerprint') and fingerprint != state['fingerprint'])
    result = 'changed' if changed else ('unchanged' if state.get('fingerprint') else 'initial')
    state.update(status='ok', error=None, content=content, fingerprint=fingerprint,
                 resources=resources, last_success_at=now)
    if result in {'initial', 'changed'}:
        state['content_observed_since'] = now
    if changed:
        state['last_change_detected_at'] = now
    return state, {'at': now, 'status': result, 'fingerprint': fingerprint,
                   'resources': resources}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temp, path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', type=Path, default=OUT)
    args = ap.parse_args()
    out = args.output
    path = out / 'data.json'
    db = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'schema_version': 1, 'companies': {}, 'observations': []}
    now = datetime.now(JST).isoformat(timespec='seconds')
    results = {}
    for key, (name, url) in SOURCES.items():
        prev = db['companies'].get(key)
        try:
            content, resources = collect(key)
            state, event = observe(prev, content, resources, now=now)
            # Immutable, content-addressed versions allow historical comparison.
            write_json(out / 'versions' / key / (state['fingerprint'] + '.json'), content)
        except Exception as exc:
            state, event = observe(prev, error=f'{type(exc).__name__}: {exc}', now=now)
        state.update(name=name, source_url=url)
        db['companies'][key] = state
        results[key] = event
        print(f'{key}: {event["status"]}' + (f' ({event["error"]})' if 'error' in event else ''))
    db['observations'].append({'at': now, 'companies': results})
    db['updated'] = now
    write_json(path, db)
    # Partial failures must still be published and visible. Total failure is an
    # explicit observation too, never a successful empty-content replacement.
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
