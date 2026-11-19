# -*- coding: utf-8 -*-
"""SBI証券「NISAランキング(国内株式)」の週間ランキングを記録し、
docs/data_nisa/data.json を再生成する。

ランキングは「買付金額」「出来高」「保有残高」の3種で各10位まで。
SBIのページは最新1週分しか出さず、期間を選べない。過去分は次の2つで補う。

  wayback … Internet Archive に保存された同じページ(2015年〜、飛び飛び)
  zai     … ザイ・オンライン(ダイヤモンド)の週次記事。SBIの表を転載したもの
            (2025年9月頃〜ほぼ毎週)

同じ週が複数の取得元にあるときは sbi > wayback > zai の順で採用する。
どれもSBIの同じ表なので中身は同じはずだが、出どころは src で残す。

使い方:
  python fetch_nisa.py                 … 最新週をSBIから取得してビルド(定時実行用)
  python fetch_nisa.py --wayback       … Wayback の保存分を取り込んでビルド
  python fetch_nisa.py --zai           … ザイの記事を取り込んでビルド
  python fetch_nisa.py --build         … 取得せずビルドだけ

生データは nisa_raw/<src>/<週の開始日>.json に1週1ファイルで置く。
"""
import argparse
import gzip
import json
import re
import sys
import time
import urllib.request
from datetime import date
from html import unescape
from pathlib import Path

BASE = Path(__file__).parent
RAW = BASE / "nisa_raw"
OUT_DIR = BASE / "docs" / "data_nisa"
OUT = OUT_DIR / "data.json"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
SBI_URL = ("https://site1.sbisec.co.jp/ETGate/?_ControlID=WPLETmgR001Control"
           "&_PageID=WPLETmgR001Mdtl20&_DataStoreID=DSWPLETmgR001Control"
           "&_ActionID=DefaultAID&burl=iris_ranking&cat1=market&cat2=ranking"
           "&dir=tl1-rnk%7Ctl2-nisa%7Ctl3-stock&file=index.html&getFlg=on")
ZAI_ARTICLE = "https://www.diamond.co.jp/zai/articles/-/{id}"
ZAI_RSS = "https://www.diamond.co.jp/zai/list/feed/rss"
SRC_ORDER = {"sbi": 0, "wayback": 1, "zai": 2}
KINDS = ("buy", "volume", "holding")
KIND_JA = {"買付金額": "buy", "出来高": "volume", "保有残高": "holding"}


def fetch(url, timeout=60, retries=3):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                b = r.read()
                if r.headers.get("Content-Encoding") == "gzip" or b[:2] == b"\x1f\x8b":
                    b = gzip.decompress(b)
                return b, r.status
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None, 404
            last = e
        except Exception as e:  # noqa: BLE001 Wayback はよく落ちるので何でも再試行
            last = e
        time.sleep(5 * (i + 1))
    raise RuntimeError(f"取得失敗 {url}: {last}")


def decode_sbi(b):
    # SBIのページは Shift_JIS(cp932)
    for enc in ("cp932", "utf-8"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            pass
    return b.decode("cp932", errors="replace")


def ymd(y, m, d):
    return date(int(y), int(m), int(d)).isoformat()


def clean(s):
    return unescape(re.sub(r"<[^>]+>", "", s)).strip()


# ---------------------------------------------------------------- SBI ページ
H3_RE = re.compile(r'<h3 class="rank-title[^"]*">(.*?)</h3>(.*?)(?=<h3 class="rank-title|※ ランキングのデータ算出定義|$)', re.S)
# cp932 で読むと「〜」は U+FF5E「～」になる。どちらでも当たるようにする
RANGE_RE = re.compile(r"(\d{4})/(\d{1,2})/(\d{1,2})\s*[〜～~]\s*(\d{4})/(\d{1,2})/(\d{1,2})")
ASOF_RE = re.compile(r"(\d{4})/(\d{1,2})/(\d{1,2})\s*現在")
ROW_RE = re.compile(r'<tr class="ranking-row">(.*?)</tr>', re.S)


def parse_sbi(html):
    """SBIのNISAランキングページ(現行・Wayback共通)から1週分を取り出す。"""
    week = None
    out = {"rankings": {}}
    for title, body in H3_RE.findall(html):
        t = clean(title)
        kind = next((v for k, v in KIND_JA.items() if k in t), None)
        if not kind:
            continue
        rows = []
        for tr in ROW_RE.findall(body):
            rk = re.search(r'class="rank-no[^"]*">(.*?)</td>', tr, re.S)
            rank_txt = rk.group(1) if rk else ""
            m = re.search(r'alt="(\d+)"', rank_txt) or re.search(r"(\d+)", clean(rank_txt))
            code = re.search(r'class="product-code[^"]*">\s*([0-9A-Z]{4})\s*<', tr)
            name = re.search(r'class="ranking-prod-link"[^>]*>(.*?)</td>', tr, re.S)
            fl = re.search(r'class="rank-fluctuation[^"]*">(.*?)</td>', tr, re.S)
            chg = ""
            if fl:
                a = re.search(r'alt="([^"]*)"', fl.group(1))
                chg = "NEW" if a and "NEW" in a.group(1) else clean(fl.group(1))
            if not (m and code and name):
                continue
            rows.append({"rank": int(m.group(1)), "code": code.group(1),
                         "name": clean(name.group(1)), "chg": chg})
        if not rows:
            continue
        out["rankings"][kind] = rows
        if kind == "holding":
            a = ASOF_RE.search(body)
            if a:
                out["holding_asof"] = ymd(*a.groups())
        else:
            r = RANGE_RE.search(body)
            if r and not week:
                week = (ymd(*r.groups()[:3]), ymd(*r.groups()[3:]))
        out.setdefault("label", t)
    if not week:
        r = RANGE_RE.search(html)
        if r:
            week = (ymd(*r.groups()[:3]), ymd(*r.groups()[3:]))
    if not week or not out["rankings"]:
        return None
    out["week_start"], out["week_end"] = week
    out["scheme"] = "成長投資枠" if "成長投資枠" in out.get("label", "") else "旧NISA"
    out.pop("label", None)
    return out


def save_raw(src, rec):
    d = RAW / src
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{rec['week_start']}.json"
    old = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None
    # 同じ週を複数回取ったときは、行数が多いほう(=欠けていないほう)を残す。
    # 中身が同じなら書き換えない(取得日だけ変わって毎日コミットが走るのを防ぐ)
    if old and (old["rankings"] == rec["rankings"] or
                sum(len(v) for v in old["rankings"].values()) > sum(len(v) for v in rec["rankings"].values())):
        return False
    p.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    return old is None


def cmd_live():
    b, _ = fetch(SBI_URL)
    rec = parse_sbi(decode_sbi(b))
    if not rec:
        raise SystemExit("SBIのページからランキングを読み取れませんでした(構成変更の可能性)")
    rec["src"] = "sbi"
    rec["fetched"] = date.today().isoformat()
    rec["url"] = SBI_URL
    new = save_raw("sbi", rec)
    n = {k: len(v) for k, v in rec["rankings"].items()}
    print(f"SBI: {rec['week_start']}〜{rec['week_end']} {n} {'(新しい週)' if new else '(取得済みの週)'}")


# ---------------------------------------------------------------- Wayback
CDX = ("https://web.archive.org/cdx/search/cdx?url={host}/ETGate&matchType=prefix"
       "&filter=original:.*tl2-nisa.*tl3-stock.*&fl=timestamp,statuscode,digest,original&limit=2000")


def cmd_wayback(cdx_file=None):
    """cdx_file: CDX の応答(timestamp statuscode digest original)を保存したファイル。
    www.sbisec.co.jp の CDX は件数が多く 504 で落ちやすいので、curl 等で取れたものを渡せるようにしてある。"""
    snaps = {}
    texts = []
    if cdx_file:
        texts.append(Path(cdx_file).read_text(encoding="utf-8", errors="replace"))
    else:
        for host in ("site1.sbisec.co.jp", "www.sbisec.co.jp"):
            try:
                b, _ = fetch(CDX.format(host=host), timeout=180, retries=5)
                texts.append(b.decode("utf-8", "replace"))
            except RuntimeError as e:
                print("  CDX取得失敗(このホストは飛ばす):", host, e)
    for text in texts:
        for line in text.splitlines():
            p = line.split(" ")
            if len(p) != 4 or p[1] != "200":
                continue  # CDX の statuscode フィルタは効かないことがあるので手元で絞る
            snaps.setdefault(p[2], (p[0], p[3]))   # 中身が同じ(digest)なら1回だけ
    done = {p.stem for p in (RAW / "wayback").glob("*.json")} if (RAW / "wayback").is_dir() else set()
    seen_weeks = set()
    print(f"Wayback: 候補 {len(snaps)} 件")
    for ts, orig in sorted(snaps.values()):
        try:
            b, st = fetch(f"https://web.archive.org/web/{ts}id_/{orig}", timeout=90, retries=4)
        except RuntimeError as e:
            print("  skip", ts, e)
            continue
        if not b:
            continue
        rec = parse_sbi(decode_sbi(b))
        if not rec:
            print("  読めず", ts)
            continue
        if rec["week_start"] in seen_weeks:
            continue
        seen_weeks.add(rec["week_start"])
        rec["src"] = "wayback"
        rec["archived"] = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]} {ts[8:10]}:{ts[10:12]}"
        rec["url"] = f"https://web.archive.org/web/{ts}/{orig}"
        new = save_raw("wayback", rec)
        print(f"  {ts} → {rec['week_start']} {rec['scheme']} {'追加' if new and rec['week_start'] not in done else ''}")
        time.sleep(1.5)


# ---------------------------------------------------------------- ザイ
ZAI_TITLE_RE = re.compile(r"<title>([^<]*)</title>")
ZAI_TABLE_RE = re.compile(r"<table[^>]*>(.*?)</table>", re.S)
ZAI_ROW_RE = re.compile(r"(\d+)位.*?\((.*?)\)</td>\s*<td[^>]*>(.*?)</td>", re.S)
ZAI_NAME_RE = re.compile(r"^(.*?)[（(]([0-9A-Z]{4})[）)]\s*$")
ZAI_PERIOD_RE = re.compile(r"(\d{4})/(\d{1,2})/(\d{1,2})\s*[～〜~]\s*(\d{4})/(\d{1,2})/(\d{1,2})")


def is_zai_nisa_stock(title):
    return "NISA口座" in title and "SBI証券" in title and "日本株" in title and "ランキング" in title


def parse_zai(html, aid):
    title = clean(ZAI_TITLE_RE.search(html).group(1)) if ZAI_TITLE_RE.search(html) else ""
    if not is_zai_nisa_stock(title):
        return None
    # 本文冒頭の期間が前週のまま直っていない記事がある(4/20週の記事に「4/13～4/17」)。
    # 題名の「M/D～M/D」と一致する期間を優先し、無ければ最初に出てくる期間を使う
    text = re.sub(r"<[^>]+>", "", html)
    pers = list(ZAI_PERIOD_RE.finditer(text))
    if not pers:
        return None
    tm = re.search(r"(\d{1,2})/(\d{1,2})\s*[～〜~]", title)
    per = next((p for p in pers if tm and (int(p.group(2)), int(p.group(3))) == (int(tm.group(1)), int(tm.group(2)))), pers[0])
    rec = {"week_start": ymd(*per.groups()[:3]), "week_end": ymd(*per.groups()[3:]),
           "scheme": "成長投資枠", "rankings": {}}
    for tb in ZAI_TABLE_RE.findall(html):
        h = re.search(r"<h3>(.*?)</h3>", tb, re.S)
        if not h:
            continue
        ht = clean(h.group(1))
        kind = next((v for k, v in KIND_JA.items() if k in ht), None)
        if not kind or "日本株" not in ht:
            continue
        rows = []
        # 記事によって「(前週比)」の入れ子が違う(</font>の前後など)ので、行ごとにセルを分けて読む
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", tb, re.S):
            tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
            if len(tds) < 2:
                continue
            head = clean(tds[0])
            rk = re.match(r"\s*(\d+)位", head)
            nm = ZAI_NAME_RE.match(clean(tds[1]))
            if not (rk and nm):
                continue
            ch = re.search(r"\((.*?)\)", head, re.S)
            c = ch.group(1).strip() if ch else ""
            rows.append({"rank": int(rk.group(1)), "code": nm.group(2), "name": nm.group(1).strip(),
                         "chg": "NEW" if "NEW" in c.upper() or "初" in c else c})
        if rows:
            rec["rankings"][kind] = rows
            if kind == "holding":
                a = re.search(r"(\d{4})/(\d{1,2})/(\d{1,2})現在", re.sub(r"<[^>]+>", "", tb))
                if a:
                    rec["holding_asof"] = ymd(*a.groups())
    if not rec["rankings"]:
        return None
    rec["src"] = "zai"
    rec["title"] = title.split(" | ")[0]
    rec["url"] = ZAI_ARTICLE.format(id=aid)
    return rec


def zai_max_id():
    b, _ = fetch(ZAI_RSS)
    ids = [int(x) for x in re.findall(r"/zai/articles/-/(\d+)", b.decode("utf-8", "replace"))]
    return max(ids) if ids else 800


def cmd_zai(start=1, end=None):
    """記事IDを総当たりで見る。題名の照合結果は nisa_raw/zai_index.json に残し、2回目以降は新しいIDだけ見る。"""
    idx_p = RAW / "zai_index.json"
    idx = json.loads(idx_p.read_text(encoding="utf-8")) if idx_p.is_file() else {}
    end = end or zai_max_id()
    print(f"ザイ: 記事ID {start}〜{end}")
    for aid in range(start, end + 1):
        k = str(aid)
        if k in idx and not idx[k].get("match"):
            continue           # 対象外と分かっている記事は見直さない
        try:
            b, st = fetch(ZAI_ARTICLE.format(id=aid), timeout=40, retries=2)
        except RuntimeError as e:
            print("  skip", aid, e)
            continue
        if not b:
            idx[k] = {"match": False, "status": st}
            continue
        html = b.decode("utf-8", "replace")
        t = ZAI_TITLE_RE.search(html)
        title = clean(t.group(1)) if t else ""
        rec = parse_zai(html, aid)
        idx[k] = {"match": bool(rec), "title": title.split(" | ")[0][:120]}
        if rec:
            save_raw("zai", rec)
            print(f"  {aid} → {rec['week_start']} {{{', '.join(f'{x}:{len(v)}' for x, v in rec['rankings'].items())}}}")
        elif is_zai_nisa_stock(title):
            print(f"  {aid} 題名は該当するが表を読めず: {title[:60]}")
        time.sleep(0.6)
        if aid % 50 == 0:
            idx_p.parent.mkdir(parents=True, exist_ok=True)
            idx_p.write_text(json.dumps(idx, ensure_ascii=False, indent=0), encoding="utf-8")
    idx_p.parent.mkdir(parents=True, exist_ok=True)
    idx_p.write_text(json.dumps(idx, ensure_ascii=False, indent=0), encoding="utf-8")


# ---------------------------------------------------------------- 初登場
# 「初登場」は種類(買付金額/出来高/保有残高)ごとに、記録した全週でその銘柄が初めて現れた週。
# 2024-04-08週より前は Wayback の飛び飛びしか無いので、そこでの「初」は判定しない(履歴としてだけ使う)。
# それ以降はほぼ毎週そろっている(欠けは数週)ので、欠けた週に出ていた銘柄を初登場と誤判定する余地は小さい。
FIRST_FROM = "2024-04-15"
STATE = BASE / "state_nisa.json"
WEBHOOK_KEY = "nisa_ranking"      # 実体は automation/webhooks.json(git管理外)
SITE = "https://al00000000.github.io/kabulog/#nisa"
KIND_LABEL = {"buy": "買付金額", "volume": "出来高", "holding": "保有残高"}


def mark_first(rows):
    """first: そのランキングに初めて入った / first_top3: そのランキングで初めて3位以内に入った(判定期間は同じ)"""
    seen = {k: set() for k in KINDS}
    seen3 = {k: set() for k in KINDS}
    for w in rows:
        for k, lst in (w.get("rankings") or {}).items():
            for r in lst:
                r.pop("first", None)
                r.pop("first_top3", None)
                if w["week_start"] >= FIRST_FROM:
                    if r["code"] not in seen[k]:
                        r["first"] = True
                    if r["rank"] <= 3 and r["code"] not in seen3[k]:
                        r["first_top3"] = True
            seen[k].update(r["code"] for r in lst)
            seen3[k].update(r["code"] for r in lst if r["rank"] <= 3)


def notify_first(data, force_week=None):
    """最新週に初登場があれば Discord に1回だけ通知する(通知済みの週は state_nisa.json に残す)。"""
    weeks = data.get("weeks") or []
    if not weeks:
        return
    w = weeks[-1] if not force_week else next(x for x in weeks if x["week_start"] == force_week)
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.is_file() else {"notified": []}
    if w["week_start"] in state["notified"] and not force_week:
        print("通知: 通知済みの週", w["week_start"])
        return
    hits = [(k, r) for k in KINDS for r in (w["rankings"].get(k) or []) if r.get("first") or r.get("first_top3")]
    period = f"{int(w['week_start'][5:7])}/{int(w['week_start'][8:])}〜{int(w['week_end'][5:7])}/{int(w['week_end'][8:])}"
    if hits:
        def tag(r):
            return "・".join(t for t, f in (("初登場", r.get("first")), ("初TOP3", r.get("first_top3"))) if f)
        firsts = list(dict.fromkeys(r["name"] for _, r in hits if r.get("first")))
        top3s = list(dict.fromkeys(r["name"] for _, r in hits if r.get("first_top3")))
        head = " / ".join(s for s in (firsts and "初登場: " + "、".join(firsts),
                                      top3s and "初TOP3: " + "、".join(top3s)) if s)
        fields = []
        for k in KINDS:
            lst = [r for kk, r in hits if kk == k]
            if lst:
                fields.append({"name": f"{KIND_LABEL[k]}ランキング", "inline": False,
                               "value": "\n".join(f"**{r['rank']}位** {r['name']}（{r['code']}）〔{tag(r)}〕" for r in lst)})
        payload = {
            "content": f"NISA {head}",     # プッシュ通知に出る1行
            "embeds": [{"title": f"SBI証券 NISAランキング 初登場・初TOP3（{period}週）", "url": SITE,
                        "color": 0xffd166, "fields": fields,
                        "footer": {"text": "成長投資枠・国内株式。2024年4月以降の記録で、初めて上位10位(初登場)/3位以内(初TOP3)に入った銘柄"}}],
        }
        names = head
        sys.path.insert(0, str(BASE))
        from webhook_config import get_webhook
        req = urllib.request.Request(get_webhook(WEBHOOK_KEY), data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json", "User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            print("通知: 送信", r.status, names)
    else:
        print("通知: 初登場・初TOP3なし", w["week_start"])
    if w["week_start"] not in state["notified"]:
        state["notified"].append(w["week_start"])
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------------------------------------------------------------- 登場後1か月の騰落率
# 起点 = 集計週の最終日以前で最後の営業日の終値(ランキングが確定した時点)
# 1か月後 = 起点日から暦で1か月後の日以前で最後の営業日の終値
# 株価は Yahoo の日足(分割調整済み)。系列ごとに1回で取り直すので、取得時期で分割調整がずれることはない
# (既存の cache_bars_* は取得時期ごとに調整状態が違い、混ぜると壊れる)。
BARS = BASE / "cache_nisa_bars"
YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/{sym}.T?period1={p1}&period2={p2}&interval=1d"
BARS_FROM = "2018-08-01"
REFRESH_DAYS = 45          # 起点がこれより新しい週の銘柄は毎回取り直す(1か月後の値がまだ確定していない)


def add_month(d):
    y, m = (d.year + (d.month == 12), d.month % 12 + 1)
    for day in (d.day, 30, 29, 28):
        try:
            return date(y, m, day)
        except ValueError:
            continue


def fetch_bars(code):
    import calendar
    p1 = calendar.timegm(date.fromisoformat(BARS_FROM).timetuple())
    p2 = calendar.timegm(date.today().timetuple()) + 86400 * 2
    b, st = fetch(YAHOO.format(sym=code, p1=p1, p2=p2), timeout=40, retries=3)
    if not b:
        return None
    j = json.loads(b)
    res = (j.get("chart") or {}).get("result") or []
    if not res or not res[0].get("timestamp"):
        return None
    r = res[0]
    closes = r["indicators"]["quote"][0].get("close") or []
    out = []
    from datetime import datetime, timedelta, timezone
    jst = timezone(timedelta(hours=9))
    for ts, c in zip(r["timestamp"], closes):
        if c is not None:
            out.append([datetime.fromtimestamp(ts, jst).date().isoformat(), round(c, 2)])
    return out


def load_bars(codes_refresh, codes_all):
    BARS.mkdir(exist_ok=True)
    bars = {}
    for code in sorted(codes_all):
        p = BARS / f"{code}.json"
        if code in codes_refresh or not p.is_file():
            try:
                rows = fetch_bars(code)
            except RuntimeError as e:
                print("  株価取得失敗", code, e)
                rows = None
            p.write_text(json.dumps({"code": code, "fetched": date.today().isoformat(), "bars": rows or []}), encoding="utf-8")
            time.sleep(0.4)
        bars[code] = json.loads(p.read_text(encoding="utf-8"))["bars"]
    return bars


def close_on_or_before(series, d):
    import bisect
    i = bisect.bisect_right(series, [d, float("inf")]) - 1
    return series[i] if i >= 0 else None


def add_returns(rows, fetch_prices=True):
    codes_all = {r["code"] for w in rows for v in w["rankings"].values() for r in v}
    cutoff = date.fromordinal(date.today().toordinal() - REFRESH_DAYS).isoformat()
    codes_refresh = {r["code"] for w in rows if w["week_end"] >= cutoff
                     for v in w["rankings"].values() for r in v} if fetch_prices else set()
    bars = load_bars(codes_refresh, codes_all) if fetch_prices else {
        c: json.loads((BARS / f"{c}.json").read_text(encoding="utf-8"))["bars"]
        for c in codes_all if (BARS / f"{c}.json").is_file()}
    last_day = max((s[-1][0] for s in bars.values() if s), default="")
    n_ok = n_pend = n_na = 0
    for w in rows:
        for v in w["rankings"].values():
            for r in v:
                for k in ("r1m", "r1m_pending"):
                    r.pop(k, None)
                s = bars.get(r["code"]) or []
                base = close_on_or_before(s, w["week_end"])
                # 起点が集計週から離れすぎている(上場前・データ欠け)ものは使わない
                if not base or (date.fromisoformat(w["week_end"]) - date.fromisoformat(base[0])).days > 6:
                    n_na += 1
                    continue
                tgt_day = add_month(date.fromisoformat(base[0])).isoformat()
                if tgt_day > last_day:
                    r["r1m_pending"] = True
                    n_pend += 1
                    continue
                tgt = close_on_or_before(s, tgt_day)
                if not tgt or tgt[0] <= base[0]:
                    n_na += 1
                    continue
                r["r1m"] = round((tgt[1] / base[1] - 1) * 100, 2)
                n_ok += 1
    print(f"1か月騰落率: 算出 {n_ok} / 集計中 {n_pend} / 株価なし {n_na}(株価は {last_day} まで)")


# ---------------------------------------------------------------- ビルド
def build(fetch_prices=True):
    weeks = {}
    for src in SRC_ORDER:
        for p in sorted((RAW / src).glob("*.json")) if (RAW / src).is_dir() else []:
            rec = json.loads(p.read_text(encoding="utf-8"))
            ws = rec["week_start"]
            cur = weeks.get(ws)
            if cur is None or SRC_ORDER[src] < SRC_ORDER[cur["src"]]:
                if cur:
                    rec.setdefault("also", []).append(cur["src"])
                weeks[ws] = rec
            else:
                cur.setdefault("also", []).append(src)
    rows = []
    for ws in sorted(weeks):
        r = weeks[ws]
        rows.append({k: r[k] for k in ("week_start", "week_end", "scheme", "src", "url", "rankings",
                                        "holding_asof", "archived", "fetched", "title", "also") if k in r})
    mark_first(rows)
    add_returns(rows, fetch_prices)
    latest = rows[-1]["week_start"] if rows else None
    # 反映日は「新しい週が増えたときだけ」進める(NEWバッジの誤爆防止、信用評価損益率タブと同じ)
    updated = date.today().isoformat()
    if OUT.is_file():
        try:
            prev = json.loads(OUT.read_text(encoding="utf-8"))
            if prev.get("latest_week") == latest and len(prev.get("weeks", [])) == len(rows) and prev.get("updated"):
                updated = prev["updated"]
        except (ValueError, OSError):
            pass
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    data = {"updated": updated, "latest_week": latest, "weeks": rows}
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    # サイトのNEWバッジ判定は毎回読み込むので、本体ではなく軽い索引を見せる
    (OUT_DIR / "index.json").write_text(json.dumps(
        {"updated": updated, "latest_week": latest, "weeks": len(rows)}, ensure_ascii=False), encoding="utf-8")
    by = {}
    for r in rows:
        by[r["src"]] = by.get(r["src"], 0) + 1
    print(f"ビルド: {len(rows)} 週 {by} 最新 {latest} updated {updated}")
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wayback", action="store_true")
    ap.add_argument("--cdx-file", help="--wayback で使う CDX 応答の保存ファイル")
    ap.add_argument("--zai", action="store_true")
    ap.add_argument("--zai-start", type=int, default=1)
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--notify-week", help="指定した週(開始日)の初登場を手動で通知する(動作確認用)")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if a.wayback:
        cmd_wayback(a.cdx_file)
    elif a.zai:
        cmd_zai(a.zai_start)
    elif not a.build:
        cmd_live()
        # 定時実行では新しいザイ記事も拾う(SBIを取り損ねた週の保険)。失敗しても本体は止めない
        try:
            idx_p = RAW / "zai_index.json"
            if idx_p.is_file():
                idx = json.loads(idx_p.read_text(encoding="utf-8"))
                cmd_zai(max(int(k) for k in idx) + 1)
        except Exception as e:  # noqa: BLE001
            print("ザイの追加取得に失敗(続行):", e)
        notify_first(build())   # 定時実行のときだけ通知する(過去分の取り込みでは鳴らさない)
        return
    data = build()
    if a.notify_week:
        notify_first(data, force_week=a.notify_week)


if __name__ == "__main__":
    main()
