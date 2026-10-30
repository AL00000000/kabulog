"""result.json, placebo.json → docs/kensho_kessan.html"""
import json, math, os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "docs", "kensho_kessan.html")
NAMES = {"9101": "日本郵船", "9104": "商船三井", "9107": "川崎汽船"}
COLORS = {"9101": "var(--slate)", "9104": "var(--teal)", "9107": "var(--brass)"}
TITLE = "海運株は決算で上がったのか"

R = json.load(open(os.path.join(HERE, "result.json"), encoding="utf-8"))
P = json.load(open(os.path.join(HERE, "placebo.json"), encoding="utf-8"))


def pct(x, d=0):
    return f"{x*100:.{d}f}%"


def mult(x):
    return f"{x:.2f}倍"


def sgn(x, d=0):
    cls = "pos" if x >= 0 else "neg"
    return f'<span class="{cls}">{x*100:+.{d}f}%</span>'


# ---- 累積リターンのチャート(対数軸・窓内を帯で塗る) ----
def chart(code):
    daily = R[code]["daily"]
    W, H, L, T, B = 860, 260, 46, 10, 28
    n = len(daily)
    lo, hi = math.log(0.25), math.log(16)  # 3社共通の目盛り
    x = lambda i: L + (W - L - 8) * i / (n - 1)
    y = lambda v: T + (H - T - B) * (hi - v) / (hi - lo)
    parts = []
    # 帯
    i = 0
    while i < n:
        if daily[i][2] != "out":
            j = i
            while j + 1 < n and daily[j + 1][2] != "out":
                j += 1
            parts.append(f'<rect x="{x(i)-1:.1f}" y="{T}" width="{x(j)-x(i)+2:.1f}" height="{H-T-B}" fill="var(--band)" />')
            i = j + 1
        else:
            i += 1
    # 目盛り
    for m in (0.25, 0.5, 1, 2, 4, 8, 16):
        yy = y(math.log(m))
        parts.append(f'<line x1="{L}" x2="{W-8}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="var(--line-soft)" />')
        parts.append(f'<text x="{L-6}" y="{yy+4:.1f}" text-anchor="end" font-size="11" fill="var(--ink-3)" class="num">{m:g}倍</text>')
    for k, (d, _, _) in enumerate(daily):
        if d[5:7] == "01" and (k == 0 or daily[k - 1][0][:4] != d[:4]):
            parts.append(f'<line x1="{x(k):.1f}" x2="{x(k):.1f}" y1="{T}" y2="{H-B}" stroke="var(--line)" />')
            parts.append(f'<text x="{x(k)+3:.1f}" y="{H-10}" font-size="11" fill="var(--ink-3)" class="num">{d[:4]}</text>')
    pts = " ".join(f"{x(k):.1f},{y(c):.1f}" for k, (_, c, _) in enumerate(daily))
    parts.append(f'<polyline points="{pts}" fill="none" stroke="{COLORS[code]}" stroke-width="1.8" />')
    return f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{NAMES[code]}の累積リターン">{"".join(parts)}</svg>'


# ---- 寄与の積み上げ棒 ----
def contrib_bar(code, key="ra"):
    d = R[code][key]
    segs = [("pre", "発表前5日", "var(--slate)"), ("day", "反応日", "var(--brass)"),
            ("post", "発表後5日", "var(--teal)"), ("out", "決算の間", "var(--ink-3)")]
    pos = [(lab, d[t]["share"], c) for t, lab, c in segs]
    html = '<div style="display:flex;height:22px;border-radius:2px;overflow:hidden;background:var(--surface-2)">'
    for lab, s, c in pos:
        if s > 0:
            html += f'<div title="{lab} {s*100:.0f}%" style="width:{s*100:.2f}%;background:{c};opacity:.85"></div>'
    html += "</div>"
    neg = [f"{lab} {s*100:.0f}%" for lab, s, _ in pos if s < 0]
    return html, neg


rows_main = ""
for code, nm in NAMES.items():
    d = R[code]["ra"]
    rows_main += (f'<tr><td><span class="tag" style="background:{COLORS[code]}"></span>{nm}（{code}）</td>'
                  f'<td class="n">{len(R[code]["events"])}回</td>'
                  f'<td class="n">{mult(d["total"]["mult"])}</td>'
                  f'<td class="n">{mult(d["in"]["mult"])}</td><td class="n">{mult(d["out"]["mult"])}</td>'
                  f'<td class="n"><b>{pct(d["in"]["share"])}</b></td>'
                  f'<td class="n">{d["in"]["n"]/d["total"]["n"]*100:.0f}%</td>'
                  f'<td class="n">{sgn(d["in"]["perday"],2)} / {sgn(d["out"]["perday"],2)}</td></tr>')

rows_alt = ""
for code, nm in NAMES.items():
    rows_alt += (f'<tr><td>{nm}</td><td class="n">{pct(R[code]["ra"]["in"]["share"])}</td>'
                 f'<td class="n">{pct(R[code]["rc"]["in"]["share"])}</td>'
                 f'<td class="n">{pct(R[code]["rx"]["in"]["share"])}</td></tr>')

rows_split = ""
for code, nm in NAMES.items():
    d = R[code]["ra"]
    rows_split += (f'<tr><td>{nm}</td>' + "".join(
        f'<td class="n">{sgn(d[t]["share"])}<br><span class="small">{mult(d[t]["mult"])}</span></td>'
        for t in ("pre", "day", "post", "out")) + "</tr>")

bars = ""
for code, nm in NAMES.items():
    b, neg = contrib_bar(code)
    note = f'<span class="small">（マイナス: {"、".join(neg)}）</span>' if neg else ""
    bars += f'<div style="margin:14px 0 4px;font-size:13px">{nm} {note}</div>{b}'

rows_seg = ""
for code, nm in NAMES.items():
    d = R[code]["ra"]
    rows_seg += (f'<tr><td>{nm}</td><td class="n">{d["seg_in"]["up"]}/{d["seg_in"]["n"]}（{pct(d["seg_in"]["rate"])}）</td>'
                 f'<td class="n">{d["seg_out"]["up"]}/{d["seg_out"]["n"]}（{pct(d["seg_out"]["rate"])}）</td></tr>')

rows_fy = ""
fys = list(R["9101"]["ra"]["fy"])
for code, nm in NAMES.items():
    fy = R[code]["ra"]["fy"]
    rows_fy += f'<tr><td>{nm}</td>' + "".join(
        f'<td class="n">{mult(math.exp(fy[f]["in"]))}<br><span class="small">{mult(math.exp(fy[f]["out"]))}</span></td>'
        for f in fys) + "</tr>"

rows_pl = ""
for code, nm in NAMES.items():
    p = P[code]
    rows_pl += (f'<tr><td>{nm}</td><td class="n"><b>{mult(p["actual"])}</b></td><td class="n">{mult(p["med"])}</td>'
                f'<td class="n">{mult(p["lo"])}〜{mult(p["hi"])}</td><td class="n">{p["p"]:.2f}</td></tr>')

rows_top = ""
for code, nm in NAMES.items():
    segs = sorted([s for s in R[code]["segs"] if s[2]], key=lambda s: -s[4])
    rows_top += f'<tr><td>{nm}</td>' + "".join(
        f'<td class="n">{s[0][2:].replace("-", "/")}〜{s[1][5:].replace("-", "/")}<br>{sgn(s[4])}</td>' for s in segs[:3]) + "</tr>"

ev_rows = ""
for code, nm in NAMES.items():
    ev_rows += f'<tr><td>{nm}</td><td style="text-align:left;white-space:normal;font-size:12.5px" class="n">' + "、".join(
        f'{d[2:].replace("-", "/")}{"*" if k == ["修正"] else ""}' for d, k in R[code]["events"]) + "</td></tr>"

charts = "".join(f'<h3>{nm}（{code}）</h3><figure style="margin-top:8px">{chart(code)}</figure>' for code, nm in NAMES.items())

head = open(os.path.join(HERE, "head.html"), encoding="utf-8").read().replace("__TITLE__", TITLE)
n9101 = R["9101"]["ra"]

html = f"""{head}
</head>
<body>
<div class="wrap">
<header class="top">
  <div class="eyebrow">2020.01 — 2024.03 ／ 大手3社 ／ 決算・業績修正 66回</div>
  <h1>コロナ特需の海運株は、<br>決算で上がったのか、決算の間に上がったのか</h1>
  <p class="sub">日本郵船・商船三井・川崎汽船の上昇を、<strong>決算短信・業績予想修正の前後5営業日（窓内）</strong>と<strong>それ以外の日（決算の間）</strong>に分けました。窓内は全営業日の約23%しかありません。そこに上昇の何割が集まったかを見ます。</p>
</header>

<div class="cards">
  <div class="card" style="--c:var(--slate)"><div class="lbl">日本郵船<br>上昇のうち決算前後の寄与</div><div class="big">{pct(R["9101"]["ra"]["in"]["share"])}</div><div class="foot">日数では{R["9101"]["ra"]["in"]["n"]/R["9101"]["ra"]["total"]["n"]*100:.0f}% ／ p={P["9101"]["p"]:.2f}</div></div>
  <div class="card" style="--c:var(--teal)"><div class="lbl">商船三井<br>上昇のうち決算前後の寄与</div><div class="big">{pct(R["9104"]["ra"]["in"]["share"])}</div><div class="foot">日数では{R["9104"]["ra"]["in"]["n"]/R["9104"]["ra"]["total"]["n"]*100:.0f}% ／ p={P["9104"]["p"]:.2f}</div></div>
  <div class="card" style="--c:var(--brass)"><div class="lbl">川崎汽船<br>上昇のうち決算前後の寄与</div><div class="big">{pct(R["9107"]["ra"]["in"]["share"])}</div><div class="foot">日数では{R["9107"]["ra"]["in"]["n"]/R["9107"]["ra"]["total"]["n"]*100:.0f}% ／ p={P["9107"]["p"]:.2f}</div></div>
</div>

<div class="note"><strong>結論。</strong>郵船と川崎は、日数で2割強の決算前後に上昇の6割前後が集まりました。窓の位置をランダムにした場合と比べても偶然では出にくい偏りです（p≒0.03〜0.04）。商船三井は偏りがなく、上昇の6割強が決算と決算の間に出ています。<span class="badge i">解釈</span>ただし偏りの大半は<strong>2021年8月の第1四半期決算</strong>と<strong>2022年7月の3社同時上方修正</strong>の2〜3回から来ています。「決算のたびに上がった」のではなく、「大きな上方修正の数回が上昇の大部分を作った」と読むのが妥当です。</div>

<section>
  <h2><span class="n">01</span>決算前後と決算の間の上昇</h2>
  <p class="lead">配当込み・株式分割補正済みです。倍率は区間内の日次リターンを掛け合わせたもので、窓内×窓外＝全期間になります。</p>
  <div class="scroll"><table>
    <thead><tr><th></th><th>イベント</th><th>全期間</th><th>決算前後</th><th>決算の間</th><th>決算前後の寄与</th><th>決算前後の日数比</th><th>1日あたり（前後 / 間）</th></tr></thead>
    <tbody>{rows_main}</tbody>
  </table></div>
  <p class="small">寄与＝対数リターンで見た全期間の上昇のうち、その区間が占めた割合。日数比と比べて寄与が大きいほど、決算前後に上昇が集中しています。</p>

  <h3>物差しを変えた場合の「決算前後の寄与」</h3>
  <div class="scroll"><table>
    <thead><tr><th></th><th>配当込み</th><th>株価のみ</th><th>TOPIX超過（配当込み同士）</th></tr></thead>
    <tbody>{rows_alt}</tbody>
  </table></div>
  <p class="small">株価のみだと寄与が上がるのは、配当の権利落ち（3月末・9月末）がいずれも決算の間にあり、決算の間の値下がりとして数えられるためです。TOPIX超過はTOPIX連動ETF（1306）の配当込みリターンを日次で差し引いています。</p>
</section>

<section>
  <h2><span class="n">02</span>累積リターンと決算前後の位置</h2>
  <p class="lead">塗りつぶした帯が決算前後（発表の前後5営業日）です。縦軸は対数、配当込み、2020年1月6日の前営業日を1倍としています。</p>
  {charts}
</section>

<section>
  <h2><span class="n">03</span>決算前後の内訳 — 発表前に上がるか、発表後に上がるか</h2>
  <div class="scroll"><table>
    <thead><tr><th></th><th>発表前5日</th><th>反応日</th><th>発表後5日</th><th>決算の間</th></tr></thead>
    <tbody>{rows_split}</tbody>
  </table></div>
  <p class="small">上段が全期間の上昇に対する寄与、下段がその区間だけを掛け合わせた倍率。窓が重なった日は「反応日 ＞ 発表後 ＞ 発表前」の順で1つに数えています。</p>
  {bars}
  <ul>
    <li><strong>郵船と川崎は発表前の5日間</strong>の上昇が大きい（寄与3割弱）。</li>
    <li><strong>商船三井は発表前がマイナス</strong>で、反応日だけで寄与2割を稼いでいる。</li>
    <li><strong>川崎は反応日がマイナス</strong>。前に上げて当日売られ、その後また上げる形。</li>
  </ul>
</section>

<section>
  <h2><span class="n">04</span>上がった「回数」には差がない</h2>
  <div class="scroll"><table>
    <thead><tr><th></th><th>決算前後の区間で上昇</th><th>決算の間の区間で上昇</th></tr></thead>
    <tbody>{rows_seg}</tbody>
  </table></div>
  <p>連続する窓内の日をひとかたまり、窓外の日をひとかたまりとして、それぞれ上がって終わった区間の割合です。どちらも6割前後で差はありません。<strong>差が出ているのは回数ではなく、上がるときの幅</strong>です。</p>
</section>

<section>
  <h2><span class="n">05</span>偶然でも出る偏りか</h2>
  <p class="lead">同じ数の11日窓をランダムな日に置き、窓内の日数をそろえて倍率を出す試行を5,000回行いました。実際の値以上になった割合がp値です。</p>
  <div class="scroll"><table>
    <thead><tr><th></th><th>実際の決算前後</th><th>ランダム中央値</th><th>ランダム90%の幅</th><th>p値</th></tr></thead>
    <tbody>{rows_pl}</tbody>
  </table></div>
  <h3>どの決算が効いたか（決算前後の上昇 上位3区間）</h3>
  <div class="scroll"><table>
    <thead><tr><th></th><th>1位</th><th>2位</th><th>3位</th></tr></thead>
    <tbody>{rows_top}</tbody>
  </table></div>
  <p>2021年7〜8月の第1四半期決算が3社とも最大です。2022年7月は21日の3社同時の上方修正と8月初めの決算の窓がつながっています。郵船の窓内倍率3.49倍のうち1.47倍はこの1区間です。<span class="badge i">解釈</span>3社×約20回しかないので、「決算前後に上がりやすい」という一般則として扱うには標本が足りません。</p>
</section>

<section>
  <h2><span class="n">06</span>年度別に見ると</h2>
  <div class="scroll"><table>
    <thead><tr><th></th>{"".join(f"<th>{f}</th>" for f in fys)}</tr></thead>
    <tbody>{rows_fy}</tbody>
  </table></div>
  <p class="small">上段が決算前後、下段が決算の間の倍率（配当込み）。FY＝4月〜翌3月。</p>
  <p>上昇局面のFY2020・FY2021は、商船三井のFY2021を除き<strong>決算の間</strong>のほうが大きく上がっています。決算前後が決算の間を上回ったのはFY2022で、この年は決算の間が3社とも下落しました。2020年1〜3月（コロナショック）も下落の大半は決算の間です。</p>
  <p><span class="badge i">解釈</span>全期間で決算前後の寄与が大きく見えるのは、「上昇が決算前後に集中した」ことに加えて、<strong>大きな下落が決算の間に起きた</strong>ことも効いています。特需の初期は、決算を待たずにコンテナ運賃の上昇そのものが材料視されていたと考えられます。</p>
</section>

<section>
  <h2><span class="n">07</span>条件と、この検証が答えていないこと</h2>
  <div class="caveats">
    <div class="cv"><h4>イベントの定義</h4><p>TDnetの開示のうち、タイトルに「決算短信」「業績予想」「予想の修正」「差異」などを含むものです。決算日と別日の業績予想修正も決算と同じ扱いにしています。15時（当時の大引け）以降の開示は翌営業日を反応日とし、その前後5営業日（計11営業日）を窓にしました。同じ日の複数開示は1回と数えています。</p></div>
    <div class="cv"><h4>発表時刻の精度</h4><p>TDnet一覧の時刻は12:00ちょうどが多く、丸められている可能性があります。前後5日の窓なので全体の結果への影響は小さいですが、「反応日」単独の数字は1日ずれている可能性があります。</p></div>
    <div class="cv"><h4>標本が小さい</h4><p>3社×20〜23回。しかも3社は同じ材料で同時に動くので、実質的には独立した観測が約20回しかありません。</p></div>
    <div class="cv"><h4>期間の端</h4><p>2020年1月6日〜2024年3月29日の1,035営業日。2024年5月の通期決算は期間外です。2020年1月末の決算の窓はコロナショックの初期と重なっています。</p></div>
  </div>
  <h3>使ったイベント日（反応日・*は業績修正のみの日）</h3>
  <div class="scroll"><table><tbody>{ev_rows}</tbody></table></div>
</section>

<footer>
  データ: TDnet適時開示（yanoshin TDnet API）／ 株価: Yahoo Finance 日足（分割補正・配当込み）／ TOPIX: 1306 TOPIX連動ETF<br>
  集計期間 2020-01-06 〜 2024-03-29。スクリプトとデータは kabutan-ranking/kensho_kessan/ にあります（開示日と株価は kensho_kaiun/cache を流用）。
</footer>

</div>
</body>
</html>
"""
open(OUT, "w", encoding="utf-8").write(html)
print("wrote", OUT)
