# -*- coding: utf-8 -*-
"""新高値銘柄を当日終値で買い、売らずに1/3/6/12か月(21/63/126/252営業日)持った騰落率。
資金の制約・売却ルールは考えない(1件ずつ独立)。2017-10以降、売買代金10億円以上。
比較: 同じ日の母集団(売買代金10億円以上)全体と、同じ日に買ったTOPIX(1306)。

出力: docs/data_kensho_newhigh/hold.json(検証ページ §06 の表)
"""
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import simulate as S        # noqa: E402
import regime as R          # noqa: E402

START = "2017-10-02"
HOLDS = (("1m", 21), ("3m", 63), ("6m", 126), ("12m", 252))


def stats(v):
    if not v:
        return None
    return {"n": len(v), "mean": round(statistics.mean(v), 5), "med": round(statistics.median(v), 5),
            "win": round(sum(x > 0 for x in v) / len(v), 4),
            "p10": round(sorted(v)[len(v) // 10], 5), "p90": round(sorted(v)[len(v) * 9 // 10], 5)}


def main():
    prices, _ = R.load_prices()
    bench = R.load_bench()
    bd = sorted(bench)
    bi = {d: i for i, d in enumerate(bd)}
    sig, uni = S.computed_signals(prices, START)
    idx = {c: {b[0]: i for i, b in enumerate(bs)} for c, bs in prices.items()}
    groups = {"w52": {d: s["w52"] for d, s in sig.items()},
              "ath": {d: s["ath"] for d, s in sig.items()}, "uni": uni}
    out = {"start": START, "end": max(uni), "holds": [h for h, _ in HOLDS], "all": {}, "year": {}}
    for kind, g in groups.items():
        for name, h in HOLDS:
            v, ex, tp, yr = [], [], [], {}
            for d in sorted(g):
                j = bi.get(d)
                tb = bench[bd[j + h]] / bench[d] - 1 if j is not None and j + h < len(bd) else None
                for c in g[d]:
                    i = idx[c][d]
                    bs = prices[c]
                    if i + h >= len(bs):
                        continue
                    r = bs[i + h][2] / bs[i][2] - 1
                    v.append(r)
                    yr.setdefault(d[:4], []).append(r)
                    if tb is not None:
                        tp.append(tb)
                        ex.append(r - tb)
            st = stats(v)
            st["topix_mean"] = round(statistics.mean(tp), 5)
            st["ex_med"] = round(statistics.median(ex), 5)
            st["big"] = sum(x > 4 for x in v)              # +400%超(外れ値の確認用)
            out["all"][f"{kind}_{name}"] = st
            out["year"][f"{kind}_{name}"] = {y: stats(x) for y, x in sorted(yr.items())}
            print(kind, name, {k: st[k] for k in ("n", "mean", "med", "win", "topix_mean", "ex_med", "big")},
                  flush=True)
    p = S.BASE / "docs" / "data_kensho_newhigh" / "hold.json"
    p.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(p)


if __name__ == "__main__":
    main()
