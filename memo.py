"""株ログの銘柄メモ(docs/data_memo/memos.json)を CLI から読み書きする。

Claude のチャットから「○○にメモ追加」「不誠実株に入れて」と頼まれたときに使う。
ブラウザ(GitHub連携あり)からも同じファイルにコミットされるので、必ず pull してから書き、書いたら push する。

  python memo.py list                         # 全銘柄の一覧
  python memo.py show 5803                    # 1銘柄のメモ
  python memo.py add 5803 "本文" [--name フジクラ] [--by 本人|Claude] [--src URL ...] [--list avoid|buy|none] [--reason 買う理由]
  python memo.py set 5803 --list buy [--reason "..."] [--name ...]
  python memo.py rm 5803 [--note N]           # 銘柄ごと削除 / N番目(1始まり)のメモだけ削除
  共通: --no-push で commit/push を省略
"""
import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PATH = ROOT / "docs" / "data_memo" / "memos.json"
JST = dt.timezone(dt.timedelta(hours=9))
LISTS = {"avoid": "不誠実・買う理由なし", "buy": "不誠実だが、それをしのぐ買う理由あり"}


def git(*args, check=True):
    return subprocess.run(["git", *args], cwd=ROOT, check=check, capture_output=True, text=True, encoding="utf-8")


def load():
    if PATH.exists():
        return json.loads(PATH.read_text(encoding="utf-8"))
    return {"lists": LISTS, "stocks": {}}


def save(d, msg, push):
    d["updated"] = dt.datetime.now(JST).isoformat(timespec="seconds")
    d.setdefault("lists", LISTS)
    PATH.parent.mkdir(parents=True, exist_ok=True)
    PATH.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if push:
        git("add", str(PATH.relative_to(ROOT)))
        git("commit", "-m", msg)
        for _ in range(2):
            git("pull", "--rebase", "--autostash", check=False)
            if git("push", check=False).returncode == 0:
                print("pushed")
                return
        sys.exit("push failed")


def norm_code(c):
    c = c.strip().upper().translate(str.maketrans("０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ",
                                                  "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
    if len(c) != 4 or not c[:3].isdigit():
        sys.exit(f"証券コードが不正: {c}")
    return c


def apply_common(s, a):
    if getattr(a, "name", None):
        s["name"] = a.name
    if getattr(a, "list", None):
        if a.list == "none":
            s.pop("list", None)
        else:
            s["list"] = a.list
    if getattr(a, "reason", None) is not None:
        if a.reason:
            s["reason"] = a.reason
        else:
            s.pop("reason", None)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    p = sub.add_parser("show"); p.add_argument("code")
    p = sub.add_parser("add"); p.add_argument("code"); p.add_argument("text")
    p.add_argument("--name"); p.add_argument("--by", default="Claude"); p.add_argument("--src", nargs="*")
    p.add_argument("--list", choices=["avoid", "buy", "none"]); p.add_argument("--reason")
    p = sub.add_parser("set"); p.add_argument("code"); p.add_argument("--name")
    p.add_argument("--list", choices=["avoid", "buy", "none"]); p.add_argument("--reason")
    p = sub.add_parser("rm"); p.add_argument("code"); p.add_argument("--note", type=int)
    for sp in sub.choices.values():
        sp.add_argument("--no-push", action="store_true")
    a = ap.parse_args()
    push = not a.no_push and a.cmd not in ("list", "show")
    if push:
        git("pull", "--rebase", "--autostash", check=False)
    d = load()
    st = d.setdefault("stocks", {})
    sys.stdout.reconfigure(encoding="utf-8")

    if a.cmd == "list":
        for c, s in st.items():
            print(f"{c} {s.get('name','')} [{LISTS.get(s.get('list'), '-')}] メモ{len(s.get('notes', []))}件")
        return
    code = norm_code(a.code)
    if a.cmd == "show":
        print(json.dumps(st.get(code), ensure_ascii=False, indent=2))
        return
    if a.cmd == "add":
        s = st.setdefault(code, {"name": a.name or "", "notes": []})
        apply_common(s, a)
        n = {"date": dt.datetime.now(JST).strftime("%Y-%m-%d"), "by": a.by, "text": a.text}
        if a.src:
            n["src"] = a.src
        s.setdefault("notes", []).append(n)
        save(d, f"Add stock memo for {code}", push)
    elif a.cmd == "set":
        s = st.setdefault(code, {"name": a.name or "", "notes": []})
        apply_common(s, a)
        save(d, f"Update stock memo list for {code}", push)
    elif a.cmd == "rm":
        if code not in st:
            sys.exit("該当なし")
        if a.note:
            st[code]["notes"].pop(a.note - 1)
        else:
            del st[code]
        save(d, f"Remove stock memo for {code}", push)
    print(json.dumps(st.get(code), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
