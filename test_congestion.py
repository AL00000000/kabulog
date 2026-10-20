import copy
import json
import unittest

from fetch_congestion import observe, parse_rakuten, parse_sbi, parse_monex


class Observations(unittest.TestCase):
    def test_headers_are_not_content_changes_and_failures_keep_baseline(self):
        content = {'tables': [{'rows': [['約5分']]}], 'basis': '2026年10月'}
        first, event = observe(None, content, [{'last_modified': 'old'}], now='2026-10-20T00:00:00+09:00')
        self.assertEqual(event['status'], 'initial')
        same, event = observe(first, copy.deepcopy(content), [{'last_modified': 'new'}], now='2026-10-20T12:00:00+09:00')
        self.assertEqual(event['status'], 'unchanged')
        self.assertEqual(same['content_observed_since'], first['content_observed_since'])
        failed, event = observe(same, error='HTTP 403', now='2026-10-21T00:00:00+09:00')
        self.assertEqual(event['status'], 'error')
        self.assertEqual(failed['content'], content)
        self.assertEqual(failed['last_success_at'], same['last_success_at'])
        recovered, event = observe(failed, content, [], now='2026-10-21T12:00:00+09:00')
        self.assertEqual(event['status'], 'unchanged')
        self.assertIsNone(recovered['error'])
        changed = copy.deepcopy(content)
        changed['tables'][0]['rows'][0][0] = '約15分'
        new, event = observe(recovered, changed, [], now='2026-10-22T00:00:00+09:00')
        self.assertEqual(event['status'], 'changed')
        self.assertEqual(new['last_change_detected_at'], event['at'])
        _, event = observe(new, content, [], now='2026-10-22T12:00:00+09:00')
        self.assertEqual(event['status'], 'changed')  # A -> B -> A across observations
        changed = copy.deepcopy(content)
        changed['basis'] = '2026年11月'
        _, event = observe(first, changed, [], now='2026-11-01T00:00:00+09:00')
        self.assertEqual(event['status'], 'changed')

    def test_rakuten_validation_and_legend(self):
        days = {d: {str(h): str((h % 3) + 1) for h in range(8, 18)} for d in ['平日平均', '土日平均']}
        raw = {'tel': copy.deepcopy(days), 'chat': copy.deepcopy(days)}
        parsed = parse_rakuten(json.dumps(raw).encode())
        self.assertEqual(parsed['tables'][0]['rows'][0][1:4], ['約30分〜', '約5分', '約15分'])
        self.assertEqual(parsed['tables'][0]['rows'][0][-1], '−')
        raw['tel']['平日平均']['9'] = '4'
        with self.assertRaises(ValueError):
            parse_rakuten(json.dumps(raw).encode())
        with self.assertRaises((ValueError, KeyError)):
            parse_rakuten(b'{}')

    def test_missing_sbi_and_monex_tables_are_failures(self):
        with self.assertRaises(ValueError):
            parse_sbi(b'<html>Maintenance</html>')
        with self.assertRaises(ValueError):
            parse_monex(b'<html>Access denied</html>')


if __name__ == '__main__':
    unittest.main()
