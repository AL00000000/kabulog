# 時価総額帯(基準日時点)ごとの期間騰落率。株価は分割調整のみ・配当含まず。
import ast, bisect, json, math, statistics as st, sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).parent
D = HERE / "data"
SRC = Path(r"C:\Users\yt\kabulog\kabutan-ranking\fetch_period.py").read_text(encoding="utf8")
tree = ast.parse(SRC)
ns = {"math": math}
for node in tree.body:
    if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") in ("JUMP", "FACTORS", "SPIKE_DAYS"):
        exec(compile(ast.Module([node], []), "x", "exec"), ns)
    if isinstance(node, ast.FunctionDef) and node.name in ("_factor", "fix_jumps"):
        exec(compile(ast.Module([node], []), "x", "exec"), ns)
fix_jumps = ns["fix_jumps"]

U = json.loads((D / "universe.json").read_text(encoding="utf8"))
SH = json.loads((D / "shares.json").read_text(encoding="utf8"))
B = {}
for c in U:
    f = D / "bars" / f"{c}.json"
    if f.exists():
        b = json.loads(f.read_text(encoding="utf8"))
        if b:
            B[c] = fix_jumps(b)
print("universe", len(U), "with bars", len(B), "shares ok", sum(1 for c in U if SH.get(c)))
print("5桁コード", [(c, U[c]["name"]) for c in U if len(c) > 4][:10])
ALL = sorted({x[0] for b in B.values() for x in b})
LAST = ALL[-1]
print("last date", LAST, "count at last", sum(1 for b in B.values() if b[-1][0] == LAST))


def at(b, d, maxgap=5):
    """d以前で直近の終値。maxgap営業日より古ければ None(売買停止・廃止の扱い)。"""
    i = bisect.bisect_right([x[0] for x in b], d) - 1
    if i < 0:
        return None
    gap = bisect.bisect_right(ALL, d) - 1 - ALL.index(b[i][0])
    return b[i][1] if gap <= maxgap else None


def rows(start, end):
    out, drop = [], {"上場前": 0, "終点なし": 0, "株式数なし": 0}
    for c, b in B.items():
        if len(c) > 4:
            continue
        s = at(b, start)
        if s is None:
            drop["上場前"] += 1
            continue
        e = at(b, end)
        if e is None:
            drop["終点なし"] += 1
            continue
        if not SH.get(c):
            drop["株式数なし"] += 1
            continue
        out.append((s * SH[c] / 1e8, (e / s - 1) * 100, c))
    return sorted(out), drop


def stats(g):
    r = [x[1] for x in g]
    return dict(n=len(g), lo=g[0][0], hi=g[-1][0], mean=st.mean(r), med=st.median(r), up=sum(x > 0 for x in r) / len(r) * 100)


def report(label, start, end, top=5):
    R, drop = rows(start, end)
    low = [x for x in R if x[0] <= 500]
    hi = [x for x in R if x[0] > 500]
    N = len(low)
    print(f"\n=== {label} {start}→{end} 計{len(R)} 除外{drop} / 500億以下 {N} / 500億超 {len(hi)}")
    p = stats(R)
    print(f"全体 平均{p['mean']:+.1f} 中央{p['med']:+.1f} 上昇{p['up']:.0f}%")
    p = stats(low)
    print(f"≤500億 n={p['n']} 平均{p['mean']:+.1f} 中央{p['med']:+.1f} 上昇{p['up']:.0f}%")
    for name, parts in (("同数刻み", [hi[i:i + N] for i in range(0, len(hi), N)]),
                        ("500億超を4等分", [hi[len(hi) * i // 4:len(hi) * (i + 1) // 4] for i in range(4)]),
                        ("全体4等分", [R[len(R) * i // 4:len(R) * (i + 1) // 4] for i in range(4)]),
                        ("500億以下を4等分", [low[N * i // 4:N * (i + 1) // 4] for i in range(4)])):
        print(" --", name)
        for g in parts:
            p = stats(g)
            print(f"  {p['lo']:>10,.0f}〜{p['hi']:>10,.0f}億 n={p['n']:>4} 平均{p['mean']:+7.1f} 中央{p['med']:+7.1f} 上昇{p['up']:.0f}%")
    print("  外れ値", [(c, round(v)) for _, v, c in sorted(R, key=lambda x: -x[1])[:top]])


report("1月(12/30終値基準)", "2025-12-30", "2026-06-30")
report("1月(1/5終値基準)", "2026-01-05", "2026-06-30")
report("7月(6/30終値基準)", "2026-06-30", LAST)
report("7月(7/1終値基準)", "2026-07-01", LAST)

# 検算: TOPIX相当の代表銘柄の時価総額
for c in ("7203", "6758", "9984"):
    print(c, U.get(c, {}).get("name"), round(at(B[c], LAST) * SH[c] / 1e12, 1), "兆円")
