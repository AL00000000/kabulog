# -*- coding: utf-8 -*-
"""新高値を付けた銘柄の1/5/20/40/60営業日後の騰落率を、同じ日の母集団(売買代金10億円以上)全体と比べる。

出力: docs/data_kensho_newhigh/forward.json(検証ページ §03 の表)
"""
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import simulate as S        # noqa: E402

prices = S.load_prices()
sig, uni = S.computed_signals(prices, S.LONG_START)
idx = {c: {b[0]: i for i, b in enumerate(bs)} for c, bs in prices.items()}
out = {}
for kind in ("w52", "ath", "uni"):
    for h in (1, 5, 20, 40, 60):
        v = []
        for d in sorted(sig if kind != "uni" else uni):
            codes = (sig[d][kind] if kind != "uni" else uni[d])
            for c in codes:
                i = idx[c][d]
                bs = prices[c]
                if i + h < len(bs):
                    v.append(bs[i + h][2] / bs[i][2] - 1)
        out[f"{kind}_{h}"] = {"n": len(v), "mean": round(statistics.mean(v), 5),
                              "med": round(statistics.median(v), 5),
                              "win": round(sum(x > 0 for x in v) / len(v), 4)}
        print(kind, h, out[f"{kind}_{h}"], flush=True)
(S.BASE / "docs" / "data_kensho_newhigh" / "forward.json").write_text(
    json.dumps(out, ensure_ascii=False), encoding="utf-8")
