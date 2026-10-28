# -*- coding: utf-8 -*-
"""新高値銘柄を機械的に売買したらどうなるか(仮説検証タブ「新高値を毎日買い続けたら」)。

ルール(本人と合意したもの。docs/kensho_newhigh.html の「運用マニュアル」と同じ):
  1. 毎営業日の引け時点で、その日の新高値銘柄(売買代金10億円以上)を確定する
  2. 新高値が0件なら何もしない
  3. 予算 = その日の引けの資産(現金+保有株の時価)の 1/5
  4. 現金が予算以上なら現金だけで買う。足りなければ不足分だけ保有株を売る
     - 売れるのは「その日の新高値でない」保有銘柄だけ
     - 平均取得単価からの騰落率が **低い順**(成績が悪い順)に売る
     - 最後の1銘柄は不足分だけ一部売却する
  5. 売っても予算に届かなければ、作れた金額だけで買う
  6. 予算を新高値銘柄の数で均等に割り、その日の引け値で全銘柄を買う(既に持っていれば買い増し)
  7. 予算を作る以外の理由では売らない(損切り・利確・保有期間の上限なし)
  最小単位・手数料・税・ストップ高で買えないことは無視する。初日は全額現金。

期間:
  long : 2022-09-06〜最新。日足から新高値を毎日判定し直す(5年キャッシュ+2年キャッシュ)
  live : 2026-06-23〜最新。docs/data_newhigh/ の日別リスト(実記録+再現)をそのまま使う

使用例:
  py kensho_newhigh/simulate.py
"""
import json
import random
import sys
import time
import urllib.request
from collections import deque
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
from backfill_newhigh import clean_bars          # noqa: E402

DOCS_NH = BASE / "docs" / "data_newhigh"
OUT = BASE / "docs" / "data_kensho_newhigh" / "result.json"
C5 = BASE / "cache_bars_5y"
CH = BASE / "cache_bars_hist"
CMO = BASE / "cache_bars_mo"
BENCH = "1306"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
MIN_VALUE = 1e9
WINDOW = 365
START_CAPITAL = 10_000_000
FRACTION = 1 / 5
LONG_START = "2022-09-06"      # 5年キャッシュは2021-09始まり。52週判定に1年ぶん要る
LIVE_START = "2026-06-23"


def load(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return default


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def yahoo(code, rng, interval):
    res = (get_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{code}.T"
                    f"?range={rng}&interval={interval}").get("chart") or {}).get("result") or []
    if not res:
        return []
    r0 = res[0]
    q = ((r0.get("indicators") or {}).get("quote") or [{}])[0]
    off = (r0.get("meta") or {}).get("gmtoffset", 32400)
    out = []
    for i, t in enumerate(r0.get("timestamp") or []):
        h = (q.get("high") or [None])[i] if i < len(q.get("high") or []) else None
        c = (q.get("close") or [None])[i] if i < len(q.get("close") or []) else None
        v = (q.get("volume") or [None])[i] if i < len(q.get("volume") or []) else None
        if h is None or c is None:
            continue
        d = datetime.fromtimestamp(t + off, tz=timezone.utc).date().isoformat()
        out.append([d, float(h), float(c), float(v or 0)])
    return out


# ------------------------------------------------------------------ 価格

def load_prices():
    """{code: [[d, high, close, vol], ...]}。5年キャッシュに2年キャッシュを日付で重ねる。"""
    codes = {p.stem for p in C5.glob("*.json")} | {p.stem for p in CH.glob("*.json")}
    codes.discard(BENCH)
    out = {}
    for c in codes:
        m = {}
        for src in (C5, CH):                   # 後から読む2年キャッシュ(新しい)を優先
            for b in (load(src / f"{c}.json", {}) or {}).get("bars") or []:
                if len(b) >= 4:
                    m[b[0]] = [b[0], b[1], b[2], b[3]]
        bars, _ = clean_bars([m[d] for d in sorted(m)])
        if len(bars) > 1:
            out[c] = bars
    return out


def load_bench():
    m = {b[0]: b[2] for b in (load(C5 / f"{BENCH}.json", {}) or {}).get("bars") or []}
    for b in yahoo(BENCH, "2y", "1d"):
        m[b[0]] = b[2]
    bars, _ = clean_bars([[d, m[d], m[d], 0] for d in sorted(m)])
    return {b[0]: b[2] for b in bars}


def monthly(code):
    c = load(CMO / f"{code}.json")
    if c and c.get("bars"):
        return c["bars"]
    try:
        bars = [[d, h] for d, h, _, _ in yahoo(code, "max", "1mo")]
    except Exception:                          # noqa: BLE001
        return None
    time.sleep(0.3)
    if bars:
        CMO.mkdir(exist_ok=True)
        (CMO / f"{code}.json").write_text(json.dumps(
            {"month": date.today().strftime("%Y-%m"), "bars": bars}), encoding="utf-8")
    return bars


# ------------------------------------------------------------------ 新高値の判定

def computed_signals(prices, start):
    """{date: {"w52": [codes], "ath": [codes]}}。fetch_newhigh.py と同じ判定。"""
    sig = {}
    hits = []
    uni = {}                 # その日の母集団(売買代金10億円以上)。対照群の抽選に使う
    for c, bars in prices.items():
        ds = [date.fromisoformat(b[0]) for b in bars]
        dq = deque()
        for i in range(len(bars)):
            if i > 0:
                k = i - 1
                while dq and bars[dq[-1]][1] <= bars[k][1]:
                    dq.pop()
                dq.append(k)
            left = ds[i] - timedelta(days=WINDOW)
            while dq and ds[dq[0]] < left:
                dq.popleft()
            d = bars[i][0]
            if d < start or not dq:
                continue
            # 1年ぶんの日足が無い銘柄(上場直後)は fetch_newhigh と同じく30本で足切り
            first = next(j for j in range(i + 1) if ds[j] >= left)
            if i - first + 1 < 30:
                continue
            if bars[i][2] * bars[i][3] < MIN_VALUE:
                continue
            uni.setdefault(d, []).append(c)
            if bars[i][1] > bars[dq[0]][1]:
                hits.append((d, c, i))
    print(f"52週新高値 {len(hits)}件 → 上場来を月足で判定", flush=True)
    mo = {}
    for c in sorted({h[1] for h in hits}):
        mo[c] = monthly(c)
    for d, c, i in hits:
        s = sig.setdefault(d, {"w52": [], "ath": []})
        s["w52"].append(c)
        m = mo.get(c)
        if not m:
            continue                           # 月足が無い銘柄は上場来を判定しない
        bars = prices[c]
        prev = max([h for md, h in m if md[:7] < d[:7]] + [b[1] for b in bars[:i]])
        if bars[i][1] >= prev:
            s["ath"].append(c)
    return sig, uni


def add_control(sig, uni, seed):
    """対照群: 新高値と同じ日・同じ銘柄数を、その日の母集団から無作為に選んで買う。"""
    rng = random.Random(seed)
    for d in sorted(sig):                      # 日付順に固定しないと実行ごとに抽選が変わる
        s = sig[d]
        pool = sorted(uni.get(d, []))
        for kind in ("w52", "ath"):
            k = min(len(s.get(kind, [])), len(pool))
            s[f"rnd_{kind}_{seed}"] = rng.sample(pool, k)


def recorded_signals(start):
    sig = {}
    for p in sorted(DOCS_NH.glob("????-??-??.json")):
        if p.stem < start:
            continue
        d = load(p) or {}
        st = d.get("stocks") or []
        sig[p.stem] = {"w52": [s["code"] for s in st],
                       "ath": [s["code"] for s in st if s.get("ath")],
                       "rec": bool(d.get("reconstructed"))}
    return sig


# ------------------------------------------------------------------ シミュレーション

def simulate(prices, closes, dates, sig, kind, sell_desc):
    """closes[d][code] = 終値。日ごとの資産推移と取引の要約を返す。"""
    cash = float(START_CAPITAL)
    pos = {}                 # code -> [株数, 平均取得単価]
    last = {}                # code -> 直近終値(休止日の評価用)
    end_date = {c: b[-1][0] for c, b in prices.items()}
    curve, n_trade_days, bought, sold_amt, short_days = [], 0, 0.0, 0.0, 0
    realized = []            # 売却したときの平均取得単価からの騰落率(株数加重ではなく1回1件)
    for d in dates:
        px = closes.get(d, {})
        last.update({c: px[c] for c in pos if c in px})
        # 上場廃止などで日足が終わった銘柄は、最後の終値で現金化したものとみなす
        for c in [c for c in pos if end_date.get(c, d) < d]:
            cash += pos[c][0] * last.get(c, pos[c][1])
            realized.append(last.get(c, pos[c][1]) / pos[c][1] - 1)
            del pos[c]
        equity = cash + sum(q * last.get(c, a) for c, (q, a) in pos.items())
        buys = [c for c in (sig.get(d) or {}).get(kind, []) if c in px]
        if buys:
            n_trade_days += 1
            budget = equity * FRACTION
            need = budget - cash
            if need > 0:
                cand = [c for c in pos if c in px and c not in set(buys)]
                cand.sort(key=lambda c: px[c] / pos[c][1] - 1, reverse=sell_desc)
                for c in cand:
                    if need <= 1e-6:
                        break
                    q, a = pos[c]
                    val = q * px[c]
                    realized.append(px[c] / a - 1)
                    if val <= need:
                        cash += val
                        need -= val
                        sold_amt += val
                        del pos[c]
                    else:
                        sq = need / px[c]
                        pos[c][0] = q - sq
                        cash += need
                        sold_amt += need
                        need = 0
            spend = min(budget, cash)
            if spend < budget - 1:
                short_days += 1
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
            bought += spend
        equity = cash + sum(q * last.get(c, a) for c, (q, a) in pos.items())
        curve.append([d, round(equity), round(cash / equity, 4) if equity else 0, len(pos)])
    top = sorted(((c, q * last.get(c, a), last.get(c, a) / a - 1) for c, (q, a) in pos.items()),
                 key=lambda x: -x[1])[:10]
    return curve, {"trade_days": n_trade_days, "short_days": short_days,
                   "bought": round(bought), "sold": round(sold_amt),
                   "realized_n": len(realized),
                   "realized_win": round(sum(1 for r in realized if r > 0) / len(realized), 4)
                   if realized else None,
                   "realized_med": round(sorted(realized)[len(realized) // 2], 4)
                   if realized else None,
                   "top": [[c, round(v), round(r, 4)] for c, v, r in top]}


def metrics(curve, bench, dates):
    eq = [x[1] for x in curve]
    peak, mdd = eq[0], 0.0
    for v in eq:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1)
    yrs = (date.fromisoformat(dates[-1]) - date.fromisoformat(dates[0])).days / 365.25
    tot = eq[-1] / START_CAPITAL - 1
    b0 = bench[dates[0]]
    bvals = [bench[d] / b0 for d in dates]
    bpeak, bmdd = bvals[0], 0.0
    for v in bvals:
        bpeak = max(bpeak, v)
        bmdd = min(bmdd, v / bpeak - 1)
    return {"total": round(tot, 4), "cagr": round((1 + tot) ** (1 / yrs) - 1, 4) if yrs > 0.5 else None,
            "mdd": round(mdd, 4), "bench_total": round(bvals[-1] - 1, 4),
            "bench_cagr": round(bvals[-1] ** (1 / yrs) - 1, 4) if yrs > 0.5 else None,
            "bench_mdd": round(bmdd, 4), "years": round(yrs, 2),
            "avg_hold": round(sum(x[3] for x in curve) / len(curve), 1),
            "avg_cash": round(sum(x[2] for x in curve) / len(curve), 4),
            "final": eq[-1]}


SEEDS = tuple(range(1, 21))     # 対照群の抽選回数。1回ごとのばらつきが大きいので20回


def run_period(name, prices, closes, bench, sig, start):
    dates = sorted(d for d in closes if d >= start and d in bench)
    out = {"start": dates[0], "end": dates[-1], "days": len(dates),
           "signal_days": sum(1 for d in dates if (sig.get(d) or {}).get("w52")),
           "avg_w52": round(sum(len((sig.get(d) or {}).get("w52", [])) for d in dates) / len(dates), 1),
           "avg_ath": round(sum(len((sig.get(d) or {}).get("ath", [])) for d in dates) / len(dates), 1),
           "bench": [[d, round(bench[d] / bench[dates[0]] * START_CAPITAL)] for d in dates],
           "runs": {}}
    for kind in ("w52", "ath"):
        for desc, key in ((False, "asc"),):        # 成績が悪い順に売る(本人の指定)
            curve, info = simulate(prices, closes, dates, sig, kind, desc)
            m = metrics(curve, bench, dates)
            out["runs"][f"{kind}_{key}"] = {"metrics": m, "info": info, "curve": curve}
            cagr = "-" if m["cagr"] is None else f"{m['cagr']:+.1%}"
            ctrl, curves = [], []
            for seed in SEEDS:
                cc, _ = simulate(prices, closes, dates, sig, f"rnd_{kind}_{seed}", desc)
                ctrl.append(metrics(cc, bench, dates))
                curves.append([x[1] for x in cc])
            # 対照群の推移は日ごとの中央値と、20回の下位/上位25%の帯
            q = lambda xs, f: sorted(xs)[int(f * (len(xs) - 1))]
            out["runs"][f"{kind}_{key}"]["ctrl_curve"] = [
                [dates[i], q(col, .5), q(col, .25), q(col, .75)]
                for i, col in enumerate(zip(*curves))]
            out["runs"][f"{kind}_{key}"]["ctrl"] = {
                k: round(sum(c[k] for c in ctrl) / len(ctrl), 4)
                for k in ("total", "mdd", "avg_hold") if all(c[k] is not None for c in ctrl)}
            out["runs"][f"{kind}_{key}"]["ctrl"]["each"] = [c["total"] for c in ctrl]
            out["runs"][f"{kind}_{key}"]["ctrl"]["median"] = sorted(
                c["total"] for c in ctrl)[len(ctrl) // 2]
            if ctrl[0]["cagr"] is not None:
                out["runs"][f"{kind}_{key}"]["ctrl"]["cagr"] = round(
                    sum(c["cagr"] for c in ctrl) / len(ctrl), 4)
            print(f"  [{name}] {kind:4s} 対照群(無作為) {[f'{c:+.1%}' for c in out['runs'][f'{kind}_{key}']['ctrl']['each']]}")
            print(f"  [{name}] {kind:4s} 売り順={key:4s}  資産 {m['total']:+.1%}"
                  f"  年率 {cagr}  最大DD {m['mdd']:.1%}  TOPIX {m['bench_total']:+.1%}"
                  f"  平均保有 {m['avg_hold']}銘柄", flush=True)
    return out


def main():
    prices = load_prices()
    print(f"日足 {len(prices)}銘柄", flush=True)
    bench = load_bench()
    closes = {}
    for c, bars in prices.items():
        for b in bars:
            closes.setdefault(b[0], {})[c] = b[2]
    names = {}
    for p in DOCS_NH.glob("????-??-??.json"):
        for s in (load(p) or {}).get("stocks") or []:
            names[s["code"]] = s["name"]

    sig_long, uni = computed_signals(prices, LONG_START)
    sig_live = recorded_signals(LIVE_START)
    for seed in SEEDS:
        add_control(sig_long, uni, seed)
        add_control(sig_live, uni, seed)
    result = {
        "generated": datetime.now().astimezone().isoformat(timespec="seconds"),
        "capital": START_CAPITAL, "fraction": FRACTION,
        "main_sell": "asc",          # 本採用は「成績が悪い順に売る」
        "long": run_period("long", prices, closes, bench, sig_long, LONG_START),
        "live": run_period("live", prices, closes, bench, sig_live, LIVE_START),
        "names": names,
    }
    result["live"]["reconstructed_days"] = sum(1 for v in sig_live.values() if v.get("rec"))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(OUT, f"{OUT.stat().st_size // 1024}KB")


if __name__ == "__main__":
    main()
