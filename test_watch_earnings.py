from datetime import date
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import watch_earnings as earnings


class EarningsTests(unittest.TestCase):
    def event(self, day, market='JP'):
        return {'date': day, 'code': '3110', 'market': market, 'name': '決算 日東紡'}

    def test_exact_days_and_no_backfill(self):
        events = [self.event(f'2026-11-{n:02}') for n in (1, 2, 3, 8, 9)]
        due = list(earnings.due_events(events, date(2026, 11, 1)))
        self.assertEqual(len(due), 2)
        self.assertTrue(due[0][0].endswith(':1'))
        self.assertTrue(due[1][0].endswith(':7'))

    def test_duplicate_rows_and_market_identity(self):
        e = self.event('2026-11-08')
        due = list(earnings.due_events([e, e, self.event('2026-11-08', 'US')], date(2026, 11, 1)))
        self.assertEqual(len(due), 2)
        self.assertNotEqual(due[0][0], due[1][0])

    def test_partial_failure_is_visible_and_list_is_authoritative(self):
        source = SimpleNamespace(load_kessan_watch=lambda: [{'code': 'OLD'}])
        original = source.load_kessan_watch
        def fetch(today):
            code = source.load_kessan_watch()[0]['code']
            if code == 'FAIL':
                raise RuntimeError('offline')
            return [] if code == 'NONE' else [self.event('2026-11-08')]
        source.kessan = fetch
        items = [{'code': c, 'name': c} for c in ('3110', 'NONE', 'FAIL')]
        with patch.object(earnings.time, 'sleep'):
            events, statuses = earnings.collect(items, date(2026, 11, 1), source)
        self.assertEqual(len(events), 1)
        self.assertEqual([s['status'] for s in statuses], ['scheduled', 'no_confirmed_date', 'fetch_failed'])
        self.assertIs(source.load_kessan_watch, original)

    def test_same_event_deduplicates_across_daily_runs(self):
        event = self.event('2026-11-08')
        first = list(earnings.due_events([event], date(2026, 11, 1)))
        second = list(earnings.due_events([event], date(2026, 11, 1)))
        self.assertEqual(first, second)
        self.assertNotEqual(first[0][0], list(earnings.due_events([event], date(2026, 11, 7)))[0][0])


if __name__ == '__main__':
    unittest.main()
