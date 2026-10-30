"""海運大手3社: 決算・業績修正の前後5営業日(窓内)と決算の間(窓外)の上昇を分ける.

開示日: ../kensho_kaiun/cache/docs_*.json (TDnet一覧)
株価  : ../kensho_kaiun/cache/yahoo_*.json (分割補正済み・配当込み)
TOPIX : topix1306.json (1306 ETF, Yahoo)
出力  : result.json, placebo.json → build_page.py
"""
import json, math, os
from collections import OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "kensho_kaiun", "cache")
START, END = "2020-01-06", "2024-03-29"
NAMES = {"9101": "日本郵船", "9104": "商船三井", "9107": "川崎汽船"}
K = 5

tpx = {d: (c, a) for d, c, a in json.load(open(os.path.join(HERE, "topix1306.json")))}


def load(code):
    bars = json.load(open(f"{SRC}/yahoo_{code}.json"))["bars"]
    return [(d, c, a) for d, c, a in bars if "2019-12-01" <= d <= "2024-04-30"]


def events(code, days):
    docs = json.load(open(f"{SRC}/docs_{code}.json", encoding="utf-8"))
    ev = OrderedDict()
    for x in sorted(docs, key=lambda x: x["pub"]):
        d, t = x["pub"][:10], x["pub"][11:16]
        if not days[0] < d < days[-1]:
            continue
        # 15:00以降(当時の大引け)の発表は翌営業日が反応日
        i = next(i for i, dd in enumerate(days) if (dd > d if t >= "15:00" else dd >= d))
        kind = "決算" if "決算短信" in x["title"] else "修正"
        ev.setdefault(i, set()).add(kind)
    return ev


out = {}
for code in NAMES:
    bars = load(code)
    days = [b[0] for b in bars]
    ev = events(code, days)
    i0, i1 = days.index(START), days.index(END)
    # 日次リターン(i0..i1): 配当込み(a) / 株価のみ(c) / TOPIX超過(配当込み同士)
    rows = []
    for i in range(i0, i1 + 1):
        d = days[i]
        ra = math.log(bars[i][2] / bars[i - 1][2])
        rc = math.log(bars[i][1] / bars[i - 1][1])
        rt = math.log(tpx[d][1] / tpx[days[i - 1]][1])
        rows.append(dict(i=i, d=d, ra=ra, rc=rc, rx=ra - rt))
    tag = {}  # i -> "pre"/"day"/"post"  (重なりは day > post > pre)
    pr = {"day": 3, "post": 2, "pre": 1}
    evlist = [(i, k) for i, k in ev.items() if i0 - K <= i <= i1 + K]
    for e, _ in evlist:
        for j in range(e - K, e + K + 1):
            p = "pre" if j < e else "day" if j == e else "post"
            if pr[p] > pr.get(tag.get(j), 0):
                tag[j] = p
    for r in rows:
        r["tag"] = tag.get(r["i"], "out")

    # 区間に分ける: 連続する窓内 / 窓外
    segs = []
    for r in rows:
        w = r["tag"] != "out"
        if segs and segs[-1]["w"] == w:
            segs[-1]["r"].append(r)
        else:
            segs.append({"w": w, "r": [r]})

    def summ(sel, key):
        s = sum(r[key] for r in sel)
        return dict(n=len(sel), log=s, mult=math.exp(s), perday=s / len(sel) if sel else 0)

    res = {"events": [(days[i], sorted(k)) for i, k in evlist]}
    for key in ("ra", "rc", "rx"):
        tot = sum(r[key] for r in rows)
        d = {"total": summ(rows, key)}
        for t in ("in", "out", "pre", "day", "post"):
            sel = [r for r in rows if (r["tag"] != "out" if t == "in" else r["tag"] == t)]
            d[t] = summ(sel, key)
            d[t]["share"] = d[t]["log"] / tot
        for w, nm in ((True, "seg_in"), (False, "seg_out")):
            ss = [sum(r[key] for r in s["r"]) for s in segs if s["w"] == w]
            d[nm] = dict(n=len(ss), up=sum(x > 0 for x in ss), rate=sum(x > 0 for x in ss) / len(ss))
        # 年度別
        fy = {}
        for r in rows:
            y, m = int(r["d"][:4]), int(r["d"][5:7])
            f = f"FY{y if m >= 4 else y - 1}" if r["d"] >= "2020-04-01" else "2020/1-3"
            fy.setdefault(f, {"in": 0, "out": 0})["in" if r["tag"] != "out" else "out"] += r[key]
        d["fy"] = fy
        res[key] = d
    res["segs"] = [(s["r"][0]["d"], s["r"][-1]["d"], s["w"], len(s["r"]),
                    math.exp(sum(r["ra"] for r in s["r"])) - 1,
                    math.exp(sum(r["rx"] for r in s["r"])) - 1) for s in segs]
    cum = 0
    res["daily"] = []
    for r in rows:
        cum += r["ra"]
        res["daily"].append((r["d"], round(cum, 5), r["tag"]))
    out[code] = res

json.dump(out, open(os.path.join(HERE, "result.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

for code, res in out.items():
    print(f"\n==== {code} {NAMES[code]}  イベント数 {len(res['events'])}")
    for key, lab in (("ra", "配当込み"), ("rc", "株価のみ"), ("rx", "TOPIX超過")):
        d = res[key]
        print(f" [{lab}] 全期間 x{d['total']['mult']:.2f} ({d['total']['n']}日)")
        for t in ("in", "out", "pre", "day", "post"):
            x = d[t]
            print(f"   {t:4s} {x['n']:4d}日 x{x['mult']:.2f}  寄与{x['share']*100:6.1f}%  日平均{x['perday']*100:+.3f}%")
        print(f"   窓区間 上昇 {d['seg_in']['up']}/{d['seg_in']['n']}  窓外区間 上昇 {d['seg_out']['up']}/{d['seg_out']['n']}")
        print("   年度別(倍率) " + "  ".join(f"{f}: 窓内x{math.exp(v['in']):.2f} 窓外x{math.exp(v['out']):.2f}" for f, v in d["fy"].items()))

# プラセボ: 同じ数の11日窓をランダムな位置に置いたとき、窓内の上昇がどのくらいになるか
import random
random.seed(0)
placebo = {}
print("\n==== プラセボ(窓の位置をランダムにしたときの窓内倍率の分布, 配当込み)")
for code, res in out.items():
    bars = load(code); days = [b[0] for b in bars]
    i0, i1 = days.index(START), days.index(END)
    r = [math.log(bars[i][2] / bars[i - 1][2]) for i in range(i0, i1 + 1)]
    n_ev = len(res["events"]); n = len(r)
    actual = res["ra"]["in"]["log"]; ndays = res["ra"]["in"]["n"]
    sims = []
    for _ in range(5000):
        sel = set()
        for _ in range(n_ev):
            c = random.randrange(n)
            sel.update(range(max(0, c - K), min(n, c + K + 1)))
        s = sum(r[j] for j in sel)
        sims.append(s * ndays / len(sel))  # 窓内日数を実際に揃えて比較
    p = sum(x >= actual for x in sims) / len(sims)
    sims.sort()
    placebo[code] = dict(actual=math.exp(actual), med=math.exp(sims[2500]),
                         lo=math.exp(sims[250]), hi=math.exp(sims[4750]), p=p)
    print(f" {code} 実際 x{math.exp(actual):.2f} / ランダム中央値 x{math.exp(sims[2500]):.2f} 90%幅 x{math.exp(sims[250]):.2f}〜x{math.exp(sims[4750]):.2f}  p={p:.3f}")
json.dump(placebo, open(os.path.join(HERE, "placebo.json"), "w"), indent=1)
