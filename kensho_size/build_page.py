# 時価総額帯別の騰落率ページ(docs/kensho_size.html)を作る。
# 先に fetch_all.py で data/ を作っておくこと。自動更新はしない(2026-11-04時点の固定レポート)。
import json, re
from pathlib import Path

import analyze as A

HERE = Path(__file__).parent
DOCS = HERE.parent / "docs"
PERIODS = {"h1": ("2025-12-30", "2026-06-30"), "h2": ("2026-06-30", "2026-11-04")}
ALT = {"h1": ("2026-01-05", "2026-06-30"), "h2": ("2026-07-01", "2026-11-04")}


def split(start, end):
    R, drop = A.rows(start, end)
    low = [x for x in R if x[0] <= 500]
    hi = [x for x in R if x[0] > 500]
    N = len(low)
    return dict(all=A.stats(R), low=A.stats(low), drop=drop,
                bands=[A.stats(hi[len(hi) * i // 4:len(hi) * (i + 1) // 4]) for i in range(4)],
                lows=[A.stats(low[N * i // 4:N * (i + 1) // 4]) for i in range(4)])


RES = {k: split(*v) for k, v in PERIODS.items()}
RES_ALT = {k: split(*v) for k, v in ALT.items()}
(HERE / "results.json").write_text(json.dumps({"base": RES, "alt": RES_ALT}, ensure_ascii=False, indent=1), encoding="utf8")


def oku(x):
    return f"約{x / 10000:.1f}兆円" if x >= 10000 else f"{x:,.0f}億円"


def pct(x):
    return f'<span class="{"pos" if x > 0 else "neg" if x < 0 else ""}">{x:+.1f}%</span>'


def row(label, s, cls=""):
    return (f'<tr{cls}><td>{label}</td><td class="n">{s["n"]:,}</td><td class="n">{pct(s["mean"])}</td>'
            f'<td class="n">{pct(s["med"])}</td><td class="n">{s["up"]:.0f}%</td></tr>')


def table(r):
    names = ["中型の下", "中型の上", "大型の下", "大型の上"]
    head = "<tr><th>基準日の時価総額</th><th>銘柄数</th><th>平均</th><th>中央値</th><th>上昇した割合</th></tr>"
    body = [row("500億円以下", r["low"])]
    for name, b in zip(names, r["bands"]):
        body.append(row(f'{oku(b["lo"])}〜{oku(b["hi"])}（{name}）', b))
    body.append(row("全体", r["all"], ' class="hl"'))
    return f'<div class="scroll"><table><thead>{head}</thead><tbody>{"".join(body)}</tbody></table></div>'


def change_table():
    names = ["500億円以下", "中型の下", "中型の上", "大型の下", "大型の上"]
    a = [RES["h1"]["low"]] + RES["h1"]["bands"]
    b = [RES["h2"]["low"]] + RES["h2"]["bands"]
    rows = "".join(
        f'<tr><td>{n}</td><td class="n">{pct(x["mean"])}</td><td class="n">{pct(y["mean"])}</td>'
        f'<td class="n">{pct(x["med"])}</td><td class="n">{pct(y["med"])}</td></tr>'
        for n, x, y in zip(names, a, b))
    return ('<div class="scroll"><table><thead><tr><th>帯</th><th>前半の平均</th><th>後半の平均</th>'
            f'<th>前半の中央値</th><th>後半の中央値</th></tr></thead><tbody>{rows}</tbody></table></div>')


def low_table(k):
    rows = "".join(row(f'{oku(s["lo"])}〜{oku(s["hi"])}', s) for s in RES[k]["lows"])
    return ('<div class="scroll"><table><thead><tr><th>基準日の時価総額</th><th>銘柄数</th><th>平均</th><th>中央値</th>'
            f'<th>上昇した割合</th></tr></thead><tbody>{rows}</tbody></table></div>')


def alt_table():
    rows = []
    for k, label in (("h1", "前半"), ("h2", "後半")):
        x, y = RES[k], RES_ALT[k]
        rows.append(f'<tr><td>{label}・500億円以下</td><td class="n">{pct(x["low"]["med"])}</td><td class="n">{pct(y["low"]["med"])}</td></tr>')
        for i, n in enumerate(["中型の下", "中型の上", "大型の下", "大型の上"]):
            rows.append(f'<tr><td>{label}・{n}</td><td class="n">{pct(x["bands"][i]["med"])}</td><td class="n">{pct(y["bands"][i]["med"])}</td></tr>')
    return ('<div class="scroll"><table><thead><tr><th>帯（中央値）</th><th>起点 12/30・6/30</th><th>起点 1/5・7/1</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')


head = (DOCS / "kensho_tob.html").read_text(encoding="utf8")
style = re.search(r"<style>.*?</style>", head, re.S).group(0)
fonts = "\n".join(re.findall(r"<link [^>]+>", head))
TITLE = "2026年前半から後半にかけて大型株から中型株に資金流入"
h1, h2 = RES["h1"], RES["h2"]

html = f"""<!doctype html>
<html lang="ja" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{TITLE}</title>
{fonts}
{style}
</head>
<body>
<div class="wrap">

<header class="top">
  <div class="eyebrow">仮説検証 / 時価総額別の騰落率</div>
  <h1>{TITLE}</h1>
  <p class="sub">内国株の全銘柄を基準日の時価総額で5つに分け、2026年の前半と後半の騰落率を比べました。騰落率の首位は大型から中型に移りましたが、<strong>測ったのは株価であり、資金の流れそのものは測っていません。</strong></p>
</header>

<div class="cards">
  <div class="card" style="--c:var(--neg)"><div class="lbl">500億円以下の中央値（前半 → 後半）</div><div class="big">{h1["low"]["med"]:+.1f}%</div><div class="foot">→ {h2["low"]["med"]:+.1f}%</div></div>
  <div class="card" style="--c:var(--slate)"><div class="lbl">大型の上の平均（前半 → 後半）</div><div class="big">{h1["bands"][3]["mean"]:+.1f}%</div><div class="foot">→ {h2["bands"][3]["mean"]:+.1f}%</div></div>
  <div class="card" style="--c:var(--teal)"><div class="lbl">中型の下の平均（前半 → 後半）</div><div class="big">{h1["bands"][0]["mean"]:+.1f}%</div><div class="foot">→ {h2["bands"][0]["mean"]:+.1f}%</div></div>
</div>

<div class="note"><strong>読み方。</strong>「資金流入」はページ名に合わせた解釈です。騰落率の順序から読んだもので、投資部門別の売買や帯ごとの買い越し額は確認していません。株価は少ない売買でも動くので、中型株の上昇だけでは資金が大型株から移った証拠にはなりません。</div>

<section>
  <h2><span class="n">01</span>前半：2025/12/30 → 2026/6/30</h2>
  <p class="lead">おおむね大きい銘柄ほど強い半年でした。</p>
  {table(h1)}
</section>

<section>
  <h2><span class="n">02</span>後半：2026/6/30 → 2026/11/4</h2>
  <p class="lead">500億円超の平均は小さい帯ほど高くなり、前半と順序が逆になりました。500億円以下だけは中央値がマイナスのままです。</p>
  {table(h2)}
</section>

<section>
  <h2><span class="n">03</span>前半と後半を並べる</h2>
  <p class="lead">帯の境目は期間ごとの基準日で決めているので、金額は前半と後半で少し違います。期間も約6か月と約4か月で長さが違い、年率換算はしていません。</p>
  {change_table()}
  <p class="small">「中型」は500億円超のうち下半分（約1,900億円まで）、「大型」は上半分を指す、このページだけの呼び方です。大型の上の中央値は後半も{h2["bands"][3]["med"]:+.1f}%とプラスで、平均のマイナスとは符号が違います。</p>
</section>

<section>
  <h2><span class="n">04</span>500億円以下の内訳</h2>
  <p class="lead">銘柄数で4等分しても、中央値に帯の差はほとんどありません。</p>
  <h3>前半</h3>
  {low_table("h1")}
  <h3>後半</h3>
  {low_table("h2")}
</section>

<section>
  <h2><span class="n">05</span>起点を1営業日ずらした場合</h2>
  <p class="lead">前半を1/5、後半を7/1の終値から測っても、傾向は変わりません。</p>
  {alt_table()}
</section>

<section>
  <h2><span class="n">06</span>条件と限界</h2>
  <ul>
    <li><strong>帯の分け方：</strong>500億円以下を1つの帯にし、500億円超を銘柄数が同じになるよう4等分しました。500億円以下が500億円超のほぼ2倍あるため、500億円以下と同じ銘柄数では上に刻めません。</li>
    <li><strong>対象：</strong>プライム・スタンダード・グロースの内国株です。ETF、REIT、優先株、起点より後に上場した銘柄は除きました（前半{h1["drop"]["上場前"]}銘柄、後半{h2["drop"]["上場前"]}銘柄）。</li>
    <li><strong>騰落率：</strong>Yahooの分割調整済み終値で計算し、配当は含みません。</li>
    <li><strong>時価総額は概算：</strong>基準日の終値に現在の発行済株式数を掛けています。その後に増資した銘柄は過大になります。</li>
    <li><strong>上場廃止の抜け：</strong>銘柄リストが2026年5月末時点より新しいものだけなので、1〜5月に廃止された銘柄は入っていません。影響の大きさは測っていません。</li>
    <li><strong>平均は急騰銘柄に引っ張られます：</strong>比較には中央値も併せて見てください。</li>
    <li><strong>対象期間：</strong>2026年の約10か月・2期間だけです。他の年でも同じかは検証していません。</li>
  </ul>
</section>

<footer>
  データ: 株価 Yahoo Finance ／ 発行済株式数 株探 ／ 銘柄一覧 JPX東証上場銘柄一覧<br>
  2026-11-04時点の固定レポートで、自動更新はしません。スクリプトは kabutan-ranking/kensho_size/ にあります。
</footer>

</div>
</body>
</html>
"""
(DOCS / "kensho_size.html").write_text(html, encoding="utf8")
print("written", len(html))
