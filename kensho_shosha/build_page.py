"""result.json → docs/kensho_shosha.html"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "docs", "kensho_shosha.html")
TITLE = "シクリカル割引は解けるか"
R = json.load(open(os.path.join(HERE, "result.json"), encoding="utf-8"))
N = R["names"]
rows = R["rows"]
C_SHO, C_KAI, C_MKT = "var(--brass)", "var(--slate)", "var(--ink-3)"


def f(x, d=1, suf="倍"):
    return "—" if x is None else f"{x:.{d}f}{suf}"


def line_chart(series, ymax, ticks, label, ref=None):
    """series: [(color, [(i, v)...], name)]  x は rows の添字"""
    W, H, L, T, B = 860, 280, 48, 12, 28
    n = len(rows)
    x = lambda i: L + (W - L - 10) * i / (n - 1)
    y = lambda v: T + (H - T - B) * (1 - min(v, ymax) / ymax)
    p = []
    for t in ticks:
        p.append(f'<line x1="{L}" x2="{W-10}" y1="{y(t):.1f}" y2="{y(t):.1f}" stroke="var(--line-soft)"/>')
        p.append(f'<text x="{L-6}" y="{y(t)+4:.1f}" text-anchor="end" font-size="11" fill="var(--ink-3)" class="num">{t:g}{label}</text>')
    if ref is not None:
        p.append(f'<line x1="{L}" x2="{W-10}" y1="{y(ref):.1f}" y2="{y(ref):.1f}" stroke="var(--ink-3)" stroke-dasharray="4 4"/>')
    for i, r in enumerate(rows):
        if r["ym"][5:] == "01":
            p.append(f'<line x1="{x(i):.1f}" x2="{x(i):.1f}" y1="{T}" y2="{H-B}" stroke="var(--line)"/>')
            p.append(f'<text x="{x(i)+3:.1f}" y="{H-10}" font-size="11" fill="var(--ink-3)" class="num">{r["ym"][:4]}</text>')
    for color, pts, _ in series:
        segs, cur = [], []
        for i, v in pts:
            if v is None:
                if cur: segs.append(cur); cur = []
            else:
                cur.append(f"{x(i):.1f},{y(v):.1f}")
        if cur: segs.append(cur)
        for s in segs:
            p.append(f'<polyline points="{" ".join(s)}" fill="none" stroke="{color}" stroke-width="2"/>')
    legend = "".join(f'<span><i style="background:{c}"></i>{nm}</span>' for c, _, nm in series)
    return f'<div class="legend">{legend}</div><svg viewBox="0 0 {W} {H}">{"".join(p)}</svg>'


idx = list(range(len(rows)))
ch_rel = line_chart([
    (C_SHO, [(i, rows[i]["shosha_rel"]) for i in idx], "総合商社5社（中央値）"),
    (C_KAI, [(i, rows[i]["kaiun_rel"]) for i in idx], "海運大手3社（中央値）"),
], 1.2, (0, 0.25, 0.5, 0.75, 1.0), "倍", ref=1.0)
ch_p5 = line_chart([
    (C_SHO, [(i, rows[i]["shosha_per5"]) for i in idx], "総合商社5社"),
    (C_KAI, [(i, rows[i]["kaiun_per5"]) for i in idx], "海運大手3社"),
], 25, (0, 5, 10, 15, 20, 25), "倍")
ch_fwd = line_chart([
    (C_SHO, [(i, rows[i]["shosha_fwd"]) for i in idx], "総合商社5社"),
    (C_KAI, [(i, rows[i]["kaiun_fwd"]) for i in idx], "海運大手3社"),
    (C_MKT, [(i, rows[i]["mkt"]) for i in idx], "市場（実績PER・参考）"),
], 30, (0, 5, 10, 15, 20, 25, 30), "倍")

pick = [r for r in rows if r["ym"][5:] in ("03", "09")] + [rows[-1]]
tab = ""
for r in pick:
    tab += (f'<tr><td>{r["ym"].replace("-", "/")}</td><td class="n">{f(r["mkt"])}</td>'
            f'<td class="n">{f(r["shosha_per"])}</td><td class="n"><b>{f(r["shosha_rel"], 2)}</b></td><td class="n">{f(r["shosha_per5"])}</td><td class="n">{f(r["shosha_pbr"], 2)}</td>'
            f'<td class="n">{f(r["kaiun_per"])}</td><td class="n"><b>{f(r["kaiun_rel"], 2)}</b></td><td class="n">{f(r["kaiun_per5"])}</td></tr>')

FYS = ["2019/03", "2020/03", "2021/03", "2022/03", "2023/03", "2024/03", "2025/03", "2026/03"]
eps_rows = ""
for g, lab in (("shosha", "商社"), ("kaiun", "海運")):
    for c in R[g]:
        e = R["eps"][c]
        pk, last = e.get("2023/03"), e.get("2026/03")
        chg = (last / pk - 1) if pk and last else None
        cls = "pos" if chg and chg >= 0 else "neg"
        eps_rows += (f'<tr><td>{N[c]}<span class="small">（{lab}）</span></td>' +
                     "".join(f'<td class="n">{e.get(k, 0):,.0f}</td>' for k in FYS) +
                     f'<td class="n"><span class="{cls}">{chg*100:+.0f}%</span></td></tr>')

last = rows[-1]


def drop(g):
    xs = [R["eps"][c]["2026/03"] / R["eps"][c]["2023/03"] - 1 for c in R[g]]
    return f"{min(xs)*100:+.0f}〜{max(xs)*100:+.0f}%".replace("-", "−")


lastm = next(r for r in reversed(rows) if r["mkt"])
low = min((r for r in rows if r["shosha_rel"]), key=lambda r: r["shosha_rel"])
head = open(os.path.join(HERE, "..", "kensho_kessan", "head.html"), encoding="utf-8").read().replace("__TITLE__", TITLE)

html = f"""{head}
</head>
<body>
<div class="wrap">
<header class="top">
  <div class="eyebrow">2020.01 — {last["ym"].replace("-", ".")} ／ 総合商社5社 × 海運大手3社 ／ 実績EPSと株価から再計算</div>
  <h1>シクリカル割引は、<br>数字が続けば解けるのか</h1>
  <p class="sub">景気循環株は、好調な利益を「天井の利益」として割り引かれます。<strong>好調な数字が出続けると、その割引は解けるのか</strong>。同じ2021〜2022年に過去最高益を出した総合商社と海運で、その後のPERを比べました。</p>
</header>

<div class="cards">
  <div class="card" style="--c:var(--brass)"><div class="lbl">総合商社のPER ÷ 市場PER<br>{low["ym"].replace("-", "/")} → {lastm["ym"].replace("-", "/")}</div><div class="big">{low["shosha_rel"]:.2f}→{lastm["shosha_rel"]:.2f}</div><div class="foot">実績PER・5社中央値</div></div>
  <div class="card" style="--c:var(--slate)"><div class="lbl">海運の5年平均利益PER<br>2022/9 → {last["ym"].replace("-", "/")}</div><div class="big">{rows[[r["ym"] for r in rows].index("2022-09")]["kaiun_per5"]:.1f}→{last["kaiun_per5"]:.1f}</div><div class="foot">倍・3社中央値（商社は{last["shosha_per5"]:.1f}倍）</div></div>
  <div class="card" style="--c:var(--teal)"><div class="lbl">ピーク（FY2023/3）からの利益の落ち方<br>FY2026/3時点</div><div class="big" style="font-size:22px">商社 {drop("shosha")}<br>海運 {drop("kaiun")}</div><div class="foot">1株益・各社</div></div>
</div>

<div class="note"><strong>結論。</strong>総合商社では割引が解けました。市場と比べたPERは0.4倍前後から1倍前後まで上がり、PBRも0.6倍台から2倍前後になっています。海運は、ならした利益に対するPERが5倍前後のまま動いていません。<span class="badge i">解釈</span>両者を分けたのは好調な数字が続いた長さではなく、<strong>ピークの後に利益がどこまで落ちたか</strong>に見えます。商社の割引が解け始めたのは、ピークを過ぎて減益になっても利益が崩れないと分かった2023年以降です。ただ同じ時期にバフェット氏の買い増しや東証のPBR改善要請が重なっており、このデータでは切り分けられません。</div>

<section>
  <h2><span class="n">01</span>市場と比べたPER</h2>
  <p class="lead">実績PER（株価 ÷ 発表済みの直近通期の1株益）を、同じ月の東証一部／プライム全体の実績PERで割った値です。1倍なら市場並みです。</p>
  <figure>{ch_rel}<figcaption>点線が市場並み（1倍）。赤字の期や、2社以上で計算できない月は線を切っています。2021年は市場の利益がコロナで落ちて市場PERが25倍前後に膨らんでいるため、比が低めに出ます。</figcaption></figure>
  <p><span class="badge m">実測</span>商社は2020〜2022年に0.4倍前後（最低は{low["ym"].replace("-", "/")}の{low["shosha_rel"]:.2f}倍）で推移し、2023年以降はほぼ一貫して上がって、2026/03に市場並みの1.00倍に達しました（{lastm["ym"].replace("-", "/")}は{lastm["shosha_rel"]:.2f}倍）。海運は利益の振れが大きすぎて、実績PERの比は0.09倍から0.93倍まで跳ね回ります。2024年後半や足元で市場並みに近く見えるのは、<strong>評価が上がったからではなく、利益が落ちて分母が縮んだから</strong>です。このため、海運は次の物差しで見ます。</p>
</section>

<section>
  <h2><span class="n">02</span>ならした利益で見たPER</h2>
  <p class="lead">株価 ÷ 直近5期の1株益の平均。景気循環の山と谷を均した利益に、市場が何倍を付けているかを見ます。</p>
  <figure>{ch_p5}<figcaption>海運は5期平均が赤字になる2022年春以前は計算できません。毎年5月に5期の範囲が1年ずれるため、段差が出ます。</figcaption></figure>
  <p><span class="badge m">実測</span>海運は2022年秋から足元まで4〜7倍の範囲で、ほぼ動いていません。ブームの利益を含めた平均利益に対しても、市場は5倍前後しか付けていません。商社は10倍前後から17〜21倍に上がりました。</p>
</section>

<section>
  <h2><span class="n">03</span>利益の推移 — ピークの後にどこまで落ちたか</h2>
  <div class="scroll"><table>
    <thead><tr><th>1株益（円・分割補正後）</th>{"".join(f"<th>FY{k[:4]}</th>" for k in FYS)}<th>FY2023/3比</th></tr></thead>
    <tbody>{eps_rows}</tbody>
  </table></div>
  <p class="small">FY2019＝2019年3月期。商社はIRBANKの値、海運は「海運株の予想PER」タブで使った自前計算の値（IRBANKは川崎汽船の分割補正が年により不完全なため）。日本郵船のFY2023のみIRBANKの値で補っています。</p>
  <p><span class="badge m">実測</span>商社はピーク後に資源系の三菱商事・三井物産が約2割減益になった一方、非資源の多い伊藤忠・丸紅・住友商事は増益です。それでも全社がコロナ前（FY2019）の1.7〜2.5倍の水準を保っています。海運は翌期に7〜8割減り、FY2026でもピークの3割前後です。</p>
  <p><span class="badge i">解釈</span>2022年のピーク時点では、商社の事後の予想PER（その期の実際の1株益で割った値）は4〜6倍で、海運と同じく「天井の利益」として割り引かれていました。違いが出たのはその後です。<strong>減益の局面で利益が崩れなかった側だけが、倍率を上げてもらえた</strong>と読めます。「好調な数字が続けば解ける」というより、「悪い局面を通っても崩れないと確認されて解ける」です。</p>
</section>

<section>
  <h2><span class="n">04</span>半年ごとの数値</h2>
  <div class="scroll"><table>
    <thead><tr><th>月末</th><th>市場PER</th><th>商社 実績PER</th><th>商社 ÷ 市場</th><th>商社 5期平均PER</th><th>商社 PBR</th><th>海運 実績PER</th><th>海運 ÷ 市場</th><th>海運 5期平均PER</th></tr></thead>
    <tbody>{tab}</tbody>
  </table></div>
  <h3>参考: 事後の予想PER</h3>
  <p class="lead">株価 ÷ その時点で進行中の期の、後から分かった実際の1株益。今期（FY2027/3）だけは会社予想です。市場は実績PERなので、水準の比較ではなく形の参考です。</p>
  <figure>{ch_fwd}</figure>
</section>

<section>
  <h2><span class="n">05</span>条件と、この検証が答えていないこと</h2>
  <div class="caveats">
    <div class="cv"><h4>なぜ商社の割引が解けたかは分けられない</h4><p>2023年以降、バフェット氏の買い増し、東証のPBR改善要請（2023年3月）、各社の累進配当・自社株買いの約束が重なりました。利益が崩れなかったことの効果と、これらの効果は、このデータでは区別できません。</p></div>
    <div class="cv"><h4>市場PERはJPXの単純な集計値</h4><p>JPX「規模別・業種別PER・PBR」の東証一部（2022年4月以降はプライム）総合の値で、小数1桁までしか公表されていません。2026年9月以降は未公表のため、比は8月までです。</p></div>
    <div class="cv"><h4>株価は配当を含まない</h4><p>Yahooの分割補正済み終値を使っています。PERの計算なので配当は関係しません。</p></div>
    <div class="cv"><h4>標本は2業種8社</h4><p>「割引が解けた例」と「解けなかった例」を1つずつ並べたものです。一般則とするには、半導体製造装置など他業種の例を足す必要があります。</p></div>
  </div>
</section>

<footer>
  データ: IRBANK（商社のEPS・BPS）／ TDnet短信からの自前計算（海運のEPS）／ Yahoo Finance 日足 ／ JPX「規模別・業種別PER・PBR」月次<br>
  期間 2020-01 〜 {last["ym"]}。スクリプトとデータは kabutan-ranking/kensho_shosha/ にあります（fetch.py → analyze.py → build_page.py）。
</footer>
</div>
</body>
</html>
"""
open(OUT, "w", encoding="utf-8").write(html)
print("wrote", OUT)
