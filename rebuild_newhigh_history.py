# -*- coding: utf-8 -*-
"""記録の無い日の新高値リストを日足から再現して埋める。

実記録(fetch_newhigh.py)は2026-07-30開始で、その後も取得できなかった日がある。
その日について「その日に新高値だった銘柄」を日足から計算し直し、
fetch_newhigh.py と同じ形式で docs/data_newhigh/YYYY-MM-DD.json に書く。
**既にある日付(実記録)は上書きしない。**再現した日には "reconstructed": true を付ける。

実記録との違い(タブにも注記を出す):
  - 母集団: 株探の売買代金ランキングではなく、JPXの上場銘柄一覧(東証3市場の内国/外国株式)
    のうち **その日の「終値×出来高」が10億円以上** の銘柄。株探の売買代金(約定代金の合計)とは
    少しずれるので、10億円の境目の銘柄が入れ替わることがある。
  - 一覧は6月版と最新版の和集合。6月版を入れるのは、その後に上場廃止になった銘柄を拾うため。
  - rank はその日の再現母集団内での「終値×出来高」順位(株探の順位ではない)。

判定は fetch_newhigh.py と同じ:
  - 52週新高値: 当日高値 > その日を含まない直近365日の最高値(同値は更新に数えない)
  - 上場来: 月足(当月より前)+当日より前の日足の最高値を当日高値が上回るか以上か

使用例:
  py rebuild_newhigh_history.py --fetch                 … 日足(2年)を全銘柄取得
  py rebuild_newhigh_history.py --start 2026-06-23      … 再現して空いている日を埋める
  py rebuild_newhigh_history.py --compare               … 実記録のある日と突き合わせるだけ
"""
import argparse
import json
import re
import sys
import time
import urllib.request
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from backfill_newhigh import clean_bars

BASE = Path(__file__).parent
DOCS = BASE / "docs" / "data_newhigh"
CACHE = BASE / "cache_bars_hist"
CACHE_MO = BASE / "cache_bars_mo"
JPX_FILES = [BASE / "cache_jpx" / "data_j_latest.xls",
             BASE / "cache_jpx" / "data_j_202606.xls"]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
URL = ("https://query1.finance.yahoo.com/v8/finance/chart/{sym}.T"
       "?range=2y&interval=1d")
MO_URL = ("https://query1.finance.yahoo.com/v8/finance/chart/{sym}.T"
          "?range=max&interval=1mo")
MARKETS = {"プライム": "東Ｐ", "スタンダード": "東Ｓ", "グロース": "東Ｇ"}
MIN_VALUE = 1000        # 百万円 = 10億円
WINDOW_DAYS = 365
FRESH_DAYS = 5
SHORT_HIST = 240
WORKERS = 3
SLEEP = 0.3


def load(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return default


def save(path, obj, indent=1):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=indent), encoding="utf-8")


def load_universe():
    """{code: (name, market)}。最新版を優先し、6月版にしか無い銘柄(上場廃止など)を足す。"""
    out = {}
    for f in JPX_FILES:
        df = pd.read_excel(f, dtype=str)
        for _, r in df.iterrows():
            seg = r["市場・商品区分"]
            mk = next((v for k, v in MARKETS.items() if seg.startswith(k)), None)
            if not mk or "株式" not in seg:
                continue
            code = str(r["コード"]).strip()
            out.setdefault(code, (r["銘柄名"].strip(), mk))
    return out


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def fetch_daily(code):
    """[[date, high, close, volume], ...] を古い順に。"""
    res = (get_json(URL.format(sym=code)).get("chart") or {}).get("result") or []
    if not res:
        return []
    r0 = res[0]
    ts = r0.get("timestamp") or []
    q = ((r0.get("indicators") or {}).get("quote") or [{}])[0]
    off = (r0.get("meta") or {}).get("gmtoffset", 32400)
    hi, cl, vo = q.get("high") or [], q.get("close") or [], q.get("volume") or []
    out = []
    for i, t in enumerate(ts):
        h = hi[i] if i < len(hi) else None
        c = cl[i] if i < len(cl) else None
        v = vo[i] if i < len(vo) else None
        if h is None or c is None:
            continue
        d = datetime.fromtimestamp(t + off, tz=timezone.utc).date().isoformat()
        out.append([d, float(h), float(c), 0.0 if v is None else float(v)])
    return out


def fetch_monthly(code):
    res = (get_json(MO_URL.format(sym=code)).get("chart") or {}).get("result") or []
    if not res:
        return []
    r0 = res[0]
    ts = r0.get("timestamp") or []
    hi = ((r0.get("indicators") or {}).get("quote") or [{}])[0].get("high") or []
    off = (r0.get("meta") or {}).get("gmtoffset", 32400)
    return [[datetime.fromtimestamp(t + off, tz=timezone.utc).date().isoformat(), float(h)]
            for t, h in zip(ts, hi) if h is not None]


def fetch_all(codes, today):
    CACHE.mkdir(parents=True, exist_ok=True)
    need = [c for c in codes
            if (load(CACHE / f"{c}.json", {}) or {}).get("fetched") != today]
    print(f"日足取得: {len(need)}/{len(codes)}銘柄")
    failed = []

    def one(c):
        try:
            bars = fetch_daily(c)
        except Exception as e:                     # noqa: BLE001 - 1銘柄の失敗で止めない
            failed.append(c)
            return f"! {c}: {e}"
        save(CACHE / f"{c}.json", {"fetched": today, "bars": bars}, indent=None)
        time.sleep(SLEEP)
        return None

    with ThreadPoolExecutor(WORKERS) as ex:
        for i, msg in enumerate(ex.map(one, need), 1):
            if msg:
                print("  " + msg, file=sys.stderr)
            if i % 200 == 0:
                print(f"  {i}/{len(need)}", flush=True)
    print(f"失敗 {len(failed)}銘柄: {failed[:20]}")


def monthly_for(code):
    c = load(CACHE_MO / f"{code}.json")
    if c and c.get("bars"):
        return c["bars"]
    bars = fetch_monthly(code)
    time.sleep(SLEEP)
    if bars:
        save(CACHE_MO / f"{code}.json",
             {"month": date.today().strftime("%Y-%m"), "bars": bars}, indent=None)
    return bars


def prev_max(bars, idx):
    """各日の「その日を含まない直近365日の最高値」(fetch_newhigh.rolling_prev_max と同じ)。"""
    out = [None] * len(bars)
    dq = deque()
    ds = [date.fromisoformat(b[0]) for b in bars]
    for i in range(len(bars)):
        if i > 0:
            k = i - 1
            while dq and bars[dq[-1]][idx] <= bars[k][idx]:
                dq.pop()
            dq.append(k)
        left = ds[i] - timedelta(days=WINDOW_DAYS)
        while dq and ds[dq[0]] < left:
            dq.popleft()
        if dq:
            out[i] = bars[dq[0]][idx]
    return out


def rebuild(universe, start, end):
    """{date: [stock, ...]} と {date: 母集団数} を返す。"""
    per_day, uni_count, hits = {}, {}, []
    for code, (name, market) in universe.items():
        raw = (load(CACHE / f"{code}.json", {}) or {}).get("bars") or []
        bars, _ = clean_bars(raw)
        if len(bars) < 2:
            continue
        ds = [date.fromisoformat(b[0]) for b in bars]
        ph, pc = prev_max(bars, 1), prev_max(bars, 2)
        flags = [ph[i] is not None and bars[i][1] > ph[i] for i in range(len(bars))]
        for i, b in enumerate(bars):
            d = b[0]
            if d < start or d > end or i == 0:
                continue
            value = b[2] * b[3] / 1e6
            if value < MIN_VALUE:
                continue
            per_day.setdefault(d, [])
            uni_count[d] = uni_count.get(d, 0) + 1
            # fetch_newhigh は range=1y の日足で判定するので、窓の中の本数で揃える
            left = ds[i] - timedelta(days=WINDOW_DAYS)
            first = next(j for j in range(i + 1) if ds[j] >= left)
            hist = i - first + 1
            row = {"code": code, "name": name, "market": market, "close": b[2],
                   "change_pct": round((b[2] / bars[i - 1][2] - 1) * 100, 2),
                   "value": round(value), "_i": i, "_bars": bars, "_hist": hist,
                   "_new": flags[i] and hist >= 30}
            per_day[d].append(row)
            if not row["_new"]:
                continue
            prev_idx = next((j for j in range(i - 1, first - 1, -1) if flags[j]), None)
            row.update({
                "high": b[1], "prev52": ph[i],
                "break_pct": round((b[1] / ph[i] - 1) * 100, 2),
                "close_break": pc[i] is not None and b[2] > pc[i],
                "prev_date": bars[prev_idx][0] if prev_idx is not None else None,
                "gap": (i - prev_idx) if prev_idx is not None else None,
                "hist_days": hist, "short_hist": hist < SHORT_HIST,
            })
            hits.append(row)
    # 上場来: 52週新高値の銘柄だけ月足を見る
    codes = sorted({r["code"] for r in hits})
    print(f"52週新高値 {len(hits)}件・{len(codes)}銘柄 → 月足で上場来を判定")
    mo = {}
    for c in codes:
        try:
            mo[c] = monthly_for(c)
        except Exception as e:                     # noqa: BLE001
            print(f"  ! 月足 {c}: {e}", file=sys.stderr)
            mo[c] = None
    for r in hits:
        bars, i, m = r["_bars"], r["_i"], mo.get(r["code"])
        d = bars[i][0]
        if not m:
            r.update({"prev_ath": None, "ath_since": None, "ath": None, "ath_break_pct": None})
            continue
        vals = [h for md, h in m if md[:7] < d[:7]] + [x[1] for x in bars[:i]]
        prev = max(vals)
        r["prev_ath"] = round(prev, 1)
        r["ath_since"] = m[0][0]
        r["ath"] = bool(r["high"] >= prev)
        r["ath_break_pct"] = round((r["high"] / prev - 1) * 100, 2) if r["ath"] else None
    out = {}
    for d, rows in per_day.items():
        rows.sort(key=lambda x: -x["value"])
        for k, r in enumerate(rows, 1):
            r["rank"] = k
        keep = []
        for r in rows:
            if r["_new"]:
                keep.append({k: r[k] for k in (
                    "rank", "code", "name", "market", "close", "change_pct", "value",
                    "high", "prev52", "break_pct", "close_break", "prev_date", "gap",
                    "hist_days", "short_hist", "prev_ath", "ath_since", "ath",
                    "ath_break_pct")})
        out[d] = keep
    return out, uni_count


def compare(rebuilt):
    """実記録のある日について、再現と実記録の銘柄の一致を数える。"""
    tot_real = tot_rec = tot_both = ath_real = ath_both = 0
    lines = []
    for p in sorted(DOCS.glob("????-??-??.json")):
        real = load(p)
        if not real or real.get("reconstructed") or p.stem not in rebuilt:
            continue
        a = {s["code"] for s in real["stocks"]}
        b = {s["code"] for s in rebuilt[p.stem]}
        aa = {s["code"] for s in real["stocks"] if s.get("ath")}
        ba = {s["code"] for s in rebuilt[p.stem] if s.get("ath")}
        tot_real += len(a)
        tot_rec += len(b)
        tot_both += len(a & b)
        ath_real += len(aa)
        ath_both += len(aa & ba)
        lines.append(f"{p.stem} 実{len(a):3d} 再現{len(b):3d} 一致{len(a & b):3d}"
                     f"  実のみ{sorted(a - b)[:6]} 再現のみ{sorted(b - a)[:6]}")
    print("\n".join(lines))
    if tot_real:
        print(f"\n合計: 実記録 {tot_real}件 / 再現 {tot_rec}件 / 一致 {tot_both}件"
              f"  → 実記録の再現率 {tot_both / tot_real:.1%}・再現の適合率 {tot_both / tot_rec:.1%}")
        print(f"上場来: 実記録 {ath_real}件のうち再現でも上場来 {ath_both}件")
    return {"real": tot_real, "rebuilt": tot_rec, "both": tot_both,
            "ath_real": ath_real, "ath_both": ath_both}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--start", default="2026-06-23")
    ap.add_argument("--end", default=date.today().isoformat())
    ap.add_argument("--compare", action="store_true", help="突き合わせだけで書き込まない")
    args = ap.parse_args()

    universe = load_universe()
    print(f"一覧: 東証3市場 {len(universe)}銘柄")
    if args.fetch:
        fetch_all(sorted(universe), date.today().isoformat())
        return

    rebuilt, uni = rebuild(universe, args.start, args.end)
    stats = compare(rebuilt)
    if args.compare:
        return
    written = []
    for d in sorted(rebuilt):
        path = DOCS / f"{d}.json"
        if path.exists():
            continue                                # 実記録は上書きしない
        stocks = rebuilt[d]
        fresh = [s for s in stocks if s["gap"] is None or s["gap"] > FRESH_DAYS]
        save(path, {
            "date": d, "as_of": f"{d} 15:30", "updated": d,
            "generated": datetime.now().astimezone().isoformat(timespec="seconds"),
            "reconstructed": True,
            "note": "日足から後日再現した記録(母集団は終値×出来高10億円以上・順位も再現値)",
            "match": stats,
            "min_value": MIN_VALUE, "fresh_days": FRESH_DAYS, "window_days": WINDOW_DAYS,
            "counts": {
                "scanned": uni.get(d, 0), "universe": uni.get(d, 0), "new_high": len(stocks),
                "fresh": len(fresh), "close_break": sum(1 for s in stocks if s["close_break"]),
                "ath": sum(1 for s in stocks if s.get("ath")),
                "failed": 0, "stale": 0, "ath_failed": sum(1 for s in stocks if s["ath"] is None),
            },
            "failed": [], "stocks": stocks,
        })
        written.append(d)
    dates = sorted((p.stem for p in DOCS.glob("????-??-??.json")
                    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.stem)), reverse=True)
    rec = [d for d in dates if (load(DOCS / f"{d}.json") or {}).get("reconstructed")]
    save(DOCS / "index.json", {"dates": dates, "updated": dates[0] if dates else None,
                               "reconstructed": rec})
    print(f"\n再現して書いた日: {len(written)}日 {written}")


if __name__ == "__main__":
    main()
