"""株ログの銘柄メモ(docs/data_memo/memos.json) と notes の銘柄別メモ(notes/投資/銘柄別/*.md)を双方向に同期する。

対応のさせ方
  - md のフロントマターに `code: 285A` (米国株なら `code: ANT`) がある md が、その銘柄のメモ
  - md 本文(「## 株ログの●メモ」の節を除く) → memos.json の `doc` (株ログでは読むだけ)
  - md の「## 株ログの●メモ」の節 ⇔ memos.json の `notes` (株ログの●から書いたメモ)
        1行1件: `- 2026-11-23｜本人｜本文`  続く行は2字下げ、`  出典: URL URL` で出典
  - フロントマターの list(avoid/buy) / reason / name ⇔ memos.json の同名項目
  - memos.json にだけある銘柄は md を新しく作る

消したメモが復活しないよう、前回同期時点の状態(memo_sync_state.json、Git管理外)と比べる三方向マージ。
片方で消した行は消える。両方で同時に別の行を足した場合は両方残る。

  python memo_sync.py            pull → 同期 → 両リポジトリを commit/push
  python memo_sync.py --dry-run  変更内容を表示するだけ
"""
import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MEMO_JSON = ROOT / "docs" / "data_memo" / "memos.json"
STATE = ROOT / "memo_sync_state.json"
NOTES_REPO = (ROOT / ".." / ".." / "notes").resolve()
NOTES_DIR = NOTES_REPO / "notes"
MD_SUBDIR = "投資/銘柄別"
MD_DIR = NOTES_DIR / MD_SUBDIR
SECTION = "## 株ログの●メモ"
SECTION_NOTE = "<!-- この節は株ログの各タブの●と自動で同期します(1行1件「- 日付｜書いた人｜本文」)。ここに足した行は株ログにも出ます -->"
AGENT = "株ログ同期"
JST = dt.timezone(dt.timedelta(hours=9))
ITEM_RE = re.compile(r"^- (\d{4}-\d{2}-\d{2})｜([^｜]*)｜(.*)$")
CODE_RE = re.compile(r"^([0-9]{3}[0-9A-Z]|[A-Z]{1,5}(\.[A-Z])?)$")


def git(repo, *args, check=True):
    r = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8")
    if check and r.returncode:
        sys.exit(f"git {' '.join(args)} failed in {repo}: {r.stderr.strip()}")
    return r


# ---------- md の読み書き ----------
def split_front(text):
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            fm = text[4:end].strip("\n")
            body = text[end + 4:].lstrip("\n")
            return fm.split("\n") if fm else [], body
    return [], text


def fm_get(lines, key):
    for ln in lines:
        m = re.match(rf"^{key}:\s*(.*)$", ln)
        if m:
            v = m.group(1).strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            return v
    return None


def fm_set(lines, key, value):
    out, done = [], False
    for ln in lines:
        if re.match(rf"^{key}:", ln):
            done = True
            if value not in (None, ""):
                out.append(f"{key}: {json.dumps(value, ensure_ascii=False) if needs_quote(value) else value}")
            continue
        out.append(ln)
    if not done and value not in (None, ""):
        out.append(f"{key}: {json.dumps(value, ensure_ascii=False) if needs_quote(value) else value}")
    return out


def needs_quote(v):
    return bool(re.search(r"[:#\[\]{},&*!|>'\"%@`]", v)) or v != v.strip() or "\n" in v


def split_section(body):
    """本文を (doc, 同期節の行リスト) に分ける。"""
    lines = body.split("\n")
    start = next((i for i, ln in enumerate(lines) if ln.strip() == SECTION), None)
    if start is None:
        return body.strip(), []
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    doc = "\n".join(lines[:start] + lines[end:]).strip()
    return doc, lines[start + 1:end]


def parse_items(sec):
    items, cur = [], None
    for ln in sec:
        m = ITEM_RE.match(ln)
        if m:
            cur = {"date": m.group(1), "by": m.group(2).strip() or "本人", "text": m.group(3).rstrip()}
            items.append(cur)
        elif cur is not None and ln.startswith("  "):
            t = ln[2:]
            if t.startswith("出典: "):
                cur["src"] = t[4:].split()
            else:
                cur["text"] += "\n" + t.rstrip()
        elif ln.startswith("- ") and ln.strip() != "-":
            # 日付なしで手で足した行も拾う(今日・本人として扱う)
            cur = {"date": today(), "by": "本人", "text": ln[2:].rstrip()}
            items.append(cur)
    for it in items:
        it["text"] = it["text"].strip()
    return [it for it in items if it["text"]]


def render_items(notes):
    out = [SECTION, "", SECTION_NOTE, ""]
    for n in notes:
        text = n.get("text", "").split("\n")
        out.append(f"- {n.get('date', '')}｜{n.get('by', '')}｜{text[0]}")
        out += ["  " + t for t in text[1:]]
        if n.get("src"):
            out.append("  出典: " + " ".join(n["src"]))
    return out


def read_md(path):
    fm, body = split_front(path.read_text(encoding="utf-8"))
    doc, sec = split_section(body)
    return {"fm": fm, "body": body, "doc": doc, "notes": parse_items(sec),
            "code": (fm_get(fm, "code") or "").upper(), "name": fm_get(fm, "name") or "",
            "list": fm_get(fm, "list") or "", "reason": fm_get(fm, "reason") or "",
            "title": fm_get(fm, "title") or path.stem}


def write_md(path, md, notes, name, lst, reason):
    fm = md["fm"]
    fm = fm_set(fm, "name", name)
    fm = fm_set(fm, "list", lst)
    fm = fm_set(fm, "reason", reason)
    doc = md["doc"]
    body = (doc + "\n\n" if doc else "") + "\n".join(render_items(notes)).rstrip() + "\n"
    text = "---\n" + "\n".join(fm) + "\n---\n\n" + body
    path.write_text(text, encoding="utf-8", newline="\n")


def new_md(code, s):
    name = s.get("name") or code
    first = next((n["text"] for n in s.get("notes", []) if n.get("text")), "")
    first = re.sub(r"\s+", " ", first)[:60]
    fm = [f"title: {name}（{code}）", "tags: [投資, 株式, 銘柄別, 株ログ]",
          f"summary: {json.dumps(f'{name}({code})の銘柄メモ。株ログの●と同期。' + first, ensure_ascii=False)}",
          f"updated: {today()}", f"code: {code}"]
    return {"fm": fm, "body": "", "doc": "", "notes": [], "code": code, "name": name,
            "list": "", "reason": "", "title": name}


def safe_filename(name, code):
    base = re.sub(r'[\\/:*?"<>|]', "・", name or code).strip() or code
    p = MD_DIR / f"{base}.md"
    return p if not p.exists() else MD_DIR / f"{base}_{code}.md"


# ---------- マージ ----------
def key(n):
    return json.dumps([n.get("date", ""), n.get("by", ""), n.get("text", "").strip(), n.get("src") or []], ensure_ascii=False)


def merge_notes(a, b, base):
    """a=json, b=md, base=前回同期時。片方で消えた(base にあって片方に無い)ものは消す。"""
    ka, kb, kbase = {key(n) for n in a}, {key(n) for n in b}, {key(n) for n in base}
    out, seen = [], set()
    for n in a + b:
        k = key(n)
        if k in seen:
            continue
        seen.add(k)
        if k in kbase and not (k in ka and k in kb):
            continue  # どちらかで削除された
        out.append(n)
    out.sort(key=lambda n: n.get("date", ""))  # 安定ソート: 同じ日付は元の順
    return out


def merge_scalar(j, m, base):
    j, m, base = j or "", m or "", base or ""
    if m != base:
        return m
    return j


def today():
    return dt.datetime.now(JST).strftime("%Y-%m-%d")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-git", action="store_true", help="pull/commit/push をしない")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if not NOTES_DIR.exists():
        sys.exit(f"notes が見つからない: {NOTES_DIR}")
    use_git = not (a.dry_run or a.no_git)
    if use_git:
        git(ROOT, "pull", "--rebase", "--autostash", check=False)
        git(NOTES_REPO, "pull", "--rebase", "--autostash", check=False)

    data = json.loads(MEMO_JSON.read_text(encoding="utf-8"))
    stocks = data.setdefault("stocks", {})
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}

    mds = {}
    MD_DIR.mkdir(parents=True, exist_ok=True)
    for p in sorted(MD_DIR.glob("*.md")):
        md = read_md(p)
        if not md["code"]:
            continue
        if not CODE_RE.match(md["code"]):
            print(f"! コードが不正なので飛ばす: {p.name} code={md['code']}")
            continue
        if md["code"] in mds:
            print(f"! 同じコードの md が2つある({md['code']}): {mds[md['code']][0].name} / {p.name} 先の方だけ使う")
            continue
        mds[md["code"]] = (p, md)

    json_changed, md_changed, new_state = [], [], {}
    for code in sorted(set(stocks) | set(mds)):
        s = stocks.get(code, {})
        base = state.get(code, {})
        if code in mds:
            path, md = mds[code]
        else:
            path, md = safe_filename(s.get("name", ""), code), new_md(code, s)
        notes = merge_notes(s.get("notes", []), md["notes"], base.get("notes", []))
        name = merge_scalar(s.get("name"), md["name"], base.get("name")) or md["title"]
        lst = merge_scalar(s.get("list"), md["list"], base.get("list"))
        reason = merge_scalar(s.get("reason"), md["reason"], base.get("reason"))
        doc = md["doc"]
        rel = path.relative_to(NOTES_DIR).as_posix()

        ns = dict(s)
        ns["name"] = name
        ns["notes"] = notes
        for k, v in (("list", lst), ("reason", reason), ("doc", doc)):
            if v:
                ns[k] = v
            else:
                ns.pop(k, None)
        if doc:
            ns["doc_path"] = rel
        else:
            ns.pop("doc_path", None)
        if ns != s:
            stocks[code] = ns
            json_changed.append(code)

        before = path.read_text(encoding="utf-8") if path.exists() else None
        if not a.dry_run:
            write_md(path, md, notes, name, lst, reason)
            after = path.read_text(encoding="utf-8")
            if after != before:
                md_changed.append(rel)
        else:
            if (md["notes"], md["list"], md["reason"], md["name"]) != (notes, lst, reason, name) or before is None:
                md_changed.append(rel)
        new_state[code] = {"name": name, "list": lst, "reason": reason, "notes": notes}

    print("株ログ側を更新:", ", ".join(json_changed) or "なし")
    print("notes側を更新:", ", ".join(md_changed) or "なし")
    if a.dry_run:
        return

    if json_changed:
        data["updated"] = dt.datetime.now(JST).isoformat(timespec="seconds")
        MEMO_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    STATE.write_text(json.dumps(new_state, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    py = sys.executable
    for rel in md_changed:
        subprocess.run([py, "notes.py", "touch", rel, "--agent", AGENT], cwd=NOTES_REPO,
                       capture_output=True, text=True, encoding="utf-8")
    if md_changed and not a.no_git:
        subprocess.run([py, "notes.py", "index"], cwd=NOTES_REPO, capture_output=True)

    if not use_git:
        return
    if json_changed:
        git(ROOT, "add", str(MEMO_JSON.relative_to(ROOT)))
        git(ROOT, "commit", "-m", f"Sync stock memos from notes ({', '.join(json_changed)})")
        push(ROOT)
    if md_changed:
        git(NOTES_REPO, "add", "index.json", *[f"notes/{r}" for r in md_changed])
        if git(NOTES_REPO, "diff", "--cached", "--quiet", check=False).returncode:
            git(NOTES_REPO, "commit", "-m", f"[{AGENT}] 株ログの銘柄メモと同期\n\nEdited-By: {AGENT}")
            push(NOTES_REPO)


def push(repo):
    for _ in range(3):
        if git(repo, "push", check=False).returncode == 0:
            print("pushed:", repo.name)
            return
        git(repo, "pull", "--rebase", "--autostash", check=False)
    sys.exit(f"push failed: {repo}")


if __name__ == "__main__":
    main()
