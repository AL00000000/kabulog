# -*- coding: utf-8 -*-
"""松井アプリから読んだ日次の売買内訳を raw/<code>_<YYYY-MM>.json に足す(既存の日付は上書き)。

使い方(標準入力に1日1行):
  python add_jukyu_rows.py <code> <name> [--unit kabu|sen] < rows.txt
  行の形式: 日付 現物買 新規買 返済買 現物売 新規売 返済売 空売り 出来高
  --unit kabu … 株数で入力(売買分析タブの円グラフ下の数字。既定)。千株に直して保存する
  --unit sen  … 千株で入力(過去情報リストの数字)
保存前に 買い合計 = 売り合計 = 出来高 を検算し、ずれた行があれば何も書かずに止まる。
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(ROOT, "docs", "data_jukyu", "raw")
KEYS = ["gb", "kb", "hb", "gs", "ks", "hs", "ur", "vol"]


def main():
    args = sys.argv[1:]
    unit = "kabu"
    if "--unit" in args:
        i = args.index("--unit")
        unit = args[i + 1]
        del args[i:i + 2]
    code, name = args[0], args[1]
    div = 1000.0 if unit == "kabu" else 1.0
    rows, bad = [], []
    for line in sys.stdin:
        p = line.replace(",", "").split()
        if not p:
            continue
        if len(p) != 9:
            sys.exit(f"列数が9でない: {line.strip()}")
        v = [float(x) / div for x in p[1:]]
        r = {"date": p[0], **{k: round(x, 3) for k, x in zip(KEYS, v)}}
        buy = r["gb"] + r["kb"] + r["hb"]
        sell = r["gs"] + r["ks"] + r["hs"] + r["ur"]
        if max(abs(buy - r["vol"]), abs(sell - r["vol"])) > 1.0:
            bad.append(f"{p[0]}: 買-出来高={buy - r['vol']:+.1f} 売-出来高={sell - r['vol']:+.1f} 千株")
        rows.append(r)
    if bad:
        sys.exit("検算不一致(何も保存していません):\n" + "\n".join(bad))
    by_month = {}
    for r in rows:
        by_month.setdefault(r["date"][:7], []).append(r)
    for month, rs in sorted(by_month.items()):
        fn = os.path.join(RAW, f"{code}_{month}.json")
        if os.path.exists(fn):
            with open(fn, encoding="utf-8") as f:
                d = json.load(f)
        else:
            d = {"code": code, "name": name, "month": month, "unit": "千株", "rows": []}
        old = {r["date"]: r for r in d["rows"]}
        for r in rs:
            old[r["date"]] = r
        d["rows"] = sorted(old.values(), key=lambda r: r["date"])
        with open(fn, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        print(f"{os.path.basename(fn)}: {len(rs)}日を保存(計{len(d['rows'])}日)")


if __name__ == "__main__":
    main()
