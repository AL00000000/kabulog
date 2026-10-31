import json
import unittest
from pathlib import Path

from fetch_sox_history import records, preceding_events, analyse, validate


class SoxHistory(unittest.TestCase):
    def test_records_use_all_earlier_history_and_exclude_equal_highs(self):
        rows = [['2000-01-03', 10, 12], ['2000-01-04', 10, 13],
                ['2000-01-05', 9, 11], ['2000-02-07', 11, 14]]
        self.assertEqual([r['date'] for r in records(rows)], ['2000-02-07'])
        self.assertEqual(records(rows)[0]['previous_record'], 10)
        self.assertEqual(records(rows)[0]['gap_days'], 35)
        self.assertEqual(len(records(rows, 2)), 2)

    def test_no_future_same_day_or_price_derived_explanations(self):
        events = [{'id': 'before', 'date': '2026-06-01'}, {'id': 'same', 'date': '2026-06-23'},
                  {'id': 'future', 'date': '2026-06-24'}, {'id': 'old', 'date': '2026-05-01'},
                  {'id': 'derived', 'date': '2026-06-01', 'evidence': '価格データから算出'}]
        self.assertEqual(preceding_events('2026-06-23', events), ['before'])
        self.assertEqual(preceding_events('2026-06-23', events, 7), [])

    def test_weekend_after_close_and_incomplete_forward_window(self):
        rows = [['2026-10-16', 100, 101], ['2026-10-19', 102, 103], ['2026-10-20', 103, 104]]
        data = analyse(rows, [{'id': 'weekend', 'date': '2026-10-17'},
                              {'id': 'afterclose', 'date': '2026-10-16', 'market_date': '2026-10-19'},
                              {'id': 'future', 'date': '2026-10-21'}])
        a, b, c = data['events']
        self.assertEqual(a['plot_date'], '2026-10-19')
        self.assertEqual(b['plot_date'], '2026-10-19')
        self.assertEqual(a['sox_change_pct'], 2)
        self.assertIsNone(a['sox_5session_pct'])
        self.assertIsNone(c['plot_date'])

    def test_real_daily_coverage_source_links_and_breakout_consistency(self):
        folder = Path(__file__).parent / 'docs/data_sox'
        data = json.loads((folder / 'prices.json').read_text(encoding='utf-8'))
        registry = json.loads((folder / 'events.json').read_text(encoding='utf-8'))
        saved = json.loads((folder / 'analysis.json').read_text(encoding='utf-8'))
        validate(data['rows'])
        self.assertEqual(saved, analyse(data['rows'], registry['events']))
        self.assertEqual(len({e['id'] for e in registry['events']}), len(registry['events']))
        self.assertTrue(all(e['sources'] and all(s['url'].startswith('https://') for s in e['sources']) for e in registry['events']))
        # 2017 surpassing the 2000 record must not reset at a chart's year boundary.
        record = next(r for r in saved['records']['close'] if r['date'] == '2017-11-21')
        self.assertEqual(record['previous_record_date'], '2000-03-10')
        # User's Saturday news maps to Monday. The forward result stays null
        # until all five actual sessions exist, then uses their saved closes.
        event = next(e for e in saved['events'] if e['id'] == 'deepseek2026')
        self.assertEqual(event['plot_date'], '2026-10-19')
        i = next(i for i, row in enumerate(data['rows']) if row[0] == event['plot_date'])
        if i + 4 < len(data['rows']):
            expected = round((data['rows'][i + 4][1] / data['rows'][i - 1][1] - 1) * 100, 4)
            self.assertEqual(event['sox_5session_pct'], expected)
        else:
            self.assertIsNone(event['sox_5session_pct'])

    def test_drop_threshold_raw_return_and_announcement_availability(self):
        rows = [['2026-01-01', 100, 100], ['2026-01-02', 95, 97],
                ['2026-01-05', 90.25001, 96], ['2026-01-06', 80, 90]]
        events = [{'id': 'before', 'date': '2026-01-01'},
                  {'id': 'afterclose', 'date': '2026-01-02', 'market_date': '2026-01-05'},
                  {'id': 'future', 'date': '2026-01-07'}]
        drops = analyse(rows, events)['drops']
        self.assertEqual([d['date'] for d in drops], ['2026-01-02', '2026-01-06'])
        self.assertEqual(drops[0]['event_ids'], ['before'])
        self.assertEqual(drops[1]['event_ids'], ['afterclose'])
        self.assertEqual(drops[0]['change_pct'], -5)


if __name__ == '__main__':
    unittest.main()
