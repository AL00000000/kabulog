# -*- coding: utf-8 -*-
"""新高値の日の高値を基準に、その後 株価が基準+10%に届いたところで買い、売らずに
1/3/6/12か月(21/63/126/252営業日)持った騰落率。資金の制約は考えない(1件ずつ独立)。

買い方は2通り:
  intraday: 日中高値が基準×1.1に届いた日に、基準×1.1で買う(寄りで既に上なら始値で買う)
  close   : 終値が初めて基準×1.1以上で引けた日の引けで買う
基準日から252営業日(約1年)以内に届かなければ買わない。2017-10以降、売買代金10億円以上。
比較: §06 の「新高値の日の引けで買った」場合(同じ新高値の全件)と、買った日に買ったTOPIX。

出力: docs/data_kensho_newhigh/plus10.json(検証ページ §07 の表)
"""
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import simulate as S        # noqa: E402
import regime as R          # noqa: E402

START = "2017-10-02"
UP = 1.10
WAIT = 252
HOLDS = (("1m", 21), ("3m", 63), ("6m", 126), ("12m", 252))


def stats(v):
    if not v:
        return None
    s = sorted(v)
    return {"n": len(v), "mean": round(statistics.mean(v), 5), "med": round(statistics.median(v), 5),
            "win": round(sum(x > 0 for x in v) / len(v), 4),
            "p10": round(s[len(s) // 10], 5), "p90": round(s[len(s) * 9 // 10], 5)}


def main():
    prices, opens = R.load_prices()
    bench = R.load_bench()
    bd = sorted(bench)
    bi = {d: i for i, d in enumerate(bd)}
    sig, _ = S.computed_signals(prices, START)
    idx = {c: {b[0]: i for i, b in enumerate(bs)} for c, bs in prices.items()}
    out = {"start": START, "end": max(sig), "up": UP, "wait": WAIT, "holds": [h for h, _ in HOLDS],
           "all": {}, "year": {}, "trig": {}}
    for kind in ("w52", "ath"):
        ents = {"intraday": [], "close": []}       # (買った日の位置, 買値, 銘柄, 買った日)
        n_ev = 0
        for d in sorted(sig):
            for c in sig[d][kind]:
                n_ev += 1
                bs = prices[c]
                i = idx[c][d]
                lv = bs[i][1] * UP
                op = opens.get(c, {})
                for j in range(i + 1, min(i + 1 + WAIT, len(bs))):
                    if bs[j][1] >= lv:
                        o = op.get(bs[j][0])
                        px = o if o and lv < o <= bs[j][1] * 1.001 else lv
                        ents["intraday"].append((j, px, c, i))
                        break
                for j in range(i + 1, min(i + 1 + WAIT, len(bs))):
                    if bs[j][2] >= lv:
                        ents["close"].append((j, bs[j][2], c, i))
                        break
        for how, es in ents.items():
            waits = sorted(j - i for j, _, _, i in es)
            out["trig"][f"{kind}_{how}"] = {"events": n_ev, "hit": len(es), "rate": round(len(es) / n_ev, 4),
                                           "wait_med": waits[len(waits) // 2]}
            for name, h in HOLDS:
                v, ex, tp, yr = [], [], [], {}
                for j, px, c, _ in es:
                    bs = prices[c]
                    if j + h >= len(bs):
                        continue
                    r = bs[j + h][2] / px - 1
                    v.append(r)
                    yr.setdefault(bs[j][0][:4], []).append(r)
                    k = bi.get(bs[j][0])
                    if k is not None and k + h < len(bd):
                        tb = bench[bd[k + h]] / bench[bd[k]] - 1
                        tp.append(tb)
                        ex.append(r - tb)
                st = stats(v)
                st["topix_mean"] = round(statistics.mean(tp), 5)
                st["ex_med"] = round(statistics.median(ex), 5)
                out["all"][f"{kind}_{how}_{name}"] = st
                out["year"][f"{kind}_{how}_{name}"] = {y: stats(x) for y, x in sorted(yr.items())}
                print(kind, how, name, {k: st[k] for k in ("n", "mean", "med", "win", "topix_mean", "ex_med")},
                      flush=True)
            print(kind, how, out["trig"][f"{kind}_{how}"], flush=True)
    p = S.BASE / "docs" / "data_kensho_newhigh" / "plus10.json"
    p.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(p)


if __name__ == "__main__":
    main()
