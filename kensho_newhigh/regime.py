# -*- coding: utf-8 -*-
"""地合いフィルター版(検証ページ §05)。simulate.py の運用ルールに次の2つを足す。

  A. 日経平均の午前引値が25日線より上の日だけ、新高値の新規買いをする(下なら買わない)
  B. 保有株の午前引値がその銘柄の25日線を下回ったら、その日の大引けで全株売る(日経の位置に関係なく)
  25日線 = 前営業日までの終値24本 + 当日の午前引値 の平均(ザラ場中にチャートで見える25日線と同じ)
  それ以外(予算1/5・均等割り・成績が悪い順に売って予算を作る・引けで買う)は simulate.py と同じ。
  売りは買いより先に処理する。同じ日に「25日線割れで売る」と「新高値で買う」が重なっても、
  手数料を無視しているので差し引きと同じになる。

比べるもの: フィルターなし / Aだけ / Bだけ / A+B(本人ルール) / A+Bを無作為な銘柄に適用(20回) / TOPIX
期間: apr = 2026-04-01〜最新
      am  = 2023-10-30〜最新(60分足が遡れる最初の日。全期間で本物の午前引値)
      max = 2017-10-02〜最新(10年日足キャッシュで52週判定ができる最初の月から)
午前引値の代わり: 60分足が無い 2023-10-30 より前は **当日の始値** で判定する(25日線も始値を入れて計算)。
  60分足のある期間で照合した一致率は 日経平均 94.8%・個別株 91.6%(前日終値で判定すると約90%)。
  am 期間では、全期間を始値で判定した場合(both_open)も計算し、代用によるずれを示す。

前提: py kensho_newhigh/fetch_am.py で cache_bars_am/ を作ってあること
      cache_bars_10y/(pbr_growth/fetch_10y.py)があること
使用例: py kensho_newhigh/regime.py
"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import simulate as S        # noqa: E402

AM = S.BASE / "cache_bars_am"
C10 = S.BASE / "cache_bars_10y"
OUT = S.BASE / "docs" / "data_kensho_newhigh" / "regime.json"
MA = 25
AM_START = "2023-10-30"
PERIODS = (("apr", "2026-04-01"), ("am", AM_START), ("max", "2017-10-02"))
VARIANTS = (("none", False, False), ("idx", True, False), ("stop", False, True), ("both", True, True))


def am_ratio(code):
    return (S.load(AM / f"{code}.json", {}) or {}).get("r") or {}


def merge_10y(code, m):
    """10年キャッシュ [d,o,h,l,c,v] を m({d: [d,h,c,v]})の下に敷く。取得時期の違いで分割調整の
    基準がずれていたら、重なる日の終値の比で合わせる。始値は {d: open} で返す。"""
    b10 = [b for b in ((S.load(C10 / f"{code}.json", {}) or {}).get("bars") or [])
           if len(b) >= 6 and b[1] and b[4]]
    rs = sorted(m[b[0]][2] / b[4] for b in b10 if b[0] in m)
    k = rs[len(rs) // 2] if rs else 1.0
    if abs(k - 1) < 0.02:
        k = 1.0
    opens = {}
    for b in b10:
        opens[b[0]] = b[1] * k
        if b[0] not in m:
            m[b[0]] = [b[0], b[2] * k, b[4] * k, (b[5] or 0) / k]
    return opens


def load_prices():
    codes = ({p.stem for p in S.C5.glob("*.json")} | {p.stem for p in S.CH.glob("*.json")}
             | {p.stem for p in C10.glob("*.json")})
    codes -= {S.BENCH, "N225", "^N225"}
    prices, opens = {}, {}
    for c in codes:
        m = {}
        for src in (S.C5, S.CH):               # 後から読む2年キャッシュ(新しい)を優先
            for b in (S.load(src / f"{c}.json", {}) or {}).get("bars") or []:
                if len(b) >= 4:
                    m[b[0]] = [b[0], b[1], b[2], b[3]]
        opens[c] = merge_10y(c, m)
        bars, _ = S.clean_bars([m[d] for d in sorted(m)])
        if len(bars) > 1:
            prices[c] = bars
    return prices, opens


def load_bench():
    m = {d: [d, v, v, 0] for d, v in S.load_bench().items()}
    merge_10y(S.BENCH, m)
    bars, _ = S.clean_bars([m[d] for d in sorted(m)])
    return {b[0]: b[2] for b in bars}


def load_n225():
    """({d: 終値}, {d: 始値})。Yahoo の10年日足+5年キャッシュ。"""
    m = {b[0]: b[2] for b in (S.load(S.C5 / "N225.json", {}) or {}).get("bars") or []}
    opens = {}
    for rng in ("10y", "3mo"):                 # 10y は最新日を落とすことがあるので直近を重ねる
        j = S.get_json(f"https://query1.finance.yahoo.com/v8/finance/chart/%5EN225?range={rng}&interval=1d")
        r0 = j["chart"]["result"][0]
        q = r0["indicators"]["quote"][0]
        for t, o, c in zip(r0["timestamp"], q["open"], q["close"]):
            if o and c:
                d = datetime.fromtimestamp(t + 32400).date().isoformat()
                m[d] = c
                opens[d] = o
    return m, opens


def am_below_ma(closes_hist, am):
    """closes_hist = 前営業日までの終値(古い順)。午前引値が25日線より下なら True、判定不能は None。"""
    if am is None or len(closes_hist) < MA - 1:
        return None
    ma = (sum(closes_hist[-(MA - 1):]) + am) / MA
    return am < ma


def am_price(c, d, close, amr, opens, open_only=False):
    """午前引値。60分足が無い AM_START より前(または open_only)は当日始値で代用する。"""
    if not open_only and d >= AM_START:
        r = amr.get(c, {}).get(d)
        return close * r if r else None
    o = opens.get(c, {}).get(d)
    return o if o and 0.5 < o / close < 2 else None


def simulate(prices, closes, dates, sig, kind, use_idx, use_stop, idx_on, amr, pidx, opens,
             open_only=False):
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
                am = am_price(c, d, px[c], amr, opens, open_only)
                if i is None or am is None:
                    no_am += 1
                    continue
                bars = prices[c]
                below = am_below_ma([b[2] for b in bars[max(0, i - MA + 1):i]], am)
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
            spend = max(0.0, min(budget, cash))
            each = spend / len(buys)
            for c in (buys if each > 0 else []):
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
    prices, opens = load_prices()
    print("日足", len(prices), "銘柄", min(b[0][0] for b in prices.values()), flush=True)
    bench = load_bench()
    closes = {}
    for c, bars in prices.items():
        for b in bars:
            closes.setdefault(b[0], {})[c] = b[2]
    pidx = {c: {b[0]: i for i, b in enumerate(bs)} for c, bs in prices.items()}
    amr = {c: am_ratio(c) for c in prices}
    print("午前引値あり", sum(1 for v in amr.values() if v), "/", len(amr), flush=True)

    n225, nopen = load_n225()
    nam, nop = {"N": am_ratio("^N225")}, {"N": nopen}
    nd = sorted(n225)

    def regime(open_only):
        on = {}
        for i, d in enumerate(nd):
            hist = [n225[x] for x in nd[max(0, i - MA + 1):i]]
            below = am_below_ma(hist, am_price("N", d, n225[d], nam, nop, open_only))
            if below is None:                   # 午前の値が無い日は前日の判定を引き継ぐ
                on[d] = on.get(nd[i - 1], True) if i else True
            else:
                on[d] = not below
        return on
    idx_on, idx_on_open = regime(False), regime(True)
    print("日経", nd[0], "〜", nd[-1], flush=True)

    sig, uni = S.computed_signals(prices, PERIODS[-1][1])
    for seed in S.SEEDS:
        S.add_control(sig, uni, seed)

    result = {"generated": datetime.now().astimezone().isoformat(timespec="seconds"),
              "ma": MA, "am_start": AM_START, "periods": {}}
    for name, start in PERIODS:
        dates = sorted(d for d in closes if d >= start and d in bench)
        out = {"start": dates[0], "end": dates[-1], "days": len(dates),
               "on_days": sum(1 for d in dates if idx_on.get(d, True)),
               "on": [1 if idx_on.get(d, True) else 0 for d in dates],
               "bench": [[d, round(bench[d] / bench[dates[0]] * S.START_CAPITAL)] for d in dates],
               "runs": {}}
        for kind in ("w52", "ath"):
            for v, ui, us in VARIANTS:
                curve, info = simulate(prices, closes, dates, sig, kind, ui, us, idx_on, amr, pidx, opens)
                m = S.metrics(curve, bench, dates)
                if v != "both":
                    curve = [x[:2] for x in curve]      # 比較線はグラフ用の資産だけ残す
                out["runs"][f"{kind}_{v}"] = {"metrics": m, "info": info, "curve": curve}
                print(f"[{name}] {kind:4s} {v:5s} 資産 {m['total']:+.1%}  年率 {m['cagr']}  最大DD {m['mdd']:.1%}"
                      f"  平均保有 {m['avg_hold']}  現金 {m['avg_cash']:.0%}  {info}", flush=True)
            if name == "am":                    # 午前引値の代わりに始値を使ったらどれだけずれるか
                curve, info = simulate(prices, closes, dates, sig, kind, True, True, idx_on_open,
                                       amr, pidx, opens, open_only=True)
                m = S.metrics(curve, bench, dates)
                out["runs"][f"{kind}_both_open"] = {"metrics": m, "info": info}
                out["agree_open"] = round(sum(idx_on.get(d, True) == idx_on_open.get(d, True) for d in dates) / len(dates), 4)
                print(f"[{name}] {kind:4s} 始値代用 資産 {m['total']:+.1%}  最大DD {m['mdd']:.1%}"
                      f"  日経判定の一致 {out['agree_open']}", flush=True)
            ctrl, curves = [], []
            for seed in S.SEEDS:
                cc, _ = simulate(prices, closes, dates, sig, f"rnd_{kind}_{seed}", True, True,
                                 idx_on, amr, pidx, opens)
                ctrl.append(S.metrics(cc, bench, dates))
                curves.append([x[1] for x in cc])
            q = lambda xs, f: sorted(xs)[int(f * (len(xs) - 1))]
            each = [c["total"] for c in ctrl]
            out["runs"][f"{kind}_both"]["ctrl"] = {
                "median": q(each, .5), "each": each,
                "mdd": round(sum(c["mdd"] for c in ctrl) / len(ctrl), 4)}
            if ctrl[0]["cagr"] is not None:
                out["runs"][f"{kind}_both"]["ctrl"]["cagr"] = q([c["cagr"] for c in ctrl], .5)
            out["runs"][f"{kind}_both"]["ctrl_curve"] = [
                [dates[i], q(col, .5), q(col, .25), q(col, .75)] for i, col in enumerate(zip(*curves))]
            print(f"[{name}] {kind:4s} 無作為+A+B 中央値 {q(each, .5):+.1%}  "
                  f"{[f'{x:+.0%}' for x in sorted(each)]}", flush=True)
        result["periods"][name] = out
    OUT.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(OUT, f"{OUT.stat().st_size // 1024}KB")


if __name__ == "__main__":
    main()
