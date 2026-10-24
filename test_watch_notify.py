import unittest
from unittest.mock import patch
import tempfile
import json
from pathlib import Path
from datetime import date, datetime
import watch_notify as watch


class ReturnTests(unittest.TestCase):
    def test_weekly_uses_wednesday_open_not_close(self):
        target=date(2026,10,21)
        rows={date(2026,10,14):{'open':100,'close':999},target:{'open':110,'close':1}}
        rate,error=watch.change(rows,target,'weekly')
        self.assertAlmostEqual(rate,10)
        self.assertIsNone(error)

    def test_holiday_does_not_shift_to_tuesday(self):
        rows={date(2026,10,13):{'open':100,'close':100},date(2026,10,21):{'open':120,'close':120}}
        rate,error=watch.change(rows,date(2026,10,21),'weekly')
        self.assertIsNone(rate)
        self.assertIn('前週水曜日',error)

    def test_daily_uses_previous_trading_day(self):
        rows={date(2026,10,16):{'open':1,'close':200},date(2026,10,19):{'open':500,'close':220}}
        self.assertAlmostEqual(watch.change(rows,date(2026,10,19),'daily')[0],10)

    def test_stale_current_quote_not_used(self):
        self.assertIsNone(watch.change({date(2026,10,22):{'open':100,'close':100}},date(2026,10,23),'daily')[0])

    def test_pending_listed_stock_is_retained(self):
        item={'name':'未上場の銘柄','code':'652A','listed_from':'2026-10-30'}
        rows,error=watch.fetch_rows(item,date(2026,10,24))
        self.assertFalse(rows)
        payload,valid=watch.build_report([item],[(rows,error)],date(2026,10,24),'daily')
        self.assertEqual(valid,0)
        self.assertIn('上場前',payload['embeds'][0]['description'])

    def test_invalid_or_duplicate_list_rejected(self):
        for items in [[{'name':'a','code':'../x'}],[{'name':'a','code':'285A'},{'name':'b','code':'285A'}],[]]:
            with self.assertRaises(ValueError):watch.validate_list({'items':items})

    def test_chart_rejects_wrong_symbol(self):
        with self.assertRaises(ValueError):watch.parse_chart({'chart':{'result':[{'meta':{'symbol':'OTHER','exchangeTimezoneName':'Asia/Tokyo'}}]}},'285A',date(2026,10,24))

    def test_us_weekly_uses_tuesday_not_wednesday(self):
        target=date(2026,10,21)
        rows={date(2026,10,13):{'open':100,'close':50},date(2026,10,20):{'open':125,'close':300},date(2026,10,14):{'open':20,'close':20},target:{'open':10,'close':10}}
        item={'name':'Qualys','code':'QLYS','market':'US'}
        payload,count=watch.build_report([item],[(rows,None)],target,'weekly')
        self.assertEqual(count,1)
        self.assertIn('+25.00%',payload['embeds'][0]['description'])
        self.assertIn('2026-10-20',payload['embeds'][0]['description'])

    def test_us_daily_uses_previous_local_date(self):
        item={'name':'Qualys','code':'QLYS','market':'US'}
        rows={date(2026,10,22):{'open':1,'close':100},date(2026,10,23):{'open':1,'close':110}}
        payload,count=watch.build_report([item],[(rows,None)],date(2026,10,24),'daily')
        self.assertEqual(count,1)
        self.assertIn('+10.00%',payload['embeds'][0]['description'])

    def test_us_bars_use_exchange_date_across_dst(self):
        data={'chart':{'result':[{'meta':{'symbol':'QLYS','exchangeTimezoneName':'America/New_York','gmtoffset':-18000},'timestamp':[int(datetime.fromisoformat('2026-10-20T13:30:00+00:00').timestamp())],'indicators':{'quote':[{'open':[100],'close':[110]}]}}]}}
        self.assertIn(date(2026,10,20),watch.parse_chart(data,'QLYS',date(2026,10,21),'US'))

    def test_acknowledged_notification_not_sent_twice(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(watch,'HOME',Path(temp)), patch.object(watch,'credential',return_value=b'https://discord.com/api/webhooks/test'), patch.object(watch,'request',return_value={'id':'test-id'}) as request:
            (Path(temp)/'webhook.dpapi').write_bytes(b'encrypted-placeholder')
            self.assertTrue(watch.send({'content':'test'},'daily:test'))
            self.assertFalse(watch.send({'content':'test'},'daily:test'))
            self.assertEqual(request.call_count,1)

    def test_uncertain_delivery_not_automatically_repeated(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(watch,'HOME',Path(temp)), patch.object(watch,'credential',return_value=b'https://discord.com/api/webhooks/test'), patch.object(watch,'request',side_effect=RuntimeError('timeout')) as request:
            (Path(temp)/'webhook.dpapi').write_bytes(b'encrypted-placeholder')
            with self.assertRaises(RuntimeError):watch.send({'content':'test'},'weekly:test')
            state=json.loads((Path(temp)/'state.json').read_text(encoding='utf-8'))
            self.assertEqual(state['weekly:test']['status'],'pending')
            self.assertFalse(watch.send({'content':'test'},'weekly:test'))
            self.assertEqual(request.call_count,1)


if __name__=='__main__':unittest.main()
