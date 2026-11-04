# 内国株全銘柄の日足(Yahoo close=分割調整のみ)と発行済株式数(株探)をスクラッチに集める。
# 既存キャッシュは読むだけで書き換えない。途中再開可。
import io, json, re, sys, time, threading, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
import openpyxl, xlrd

BASE = Path(r"C:\Users\yt\kabulog\kabutan-ranking")
OUT = Path(__file__).parent / "data"
(OUT / "bars").mkdir(parents=True, exist_ok=True)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
JST = timezone(timedelta(hours=9))
P1 = int(datetime(2025, 12, 1, tzinfo=JST).timestamp())
P2 = int(datetime(2026, 11, 6, tzinfo=JST).timestamp())
URL = "https://query1.finance.yahoo.com/v8/finance/chart/{c}.T?period1={a}&period2={b}&interval=1d"
SHARES_RE = re.compile(r"発行済株式数</th>\s*<td>([\d,]+)")


def universe():
    u = {}
    s = xlrd.open_workbook(str(BASE / "cache_jpx/data_j_202606.xls")).sheet_by_index(0)
    for r in range(1, s.nrows):
        v = s.row_values(r)
        if "内国株式" in str(v[3]):
            c = v[1]
            c = str(int(c)) if isinstance(c, float) else str(c)
            u[c] = {"name": v[2], "mkt": v[3].split("（")[0], "in": "202606"}
    wb = openpyxl.load_workbook(io.BytesIO((BASE / "cache_jpx/data_j_latest.xls").read_bytes()), read_only=True)
    for row in list(wb.worksheets[0].iter_rows(values_only=True))[1:]:
        if row[3] and "内国株式" in str(row[3]):
            c = str(row[1]).replace(".0", "")
            if c in u:
                u[c]["in"] = "both"
            else:
                u[c] = {"name": row[2], "mkt": row[3].split("（")[0], "in": "latest"}
    return u


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read()


def bars(u):
    n = ok = miss = 0
    for c in u:
        n += 1
        f = OUT / "bars" / f"{c}.json"
        if f.exists():
            continue
        for k in range(3):
            try:
                j = json.loads(get(URL.format(c=c, a=P1, b=P2)))
                res = j["chart"]["result"][0]
                q = res["indicators"]["quote"][0]
                b = [[datetime.fromtimestamp(t, JST).strftime("%Y-%m-%d"), round(x, 2), q["volume"][i] or 0]
                     for i, (t, x) in enumerate(zip(res.get("timestamp", []), q.get("close", []))) if x is not None]
                f.write_text(json.dumps(b), encoding="utf8")
                ok += 1
                break
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    f.write_text("[]", encoding="utf8")
                    miss += 1
                    break
                time.sleep(5 * (k + 1))
            except Exception:
                time.sleep(5 * (k + 1))
        time.sleep(0.3)
        if n % 200 == 0:
            print("bars", n, "ok", ok, "404", miss, flush=True)
    print("bars done", n, ok, miss, flush=True)


def shares(u):
    p = OUT / "shares.json"
    d = json.loads(p.read_text(encoding="utf8")) if p.exists() else {}
    old = json.loads((BASE / "cache_period/shares.json").read_text(encoding="utf8"))
    for c, v in old.items():
        if c in u and c not in d and v.get("n"):
            d[c] = v["n"]
    n = 0
    for c in u:
        if c in d:
            continue
        n += 1
        for k in range(3):
            try:
                m = SHARES_RE.search(get(f"https://kabutan.jp/stock/?code={c}").decode("utf-8", "replace"))
                d[c] = int(m.group(1).replace(",", "")) if m else None
                break
            except Exception:
                time.sleep(5 * (k + 1))
        time.sleep(0.5)
        if n % 100 == 0:
            p.write_text(json.dumps(d), encoding="utf8")
            print("shares", n, flush=True)
    p.write_text(json.dumps(d), encoding="utf8")
    print("shares done", len(d), flush=True)


u = universe()
(OUT / "universe.json").write_text(json.dumps(u, ensure_ascii=False), encoding="utf8")
print("universe", len(u), flush=True)
ts = [threading.Thread(target=bars, args=(u,)), threading.Thread(target=shares, args=(u,))]
[t.start() for t in ts]
[t.join() for t in ts]
print("ALL DONE", flush=True)
