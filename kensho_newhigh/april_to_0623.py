# -*- coding: utf-8 -*-
"""2026年4月に新高値を付けた銘柄を、その日の引けで買って 2026-06-23 の引けまで持ったらどうだったか。

比較対象は同じ日の母集団(売買代金10億円以上)全体を同じく 6/23 まで持った場合と、TOPIX(1306)。
「件数ベース」は新高値1回=1件(何度も新高値を付けた銘柄は何件も入る)、
「銘柄ベース」は4月に最初に新高値を付けた日だけを1件として数える。
出力: docs/data_kensho_newhigh/april.json
"""
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import simulate as S        # noqa: E402

FROM, TO, END = "2026-04-01", "2026-04-30", "2026-06-23"

prices = S.load_prices()
sig, uni = S.computed_signals(prices, "2026-03-01")
bench = S.load_bench()
close = {c: {b[0]: b[2] for b in bs} for c, bs in prices.items()}


def stats(v):
    return {"n": len(v), "mean": round(statistics.mean(v), 4), "med": round(statistics.median(v), 4),
            "win": round(sum(x > 0 for x in v) / len(v), 4)} if v else None


days = sorted(d for d in sig if FROM <= d <= TO)
out = {"from": FROM, "to": TO, "end": END, "days": len(days)}
for kind in ("w52", "ath", "uni"):
    ev, first, seen = [], [], set()
    for d in days:
        for c in (sig[d][kind] if kind != "uni" else uni.get(d, [])):
            e = close[c].get(END)
            if e is None:
                continue                         # 6/23 に値が無い(上場廃止など)
            r = e / close[c][d] - 1
            ev.append(r)
            if c not in seen:
                seen.add(c)
                first.append(r)
    out[kind] = {"events": stats(ev), "stocks": stats(first)}
out["topix"] = {d: round(bench[END] / bench[d] - 1, 4) for d in (days[0], days[-1])}
out["topix_avg"] = round(statistics.mean(bench[END] / bench[d] - 1 for d in days), 4)
print(json.dumps(out, ensure_ascii=False, indent=1))
(S.BASE / "docs" / "data_kensho_newhigh" / "april.json").write_text(
    json.dumps(out, ensure_ascii=False), encoding="utf-8")
