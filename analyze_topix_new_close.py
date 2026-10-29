# -*- coding: utf-8 -*-
"""TOPIX新規追加35銘柄の 10/29 15:24→引け 変化率が、何で説明できるかを調べる。

仮説: 普段の売買代金に対して指数買いの額が大きい銘柄ほど、引けで値が飛ぶ。

説明変数(すべて当日の引けより前に分かる値か、引けの約定そのもの)
  demand_days  … 推定浮動株時価総額(10/28時点) ÷ 過去20営業日の売買代金中央値
                 = 「浮動株を全部買うと普段の何日分か」。指数買いの額は浮動株時価総額 ×
                 パッシブ比率(全銘柄共通の定数)なので、順位相関はこの比と同じになる
  close_mult   … 10/29の引け約定代金 ÷ 過去20営業日の売買代金中央値(実際に引けで出た量)
  runup        … 公表前日 10/6 終値 → 10/28 終値 の騰落率から同期間のTOPIXを引いた値(先回り)
  r5           … 直近5営業日 10/21 終値 → 10/28 終値 の騰落率
  r5x          … r5 から同期間の市場指数(スタンダード=TOPIX、グロース=グロース250)を引いた値
  r5_1524      … 10/21 終値 → 10/29 15:24 の騰落率(当日の引け直前まで含めた5営業日)
  chg1524      … 15:24時点の前日比(当日のザラ場で既に動いていた分)
  float_oku    … 推定浮動株時価総額(億円、サイズ)
  growth       … グロース市場なら1
  vol          … 過去20営業日の日次リターンの標準偏差(%)
目的変数は pct(15:24→引け)と、市場全体の引けの動きを引いた excess
(スタンダード銘柄はTOPIX、グロース銘柄はグロース250の同時間帯の変化率を引く)。

浮動株時価総額は data_topix/summary.json の推計(8月平均ベース、JPX公表値でなく
誤差±20%程度)を、8/31終値 → 10/28終値 の株価変化で引き直したもの。

出力: docs/data_intraday/topix_new_2026-10-29_analysis.json
"""
import json
import math
import time
import urllib.request
from pathlib import Path
from statistics import mean, median

import fetch_ranking as fr

BASE = Path(__file__).parent
D = BASE / "docs" / "data_intraday"
DATE = "2026-10-29"
ANNOUNCE_PREV = "20261006"   # 公表(10/7)の前営業日
PREV = "20261028"
FIVE_AGO = "20261021"        # 10/28 から5営業日前


def daily(code):
    url = f"https://kabutan.jp/stock/read?c={code}&m=1&k=1"
    req = urllib.request.Request(url, headers={"User-Agent": fr.UA})
    for i in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                text = r.read().decode("utf-8", "replace")
            break
        except Exception:
            if i == 2:
                raise
            time.sleep(1 + i)
    lines = text.strip().split("\n")
    div = 100 if lines[0].split(",")[1] == "0" else 10
    rows = {}
    for ln in lines[1:200]:
        p = ln.split(",")
        if len(p) < 7 or not p[4]:
            continue
        rows[p[0]] = (float(p[4]) / div, float(p[6] or 0))  # 終値, 売買代金(百万円)
    return rows


def index_close_move(code):
    """指数の 15:24→15:30 変化率(%)。"""
    import fetch_intraday as fi
    td, cl = fi.fetch_read(code)
    assert td == DATE, (code, td)
    return (cl["15:30"] / cl["15:24"] - 1) * 100


def rank(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def pearson(x, y):
    mx, my = mean(x), mean(y)
    sx = math.sqrt(sum((a - mx) ** 2 for a in x))
    sy = math.sqrt(sum((b - my) ** 2 for b in y))
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy)


def spearman(x, y):
    return pearson(rank(x), rank(y))


def perm_p(x, y, n=20000, seed=1):
    """スピアマン相関の並べ替え検定(両側)。n=35と小さいので正規近似に頼らない。"""
    import random
    rnd = random.Random(seed)
    obs = abs(spearman(x, y))
    rx, ry = rank(x), rank(y)
    hit = 0
    for _ in range(n):
        ry2 = ry[:]
        rnd.shuffle(ry2)
        if abs(pearson(rx, ry2)) >= obs - 1e-12:
            hit += 1
    return hit / n


def main():
    base = json.loads((D / f"topix_new_{DATE}.json").read_text(encoding="utf-8"))
    est = {a["code"]: a for a in json.loads(
        (BASE / "docs" / "data_topix" / "summary.json").read_text(encoding="utf-8"))["added"]}

    topix = daily("0010")
    topix_ret = topix[PREV][0] / topix[ANNOUNCE_PREV][0] - 1
    growth = daily("0012")
    r5_bench = {"スタンダード": (topix[PREV][0] / topix[FIVE_AGO][0] - 1) * 100,
                "グロース": (growth[PREV][0] / growth[FIVE_AGO][0] - 1) * 100}
    time.sleep(0.3)

    bench = {"スタンダード": index_close_move("0010"), "グロース": index_close_move("0012")}

    ymd = DATE.replace("-", "")
    rows = []
    for s in base["stocks"]:
        dd = daily(s["code"])
        time.sleep(0.3)
        hist = sorted((k for k in dd if k < ymd), reverse=True)[:20]
        adv = median(dd[k][1] for k in hist)
        e = est[s["code"]]
        float_now = e["float_mktcap"] * dd[PREV][0] / e["close"] / 1e6  # 百万円
        pre = dd.get(ANNOUNCE_PREV)
        cl = [dd[k][0] for k in sorted((k for k in dd if k < ymd), reverse=True)[:21]]
        vol = (sum((math.log(cl[i] / cl[i + 1])) ** 2 for i in range(20)) / 20
               - (sum(math.log(cl[i] / cl[i + 1]) for i in range(20)) / 20) ** 2) ** 0.5 * 100
        runup = (dd[PREV][0] / pre[0] - 1 - topix_ret) * 100 if pre else None
        rows.append({
            "code": s["code"], "name": s["name"], "market": s["market"],
            "pct": s["pct"], "excess": round(s["pct"] - bench[s["market"]], 4),
            "chg1524": s["change1524_pct"], "vol": round(vol, 2),
            "adv": round(adv, 1), "float_oku": round(float_now / 100, 1),
            "demand_days": round(float_now / adv, 1),
            "close_mult": round(s["close_value"] / adv, 2),
            "runup": round(runup, 2) if runup is not None else None,
            "r5": round((dd[PREV][0] / dd[FIVE_AGO][0] - 1) * 100, 2),
            "r5x": round((dd[PREV][0] / dd[FIVE_AGO][0] - 1) * 100 - r5_bench[s["market"]], 2),
            "r5_1524": round((s["p1524"] / dd[FIVE_AGO][0] - 1) * 100, 2),
            "growth": 1 if s["market"] == "グロース" else 0,
            # 引けの超過約定(平常の引けを1日の売買代金の10%と置いた差)÷浮動株 = 実質のパッシブ比率の目安
            "implied_passive": round((s["close_value"] - 0.1 * adv) / float_now * 100, 2),
        })
        print(s["code"], rows[-1]["demand_days"], rows[-1]["close_mult"], rows[-1]["runup"])

    tests = []
    for key, label in [
        ("demand_days", "推定指数買い ÷ 普段の売買代金(浮動株時価総額 ÷ 20日売買代金中央値)"),
        ("close_mult", "引け約定代金 ÷ 普段の売買代金"),
        ("runup", "公表前日→10/28 の対TOPIX騰落率(先回り)"),
        ("r5", "直近5営業日騰落率(10/21→10/28)"),
        ("r5x", "直近5営業日騰落率の市場指数比(10/21→10/28)"),
        ("r5_1524", "10/21終値→10/29 15:24の騰落率"),
        ("chg1524", "15:24時点の前日比"),
        ("float_oku", "推定浮動株時価総額(サイズ)"),
        ("adv", "普段の売買代金(20日中央値)"),
        ("growth", "グロース市場ダミー"),
        ("vol", "ボラティリティ(20日)"),
    ]:
        t = {"key": key, "label": label}
        for yk in ("pct", "excess"):
            ok = [(r[key], r[yk]) for r in rows if r[key] is not None]
            xs, ys = [a for a, _ in ok], [b for _, b in ok]
            t[yk] = {"n": len(ok), "spearman": round(spearman(xs, ys), 3),
                     "pearson": round(pearson(xs, ys), 3), "p": round(perm_p(xs, ys), 4)}
        tests.append(t)
        print(key, t)

    # 指数買い圧力で3分位に分けて変化率を比べる
    srt = sorted(rows, key=lambda r: r["demand_days"])
    k = len(srt) // 3
    groups = []
    for name, sub in (("小", srt[:k]), ("中", srt[k:len(srt) - k]), ("大", srt[len(srt) - k:])):
        groups.append({"label": name, "n": len(sub),
                       "range": [sub[0]["demand_days"], sub[-1]["demand_days"]],
                       "mean": round(mean(r["pct"] for r in sub), 3),
                       "excess_mean": round(mean(r["excess"] for r in sub), 3),
                       "median": round(median(r["pct"] for r in sub), 3),
                       "growth": sum(r["growth"] for r in sub)})

    # 市場の違いで説明されてしまっていないか: 市場内での順位相関
    within = {}
    for m in ("スタンダード", "グロース"):
        sub = [r for r in rows if r["market"] == m]
        within[m] = {"n": len(sub), "bench_close_move": round(bench[m], 3),
                     "pct_mean": round(mean(r["pct"] for r in sub), 3),
                     "excess_mean": round(mean(r["excess"] for r in sub), 3)}
        for key in ("demand_days", "close_mult", "vol", "r5", "r5x", "r5_1524"):
            xs, ys = [r[key] for r in sub], [r["pct"] for r in sub]
            within[m][key] = {"spearman": round(spearman(xs, ys), 3), "p": round(perm_p(xs, ys), 4)}

    out = {"date": DATE, "topix_runup_pct": round(topix_ret * 100, 2),
           "r5_bench_pct": {k: round(v, 2) for k, v in r5_bench.items()},
           "implied_passive_median": round(median(r["implied_passive"] for r in rows), 2),
           "tests": tests, "terciles": groups, "within_market": within, "rows": rows}
    (D / f"topix_new_{DATE}_analysis.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
