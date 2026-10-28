# -*- coding: utf-8 -*-
"""地合いフィルター版(検証ページ §06)。simulate.py の運用ルールに次の2つを足す。

  A. 日経平均の午前引値が25日線より上の日だけ、新高値の新規買いをする(下なら買わない)
  B. 保有株の午前引値がその銘柄の25日線を下回ったら、その日の大引けで全株売る(日経の位置に関係なく)
  25日線 = 前営業日までの終値24本 + 当日の午前引値 の平均(ザラ場中にチャートで見える25日線と同じ)
  それ以外(予算1/5・均等割り・成績が悪い順に売って予算を作る・引けで買う)は simulate.py と同じ。
  売りは買いより先に処理する。同じ日に「25日線割れで売る」と「新高値で買う」が重なっても、
  手数料を無視しているので差し引きと同じになる。

比べるもの: フィルターなし / Aだけ / Bだけ / A+B(本人ルール) / A+Bを無作為な銘柄に適用(20回) / TOPIX
期間: apr = 2026-04-01〜最新、ref = 2023-12-01〜最新(60分足が遡れるのは2023-10末まで)

前提: py kensho_newhigh/fetch_am.py で cache_bars_am/ を作ってあること
使用例: py kensho_newhigh/regime.py
"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import simulate as S        # noqa: E402

AM = S.BASE / "cache_bars_am"
OUT = S.BASE / "docs" / "data_kensho_newhigh" / "regime.json"
MA = 25
PERIODS = (("apr", "2026-04-01"), ("ref", "2023-12-01"))
VARIANTS = (("none", False, False), ("idx", True, False), ("stop", False, True), ("both", True, True))


def am_ratio(code):
    return (S.load(AM / f"{code}.json", {}) or {}).get("r") or {}


def load_n225():
    m = {b[0]: b[2] for b in (S.load(S.C5 / "N225.json", {}) or {}).get("bars") or []}
    j = S.get_json("https://query1.finance.yahoo.com/v8/finance/chart/%5EN225?range=2y&interval=1d")
    r0 = j["chart"]["result"][0]
    for t, c in zip(r0["timestamp"], r0["indicators"]["quote"][0]["close"]):
        if c is not None:
            m[datetime.fromtimestamp(t + 32400).date().isoformat()] = c
    return m


def am_below_ma(closes_hist, am):
    """closes_hist = 前営業日までの終値(古い順)。午前引値が25日線より下なら True、判定不能は None。"""
    if am is None or len(closes_hist) < MA - 1:
        return None
    ma = (sum(closes_hist[-(MA - 1):]) + am) / MA
    return am < ma


def simulate(prices, closes, dates, sig, kind, use_idx, use_stop, idx_on, amr, pidx):
    cash = float(S.START_CAPITAL)
    pos, last = {}, {}
    end_date = {c: b[-1][0] for c, b in prices.items()}
    curve, realized = [], []
    stop_n, stop_ret, no_am, skip_days = 0, [], 0, 0
    for d in dates:
        px = closes.get(d, {})
        last.update({c: px[c] for c in pos if c in px})
        for c in [c for c in pos if end_date.get(c, d) < d]:
            cash += pos[c][0] * last.get(c, pos[c][1])
            realized.append(last.get(c, pos[c][1]) / pos[c][1] - 1)
            del pos[c]
        # B. 保有株の25日線割れ(午前引値で判定 → 大引けで売る)
        if use_stop:
            for c in list(pos):
                if c not in px:
                    continue
                i = pidx[c].get(d)
                r = amr.get(c, {}).get(d)
                if i is None or r is None:
                    no_am += 1
                    continue
                bars = prices[c]
                below = am_below_ma([b[2] for b in bars[max(0, i - MA + 1):i]], px[c] * r)
                if below:
                    q, a = pos.pop(c)
                    cash += q * px[c]
                    ret = px[c] / a - 1
                    realized.append(ret)
                    stop_ret.append(ret)
                    stop_n += 1
        equity = cash + sum(q * last.get(c, a) for c, (q, a) in pos.items())
        buys = [c for c in (sig.get(d) or {}).get(kind, []) if c in px]
        if buys and use_idx and not idx_on.get(d, True):
            skip_days += 1
            buys = []
        if buys:
            budget = equity * S.FRACTION
            need = budget - cash
            if need > 0:
                bs = set(buys)
                cand = sorted((c for c in pos if c in px and c not in bs),
                              key=lambda c: px[c] / pos[c][1] - 1)
                for c in cand:
                    if need <= 1e-6:
                        break
                    q, a = pos[c]
                    val = q * px[c]
                    realized.append(px[c] / a - 1)
                    if val <= need:
                        cash += val
                        need -= val
                        del pos[c]
                    else:
                        pos[c][0] = q - need / px[c]
                        cash += need
                        need = 0
            spend = min(budget, cash)
            each = spend / len(buys)
            for c in buys:
                q = each / px[c]
                if c in pos:
                    oq, oa = pos[c]
                    pos[c] = [oq + q, (oq * oa + q * px[c]) / (oq + q)]
                else:
                    pos[c] = [q, px[c]]
                last[c] = px[c]
            cash -= spend
        equity = cash + sum(q * last.get(c, a) for c, (q, a) in pos.items())
        curve.append([d, round(equity), round(cash / equity, 4) if equity else 0, len(pos)])
    med = lambda xs: round(sorted(xs)[len(xs) // 2], 4) if xs else None
    return curve, {"stop_n": stop_n, "stop_win": round(sum(r > 0 for r in stop_ret) / len(stop_ret), 4)
                   if stop_ret else None, "stop_med": med(stop_ret),
                   "realized_n": len(realized),
                   "realized_win": round(sum(r > 0 for r in realized) / len(realized), 4)
                   if realized else None, "realized_med": med(realized),
                   "no_am": no_am, "skip_days": skip_days}


def main():
    prices = S.load_prices()
    prices.pop("N225", None)
    bench = S.load_bench()
    closes = {}
    for c, bars in prices.items():
        for b in bars:
            closes.setdefault(b[0], {})[c] = b[2]
    pidx = {c: {b[0]: i for i, b in enumerate(bs)} for c, bs in prices.items()}
    amr = {c: am_ratio(c) for c in prices}
    print("午前引値あり", sum(1 for v in amr.values() if v), "/", len(amr), flush=True)

    n225 = load_n225()
    nam = am_ratio("^N225")
    nd = sorted(n225)
    idx_on, nk = {}, {}
    for i, d in enumerate(nd):
        hist = [n225[x] for x in nd[max(0, i - MA + 1):i]]
        r = nam.get(d)
        below = am_below_ma(hist, n225[d] * r) if r else None
        if below is None:                       # 午前引値が無い日は前日の判定を引き継ぐ
            idx_on[d] = idx_on.get(nd[i - 1], True) if i else True
        else:
            idx_on[d] = not below
        ma = (sum(hist[-(MA - 1):]) + n225[d] * (r or 1)) / MA if len(hist) >= MA - 1 else None
        nk[d] = [round(n225[d]), round(n225[d] * r) if r else None, round(ma) if ma else None]

    sig, uni = S.computed_signals(prices, PERIODS[-1][1])
    for seed in S.SEEDS:
        S.add_control(sig, uni, seed)

    result = {"generated": datetime.now().astimezone().isoformat(timespec="seconds"),
              "ma": MA, "periods": {}}
    for name, start in PERIODS:
        dates = sorted(d for d in closes if d >= start and d in bench)
        out = {"start": dates[0], "end": dates[-1], "days": len(dates),
               "on_days": sum(1 for d in dates if idx_on.get(d, True)),
               "on": [1 if idx_on.get(d, True) else 0 for d in dates],
               "n225": [[d] + nk.get(d, [None] * 3) for d in dates],
               "bench": [[d, round(bench[d] / bench[dates[0]] * S.START_CAPITAL)] for d in dates],
               "runs": {}}
        for kind in ("w52", "ath"):
            for v, ui, us in VARIANTS:
                curve, info = simulate(prices, closes, dates, sig, kind, ui, us, idx_on, amr, pidx)
                m = S.metrics(curve, bench, dates)
                out["runs"][f"{kind}_{v}"] = {"metrics": m, "info": info, "curve": curve}
                print(f"[{name}] {kind:4s} {v:5s} 資産 {m['total']:+.1%}  最大DD {m['mdd']:.1%}"
                      f"  平均保有 {m['avg_hold']}  現金 {m['avg_cash']:.0%}  {info}", flush=True)
            ctrl, curves = [], []
            for seed in S.SEEDS:
                cc, _ = simulate(prices, closes, dates, sig, f"rnd_{kind}_{seed}", True, True,
                                 idx_on, amr, pidx)
                ctrl.append(S.metrics(cc, bench, dates))
                curves.append([x[1] for x in cc])
            q = lambda xs, f: sorted(xs)[int(f * (len(xs) - 1))]
            each = [c["total"] for c in ctrl]
            out["runs"][f"{kind}_both"]["ctrl"] = {
                "median": q(each, .5), "each": each,
                "mdd": round(sum(c["mdd"] for c in ctrl) / len(ctrl), 4)}
            out["runs"][f"{kind}_both"]["ctrl_curve"] = [
                [dates[i], q(col, .5), q(col, .25), q(col, .75)] for i, col in enumerate(zip(*curves))]
            print(f"[{name}] {kind:4s} 無作為+A+B 中央値 {q(each, .5):+.1%}  "
                  f"{[f'{x:+.0%}' for x in sorted(each)]}", flush=True)
        result["periods"][name] = out
    OUT.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(OUT, f"{OUT.stat().st_size // 1024}KB")


if __name__ == "__main__":
    main()
