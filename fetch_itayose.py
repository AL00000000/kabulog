# -*- coding: utf-8 -*-
"""名前にGMOが入る上場銘柄の、板寄せ4回の出来高と売買代金を毎日記録する。

4回の取り方(株探の分足 /stock/read):
  open     … 前場で最初に出来高が付いた足。9:00とは限らない(気配のまま遅れて寄る銘柄がある)
  am_close … 11:30の足
  pm_open  … 後場で最初に出来高が付いた足。12:30とは限らない
  close    … 15:30の足

11:30と15:30は四本値が同値で、価格×出来高がそのまま売買代金になる。
寄りと後場寄りの足は同じ1分の連続約定が混ざり板寄せ分だけを分離できないので、
足の安値×出来高〜高値×出来高の幅で持つ。

m=4(1分足)は当日分しか返らない。取り逃した日は m=5(5分足、直近5営業日)から
11:30と15:30だけ埋める。5分足の9:00足は5分間の約定を含み1分足と混ぜられないので、
寄りと後場寄りは null のままにする。

出力: docs/data_itayose/data.json
  days[日付][コード] = {open, am_close, pm_open, close, day_vol}
  各値は [時刻, 出来高, 安値, 高値]。出来高が付かなければ null。
"""
import io
import json
import sys
import time
import unicodedata
import urllib.request
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook

BASE = Path(__file__).parent
OUT = BASE / "docs" / "data_itayose" / "data.json"

KEYWORD = "GMO"
JPX_URL = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xlsx"
READ_URL = "https://kabutan.jp/stock/read?c={code}&m={m}&k=1"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
SLEEP = 0.3
RETRY = 2
PRICE_DIV = 10   # 個別株の価格は全市場10倍で返る(指数のみ100倍)


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for i in range(RETRY + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception:
            if i == RETRY:
                raise
            time.sleep(2)


def fetch_symbols():
    """JPXの上場銘柄一覧から対象銘柄を抜く。全角・半角の表記ゆれは正規化して判定する。"""
    wb = load_workbook(io.BytesIO(get(JPX_URL)), read_only=True)
    rows = wb.worksheets[0].iter_rows(values_only=True)
    next(rows)
    out = []
    for r in rows:
        name = unicodedata.normalize("NFKC", str(r[2]))
        if KEYWORD in name.upper():
            market = unicodedata.normalize("NFKC", str(r[3])).split("(")[0]
            out.append({"code": str(r[1]), "name": name, "market": market})
    return out


def fetch_bars(code, m):
    """日付 -> [[時刻, 始, 高, 安, 終, 出来高], ...] を時刻昇順で返す。"""
    text = get(READ_URL.format(code=code, m=m)).decode("utf-8", "replace")
    days = {}
    for line in reversed(text.splitlines()[1:]):
        f = line.split(",")
        if len(f) < 7 or "/" not in f[0]:
            continue
        d = f[6].replace(".", "-")
        days.setdefault(d, []).append(
            [f[0].split("/")[1], *(int(x) / PRICE_DIV for x in f[1:5]), int(f[5])])
    return days


def cell(bar):
    if bar is None or bar[5] == 0:
        return None
    return [bar[0], bar[5], bar[3], bar[2]]


def at(bars, hm):
    return next((b for b in bars if b[0] == hm), None)


def first_trade(bars, start, end):
    """start〜end で最初に出来高が付いた足。"""
    return next((b for b in bars if start <= b[0] <= end and b[5] > 0), None)


def record_1min(bars):
    return {
        "open": cell(first_trade(bars, "09:00", "11:30")),
        "am_close": cell(at(bars, "11:30")),
        "pm_open": cell(first_trade(bars, "12:30", "15:30")),
        "close": cell(at(bars, "15:30")),
        "day_vol": sum(b[5] for b in bars),
    }


def record_5min(bars):
    return {
        "open": None,
        "am_close": cell(at(bars, "11:30")),
        "pm_open": None,
        "close": cell(at(bars, "15:30")),
        "day_vol": sum(b[5] for b in bars),
        "res5": True,
    }


def is_complete(day, bars, now):
    """場中に走っても途中の足を保存しない。"""
    if at(bars, "15:30") is None:
        return False
    return not (day == now.strftime("%Y-%m-%d") and now.strftime("%H:%M") < "15:35")


def main():
    data = {"updated": None, "symbols": [], "days": {}}
    if OUT.exists():
        data = json.loads(OUT.read_text(encoding="utf-8"))

    try:
        symbols = fetch_symbols()
    except Exception as e:
        # 銘柄一覧が取れなくても、前回の銘柄で記録は続ける
        print(f"WARN: JPX list failed, using saved symbols: {e}")
        symbols = data["symbols"]
    if not symbols:
        print("ERROR: no symbols", file=sys.stderr)
        return 1
    # 上場廃止や社名変更で一覧から消えた銘柄も、過去の記録の表示用に残す
    known = {s["code"]: s for s in data["symbols"]}
    known.update({s["code"]: s for s in symbols})
    data["symbols"] = sorted(known.values(), key=lambda s: s["code"])

    now = datetime.now()
    days = data["days"]
    changed = False
    failed = []
    for s in symbols:
        code = s["code"]
        try:
            one = fetch_bars(code, 4)
            time.sleep(SLEEP)
            five = fetch_bars(code, 5)
            time.sleep(SLEEP)
        except Exception as e:
            print(f"WARN: {code} failed: {e}")
            failed.append(code)
            continue
        for d, bars in one.items():
            cur = days.get(d, {}).get(code)
            if is_complete(d, bars, now) and (cur is None or cur.get("res5")):
                days.setdefault(d, {})[code] = record_1min(bars)
                changed = True
        for d, bars in five.items():
            if code not in days.get(d, {}) and is_complete(d, bars, now):
                days.setdefault(d, {})[code] = record_5min(bars)
                changed = True

    if failed and len(failed) == len(symbols):
        print("ERROR: all symbols failed", file=sys.stderr)
        return 1

    if changed:
        # NEWバッジの判定に使うので、新しいデータが入ったときだけ進める
        data["updated"] = now.strftime("%Y-%m-%d %H:%M")
        data["days"] = dict(sorted(days.items()))
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"symbols={len(symbols)} days={len(days)} changed={changed} failed={failed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
