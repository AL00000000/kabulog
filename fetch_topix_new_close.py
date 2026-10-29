# -*- coding: utf-8 -*-
"""TOPIX定期入替(2026/10/30反映)の新規追加35銘柄について、
入替前日 2026-10-29 の 15:24 → 15:30(大引け)の変化率と引けの出来高集中度を取る。

一度きりの調査用。売買代金上位200に入らない銘柄も含めて35銘柄すべてを取る。
  分足: https://kabutan.jp/stock/read?c={code}&m=4&k=1 (当日分のみ)
  日足: https://kabutan.jp/stock/read?c={code}&m=1&k=1 (前日終値・当日売買代金)

出力: docs/data_intraday/topix_new_YYYY-MM-DD.json
"""
import json
import sys
import time
import urllib.request
from pathlib import Path
from statistics import mean, median

import fetch_ranking as fr

BASE = Path(__file__).parent
OUT_DIR = BASE / "docs" / "data_intraday"
TARGET_DATE = "2026-10-29"

# 出典: JPX総研 2026/10/7公表 topix_j.pdf「(1)新規追加銘柄」
CODES = [
    ("1723", "スタンダード"), ("1965", "スタンダード"), ("2160", "グロース"),
    ("2702", "スタンダード"), ("2782", "スタンダード"), ("2805", "スタンダード"),
    ("4107", "スタンダード"), ("4478", "グロース"), ("4588", "グロース"),
    ("4816", "スタンダード"), ("4966", "スタンダード"), ("5161", "スタンダード"),
    ("6227", "スタンダード"), ("6366", "スタンダード"), ("6613", "グロース"),
    ("6736", "スタンダード"), ("6777", "スタンダード"), ("6834", "スタンダード"),
    ("6890", "スタンダード"), ("6960", "スタンダード"), ("7287", "スタンダード"),
    ("7564", "スタンダード"), ("7716", "スタンダード"), ("7806", "グロース"),
    ("7906", "スタンダード"), ("8117", "スタンダード"), ("8508", "スタンダード"),
    ("9436", "スタンダード"), ("141A", "グロース"), ("186A", "グロース"),
    ("215A", "グロース"), ("290A", "グロース"), ("485A", "グロース"),
    ("581A", "グロース"), ("593A", "グロース"),
]


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": fr.UA})
    for i in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as res:
                return res.read()
        except Exception:
            if i == 2:
                raise
            time.sleep(1.0 + i)


def divisor(header):
    return 100 if (len(header) > 1 and header[1] == "0") else 10


def minute(code):
    """{"HH:MM": (終値, 出来高)} と取引日、銘柄名。"""
    raw = get(f"https://kabutan.jp/stock/read?c={code}&m=4&k=1")
    lines = raw.decode("utf-8", "replace").strip().split("\n")
    header = lines[0].split(",")
    div = divisor(header)
    name = header[2] if len(header) > 2 else ""
    bars, td = {}, None
    for line in lines[1:]:
        p = line.split(",")
        if len(p) < 7 or "/" not in p[0]:
            continue
        bars[p[0].split("/")[1]] = (float(p[4]) / div, int(p[5] or 0))
        td = td or p[6].replace(".", "-")
    return td, name, bars


def daily(code):
    """[(YYYYMMDD, 終値, 出来高, 売買代金百万円)] 新しい順。"""
    raw = get(f"https://kabutan.jp/stock/read?c={code}&m=1&k=1")
    lines = raw.decode("utf-8", "replace").strip().split("\n")
    div = divisor(lines[0].split(","))
    rows = []
    for line in lines[1:3]:
        p = line.split(",")
        rows.append((p[0], float(p[4]) / div, int(p[5] or 0), float(p[6] or 0)))
    return rows


def main():
    ymd = TARGET_DATE.replace("-", "")
    stocks = []
    for code, market in CODES:
        td, name, bars = minute(code)
        time.sleep(0.3)
        d = daily(code)
        time.sleep(0.3)
        if td != TARGET_DATE:
            print(f"ERROR: {code} の分足が {td} (想定 {TARGET_DATE})。当日中に実行すること",
                  file=sys.stderr)
            sys.exit(1)
        p1524 = bars.get("15:24", (None, 0))[0]
        p1530, v1530 = bars.get("15:30", (None, 0))
        today = next((r for r in d if r[0] == ymd), None)
        prev = next((r for r in d if r[0] < ymd), None)
        pct = round((p1530 - p1524) / p1524 * 100, 4) if p1524 and p1530 is not None else None
        day_vol = today[2] if today else None
        stocks.append({
            "code": code, "name": name, "market": market,
            "prev": prev[1] if prev else None,
            "p1524": p1524, "p1530": p1530, "pct": pct,
            "change_pct": round((p1530 / prev[1] - 1) * 100, 4) if prev and p1530 else None,
            # 15:24時点の前日比。引けで上乗せされた分と切り分けるため
            "change1524_pct": round((p1524 / prev[1] - 1) * 100, 4) if prev and p1524 else None,
            "value": today[3] if today else None,            # 当日売買代金(百万円)
            "close_vol": v1530, "day_vol": day_vol,
            "close_share": round(v1530 / day_vol * 100, 2) if day_vol else None,
            "close_value": round(v1530 * p1530 / 1e6, 1) if p1530 else None,  # 引け約定代金(百万円)
        })
        print(code, name, pct, stocks[-1]["close_share"], file=sys.stderr)

    valid = [s for s in stocks if s["pct"] is not None]
    ps = [s["pct"] for s in valid]
    shares = [s["close_share"] for s in stocks if s["close_share"] is not None]
    payload = {
        "date": TARGET_DATE,
        "source": "JPX総研 2026/10/7公表「TOPIX初回定期入替」新規追加銘柄(10/30反映)",
        "count": len(stocks), "valid": len(valid),
        "mean": round(mean(ps), 4), "median": round(median(ps), 4),
        "up": sum(p > 0 for p in ps), "down": sum(p < 0 for p in ps), "flat": sum(p == 0 for p in ps),
        "close_share_median": round(median(shares), 2),
        "close_value_sum": round(sum(s["close_value"] or 0 for s in stocks), 1),
        "stocks": stocks,
    }
    out = OUT_DIR / f"topix_new_{TARGET_DATE}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(out)
    print(f"平均 {payload['mean']}% / 中央 {payload['median']}% / 上{payload['up']} 下{payload['down']} "
          f"変{payload['flat']} / 引け出来高比率 中央 {payload['close_share_median']}%", file=sys.stderr)


if __name__ == "__main__":
    main()
