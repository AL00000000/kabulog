# -*- coding: utf-8 -*-
"""「空売り5日集計」タブ用の docs/data_karauri5/analysis.json を生成する。

指標⑤(売残ネット ÷ 発行済, %)を 5営業日の窓ごとに集計する。
  売残ネット = 空売り + 新規売 − 返済買
生データは信用需給分析と共通の docs/data_jukyu/raw/<code>_<YYYY-MM>.json(千株)。
日次検算と指標の式は build_jukyu.py のものをそのまま使う(ここで再実装しない)。

使い方:
  python build_karauri5.py           … 検算して analysis.json を書き出す
  python build_karauri5.py --check   … 検算と欠けている日の一覧だけ
"""
import argparse
import json
import os
import sys

import build_jukyu as bj

OUT = os.path.join(bj.ROOT, "docs", "data_karauri5", "analysis.json")

# 窓は 2026-11-26 にユーザー指定(各5営業日。祝日は docs/holidays.json で除外済みの日付を直書き)
WINDOWS = [
    {"key": "may_end", "label": "5月末の5営業日",
     "dates": ["2026-05-25", "2026-05-26", "2026-05-27", "2026-05-28", "2026-05-29"]},
    {"key": "pre_0623", "label": "6/23以前の5営業日",
     "dates": ["2026-06-17", "2026-06-18", "2026-06-19", "2026-06-22", "2026-06-23"]},
    {"key": "oct_start", "label": "10/1からの5営業日",
     "dates": ["2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06", "2026-10-07"]},
    # 2026-11-26 追加(ユーザー命名。音声入力「JT 寄ってからご営業日」を「5営業日」と解釈)
    {"key": "jt_yori", "label": "JT寄ってから5営業日",
     "dates": ["2026-11-10", "2026-11-11", "2026-11-12", "2026-11-13", "2026-11-16"]},
    {"key": "latest", "label": "最新の5営業日",
     "dates": ["2026-11-19", "2026-11-20", "2026-11-24", "2026-11-25", "2026-11-26"]},
]

# 表示順 = 調べる順(キオクシア → JT → 直近1週間の売買代金順)
# 対象: 2026-11-19〜26 の売買代金(株探ランキング 15:24時点値)の5日合計 上位10 + JT
CODES = ["285A", "2914", "6857", "9984", "8035", "6920", "1570", "6976", "5803", "4062", "6981",
         # 2026-11-26 追加(ユーザー指定)
         "3110", "278A", "4588", "6532", "4478", "593A"]

# 松井アプリは過去の出来高を株式分割で遡って調整して表示する(2026-11-26確認: キオクシア6/23が8月読取値のちょうど3倍)。
# 8月に読んだ raw(分割前)を今日読んだ値(分割調整済み)と揃えるための倍率。キーは (コード, 月ファイル)
SPLIT_ADJ = {("285A", "2026-06"): 3, ("8035", "2026-06"): 5, ("278A", "2026-06"): 2}  # テラドローン6/1が8月値のちょうど2倍
# ⑤の分母は現在の発行済株式数(分割後)。stocks.json は信用需給分析タブ(分割前データ)と共用なので書き換えず、ここで上書きする
SHARES_NOW = {"278A": 21640000, "285A": 1646577342, "8035": 2340163665, "9984": 5711848120, "6976": 137564793}
SHARES_NOW_ASOF = "2026-11-26（株探）"

SELECTION_NOTE = ("2026-11-19〜11-26(5営業日)の売買代金合計の上位10銘柄 + JT(ここまで売買代金順)、"
                  "続いて個別指定の日東紡・テラドローン・オンコリス・ベイカレント・フリー・ティアフォー。"
                  "売買代金は株探ランキング(15:24時点の値)を合計したもので、引け値ではない")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    master, by_code = bj.load_master()
    rows = {}            # (code, date) → row
    errors, warns = [], []
    for fn, d in bj.load_raw():
        if d["code"] not in CODES:
            continue
        f = SPLIT_ADJ.get((d["code"], d["month"]), 1)
        for r in d["rows"]:
            if f != 1:
                r = {**r, **{k: r[k] * f for k in bj.FIELDS}}
            db, ds = bj.check_day(r)
            db, ds = db / f, ds / f   # 丸め誤差は元の読み取り単位で判定する(倍率を掛けた分だけ膨らむため)
            if max(db, ds) > bj.TOL:
                errors.append(f"{fn} {r['date']}: 検算不一致 買-出来高={db:+.1f} 売-出来高={ds:+.1f} 千株")
            elif max(db, ds) > 0.05:
                warns.append(f"{fn} {r['date']}: 検算 {max(db, ds):.1f}千株ずれ(丸め誤差の範囲)")
            rows[(d["code"], r["date"])] = r

    stocks, missing = [], []
    for code in CODES:
        st = by_code.get(code)
        if st is None:
            missing.append(f"{code}: stocks.json に無い(発行済株式数を追加すること)")
            continue
        shares = SHARES_NOW.get(code, st["shares"])
        shares_man = bj.r1(shares / 10000.0)
        e = {"code": code, "name": st["name"], "market": st["market"],
             "shares": shares, "shares_man": shares_man,
             "shares_asof": SHARES_NOW_ASOF if code in SHARES_NOW else st.get("shares_asof", master["shares_asof"]),
             "w": {}}
        for w in WINDOWS:
            got = [rows[(code, dt)] for dt in w["dates"] if (code, dt) in rows]
            lack = [dt for dt in w["dates"] if (code, dt) not in rows]
            if lack:
                missing.append(f"{code} {st['name']} {w['label']}: 未取得 {', '.join(lack)}")
            if not got:
                continue
            tot = {k: sum(r[k] for r in got) for k in bj.FIELDS}
            m = bj.metrics(tot, len(got), [got[0]["date"], got[-1]["date"]],
                           shares_man, f"{code} {w['key']}", errors)
            e["w"][w["key"]] = {
                "days": len(got), "complete": not lack,
                "un": m["un"], "i5": m["i5"], "vol": m["vol"],
                # 内訳(万株)
                "ur": bj.r1(tot["ur"] / 10), "ks": bj.r1(tot["ks"] / 10), "hb": bj.r1(tot["hb"] / 10),
                "ur_pct": bj.r1(tot["ur"] / tot["vol"] * 100) if tot["vol"] else None,  # 空売り ÷ 出来高
            }
        stocks.append(e)

    for w in sorted(set(warns)):
        print("WARN " + w)
    for x in missing:
        print("MISSING " + x)
    if errors:
        for x in sorted(set(errors)):
            print("ERROR " + x)
        sys.exit(f"検算エラー {len(set(errors))}件。書き出していません")
    if args.check:
        print("--check のため書き出しませんでした")
        return

    generated = None
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            old = json.load(f)
        generated = old.get("generated")
    import datetime as _d
    out = {"generated": generated, "windows": WINDOWS, "selection": SELECTION_NOTE,
           "source": master["source"], "stocks": stocks}
    if generated is None or old_differs(out):
        out["generated"] = _d.date.today().isoformat()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {OUT} ({len(stocks)}銘柄)")


def old_differs(out):
    """データの中身が変わったときだけ generated を進める(NEWバッジ誤爆防止)"""
    if not os.path.exists(OUT):
        return True
    with open(OUT, encoding="utf-8") as f:
        old = json.load(f)
    return old.get("stocks") != out["stocks"]


if __name__ == "__main__":
    main()
