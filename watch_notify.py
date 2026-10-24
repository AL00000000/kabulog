"""株ログの注目銘柄をDiscordへ通知。秘密・状態はPC内のDPAPI保存先だけに置く。"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import ctypes
from ctypes import wintypes
from datetime import date, datetime, timedelta, timezone
import json
import math
import msvcrt
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request

JST = timezone(timedelta(hours=9))
HOME = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'KabulogWatchNotify'
LIST_URL = 'https://al00000000.github.io/kabulog/data_personal/bottom-up.json'
PAGE_URL = 'https://al00000000.github.io/kabulog/#bottomup'


class Blob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]


def credential(data, protect=False):
    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source, target = Blob(len(data), buffer), Blob()
    method = ctypes.windll.crypt32.CryptProtectData if protect else ctypes.windll.crypt32.CryptUnprotectData
    if not method(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise RuntimeError('DPAPI failed')
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        ctypes.windll.kernel32.LocalFree(target.data)


def request(url, payload=None):
    headers = {'User-Agent': 'Mozilla/5.0 KabulogWatch/1.0', 'Cache-Control': 'no-cache'}
    if payload is not None:
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=payload, headers=headers)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=30) as response:
            data = response.read()
            return json.loads(data) if data else None
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f'HTTP {exc.code}') from None
    except Exception as exc:
        # Never print a URL or underlying exception containing a webhook token.
        raise RuntimeError(f'Network error: {type(exc).__name__}') from None


def positive(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def validate_list(data):
    items = data.get('items')
    if not isinstance(items, list) or not items:
        raise ValueError('Watch list is empty or invalid')
    seen = set()
    for item in items:
        if not isinstance(item.get('name'), str) or not item['name'].strip():
            raise ValueError('Invalid stock name')
        code = item.get('code', '')
        if code and not re.fullmatch(r'[0-9A-Z]{4}', code):
            raise ValueError('Invalid Japanese security code')
        key = code or item['name']
        if key in seen:
            raise ValueError('Duplicate stock')
        seen.add(key)
    return items


def parse_chart(data, code, target):
    result = data.get('chart', {}).get('result')
    if not result:
        raise ValueError('No price series')
    result = result[0]
    meta = result.get('meta', {})
    if meta.get('symbol') != code + '.T' or meta.get('exchangeTimezoneName') != 'Asia/Tokyo':
        raise ValueError('Wrong stock or exchange')
    quotes = result['indicators']['quote'][0]
    rows = {}
    for i, timestamp in enumerate(result.get('timestamp', [])):
        day = datetime.fromtimestamp(timestamp, JST).date()
        if day > target:
            continue
        opening, closing = quotes['open'][i], quotes['close'][i]
        if positive(opening) and positive(closing):
            rows[day] = {'open': opening, 'close': closing}
    return rows


def fetch_rows(item, target):
    code = item.get('code')
    if not code:
        return {}, '証券コード未登録'
    if item.get('listed_from') and target < date.fromisoformat(item['listed_from']):
        return {}, f"上場前（{item['listed_from']}予定）"
    try:
        data = request(f'https://query1.finance.yahoo.com/v8/finance/chart/{code}.T?range=3mo&interval=1d')
        return parse_chart(data, code, target), None
    except Exception as exc:
        return {}, f'価格取得失敗（{type(exc).__name__}）'


def change(rows, target, mode):
    current = rows.get(target)
    if not current:
        return None, '当日の価格なし（休場・未取得等）'
    if mode == 'weekly':
        previous_day = target - timedelta(days=7)
        previous = rows.get(previous_day)
        if not previous:
            return None, '前週水曜日の始値なし（休場・上場前・未取得等）'
        return (current['open'] / previous['open'] - 1) * 100, None
    earlier = sorted(day for day in rows if day < target)
    if not earlier:
        return None, '前営業日の終値なし'
    previous_day = earlier[-1]
    # A stale/missing run of prices must not be presented as a one-day return.
    if (target - previous_day).days > 7:
        return None, '前営業日の価格を確認できず'
    return (current['close'] / rows[previous_day]['close'] - 1) * 100, None


def build_report(items, results, target, mode):
    lines, values = [], []
    for item, (rows, error) in zip(items, results):
        value, reason = (None, error) if error else change(rows, target, mode)
        # Plain labels plus allowed_mentions prevent mention injection.
        name = item['name'].replace('\n', ' ')[:90]
        label = f"{name}（{item['code']}）" if item.get('code') else name
        lines.append(f'{label}：{value:+.2f}%' if value is not None else f'{label}：算出不可 — {reason}')
        if value is not None:
            values.append(value)
    if mode == 'weekly':
        title = f'株ログ 注目銘柄｜1週間騰落率 {target.isoformat()}'
        footer = f'{(target-timedelta(days=7)).isoformat()} 水曜始値 → {target.isoformat()} 水曜始値。休場時は別日に置換しません。'
    else:
        title = f'株ログ 注目銘柄｜1日騰落率 {target.isoformat()}'
        footer = '前営業日終値 → 当日終値。配当再投資を含まない価格騰落率。'
    # Discord embed description limit is 4096. Split large future lists safely.
    pages, page = [], ''
    for line in lines:
        if len(page) + len(line) + 1 > 3500:
            pages.append(page)
            page = ''
        page += line + '\n'
    if page:
        pages.append(page)
    embeds = [{'title': title if i == 0 else title+'（続き）', 'description': text,
               'url': PAGE_URL, 'color': 0x36BDB7,
               'footer': {'text': footer+' 取得元：Yahoo Finance（日足・株式分割調整済み価格）'}} for i, text in enumerate(pages)]
    if len(embeds) > 10 or sum(len(e['description'])+len(e['title'])+len(e['footer']['text']) for e in embeds) > 5900:
        raise ValueError('Watch list exceeds a single Discord message; review required')
    return {'allowed_mentions': {'parse': []}, 'embeds': embeds}, len(values)


def save_json(path, data):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def log(message):
    HOME.mkdir(parents=True, exist_ok=True)
    line = datetime.now(JST).isoformat(timespec='seconds')+' '+message
    with (HOME/'monitor.log').open('a', encoding='utf-8') as file:
        file.write(line+'\n')
    if sys.stdout:
        print(line)


def send(payload, key):
    state_path = HOME/'state.json'
    state = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {}
    if key in state:
        log(f'SKIP already handled: {key} ({state[key]["status"]})')
        return False
    webhook = credential((HOME/'webhook.dpapi').read_bytes()).decode('utf-8')
    state[key] = {'status': 'pending', 'at': datetime.now(JST).isoformat()}
    save_json(state_path, state)
    try:
        result = request(webhook+'?wait=true', json.dumps(payload, ensure_ascii=False).encode('utf-8'))
        if not isinstance(result, dict) or not result.get('id'):
            raise RuntimeError('Discord acknowledgement missing')
    except Exception:
        # Unknown delivery outcome: do not auto-resend and cause duplicates.
        log('ERROR Discord delivery uncertain; pending record retained for review')
        raise
    state[key] = {'status': 'sent', 'at': datetime.now(JST).isoformat(), 'message_id': result['id']}
    save_json(state_path, state)
    log('SENT '+key)
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['daily', 'weekly', 'setup', 'test'])
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--as-of', type=date.fromisoformat)
    args = parser.parse_args()
    HOME.mkdir(parents=True, exist_ok=True)
    if args.mode == 'setup':
        webhook = sys.stdin.read().strip()
        if not re.fullmatch(r'https://discord\.com/api/webhooks/\d+/[\w-]+', webhook):
            raise ValueError('Invalid Discord webhook')
        (HOME/'webhook.dpapi').write_bytes(credential(webhook.encode('utf-8'), protect=True))
        log('Discord credential saved with user DPAPI')
        return
    with (HOME/'run.lock').open('a+b') as lock:
        lock.seek(0)
        if lock.read(1) == b'':
            lock.write(b'0'); lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            log('SKIP another execution is running')
            return
        if args.mode == 'test':
            send({'content': '株ログ「注目銘柄」の通知設定テストです。\n毎週水曜12:00：前週水曜始値→今週水曜始値の1週間騰落率\n毎営業日17:10：前営業日終値→当日終値の1日騰落率\n公開中の注目銘柄リスト全件を毎回読み込みます。上場前・価格不足は算出不可と表示します。', 'allowed_mentions': {'parse': []}}, 'setup-test-v1')
            return
        if args.as_of and not args.dry_run:
            raise ValueError('--as-of is available only with --dry-run')
        now = datetime.now(JST)
        target = args.as_of or now.date()
        if args.mode == 'weekly' and target.weekday() != 2:
            log('SKIP not Wednesday'); return
        if args.mode == 'daily' and target.weekday() >= 5:
            log('SKIP weekend'); return
        if not args.dry_run:
            minimum = (12, 0) if args.mode == 'weekly' else (17, 10)
            if (now.hour, now.minute) < minimum:
                log('SKIP before scheduled time'); return
        key = args.mode+':'+target.isoformat()
        state_path = HOME/'state.json'
        state = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {}
        if not args.dry_run and key in state:
            log('SKIP already handled '+key); return
        items = validate_list(request(LIST_URL+'?v='+str(int(now.timestamp()))))
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(lambda item: fetch_rows(item, target), items))
        payload, valid = build_report(items, results, target, args.mode)
        # Old quotes on a holiday are not today's performance. Do not backfill.
        has_today = any(target in rows for rows, error in results)
        has_history = any(rows for rows, error in results)
        if args.mode == 'daily' and not has_today and has_history and not args.dry_run:
            log('SKIP no current-day prices (holiday or stale provider)'); return
        if args.dry_run:
            save_json(HOME/('preview-'+args.mode+'.json'), payload)
            log(f'PREVIEW {key} stocks={len(items)} calculated={valid}; not sent')
        else:
            send(payload, key)


if __name__ == '__main__':
    try:
        if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
        main()
    except Exception as exc:
        log(f'ERROR {type(exc).__name__}: {exc}')
        raise SystemExit(1)
