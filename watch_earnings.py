"""注目銘柄リストの決算予定を1週間前・前日に通知する。"""
import argparse
from datetime import date, datetime
import importlib.util
import json
import msvcrt
from pathlib import Path
import sys
import time

import watch_notify as common

HOME = common.HOME.parent / 'KabulogWatchEarnings'
SOURCES_PATH = Path.home() / 'econ-calendar-bot' / 'sources.py'


def load_sources():
    spec = importlib.util.spec_from_file_location('earnings_sources', SOURCES_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def collect(items, today, source):
    events, status = [], []
    previous_loader = source.load_kessan_watch
    try:
        for index, item in enumerate(items):
            target = {'code': item['code'], 'name': item['name'], 'market': item.get('market', 'JP')}
            source.load_kessan_watch = lambda t=target: [t]
            try:
                rows = source.kessan(today=today)
                events.extend(dict(row, code=target['code'], market=target['market']) for row in rows)
                status.append(dict(target, status='scheduled' if rows else 'no_confirmed_date', events=len(rows)))
            except Exception as exc:
                status.append(dict(target, status='fetch_failed', error=type(exc).__name__))
            if index < len(items) - 1:
                time.sleep(0.4)
    finally:
        source.load_kessan_watch = previous_loader
    return events, status


def due_events(events, today):
    seen = set()
    for event in events:
        days = (date.fromisoformat(event['date']) - today).days
        if days not in (7, 1):
            continue
        key = f"earnings:{event['market']}:{event['code']}:{event['date']}:{days}"
        if key in seen:
            continue
        seen.add(key)
        label = '1週間前' if days == 7 else '前日'
        source_label = '日経の決算発表スケジュール' if event['market'] == 'JP' else 'Yahoo Finance（推定日を除外）'
        content = (f"株ログ・注目銘柄の決算通知【{label}】\n"
                   f"{event['code']} {event['name']}\n"
                   f"決算予定：{event['date']} {event.get('time', '')}（日本時間）\n"
                   f"{event.get('note', '')}\n取得元：{source_label}\n{common.PAGE_URL}")
        yield key, {'content': content, 'allowed_mentions': {'parse': []}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--as-of', type=date.fromisoformat)
    parser.add_argument('--list-file', type=Path)
    parser.add_argument('--setup', action='store_true')
    parser.add_argument('--test', action='store_true')
    args = parser.parse_args()
    if (args.as_of or args.list_file) and not args.dry_run:
        parser.error('--as-of / --list-file require --dry-run')
    common.HOME = HOME
    HOME.mkdir(parents=True, exist_ok=True)
    if args.setup:
        webhook = sys.stdin.read().strip()
        if not common.re.fullmatch(r'https://discord\.com/api/webhooks/\d+/[\w-]+', webhook):
            raise ValueError('Invalid webhook')
        # Read-only verification; do not log response fields or the URL.
        metadata = common.request(webhook)
        if not isinstance(metadata, dict) or not metadata.get('id'):
            raise ValueError('Webhook verification failed')
        (HOME / 'webhook.dpapi').write_bytes(common.credential(webhook.encode(), protect=True))
        common.log('Earnings credential verified and saved with DPAPI')
        return
    with (HOME / 'run.lock').open('a+b') as lock:
        lock.seek(0)
        if not lock.read(1):
            lock.write(b'0'); lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            common.log('SKIP another earnings run is active')
            return
        now = datetime.now(common.JST)
        today = args.as_of or now.date()
        data = (json.loads(args.list_file.read_text(encoding='utf-8')) if args.list_file else
                common.request(common.LIST_URL + '?v=' + str(int(now.timestamp()))))
        items = common.validate_list(data)
        if args.test:
            common.send({'content': f'株ログ「注目銘柄」の決算通知を設定しました。現在{len(items)}銘柄。公開リストの追加・削除に自動追従します。\n決算予定の1週間前・前日に通知。毎日7時・12時（日本時間）に確認し、同じ通知は1回だけ送信します。\n日本株は日経の予定表、米国株はYahoo Financeの推定でない日程を参照。取得失敗・日程未確認は予定を推測しません。', 'allowed_mentions': {'parse': []}}, 'earnings-setup-v1')
            return
        if not args.dry_run and now.hour < 7:
            common.log('SKIP before 07:00 JST')
            return
        events, status = collect(items, today, load_sources())
        due = list(due_events(events, today))
        common.save_json(HOME / 'preview.json', {'as_of': today.isoformat(), 'stocks': len(items),
                         'status': status, 'events': events, 'due': [{'key': k, 'payload': p} for k, p in due]})
        failures = sum(row['status'] == 'fetch_failed' for row in status)
        common.log(f'EARNINGS stocks={len(items)} events={len(events)} due={len(due)} failures={failures} dry_run={args.dry_run}')
        if not args.dry_run:
            for key, payload in due:
                common.send(payload, key)
        if failures:
            raise RuntimeError(f'{failures} earnings sources failed; see local preview.json')


if __name__ == '__main__':
    if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    try:
        main()
    except Exception as exc:
        common.HOME = HOME
        common.log(f'ERROR earnings: {type(exc).__name__}')
        raise SystemExit(1)
