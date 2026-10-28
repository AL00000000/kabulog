# -*- coding: utf-8 -*-
"""午前引値(11:30)を Yahoo の60分足から取る。地合いフィルター版(regime.py)の判定に使う。

Yahoo の60分足は約730日(2023-10末〜)まで遡れる。11:00 の足(11:00〜11:30)の終値が午前引値。
日足の終値と調整(分割)の基準がずれていても困らないよう、「午前引値 ÷ 同じ日の60分足の大引け」
の比率で保存し、使うときに日足の終値に掛ける。

出力: cache_bars_am/{code}.json = {"r": {"YYYY-MM-DD": 比率}}(N225 は ^N225)
使用例: py kensho_newhigh/fetch_am.py
"""
import json
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "cache_bars_am"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def get(url):
    for k in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (404, 422):
                return e.code
            time.sleep(3 * (k + 1))
        except Exception:                      # noqa: BLE001
            time.sleep(3 * (k + 1))
    return None


def fetch(sym):
    j = get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=730d&interval=60m")
    if j == 422:                               # 銘柄によっては range=730d を受け付けない。期間指定で取り直す
        now = int(time.time())
        j = get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
                f"?period1={now - 729 * 86400}&period2={now}&interval=60m")
    if j is None or j == 422:
        return None
    if j == 404:
        return {}
    res = (j.get("chart") or {}).get("result") or []
    if not res:
        return {}
    ts = res[0].get("timestamp") or []
    cl = (((res[0].get("indicators") or {}).get("quote") or [{}])[0]).get("close") or []
    am, pm = {}, {}
    for t, c in zip(ts, cl):
        if c is None:
            continue
        dt = datetime.fromtimestamp(t + 32400, tz=timezone.utc)
        d = dt.date().isoformat()
        if dt.hour < 12:
            am[d] = c                          # 午前の最後に約定した足(通常は11:00の足)
        pm[d] = c                              # その日の最後の足 = 大引け
    return {d: round(am[d] / pm[d], 6) for d in am if pm.get(d)}


def job(code):
    p = OUT / f"{code}.json"
    if p.exists():
        return code, "skip"
    sym = code if code.startswith("^") else f"{code}.T"
    r = fetch(sym)
    if r is None:
        return code, "fail"
    p.write_text(json.dumps({"fetched": datetime.now().isoformat(timespec="seconds"), "r": r}),
                 encoding="utf-8")
    return code, len(r)


def main():
    OUT.mkdir(exist_ok=True)
    codes = sorted({p.stem for p in (BASE / "cache_bars_5y").glob("*.json")}
                   | {p.stem for p in (BASE / "cache_bars_hist").glob("*.json")})
    codes = ["^N225"] + codes
    n = 0
    with ThreadPoolExecutor(4) as ex:
        for code, st in ex.map(job, codes):
            n += 1
            if st == "fail" or n % 200 == 0:
                print(n, len(codes), code, st, flush=True)
    print("done", flush=True)


if __name__ == "__main__":
    sys.exit(main())
