"""月末ごとの実績PER・事後の予想PER・PBRと、市場PERとの比を出す.

実績PER   : 株価 ÷ その時点で発表済みの直近通期EPS (5/15で前期に切り替え)
事後予想PER: 株価 ÷ その時点で進行中の期の実際のEPS (後から分かる値。最新期は会社予想)
市場PER   : JPX「規模別・業種別PER・PBR」の東証一部/プライム総合 (../kensho_tob/jpx_perpbr.json)
赤字の期はPERを出さない。グループの値は中央値 (2社以上で計算できた月のみ)
出力: result.json → build_page.py
"""
import json
import os
import statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(HERE, "data.json"), encoding="utf-8"))
JPX = json.load(open(os.path.join(HERE, "..", "kensho_tob", "jpx_perpbr.json"), encoding="utf-8"))
START = "2020-01"


def last_actual(d):
    y = int(d[:4])
    return f"{y}/03" if d[5:] >= "05-15" else f"{y - 1}/03"


def in_progress(d):
    y, m = int(d[:4]), int(d[5:7])
    return f"{y + 1 if m >= 4 else y}/03"


def market(ym):
    mk = JPX.get(ym)
    if not mk:
        return None
    p = mk.get("プライム市場") or mk.get("市場一部")
    return p["総合"]["per"] if p and "総合" in p else None


months = {}
for d, _ in D["px"]["8058"]:
    if d[:7] >= START:
        months[d[:7]] = d  # 月末の営業日
rows = []
for ym, d in months.items():
    row = {"ym": ym, "d": d, "mkt": market(ym), "co": {}}
    for c in D["names"]:
        px = dict(D["px"][c]).get(d)
        fy = D["fy"][c]
        e1 = fy.get(last_actual(d), {}).get("eps")
        cur = in_progress(d)
        e2 = (fy.get(cur) or fy.get(cur + "予") or {}).get("eps")
        b = fy.get(last_actual(d), {}).get("bps")
        # 直近5期の平均EPS (景気循環の山と谷をならした利益)
        y = int(last_actual(d)[:4])
        e5 = [fy.get(f"{k}/03", {}).get("eps") for k in range(y - 4, y + 1)]
        avg5 = sum(e5) / 5 if None not in e5 else None
        row["co"][c] = {
            "px": px,
            "per": round(px / e1, 2) if px and e1 and e1 > 0 else None,
            "fwd": round(px / e2, 2) if px and e2 and e2 > 0 else None,
            "per5": round(px / avg5, 2) if px and avg5 and avg5 > 0 else None,
            "pbr": round(px / b, 3) if px and b else None,
        }
    for g in ("shosha", "kaiun"):
        for k in ("per", "fwd", "per5", "pbr"):
            xs = [row["co"][c][k] for c in D[g] if row["co"][c][k]]
            row[f"{g}_{k}"] = round(st.median(xs), 2) if len(xs) >= 2 else None
        row[f"{g}_rel"] = round(row[f"{g}_per"] / row["mkt"], 3) if row[f"{g}_per"] and row["mkt"] else None
    rows.append(row)

# 期ごとのEPS (ピーク=FY2023/3 比)
eps = {}
for c in D["names"]:
    fy = D["fy"][c]
    eps[c] = {k: v["eps"] for k, v in sorted(fy.items()) if "2019/03" <= k <= "2027/03予"}

json.dump({"names": D["names"], "shosha": D["shosha"], "kaiun": D["kaiun"], "rows": rows, "eps": eps},
          open(os.path.join(HERE, "result.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)

for r in rows:
    if r["ym"][5:] in ("03", "09") or r is rows[-1]:
        print(r["ym"], "市場", r["mkt"], "| 商社", r["shosha_per"], r["shosha_rel"], r["shosha_fwd"], r["shosha_per5"],
              "| 海運", r["kaiun_per"], r["kaiun_rel"], r["kaiun_fwd"], r["kaiun_per5"])
