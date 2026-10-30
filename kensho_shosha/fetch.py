"""総合商社5社と海運大手3社の実績EPSと日足を集める.

商社: IRBANK results の EPS/BPS (分割補正済み。三菱3:1・三井2:1・伊藤忠5:1・住商4:1で確認)
海運: ../kensho_kaiun/result.json の fy_table (IRBANKは川崎の分割補正が年により不完全なので自前計算の値)
株価: Yahoo 日足 close (分割補正済み・配当は含まない)
出力: data.json
"""
import datetime as dt
import json
import os
import re
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
SHOSHA = {"8001": "伊藤忠商事", "8002": "丸紅", "8031": "三井物産", "8053": "住友商事", "8058": "三菱商事"}
KAIUN = {"9101": "日本郵船", "9104": "商船三井", "9107": "川崎汽船"}
# fy_table に無い期 (IRBANKの値。同社の2022/03はfy_tableと一致するので基準は同じ)
KAIUN_PATCH = {("9101", "2023/03"): 1993.71,
               # 今期の会社予想 (2026年7〜8月の上方修正後。../kensho_kaiun/forecasts_raw.csv)
               ("9101", "2027/03予"): 594.49, ("9104", "2027/03予"): 698.27, ("9107", "2027/03予"): 220.79}


def num(s):
    s = s.replace("*", "").replace(",", "")
    for k, v in {"兆": 1e12, "億": 1e8}.items():
        if s.endswith(k):
            return float(s[:-1]) * v
    try:
        return float(s)
    except ValueError:
        return None


def irbank(code):
    t = requests.get(f"https://irbank.net/{code}/results", headers=UA, timeout=30).text
    rows = {}
    for m in re.finditer(r"<tr[^>]*>(.*?)</tr>", t, re.S):
        cells = [re.sub(r"<[^>]+>", "", x).strip() for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", m.group(1), re.S)]
        if cells and re.match(r"20(1[5-9]|2\d)/03", cells[0]):
            rows.setdefault(cells[0], []).append(cells)
    fy = {}
    for k, v in rows.items():
        fy[k] = {"eps": num(v[0][5])}  # 1つ目の表: 年度|収益|営利|当期利益|包括|EPS
        if len(v) > 1:
            fy[k]["bps"] = num(v[1][-1])  # 2つ目の表の最終列がBPS
    return fy


def kaiun_fy():
    tab = json.load(open(os.path.join(HERE, "..", "kensho_kaiun", "result.json"), encoding="utf-8"))["fy_table"]
    out = {c: {} for c in KAIUN}
    for r in tab:
        if r["code"] in KAIUN and r["actual"] is not None:
            out[r["code"]][r["fy"].replace("-", "/")] = {"eps": r["actual"]}
    for (c, f), v in KAIUN_PATCH.items():
        out[c].setdefault(f, {"eps": v})
    return out


def yahoo(code):
    q = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{code}.T"
                     "?period1=1546300800&period2=1830297600&interval=1d", headers=UA, timeout=30).json()
    r = q["chart"]["result"][0]
    return [(dt.datetime.fromtimestamp(ts + 9 * 3600, dt.timezone.utc).strftime("%Y-%m-%d"), round(c, 3))
            for ts, c in zip(r["timestamp"], r["indicators"]["quote"][0]["close"]) if c]


if __name__ == "__main__":
    out = {"names": {**SHOSHA, **KAIUN}, "shosha": list(SHOSHA), "kaiun": list(KAIUN), "fy": {}, "px": {}}
    for c in SHOSHA:
        out["fy"][c] = irbank(c)
        time.sleep(1)
    out["fy"].update(kaiun_fy())
    for c in out["names"]:
        out["px"][c] = yahoo(c)
        print(c, out["names"][c], out["px"][c][-1], {k: v["eps"] for k, v in out["fy"][c].items() if k >= "2019"})
    json.dump(out, open(os.path.join(HERE, "data.json"), "w", encoding="utf-8"), ensure_ascii=False)
